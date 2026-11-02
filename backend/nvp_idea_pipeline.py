"""NVP's local creative-development ledger and optional loopback AI writer.

The screenplay remains the user's editable source. AI suggestions are draft records,
never automatic writes to the screenplay. Video integration is a future subsystem.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

from backend.nvp_studio import Studio, parse_screenplay, SCENE_HEADING

from backend.nvp_creative_schema import STAGES, MAX_DRAFT, MAX_NOTES
from backend.nvp_story_context import build_story_messages
from backend.nvp_story_bible import StoryBible
from backend.nvp_bible_context import canon_snapshot
from backend.nvp_story_timeline import StoryTimeline
from backend.nvp_scene_mind import SceneMind


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_llm_endpoint() -> str | None:
    url = os.environ.get("NVP_LLM_URL", "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    if (parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != "/v1/chat/completions" or not parsed.port):
        raise ValueError("NVP_LLM_URL must be http://127.0.0.1:PORT/v1/chat/completions (loopback only)")
    return url


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalModelUnavailable(Exception):
    pass


class LocalScriptModel:
    """OpenAI-compatible loopback endpoint (e.g. llama.cpp server).

    This is an adapter, not a bundled LLM. A configured URL is NOT evidence a
    model is actually loaded or that it can generate an acceptable screenplay.
    """
    def __init__(self, endpoint: str | None = None, model_name: str | None = None):
        self.endpoint = endpoint if endpoint is not None else local_llm_endpoint()
        self.model_name = model_name or os.environ.get("NVP_LLM_MODEL", "local")

    def complete(self, system: str, user: str) -> str:
        if not self.endpoint:
            raise LocalModelUnavailable("No local writing model configured; set NVP_LLM_URL to a running local server")
        body = json.dumps({"model": self.model_name,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}],
                           "temperature": 0.65, "max_tokens": 2800, "stream": False}).encode("utf-8")
        request = Request(self.endpoint, body,
                          {"Content-Type": "application/json"}, method="POST")
        try:
            # Do not route local scripts through HTTP_PROXY settings.
            with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=90) as resp:
                raw = resp.read(512_001)
                if len(raw) > 512_000:
                    raise ValueError("Local model response was too large")
                reply = json.loads(raw)
            text = reply["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("The local model returned no writing")
            return text.strip()
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LocalModelUnavailable(f"The local writing model did not return a usable draft: {exc}") from exc


class IdeaPipeline:
    def __init__(self, studio: Studio, llm=None):
        self.studio = studio
        self.llm = llm
        StoryBible(studio)  # schema only; film bible remains independent from model transport
        StoryTimeline(studio)  # chronology schema; no Lu/model dependency
        SceneMind(studio)  # within-scene beliefs, lies, reviewed suggestions
        with self.studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS creative_drafts (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                stage TEXT NOT NULL,
                content TEXT NOT NULL,
                instructions TEXT NOT NULL DEFAULT '',
                origin TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed',
                project_revision INTEGER NOT NULL,
                edit_revision INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_creative_drafts_project ON creative_drafts(project_id,created_at)")
            db.execute("""CREATE TABLE IF NOT EXISTS creative_draft_contexts (
                draft_id TEXT PRIMARY KEY REFERENCES creative_drafts(id) ON DELETE CASCADE,
                upstream_json TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS creative_draft_bible_contexts (
                draft_id TEXT PRIMARY KEY REFERENCES creative_drafts(id) ON DELETE CASCADE,
                canon_digest TEXT NOT NULL,
                scene_id TEXT,
                facts_total INTEGER NOT NULL,
                facts_included INTEGER NOT NULL
            )""")

    @staticmethod
    def _approved_upstream(db, project_id: str, stage: str) -> list[dict]:
        """Newest *creator-approved* decision for each earlier stage."""
        sources = []
        for upstream in STAGES[:STAGES.index(stage)]:
            row = db.execute("""SELECT id,project_id,stage,content,edit_revision FROM creative_drafts
                    WHERE project_id=? AND stage=? AND status='accepted'
                    ORDER BY updated_at DESC,id DESC LIMIT 1""",
                    (project_id, upstream)).fetchone()
            if row is not None:
                sources.append(dict(row))
        return sources

    @staticmethod
    def _source_ids(rows: list[dict]) -> dict[str, str]:
        return {row["stage"]: row["id"] for row in rows}

    def approved_story(self, project_id: str, stage: str) -> list[dict]:
        if stage not in STAGES:
            raise ValueError("Unknown writing stage")
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            selected = self._approved_upstream(db, project_id, stage)
            return [self._annotate(db, item) for item in selected]

    def bible_context(self, project_id: str, scene_id: str | None = None) -> dict:
        with self.studio._connection() as db:
            return canon_snapshot(db, project_id, scene_id)

    def _annotate(self, db, row: dict) -> dict:
        result = dict(row)
        stored = db.execute("SELECT upstream_json FROM creative_draft_contexts WHERE draft_id=?",
                            (result["id"],)).fetchone()
        if stored is None:
            result.update(context_status="legacy_untracked", changed_upstream_stages=[],
                          upstream_sources=[])
        else:
            sources = json.loads(stored["upstream_json"])
            current = self._source_ids(self._approved_upstream(db, result["project_id"], result["stage"]))
            recorded = self._source_ids(sources)
            changed = [stage for stage in STAGES if stage in set(current) | set(recorded)
                       and current.get(stage) != recorded.get(stage)]
            result.update(context_status="needs_review" if changed else "current",
                          changed_upstream_stages=changed, upstream_sources=sources)
        bible = db.execute("SELECT canon_digest,scene_id,facts_total,facts_included "
                           "FROM creative_draft_bible_contexts WHERE draft_id=?",
                           (result["id"],)).fetchone()
        if bible is None:
            result.update(bible_context_status="legacy_untracked", bible_scene_id=None,
                          bible_facts_total=None, bible_facts_included=None)
        else:
            try:
                current_bible = canon_snapshot(db, result["project_id"], bible["scene_id"])
                bible_status = ("current" if current_bible["digest"] == bible["canon_digest"]
                                else "needs_review")
            except (KeyError, RuntimeError):
                bible_status = "needs_review"
            result.update(bible_context_status=bible_status,
                          bible_scene_id=bible["scene_id"],
                          bible_facts_total=bible["facts_total"],
                          bible_facts_included=bible["facts_included"])
        return result

    def list(self, project_id: str):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            return [self._annotate(db, dict(row)) for row in db.execute(
                "SELECT * FROM creative_drafts WHERE project_id=? ORDER BY created_at DESC,id DESC",
                (project_id,)).fetchall()]

    def _check(self, stage: str, content: str, instructions: str):
        if stage not in STAGES:
            raise ValueError("Unknown writing stage")
        if not content.strip() or len(content) > MAX_DRAFT or len(instructions) > MAX_NOTES:
            raise ValueError("A draft must contain writing (up to 120,000 characters) and brief notes")
        if stage == "screenplay":
            if not any(SCENE_HEADING.fullmatch(line.strip()) for line in content.splitlines()):
                raise ValueError("A screenplay draft needs at least one INT./EXT. scene heading")
            parse_screenplay(content)

    def create(self, project_id: str, stage: str, content: str, instructions: str = "", origin: str = "creator", expected_project_revision: int | None = None, expected_upstream: list[dict] | None = None,
               expected_bible_digest: str | None = None, bible_scene_id: str | None = None):
        self._check(stage, content, instructions)
        if origin not in ("creator", "local_ai"):
            raise ValueError("Unknown draft origin")
        self.studio.get_project(project_id)
        draft_id, stamp = uuid.uuid4().hex, timestamp()
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            revision_now = db.execute("SELECT revision FROM projects WHERE id=?", (project_id,)).fetchone()
            if revision_now is None:
                raise KeyError("Project not found")
            if expected_project_revision is not None and revision_now["revision"] != expected_project_revision:
                raise RuntimeError("Screenplay changed while the AI was generating; discard and retry")
            upstream = self._approved_upstream(db, project_id, stage)
            bible = canon_snapshot(db, project_id, bible_scene_id)
            if expected_bible_digest is not None and bible["digest"] != expected_bible_digest:
                raise RuntimeError("Approved Story Bible changed while AI was generating; discard and retry")
            if expected_upstream is not None and self._source_ids(upstream) != self._source_ids(expected_upstream):
                raise RuntimeError("Accepted story decisions changed while the AI was generating; discard and retry")
            db.execute("""INSERT INTO creative_drafts
                (id,project_id,stage,content,instructions,origin,project_revision,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (draft_id,project_id,stage,content,instructions,origin,revision_now["revision"],stamp,stamp))
            db.execute("INSERT INTO creative_draft_contexts (draft_id,upstream_json) VALUES (?,?)",
                       (draft_id,json.dumps([{ "stage": r["stage"], "id": r["id"] }
                                             for r in upstream], sort_keys=True)))
            db.execute("INSERT INTO creative_draft_bible_contexts "
                       "(draft_id,canon_digest,scene_id,facts_total,facts_included) "
                       "VALUES (?,?,?,?,?)",
                       (draft_id, bible["digest"], bible_scene_id,
                        bible["facts_total"], bible["facts_included"]))
        return self.get(project_id, draft_id)

    def get(self, project_id: str, draft_id: str):
        with self.studio._connection() as db:
            row = db.execute("SELECT * FROM creative_drafts WHERE id=? AND project_id=?",
                             (draft_id,project_id)).fetchone()
            if row is None:
                raise KeyError("Creative draft not found")
            return self._annotate(db, dict(row))

    def edit(self, project_id: str, draft_id: str, content: str, expected_edit_revision: int):
        with self.studio._connection() as db:
            row = db.execute("SELECT * FROM creative_drafts WHERE project_id=? AND id=?",
                             (project_id, draft_id)).fetchone()
            if row is None:
                raise KeyError("Creative draft not found")
            if row["status"] != "proposed":
                raise RuntimeError("Approved or discarded drafts are immutable; create a new draft")
            self._check(row["stage"], content, row["instructions"])
            changed = db.execute("""UPDATE creative_drafts SET content=?,edit_revision=edit_revision+1,updated_at=?
                    WHERE project_id=? AND id=? AND edit_revision=? AND status='proposed'""",
                    (content,timestamp(),project_id,draft_id,expected_edit_revision))
            if changed.rowcount != 1:
                raise RuntimeError("Draft changed elsewhere; reload before saving")
        return self.get(project_id, draft_id)

    def decide(self, project_id: str, draft_id: str, decision: str, expected_project_revision: int):
        if decision not in ("accept", "discard", "use_as_screenplay"):
            raise ValueError("Unknown draft decision")
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM creative_drafts WHERE project_id=? AND id=?",
                             (project_id,draft_id)).fetchone()
            if row is None:
                raise KeyError("Creative draft not found")
            if row["status"] != "proposed":
                raise RuntimeError("This draft has already been decided")
            project = db.execute("SELECT revision,screenplay FROM projects WHERE id=?", (project_id,)).fetchone()
            if project is None:
                raise KeyError("Project not found")
            if (project["revision"] != expected_project_revision
                    or project["revision"] != row["project_revision"]):
                raise RuntimeError("Screenplay changed since this draft; reload and review before applying")
            if decision != "discard":
                bible_row = db.execute("SELECT canon_digest,scene_id FROM creative_draft_bible_contexts "
                                       "WHERE draft_id=?", (draft_id,)).fetchone()
                if bible_row is not None:
                    try:
                        latest_bible = canon_snapshot(db, project_id, bible_row["scene_id"])
                    except (KeyError, RuntimeError) as exc:
                        raise RuntimeError("Story Bible scene context changed; refresh before approval") from exc
                    if latest_bible["digest"] != bible_row["canon_digest"]:
                        raise RuntimeError("Story Bible canon changed; refresh and revise the draft before approval")
                elif canon_snapshot(db, project_id)["entities_count"]:
                    raise RuntimeError("Legacy draft lacks Story Bible provenance; recreate and review before approval")
                if any(self._annotate(db, source)[field] == "needs_review"
                       for source in self._approved_upstream(db, project_id, row["stage"])
                       for field in ("context_status", "bible_context_status")):
                    raise RuntimeError("Earlier accepted story stages need review before approving this draft")
                metadata = db.execute("SELECT upstream_json FROM creative_draft_contexts WHERE draft_id=?",
                                      (draft_id,)).fetchone()
                if metadata is not None:
                    previous = self._source_ids(json.loads(metadata["upstream_json"]))
                    current = self._source_ids(self._approved_upstream(db, project_id, row["stage"]))
                    if previous != current:
                        raise RuntimeError("Approved story context changed; review and regenerate this draft before accepting")
            if decision == "use_as_screenplay":
                if row["stage"] != "screenplay":
                    raise ValueError("Only a screenplay draft can replace the screenplay")
                parse_screenplay(row["content"])
                db.execute("""INSERT OR IGNORE INTO screenplay_revisions
                    (project_id,revision,screenplay,saved_at,reason) VALUES (?,?,?,?,?)""",
                    (project_id,project["revision"],project["screenplay"],timestamp(),"before_ai_draft"))
                changed = db.execute("""UPDATE projects SET screenplay=?,revision=revision+1,updated_at=?
                                  WHERE id=? AND revision=?""",
                           (row["content"],timestamp(),project_id,expected_project_revision))
                if changed.rowcount != 1:
                    raise RuntimeError("Screenplay changed during approval; reload and try again")
            status = "discarded" if decision == "discard" else "accepted"
            db.execute("UPDATE creative_drafts SET status=?,updated_at=? WHERE id=?",
                       (status,timestamp(),draft_id))
        return self.studio.get_project(project_id)

    def generate(self, project_id: str, stage: str, instructions: str = "", scene_id: str | None = None):
        if stage not in STAGES or len(instructions) > MAX_NOTES:
            raise ValueError("Unknown writing stage or instructions too long")
        project = self.studio.get_project(project_id)
        approved = self.approved_story(project_id, stage)
        if any(source[field] == "needs_review" for source in approved
               for field in ("context_status", "bible_context_status")):
            raise RuntimeError("Earlier accepted story stages are out of date; review those decisions before generating this stage")
        bible = self.bible_context(project_id, scene_id)
        system, user = build_story_messages(project, stage, instructions, scene_id, approved,
                                            bible_context=bible)
        text = (self.llm or LocalScriptModel()).complete(system, user)
        # AI drafts remain proposals. Never directly overwrite the screenplay.
        return self.create(project_id, stage, text, instructions, "local_ai",
                           project["revision"], expected_upstream=approved,
                           expected_bible_digest=bible["digest"], bible_scene_id=scene_id)
