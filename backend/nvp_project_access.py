"""G03: per-project API lock with scrypt verifier and revocable host sessions.

A lock is real *local API* authorization, NOT encryption-at-rest or OS
account isolation. SQLite, source assets and backups remain readable to the
local account until a separately accepted encryption/key-custody gate exists.
Tokens never enter JavaScript: HTTP-only SameSite cookies are used by the API.
"""
from __future__ import annotations

from hashlib import scrypt
from contextlib import contextmanager
import hmac
import secrets
import sqlite3
import threading
import time
import re

PROJECT = re.compile(r"^[a-f0-9]{32}$")
COOKIE = "nvp_film_access"
SESSION_SECONDS = 20 * 60
KEY_BYTES = 32
SALT_BYTES = 16
MAX_ATTEMPTS = 5
COOLDOWN_SECONDS = 30


class ProjectAccess:
    def __init__(self, db_path, *, clock=time.monotonic, wall_clock=time.time):
        self.db_path = str(db_path)
        self.clock = clock
        self.wall_clock = wall_clock
        self._guard = threading.RLock()
        self._sessions = {}
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS project_access_locks(
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                salt BLOB NOT NULL, verifier BLOB NOT NULL, created_at REAL NOT NULL,
                generation INTEGER NOT NULL DEFAULT 1)""")
            db.execute("""CREATE TABLE IF NOT EXISTS project_access_attempts(
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                failures INTEGER NOT NULL CHECK(failures>=0 AND failures<=5),
                blocked_until REAL NOT NULL DEFAULT 0)""")
            columns={row[1] for row in db.execute(
                "PRAGMA table_info(project_access_locks)").fetchall()}
            if "generation" not in columns:
                # Non-destructive migration for projects protected before G03.
                db.execute("""ALTER TABLE project_access_locks
                    ADD COLUMN generation INTEGER NOT NULL DEFAULT 1""")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def _check_id(self, project_id):
        if not isinstance(project_id, str) or not PROJECT.fullmatch(project_id):
            raise KeyError("Unknown film project")
        with self._db() as db:
            if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
                raise KeyError("Unknown film project")

    @staticmethod
    def _check_password(password):
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError("Use a movie passphrase of 12 to 256 characters")
        return password.encode("utf8")

    @staticmethod
    def _derive(password, salt):
        return scrypt(password, salt=salt, n=2**14, r=8, p=1, dklen=KEY_BYTES)

    def protected(self, project_id):
        self._check_id(project_id)
        with self._db() as db:
            return db.execute(
                "SELECT 1 FROM project_access_locks WHERE project_id=?",
                (project_id,)).fetchone() is not None

    def _revoke(self, project_id):
        for token, entry in list(self._sessions.items()):
            if entry[0] == project_id:
                del self._sessions[token]

    def protect(self, project_id, password):
        self._check_id(project_id)
        secret = self._check_password(password)
        salt = secrets.token_bytes(SALT_BYTES)
        verifier = self._derive(secret, salt)
        with self._guard:
            with self._db() as db:
                with db:
                    try:
                        db.execute("""INSERT INTO project_access_locks
                            (project_id,salt,verifier,created_at) VALUES (?,?,?,?)""",
                            (project_id,salt,verifier,time.time()))
                    except sqlite3.IntegrityError as exc:
                        raise PermissionError("Movie already protected") from exc
            self._revoke(project_id)
        return {"locked": True, "access": "locked"}

    def unlock(self, project_id, password):
        self._check_id(project_id)
        secret = self._check_password(password)
        with self._guard:
            now = self.wall_clock()
            with self._db() as db:
                # BEGIN IMMEDIATE makes failed-attempt accounting atomic even
                # across separate NVP processes opening one SQLite store.
                db.execute("BEGIN IMMEDIATE")
                attempt = db.execute("""SELECT failures,blocked_until
                    FROM project_access_attempts WHERE project_id=?""",
                    (project_id,)).fetchone()
                count, until = attempt if attempt is not None else (0, 0.0)
                if until > now:
                    raise PermissionError("Too many attempts; try again later")
                row = db.execute(
                    "SELECT salt,verifier,generation FROM project_access_locks WHERE project_id=?",
                    (project_id,)).fetchone()
                if row is None:
                    raise PermissionError("Movie has no protection configured")
                actual = self._derive(secret, row[0])
                if not hmac.compare_digest(actual, row[1]):
                    count += 1
                    blocked = now + COOLDOWN_SECONDS if count >= MAX_ATTEMPTS else 0.0
                    db.execute("""INSERT INTO project_access_attempts
                        (project_id,failures,blocked_until) VALUES (?,?,?)
                        ON CONFLICT(project_id) DO UPDATE SET
                        failures=excluded.failures,
                        blocked_until=excluded.blocked_until""",
                        (project_id,0 if count>=MAX_ATTEMPTS else count,blocked))
                    # Explicit commit: a rejected request must still persist
                    # the failed attempt, including through process restart.
                    db.commit()
                    raise PermissionError("Movie passphrase is incorrect")
                db.execute("DELETE FROM project_access_attempts WHERE project_id=?",
                           (project_id,))
                # Every successful host unlock revokes older grants in ALL
                # processes, not merely this process's in-memory sessions.
                new_generation=int(row[2])+1
                db.execute("""UPDATE project_access_locks
                    SET generation=? WHERE project_id=? AND generation=?""",
                    (new_generation,project_id,row[2]))
                db.commit()
            self._revoke(project_id)
            token = secrets.token_urlsafe(32)
            self._sessions[token] = (
                project_id, self.clock() + SESSION_SECONDS, new_generation)
            return token

    def permitted(self, project_id, token, *, renew=False):
        self._check_id(project_id)
        with self._guard:
            with self._db() as db:
                lock_row = db.execute(
                    "SELECT generation FROM project_access_locks WHERE project_id=?",
                    (project_id,)).fetchone()
            if lock_row is None:
                return True
            if not token or not isinstance(token, str):
                return False
            entry = self._sessions.get(token)
            if entry is None:
                return False
            if entry[1] <= self.clock():
                del self._sessions[token]
                return False
            if not hmac.compare_digest(entry[0], project_id):
                return False
            if entry[2] != lock_row[0]:
                # Another native process relocked or unlocked the same film.
                del self._sessions[token]
                return False
            if renew:
                self._sessions[token] = (
                    project_id, self.clock() + SESSION_SECONDS, entry[2])
            return True

    def lock(self, project_id, token):
        self._check_id(project_id)
        with self._guard:
            if not self.protected(project_id) or not self.permitted(project_id, token):
                raise PermissionError("Unlock the protected movie before locking")
            entry=self._sessions.get(token)
            if entry is None:
                raise PermissionError("Active host unlock session required")
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                row=db.execute(
                    "SELECT generation FROM project_access_locks WHERE project_id=?",
                    (project_id,)).fetchone()
                if row is None or row[0]!=entry[2]:
                    raise PermissionError("Another process revoked this movie session")
                db.execute("""UPDATE project_access_locks SET generation=generation+1
                    WHERE project_id=? AND generation=?""",(project_id,row[0]))
                db.commit()
            self._revoke(project_id)
        return {"locked": True, "access": "locked"}

    def any_protected(self):
        """Conservative native IPC barrier until per-project key custody."""
        with self._db() as db:
            return db.execute(
                "SELECT 1 FROM project_access_locks LIMIT 1").fetchone() is not None

    def public_projects(self, projects, token):
        result = []
        for p in projects:
            locked = self.protected(p["id"])
            unlocked = not locked or self.permitted(p["id"], token)
            # A locked project exposes only its chosen display title and ID.
            row = {"id":p["id"], "title":p["title"], "revision":p["revision"],
                   "updated_at":p["updated_at"], "locked":locked,
                   "unlocked":unlocked}
            if unlocked:
                row["idea"] = p["idea"]
            result.append(row)
        return result
