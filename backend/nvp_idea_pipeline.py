"""Local creative-development ledger and optional offline screenplay-writing adapter.

AI suggestions are separate draft records, not writes to the creator's screenplay.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

from backend.nvp_studio import Studio, parse_screenplay, SCENE_HEADING

from backend.nvp_creative_schema import STAGES, MAX_DRAFT, MAX_NOTES


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
    """Connects to a local OpenAI-compatible llama.cpp-style server.

    This adapter does not bundle, load, or verify any actual writing model.
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
        request = Request(self.endpoint, body, {"Content-Type": "application/json"}, method="POST")
        try:
            # Never follow HTTP redirects or system HTTP_PROXY settings with private scripts.
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

    def list(self, project_id: str):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            return [dict(row) for row in db.execute(
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

    def create(self, project_id: str, stage: str, content: str, instructions: str = "", origin: str = "creator", expected_project_revision: int | None = None):
        self._check(stage, content, instructions)
        if origin not in ("creator", "local_ai"):
            raise ValueError("Unknown draft origin")
        project = self.studio.get_project(project_id)
        draft_id, stamp = uuid.uuid4().hex, timestamp()
        with self.studio._connection() as db:
            revision_now = db.execute("SELECT revision FROM projects WHERE id=?", (project_id,)).fetchone()
            if revision_now is None:
                raise KeyError("Project not found")
            if expected_project_revision is not None and revision_now["revision"] != expected_project_revision:
                raise RuntimeError("Screenplay changed while the AI was generating; discard and retry")
            db.execute("""INSERT INTO creative_drafts
                (id,project_id,stage,content,instructions,origin,project_revision,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (draft_id,project_id,stage,content,instructions,origin,revision_now["revision"],stamp,stamp))
        return self.get(project_id, draft_id)

    def get(self, project_id: str, draft_id: str):
        with self.studio._connection() as db:
            row = db.execute("SELECT * FROM creative_drafts WHERE id=? AND project_id=?",
                             (draft_id,project_id)).fetchone()
            if row is None:
                raise KeyError("Creative draft not found")
            return dict(row)

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
        if scene_id:
            scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
            if scene is None:
                raise KeyError("Selected scene not found")
            context = f"Selected scene ({scene['heading']}):\n{scene['text'][:12000]}"
        else:
            script = project["screenplay"]
            if len(script) > 16000:
                context = ("Screenplay excerpt only; full script exceeds this local writing request. "
                           "Do not pretend to have read the whole screenplay.\n" + script[:16000])
            else:
                context = script or "No screenplay yet"
        system = ("You are NVP's collaborative screenplay-development assistant. "
                  "The human creator decides the story. Offer concrete creative writing, not production hype. "
                  "Keep named characters and established plot facts consistent with supplied context. "
                  "Do not claim that any video was generated or any software ran. "
                  "For screenplay output, write real Fountain-style dramatic scenes with INT./EXT. "
                  "headings, action, character cues and speakable dialogue. Avoid camera directions "
                  "except where narratively indispensable. Output the requested draft only; no markdown fences.")
        user = (f"Movie: {project['title']}\nOriginal creator idea: {project['idea']}\n"
                f"Writing stage: {stage}\nDirector's instructions: {instructions or 'Preserve creator intent'}\n"
                f"Existing script/context:\n{context}\n"
                "Write a focused, editable proposal for this stage; treat ambiguous choices as creative proposals.")
        text = (self.llm or LocalScriptModel()).complete(system, user)
        return self.create(project_id, stage, text, instructions, "local_ai", project["revision"])
