"""Offline-first production planning foundation. No GPU, network, or model needed.

This module deliberately does NOT pretend to render movies or understand a story.
It keeps a creator's words and approved choices persistent and recoverable.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_SCRIPT_CHARS = 1_000_000
SCENE_HEADING = re.compile(r"^(?:INT\.?/EXT\.?|EXT\.?/INT\.?|INT\.?|EXT\.?|I/E\.?)\s+.+", re.IGNORECASE)
CHARACTER_CUE = re.compile(r"^[A-Z][A-Z0-9 .,'()\-]{0,39}$")
CUE_SUFFIX = re.compile(r"\s*\((?:V\.O\.|O\.S\.|CONT'D|CONTINUED)\)\s*$")
FRAMINGS = {"wide", "two_shot", "medium", "close_up", "insert"}


def now():
    return datetime.now(timezone.utc).isoformat()


def parse_screenplay(script: str) -> list[dict]:
    """Conservative Fountain-style parser; ambiguous input remains available in raw text.

    Not a general PDF/FDX parser. User should review cues and scene boundaries.
    Scene identity follows normalized heading + occurrence, not line number.
    """
    if len(script) > MAX_SCRIPT_CHARS:
        raise ValueError("Screenplay exceeds the 1,000,000-character planning limit")
    lines = script.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    scenes = []
    occurrences = {}
    scene = None
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if SCENE_HEADING.fullmatch(stripped):
            norm = " ".join(stripped.upper().split())
            occurrences[norm] = occurrences.get(norm, 0) + 1
            identity = f"{norm}#{occurrences[norm]}".encode("utf-8")
            scene = {"id": "SC_" + hashlib.sha256(identity).hexdigest()[:12],
                     "number": len(scenes) + 1, "heading": stripped, "start_line": index,
                     "end_line": index, "text": "", "characters": [], "dialogue": []}
            scenes.append(scene)
            continue
        if scene is None:
            if not stripped:
                continue
            norm = "UNHEADED SCENE"
            scene = {"id": "SC_" + hashlib.sha256(norm.encode()).hexdigest()[:12],
                     "number": 1, "heading": "SCENE WITHOUT HEADING", "start_line": index,
                     "end_line": index, "text": "", "characters": [], "dialogue": []}
            scenes.append(scene)
        scene["end_line"] = index
    # Retain verbatim scene source instead of reformatting the creator's text.
    for scene in scenes:
        excerpt = lines[scene["start_line"] - 1:scene["end_line"]]
        scene["text"] = "\n".join(excerpt).strip()
        for offset, original in enumerate(excerpt):
            cue = original.strip()
            if not CHARACTER_CUE.fullmatch(cue) or cue in {"CUT TO:", "FADE OUT:", "THE END"}:
                continue
            if SCENE_HEADING.fullmatch(cue):
                continue
            next_line = next((x.strip() for x in excerpt[offset + 1:] if x.strip()), "")
            if not next_line or next_line == cue or CHARACTER_CUE.fullmatch(next_line):
                continue
            canonical = CUE_SUFFIX.sub("", cue).strip()
            if canonical and canonical not in scene["characters"]:
                scene["characters"].append(canonical)
            if canonical:
                scene["dialogue"].append({"speaker": canonical, "line": next_line})
    return scenes


def initial_shots(scene: dict) -> list[dict]:
    """Plain, editable coverage suggestions. Not AI judgments or render jobs."""
    actors = scene["characters"]
    result = [{"shot_id": "S01", "framing": "wide", "subject": "scene",
               "intent": "Show where the scene happens", "notes": "Establish space and relationships"}]
    if len(actors) >= 2:
        result.append({"shot_id": "S02", "framing": "two_shot", "subject": ", ".join(actors[:2]),
                       "intent": "Show how the characters relate", "notes": "Review spacing and eyelines"})
    for actor in actors[:3]:
        result.append({"shot_id": f"S{len(result)+1:02d}", "framing": "medium", "subject": actor,
                       "intent": f"See {actor}'s performance", "notes": "Consider reaction and listening"})
    if len(result) == 1:
        result.append({"shot_id": "S02", "framing": "medium", "subject": "main action",
                       "intent": "Show the important action", "notes": "Choose subject before animation"})
    return result


class Studio:
    def __init__(self, db_path: str | Path | None = None):
        root = Path(os.environ.get("NVP_HOME", str(Path.home() / "NVP_Projects")))
        self.db_path = Path(db_path) if db_path else root / "nvp_studio.sqlite3"
        if getattr(sys,"frozen",False):
            # An NSIS/Debian upgrade/uninstall may replace the executable
            # installation tree, but must NEVER own movie projects, original
            # USD/PCM, approved creative history or imported film packages.
            # Use the historical user NVP_Projects root unless the director
            # explicitly selected NVP_HOME; no silent path migration.
            executable=Path(sys.executable).resolve(strict=True).parent
            selected=self.db_path.expanduser().resolve()
            if selected==executable or executable in selected.parents:
                raise RuntimeError(
                    "NVP project storage cannot be inside the installed "
                    "application directory. Move NVP_HOME to a user-owned "
                    "folder before opening your original films.")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.db_path, timeout=15)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def _init_db(self):
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, idea TEXT NOT NULL,
                screenplay TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS shots (
                project_id TEXT NOT NULL, scene_id TEXT NOT NULL, shot_id TEXT NOT NULL,
                framing TEXT NOT NULL, subject TEXT NOT NULL, intent TEXT NOT NULL,
                notes TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, scene_id, shot_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
            db.execute("""CREATE TABLE IF NOT EXISTS screenplay_revisions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL, screenplay TEXT NOT NULL,
                saved_at TEXT NOT NULL, reason TEXT NOT NULL,
                PRIMARY KEY(project_id,revision))""")

    def screenplay_history(self, project_id: str):
        self.get_project(project_id)
        with self._connection() as db:
            rows = db.execute("""SELECT revision, screenplay, saved_at, reason
                FROM screenplay_revisions WHERE project_id=? ORDER BY revision DESC""",
                (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def restore_screenplay(self, project_id: str, source_revision: int, expected_revision: int):
        with self._connection() as db:
            current = db.execute("SELECT revision,screenplay FROM projects WHERE id=?",
                                 (project_id,)).fetchone()
            if current is None:
                raise KeyError("Project not found")
            if current["revision"] != expected_revision:
                raise RuntimeError("Screenplay changed; reload before restoring an older version")
            source = db.execute("""SELECT screenplay FROM screenplay_revisions
                    WHERE project_id=? AND revision=?""", (project_id,source_revision)).fetchone()
            if source is None:
                raise KeyError("Requested screenplay revision not found")
            db.execute("""INSERT OR IGNORE INTO screenplay_revisions
                (project_id,revision,screenplay,saved_at,reason) VALUES (?,?,?,?,?)""",
                (project_id,current["revision"],current["screenplay"],now(),"before_restore"))
            changed = db.execute("""UPDATE projects SET screenplay=?,revision=revision+1,updated_at=?
                                  WHERE id=? AND revision=?""",
                                 (source["screenplay"],now(),project_id,expected_revision))
            if changed.rowcount != 1:
                raise RuntimeError("Screenplay changed during restore; reload and try again")
        return self.get_project(project_id)

    def create_project(self, title: str, idea: str, screenplay: str = ""):
        """Atomically create a film, optionally with its original screenplay.

        A rejected source cannot leave behind an empty half-created movie.
        This is screenplay parsing, NOT a claim that AI has staged scenes.
        """
        if not all(isinstance(x, str) for x in (title, idea, screenplay)):
            raise ValueError("Movie title, idea and screenplay must be text")
        title, idea = title.strip(), idea.strip()
        if not title or len(title) > 150 or len(idea) > 10000:
            raise ValueError("Enter a title (up to 150 characters) and an idea under 10,000 characters")
        parse_screenplay(screenplay)
        project_id = uuid.uuid4().hex
        stamp = now()
        with self._connection() as db:
            db.execute("""INSERT INTO projects
                (id, title, idea, screenplay, created_at, updated_at)
                VALUES (?,?,?,?,?,?)""",
                (project_id, title, idea, screenplay, stamp, stamp))
        return self.get_project(project_id)

    def list_projects(self):
        with self._connection() as db:
            rows = db.execute("SELECT id,title,idea,revision,updated_at FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str):
        with self._connection() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if not row:
                raise KeyError("Project not found")
            shots = db.execute("SELECT * FROM shots WHERE project_id=? ORDER BY scene_id,shot_id",
                               (project_id,)).fetchall()
        project = dict(row)
        scenes = parse_screenplay(project["screenplay"])
        grouped = {}
        for shot in shots:
            grouped.setdefault(shot["scene_id"], []).append(dict(shot))
        for scene in scenes:
            scene["shots"] = grouped.get(scene["id"], [])
        # Orphaned shots are never destroyed after screenplay edits.
        active_ids = {s["id"] for s in scenes}
        project["archived_shots"] = sum(len(v) for k, v in grouped.items() if k not in active_ids)
        project["scenes"] = scenes
        project["bible"] = {"characters": sorted({n for s in scenes for n in s["characters"]}),
                            "locations": list(dict.fromkeys(s["heading"] for s in scenes))}
        return project

    def save_screenplay(self, project_id: str, screenplay: str, expected_revision: int):
        parse_screenplay(screenplay)
        with self._connection() as db:
            current = db.execute("SELECT screenplay,revision FROM projects WHERE id=?",
                                 (project_id,)).fetchone()
            if current is None:
                raise KeyError("Project not found")
            if current["revision"] != expected_revision:
                raise RuntimeError("Project changed elsewhere. Reload before saving to avoid overwriting edits")
            db.execute("""INSERT OR IGNORE INTO screenplay_revisions
                (project_id,revision,screenplay,saved_at,reason) VALUES (?,?,?,?,?)""",
                (project_id,current["revision"],current["screenplay"],now(),"before_manual_edit"))
            changed = db.execute("""UPDATE projects SET screenplay=?,revision=revision+1,updated_at=?
                    WHERE id=? AND revision=?""", (screenplay,now(),project_id,expected_revision))
            if changed.rowcount != 1:
                raise RuntimeError("Project changed during save; reload before editing")
        return self.get_project(project_id)

    def plan_scene(self, project_id: str, scene_id: str):
        project = self.get_project(project_id)
        scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
        if scene is None:
            raise KeyError("Scene not found")
        with self._connection() as db:
            for shot in initial_shots(scene):
                db.execute("""INSERT OR IGNORE INTO shots
                    (project_id,scene_id,shot_id,framing,subject,intent,notes,status,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (project_id, scene_id, shot["shot_id"], shot["framing"], shot["subject"],
                     shot["intent"], shot["notes"], "proposed", now()))
        return self.get_project(project_id)

    def edit_shot(self, project_id: str, scene_id: str, shot_id: str, *, framing: str,
                  subject: str, intent: str, notes: str, approved: bool):
        if framing not in FRAMINGS or any(len(x) > lim for x, lim in
           [(subject, 200), (intent, 500), (notes, 2000)]):
            raise ValueError("Invalid shot framing or field length")
        # Only edit shots attached to active scenes; archived records remain recoverable.
        if scene_id not in {s["id"] for s in self.get_project(project_id)["scenes"]}:
            raise KeyError("Scene not found in current screenplay")
        with self._connection() as db:
            result = db.execute("""UPDATE shots SET framing=?,subject=?,intent=?,notes=?,status=?,updated_at=?
                        WHERE project_id=? AND scene_id=? AND shot_id=?""",
                        (framing, subject.strip(), intent.strip(), notes.strip(),
                         "approved" if approved else "proposed", now(), project_id, scene_id, shot_id))
            if result.rowcount != 1:
                raise KeyError("Shot not found")
        return self.get_project(project_id)
