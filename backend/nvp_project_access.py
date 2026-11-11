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
    def __init__(self, db_path, *, clock=time.monotonic):
        self.db_path = str(db_path)
        self.clock = clock
        self._guard = threading.RLock()
        self._sessions = {}
        self._denied = {}
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS project_access_locks(
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                salt BLOB NOT NULL, verifier BLOB NOT NULL, created_at REAL NOT NULL)""")

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
            now = self.clock()
            count, until = self._denied.get(project_id, (0, 0.0))
            if until > now:
                raise PermissionError("Too many attempts; try again later")
            with self._db() as db:
                row = db.execute(
                    "SELECT salt,verifier FROM project_access_locks WHERE project_id=?",
                    (project_id,)).fetchone()
            if row is None:
                raise PermissionError("Movie has no protection configured")
            actual = self._derive(secret, row[0])
            if not hmac.compare_digest(actual, row[1]):
                count += 1
                self._denied[project_id] = (
                    0 if count >= MAX_ATTEMPTS else count,
                    now + COOLDOWN_SECONDS if count >= MAX_ATTEMPTS else 0.0)
                raise PermissionError("Movie passphrase is incorrect")
            self._denied.pop(project_id, None)
            self._revoke(project_id)
            token = secrets.token_urlsafe(32)
            self._sessions[token] = (project_id, now + SESSION_SECONDS)
            return token

    def permitted(self, project_id, token, *, renew=False):
        self._check_id(project_id)
        with self._guard:
            with self._db() as db:
                locked = db.execute(
                    "SELECT 1 FROM project_access_locks WHERE project_id=?",
                    (project_id,)).fetchone() is not None
            if not locked:
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
            if renew:
                self._sessions[token] = (project_id, self.clock() + SESSION_SECONDS)
            return True

    def lock(self, project_id, token):
        self._check_id(project_id)
        with self._guard:
            if not self.protected(project_id) or not self.permitted(project_id, token):
                raise PermissionError("Unlock the protected movie before locking")
            self._revoke(project_id)
        return {"locked": True, "access": "locked"}

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
