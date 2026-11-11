"""Truthful local NVP planning API and optional local screenplay-writing proposals."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from backend.nvp_studio import Studio
from backend.nvp_g04_preproduction import G04Preproduction
from backend.nvp_g05_scene_authoring import G05SceneAuthoring
from backend.nvp_screenplay_review import ScreenplayContinuityReview
from backend.nvp_story_bible import StoryBible
from backend.nvp_idea_pipeline import IdeaPipeline, LocalModelUnavailable, STAGES, local_llm_endpoint
from backend.nvp_model_service import discover_models, writer_for
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_render_preflight import preflight_scene
import uuid
import re
import sys
import base64
import binascii
from backend.nvp_project_access import ProjectAccess, COOKIE, SESSION_SECONDS
from backend.nvp_g03_live_store import LiveFilmStore, LiveFilmError
from backend.nvp_g03_windows_vault import VaultError

app = FastAPI(title="NVP — Your movie, your way", version="0.3.0-creative-foundation")
studio = Studio()
resource_activity = TaskLedger()
_film_access = None
_film_access_db = None
_live_films = None
_live_films_db = None
_g08_controller = None

def live_films():
    """One trusted per-Studio encrypted live store, no keys in JavaScript."""
    global _live_films, _live_films_db
    source=str(studio.db_path.resolve())
    if _live_films is None or _live_films_db != source:
        _live_films=LiveFilmStore(
            studio.db_path.parent/"nvp_g03_encrypted_live",
            grant_checker=lambda pid,token: film_access().permitted(pid,token))
        _live_films_db=source
    return _live_films


def film_access():
    """Attach lock state to this exact Studio DB, including test DB swaps."""
    global _film_access, _film_access_db
    source = str(studio.db_path)
    if _film_access is None or _film_access_db != source:
        _film_access = ProjectAccess(source)
        _film_access_db = source
    return _film_access


@app.middleware("http")
async def film_project_access_guard(request: Request, call_next):
    """All project-id URL families share the same authoritative lock gate."""
    path = request.url.path
    parts = path.split("/")
    if (len(parts) >= 4 and parts[:3] == ["", "api", "projects"] and
            re.fullmatch(r"[a-f0-9]{32}", parts[3])):
        project_id = parts[3]
        action = parts[4] if len(parts) == 5 else ""
        if action in {"unlock", "protect"}:
            if request.headers.get("x-nvp-director") != "1":
                return JSONResponse({"detail": "Film action requires the local director UI"},
                                    status_code=403)
            return await call_next(request)
        locks = film_access()
        try:
            protected = locks.protected(project_id)
            authorized = locks.permitted(project_id, request.cookies.get(COOKIE),
                                         renew=protected)
        except KeyError:
            return JSONResponse({"detail": "Movie not found"}, status_code=404)
        if not authorized:
            return JSONResponse({"detail": "This movie is locked. Unlock it to continue."},
                                status_code=423)
        if live_films().exists(project_id):
            # Only host-backed encrypted routes may touch a secured movie.
            # All 55 legacy source/UI/worker project API handlers are denied.
            tail="/".join(parts[4:])
            allowed=(request.method=="POST" and tail=="lock") or (
                request.method=="GET" and tail in {"live","live/recovery"}) or (
                request.method=="PUT" and tail=="live/screenplay") or (
                request.method=="POST" and tail=="live/source") or (
                tail=="live/preproduction" or tail.startswith("live/preproduction/")) or (
                tail.startswith("live/stage/")) or (
                tail.startswith("live/film/")) or (
                tail=="live/edit" or tail.startswith("live/edit/")) or (
                tail=="live/export" or tail.startswith("live/export/")) or (
                tail.startswith("live/production/looks/")) or (
                tail.startswith("live/production/actors/")) or (
                tail.startswith("live/production/sound/")) or (
                tail=="live/av" or tail.startswith("live/av/"))
            if not allowed:
                return JSONResponse(
                    {"detail":"Encrypted movie requires its protected director workspace"},
                    status_code=403)
        if (protected and request.method not in {"GET", "HEAD", "OPTIONS"} and
                request.headers.get("x-nvp-director") != "1"):
            return JSONResponse({"detail": "Film action requires the local director UI"},
                                status_code=403)
        response = await call_next(request)
        if protected:
            # Another native host may relock while a request is in progress.
            # Never return decrypted body content after a grant was revoked.
            token = request.cookies.get(COOKIE)
            if (live_films().exists(project_id) and action!="lock" and
                    not locks.permitted(project_id, token)):
                live_films().revoke(project_id)
                return JSONResponse(
                    {"detail":"Movie locked while this operation was in progress"},
                    status_code=423)
            # A renewed HTTP-only cookie expires after an idle session.
            if token and locks.permitted(project_id, token):
                response.set_cookie(COOKIE, token, httponly=True,
                                    samesite="strict", secure=request.url.scheme == "https",
                                    max_age=SESSION_SECONDS, path="/api")
        return response
    return await call_next(request)



@app.get('/api/system/activity')
def resource_activity_snapshot():
    # Task descriptions can contain director-created project names, source
    # notes and sensitive movie details. Public telemetry must not bypass the
    # protected-project API gate simply because its URI lacks a project ID.
    if film_access().any_protected():
        return {"format":"nvp.system.resource_activity.v1",
                "redacted":True,"tasks":[],"sample":None,
                "reservations":None,
                "message":"Activity hidden while movies are locked"}
    return resource_activity.snapshot()



class NewProject(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    idea: str = Field(default="", max_length=10000)
    screenplay: str = Field(default="", max_length=1_000_000)


class NewEncryptedProject(NewProject):
    passphrase: str = Field(min_length=12, max_length=256)


class NewEncryptedSource(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    media_type: str = Field(default="application/octet-stream", max_length=120)
    base64_data: str = Field(min_length=1, max_length=22_000_000)


class ScreenplayUpdate(BaseModel):
    screenplay: str = Field(max_length=1_000_000)
    expected_revision: int = Field(ge=0)


class ShotUpdate(BaseModel):
    framing: str
    subject: str = Field(max_length=200)
    intent: str = Field(max_length=500)
    notes: str = Field(max_length=2000)
    approved: bool = False


def run(action):
    try:
        return action()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/status")
def status():
    return {"status": "ready", "mode": "offline_planning", "gpu_required": False,
            "capabilities": {"project_storage": "ready", "script_breakdown": "basic_fountain",
                             "editable_shots": "ready", "local_llm": "not_connected",
                             "3d_renderer": "not_connected", "voice": "not_connected",
                             "project_file_encryption": "new_windows_movies_only" if sys.platform=="win32" else "not_available",
                             "3d_stage_planning": "deterministic_proxies_ready",
                             "blender_export": "bpy_script_only_not_executed"}}


@app.get("/api/projects")
def projects(request: Request):
    rows=film_access().public_projects(studio.list_projects(),request.cookies.get(COOKIE))
    for row in rows:
        row["encrypted"]=live_films().exists(row["id"])
    return rows


class FilmPassphrase(BaseModel):
    passphrase: str = Field(min_length=12, max_length=256)


@app.post("/api/projects/{project_id}/protect")
def protect_movie(project_id: str, payload: FilmPassphrase):
    try:
        return film_access().protect(project_id, payload.passphrase)
    except KeyError:
        raise HTTPException(status_code=404, detail="Movie not found")
    except PermissionError:
        raise HTTPException(status_code=409, detail="Movie already locked")


@app.post("/api/projects/{project_id}/unlock")
def unlock_movie(project_id: str, payload: FilmPassphrase, request: Request):
    try:
        token = film_access().unlock(project_id, payload.passphrase)
        try:
            if live_films().exists(project_id):
                live_films().authorize(project_id, payload.passphrase, token)
        except Exception:
            film_access().lock(project_id, token)
            raise
    except KeyError:
        raise HTTPException(status_code=404, detail="Movie not found")
    except (PermissionError, VaultError, LiveFilmError):
        raise HTTPException(status_code=403, detail="Unable to unlock movie")
    response = JSONResponse({"locked": False, "access": "unlocked",
                             "encrypted": live_films().exists(project_id)})
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https",
                        max_age=SESSION_SECONDS, path="/api")
    return response


@app.post("/api/projects/{project_id}/lock")
def lock_movie(project_id: str, request: Request):
    try:
        result = film_access().lock(project_id, request.cookies.get(COOKIE))
        from backend.nvp_g06_routes import revoke_recording
        revoke_recording(project_id)
        if _g08_controller is not None:
            _g08_controller["ordinary"].cancel_project(project_id)
            _g08_controller["sealed"].cancel_project(project_id)
        live_films().revoke(project_id)
    except (PermissionError, KeyError):
        raise HTTPException(status_code=403, detail="Unable to lock movie")
    response = JSONResponse(result)
    response.delete_cookie(COOKIE, path="/api")
    return response



@app.post("/api/projects", status_code=201)
def create_project(payload: NewProject):
    return run(lambda: studio.create_project(payload.title, payload.idea, payload.screenplay))


@app.post("/api/projects/encrypted", status_code=201)
def create_encrypted_movie(payload: NewEncryptedProject, request: Request):
    """All sensitive fields go straight to encrypted in-memory SQLite.

    The legacy Studio receives only a public title and an empty shell. No
    media or screenplay is ever first copied into plaintext shared SQLite.
    """
    if request.headers.get("x-nvp-director")!="1":
        raise HTTPException(status_code=403,detail="Director confirmation required")
    if sys.platform!="win32":
        raise HTTPException(status_code=501,detail="Windows account encryption unavailable here")
    # The legacy catalog has only public title metadata; orphan shells on
    # failure can be removed without losing any private content.
    shell=studio.create_project(payload.title,"","")
    pid=shell["id"]
    try:
        live_films().create(pid,payload.title,payload.idea,payload.screenplay,
                            payload.passphrase)
    except Exception:
        if not live_films().exists(pid):
            with studio._connection() as db:
                db.execute("DELETE FROM projects WHERE id=? AND idea='' AND screenplay=''",
                           (pid,))
        raise HTTPException(status_code=503,
                            detail="Encrypted movie could not be created")
    # The encrypted payload is durable and readable before granting access.
    film_access().protect(pid,payload.passphrase)
    token=film_access().unlock(pid,payload.passphrase)
    live_films().authorize(pid,payload.passphrase,token)
    output=live_films().read(pid,token)
    response=JSONResponse(output,status_code=201)
    response.set_cookie(COOKIE,token,httponly=True,samesite="strict",
                        secure=request.url.scheme=="https",
                        max_age=SESSION_SECONDS,path="/api")
    return response


@app.get("/api/projects/{project_id}/live")
def encrypted_live_movie(project_id: str, request: Request):
    try:
        return live_films().read(project_id,request.cookies.get(COOKIE))
    except (LiveFilmError, VaultError):
        raise HTTPException(status_code=423,detail="Encrypted movie unavailable or locked")


@app.put("/api/projects/{project_id}/live/screenplay")
def save_encrypted_screenplay(project_id: str, payload: ScreenplayUpdate,
                             request: Request):
    try:
        return live_films().save_screenplay(
            project_id,request.cookies.get(COOKIE),
            payload.screenplay,payload.expected_revision)
    except (LiveFilmError, VaultError) as exc:
        raise HTTPException(status_code=409,detail=str(exc))


@app.post("/api/projects/{project_id}/live/source")
def upload_encrypted_original(project_id: str, payload: NewEncryptedSource,
                              request: Request):
    try:
        binary=base64.b64decode(payload.base64_data,validate=True)
        if len(binary)>16*1024*1024:
            raise ValueError("WebView source transfer too large; use native supervised capture")
        return live_films().put_original(
            project_id,request.cookies.get(COOKIE),
            payload.name,binary,payload.media_type)
    except (binascii.Error,ValueError):
        raise HTTPException(status_code=422,detail="Invalid source content")
    except (LiveFilmError,VaultError) as exc:
        raise HTTPException(status_code=409,detail=str(exc))


@app.get("/api/projects/{project_id}/live/recovery")
def encrypted_recovery_receipts(project_id: str,request: Request):
    try:
        return live_films().recovery_candidates(project_id,request.cookies.get(COOKIE))
    except (LiveFilmError,VaultError):
        raise HTTPException(status_code=423,detail="Encrypted movie unavailable or locked")


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return run(lambda: studio.get_project(project_id))


@app.put("/api/projects/{project_id}/screenplay")
def save_screenplay(project_id: str, payload: ScreenplayUpdate):
    return run(lambda: studio.save_screenplay(project_id, payload.screenplay, payload.expected_revision))


# G04: director's Scene Library and approved Production Bible.
# The model only suggests; no renderer, source write, or Take permission is
# exposed from this surface. Secured movies use sealed in-memory SQLite.
class G04SceneNotes(BaseModel):
    notes: dict[str,str]
    expected_notes_revision: int = Field(ge=0)
    expected_screenplay_revision: int = Field(ge=0)

class G04SceneAdd(BaseModel):
    expected_screenplay_revision: int = Field(ge=0)

class G04RestoreSceneNotes(BaseModel):
    source_revision: int = Field(ge=0)
    expected_notes_revision: int = Field(ge=0)
    expected_screenplay_revision: int = Field(ge=0)

class G04ScreenplayPrompt(BaseModel):
    direction: str = Field(default="",max_length=1200)

class G04ScreenplayDecision(BaseModel):
    decision: str
    expected_screenplay_revision: int = Field(ge=0)
    edited_text: str | None = Field(default=None,max_length=1_000_000)

class G04SpeakerAssignment(BaseModel):
    source_cue: str = Field(min_length=1,max_length=40)
    expected_screenplay_revision: int = Field(ge=0)
    actor_id: str | None = Field(default=None,max_length=40)
    new_name: str | None = Field(default=None,max_length=100)

class G04SuggestionDecision(BaseModel):
    decision: str
    expected_screenplay_revision: int = Field(ge=0)
    approved_value: str | None = Field(default=None,max_length=1500)

def _director_preproduction(project_id: str, request: Request):
    secured=live_films().exists(project_id)
    return G04Preproduction(studio,
        live=live_films() if secured else None,
        token=request.cookies.get(COOKIE) if secured else None)

@app.get("/api/projects/{project_id}/preproduction")
@app.get("/api/projects/{project_id}/live/preproduction")
def g04_scene_library(project_id: str,request: Request):
    return run(lambda: _director_preproduction(project_id,request).view(project_id))

@app.post("/api/projects/{project_id}/preproduction/screenplay/suggestions")
@app.post("/api/projects/{project_id}/live/preproduction/screenplay/suggestions")
def g04_suggest_screenplay(project_id:str,request:Request,
                           payload:G04ScreenplayPrompt):
    try:
        return run(lambda:_director_preproduction(project_id,request)
            .generate_screenplay(project_id,payload.direction))
    except LocalModelUnavailable:
        raise HTTPException(status_code=503,
            detail="AI writing is unavailable. You can continue writing your own screenplay.")

@app.post("/api/projects/{project_id}/preproduction/screenplay/{draft_id}/decision")
@app.post("/api/projects/{project_id}/live/preproduction/screenplay/{draft_id}/decision")
def g04_review_screenplay(project_id:str,draft_id:str,request:Request,
                          payload:G04ScreenplayDecision):
    return run(lambda:_director_preproduction(project_id,request)
        .decide_screenplay(project_id,draft_id,payload.decision,
            payload.expected_screenplay_revision,payload.edited_text))

@app.post("/api/projects/{project_id}/preproduction/scenes")
@app.post("/api/projects/{project_id}/live/preproduction/scenes")
def g04_add_scene(project_id: str,request: Request,payload: G04SceneAdd):
    return run(lambda:_director_preproduction(project_id,request).add_scene(
        project_id,payload.expected_screenplay_revision))

@app.put("/api/projects/{project_id}/preproduction/scenes/{scene_id}")
@app.put("/api/projects/{project_id}/live/preproduction/scenes/{scene_id}")
def g04_edit_scene(project_id:str,scene_id:str,request:Request,
                   payload:G04SceneNotes):
    return run(lambda:_director_preproduction(project_id,request).save_scene(
        project_id,scene_id,payload.notes,payload.expected_notes_revision,
        payload.expected_screenplay_revision))

@app.post("/api/projects/{project_id}/preproduction/scenes/{scene_id}/restore")
@app.post("/api/projects/{project_id}/live/preproduction/scenes/{scene_id}/restore")
def g04_restore_scene_details(project_id:str,scene_id:str,request:Request,
                             payload:G04RestoreSceneNotes):
    return run(lambda:_director_preproduction(project_id,request).restore_notes(
        project_id,scene_id,payload.source_revision,payload.expected_notes_revision,
        payload.expected_screenplay_revision))

@app.post("/api/projects/{project_id}/preproduction/scenes/{scene_id}/speakers")
@app.post("/api/projects/{project_id}/live/preproduction/scenes/{scene_id}/speakers")
def g04_assign_speaker(project_id:str,scene_id:str,request:Request,
                       payload:G04SpeakerAssignment):
    return run(lambda:_director_preproduction(project_id,request).bind_speaker(
        project_id,scene_id,payload.source_cue,
        payload.expected_screenplay_revision,
        actor_id=payload.actor_id,new_name=payload.new_name))

@app.post("/api/projects/{project_id}/preproduction/scenes/{scene_id}/suggestions")
@app.post("/api/projects/{project_id}/live/preproduction/scenes/{scene_id}/suggestions")
def g04_ask_ai(project_id:str,scene_id:str,request:Request):
    try:
        return run(lambda:_director_preproduction(project_id,request).generate(
            project_id,scene_id))
    except LocalModelUnavailable:
        raise HTTPException(status_code=503,
            detail="AI assistance is unavailable. You can still develop your scene.")

@app.post("/api/projects/{project_id}/preproduction/suggestions/{proposal_id}/decision")
@app.post("/api/projects/{project_id}/live/preproduction/suggestions/{proposal_id}/decision")
def g04_review_ai(project_id:str,proposal_id:str,request:Request,
                  payload:G04SuggestionDecision):
    return run(lambda:_director_preproduction(project_id,request).decide(
        project_id,proposal_id,payload.decision,
        payload.expected_screenplay_revision,payload.approved_value))


# G05: model and UI may draft a native OpenUSD stage but cannot run
# rendering, filmmaking workers, nor freeze a Take. All project identity,
# G04 source and director approval checks remain native-host decisions.
class G05Revision(BaseModel):
    expected_revision: int = Field(ge=0,le=1000000)

class G05Change(G05Revision):
    operation: str = Field(min_length=2,max_length=20)
    details: dict

class G05Undo(G05Revision):
    source_revision: int = Field(ge=1,le=1000000)

class G05IdeaDecision(G05Revision):
    decision: str = Field(min_length=6,max_length=6)

def _director_scene_authoring(project_id: str,request: Request):
    secured=live_films().exists(project_id)
    return G05SceneAuthoring(studio,live=live_films() if secured else None,
                            token=request.cookies.get(COOKIE) if secured else None)

@app.get("/api/projects/{project_id}/stage/{scene_id}")
@app.get("/api/projects/{project_id}/live/stage/{scene_id}")
def g05_stage_read(project_id:str,scene_id:str,request:Request):
    return run(lambda:_director_scene_authoring(project_id,request)
               .view(project_id,scene_id))

@app.post("/api/projects/{project_id}/stage/{scene_id}/generate")
@app.post("/api/projects/{project_id}/live/stage/{scene_id}/generate")
def g05_stage_generate(project_id:str,scene_id:str,request:Request,
                       payload:G05Revision):
    return run(lambda:_director_scene_authoring(project_id,request)
        .generate(project_id,scene_id,payload.expected_revision))

@app.post("/api/projects/{project_id}/stage/{scene_id}/edit")
@app.post("/api/projects/{project_id}/live/stage/{scene_id}/edit")
def g05_stage_edit(project_id:str,scene_id:str,request:Request,
                   payload:G05Change):
    return run(lambda:_director_scene_authoring(project_id,request)
        .edit(project_id,scene_id,payload.expected_revision,
              payload.operation,payload.details))

@app.post("/api/projects/{project_id}/stage/{scene_id}/reconcile")
@app.post("/api/projects/{project_id}/live/stage/{scene_id}/reconcile")
def g05_stage_reconcile(project_id:str,scene_id:str,request:Request,
                        payload:G05Revision):
    return run(lambda:_director_scene_authoring(project_id,request)
        .reconcile(project_id,scene_id,payload.expected_revision))

@app.post("/api/projects/{project_id}/stage/{scene_id}/restore")
@app.post("/api/projects/{project_id}/live/stage/{scene_id}/restore")
def g05_stage_restore(project_id:str,scene_id:str,request:Request,
                      payload:G05Undo):
    return run(lambda:_director_scene_authoring(project_id,request)
        .restore(project_id,scene_id,payload.expected_revision,
                 payload.source_revision))

@app.post("/api/projects/{project_id}/stage/{scene_id}/ideas")
@app.post("/api/projects/{project_id}/live/stage/{scene_id}/ideas")
def g05_stage_ai_ideas(project_id:str,scene_id:str,request:Request):
    try:
        return run(lambda:_director_scene_authoring(project_id,request)
            .suggest_scene_objects(project_id,scene_id))
    except LocalModelUnavailable:
        raise HTTPException(status_code=503,
            detail="Scene AI is unavailable. You can still arrange every object yourself.")

@app.post("/api/projects/{project_id}/stage/{scene_id}/ideas/{idea_id}/decision")
@app.post("/api/projects/{project_id}/live/stage/{scene_id}/ideas/{idea_id}/decision")
def g05_stage_idea_review(project_id:str,scene_id:str,idea_id:str,
                          request:Request,payload:G05IdeaDecision):
    return run(lambda:_director_scene_authoring(project_id,request)
        .decide_scene_object(project_id,scene_id,idea_id,payload.decision,
                             payload.expected_revision))

@app.post("/api/projects/{project_id}/stage/{scene_id}/approve")
@app.post("/api/projects/{project_id}/live/stage/{scene_id}/approve")
def g05_stage_approve(project_id:str,scene_id:str,request:Request,
                      payload:G05Revision):
    return run(lambda:_director_scene_authoring(project_id,request)
        .approve(project_id,scene_id,payload.expected_revision))


@app.post("/api/projects/{project_id}/scenes/{scene_id}/shot-plan")
def plan_scene(project_id: str, scene_id: str):
    return run(lambda: studio.plan_scene(project_id, scene_id))


@app.put("/api/projects/{project_id}/scenes/{scene_id}/shots/{shot_id}")
def edit_shot(project_id: str, scene_id: str, shot_id: str, payload: ShotUpdate):
    return run(lambda: studio.edit_shot(project_id, scene_id, shot_id, **payload.model_dump()))


class NewCreativeDraft(BaseModel):
    stage: str
    content: str = Field(min_length=1, max_length=120000)
    instructions: str = Field(default="", max_length=5000)


class GenerateCreativeDraft(BaseModel):
    model_id: str | None = Field(default=None, max_length=256)
    model_port: int | None = Field(default=None, ge=1024, le=65535)
    stage: str
    instructions: str = Field(default="", max_length=5000)
    scene_id: str | None = None


class EditCreativeDraft(BaseModel):
    content: str = Field(min_length=1, max_length=120000)
    expected_edit_revision: int = Field(ge=0)


class DecideCreativeDraft(BaseModel):
    decision: str
    expected_project_revision: int = Field(ge=0)


@app.get("/api/creative/status")
def creative_status():
    try:
        configured = bool(local_llm_endpoint())
        detail = "configured_unverified" if configured else "not_configured"
    except ValueError:
        configured = False
        detail = "invalid_loopback_configuration"
    return {
        "stages": list(STAGES),
        "draft_storage": "ready",
        "local_writer": detail,
        "ai_model_bundled": False,
        "film_renderer_connected": False,
    }


@app.get("/api/creative/models")
def creative_models(port: int | None = None):
    return discover_models(port)


@app.get("/api/projects/{project_id}/creative/bible-context")
def creative_bible_context(project_id: str, scene_id: str | None = None):
    return run(lambda: IdeaPipeline(studio).bible_context(project_id, scene_id))


@app.get("/api/projects/{project_id}/approved-story")
def approved_story(project_id: str, stage: str):
    return {"stage": stage, "approved": run(lambda: IdeaPipeline(studio).approved_story(project_id, stage))}


@app.get("/api/projects/{project_id}/creative-drafts")
def list_creative_drafts(project_id: str):
    return run(lambda: IdeaPipeline(studio).list(project_id))


@app.post("/api/projects/{project_id}/creative-drafts", status_code=201)
def add_creative_draft(project_id: str, payload: NewCreativeDraft):
    return run(lambda: IdeaPipeline(studio).create(
        project_id, payload.stage, payload.content, payload.instructions))


@app.post("/api/projects/{project_id}/creative-drafts/generate", status_code=201)
def generate_creative_draft(project_id: str, payload: GenerateCreativeDraft):
    # The local server may be LM Studio or another OpenAI-compatible provider.
    # NVP observes its request duration, not model ownership/load %, RAM or VRAM.
    activity_id="ai_"+uuid.uuid4().hex
    resource_activity.observe_external(activity_id,
        "AI writing: "+str(payload.stage)[:65])
    try:
        resource_activity.update(activity_id,"processing_prompt",
            "Sending approved writing request to the separately managed AI server")
        result=run(lambda: IdeaPipeline(studio,
            llm=(writer_for(payload.model_id, payload.model_port) if payload.model_id else None)).generate(
                project_id, payload.stage, payload.instructions, payload.scene_id))
        resource_activity.finish(activity_id,"SUCCEEDED",
            "AI draft received; creator approval still required")
        return result
    except LocalModelUnavailable as error:
        resource_activity.finish(activity_id,"FAILED","Local AI server is unavailable")
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception:
        resource_activity.finish(activity_id,"FAILED","Writing task did not complete")
        raise


@app.put("/api/projects/{project_id}/creative-drafts/{draft_id}")
def edit_creative_draft(project_id: str, draft_id: str, payload: EditCreativeDraft):
    return run(lambda: IdeaPipeline(studio).edit(
        project_id, draft_id, payload.content, payload.expected_edit_revision))


@app.post("/api/projects/{project_id}/creative-drafts/{draft_id}/decision")
def decide_creative_draft(project_id: str, draft_id: str, payload: DecideCreativeDraft):
    return run(lambda: IdeaPipeline(studio).decide(
        project_id, draft_id, payload.decision, payload.expected_project_revision))


class RestoreScreenplay(BaseModel):
    expected_revision: int = Field(ge=0)


@app.get("/api/projects/{project_id}/screenplay-history")
def screenplay_history(project_id: str):
    return run(lambda: studio.screenplay_history(project_id))


@app.post("/api/projects/{project_id}/screenplay-history/{source_revision}/restore")
def restore_screenplay(project_id: str, source_revision: int, payload: RestoreScreenplay):
    return run(lambda: studio.restore_screenplay(
        project_id, source_revision, payload.expected_revision))


# Story Bible is a film-specific development service. The eventual product is
# an optional Lu DLC, but no Lu code is touched until Lu v1.0.
class BibleEntityCreate(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=3000)


class BibleRename(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    expected_revision: int = Field(ge=0)


class BibleAlias(BaseModel):
    alias: str = Field(min_length=1, max_length=150)
    expected_revision: int = Field(ge=0)


class BibleFactProposal(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default="global", max_length=96)
    origin: str = "creator"
    source_note: str = Field(default="", max_length=500)


class BibleFactDecision(BaseModel):
    decision: str
    expected_entity_revision: int = Field(ge=0)
    replaces_fact_id: str | None = None


class BibleSceneLink(BaseModel):
    scene_id: str
    expected_entity_revision: int = Field(ge=0)
    note: str = Field(default="", max_length=1000)


class BibleAcknowledge(BaseModel):
    expected_screenplay_revision: int = Field(ge=0)


@app.get("/api/projects/{project_id}/story-bible")
def story_bible(project_id: str):
    return run(lambda: {"entities": StoryBible(studio).list_entities(project_id),
                        "continuity": StoryBible(studio).report(project_id)})


@app.get("/api/projects/{project_id}/story-bible/continuity")
def story_bible_continuity(project_id: str):
    return run(lambda: StoryBible(studio).report(project_id))


@app.post("/api/projects/{project_id}/story-bible/entities", status_code=201)
def story_bible_create_entity(project_id: str, payload: BibleEntityCreate):
    return run(lambda: StoryBible(studio).create_entity(project_id, payload.kind,
                                                          payload.name, payload.description))


@app.put("/api/projects/{project_id}/story-bible/entities/{entity_id}/name")
def story_bible_rename(project_id: str, entity_id: str, payload: BibleRename):
    return run(lambda: StoryBible(studio).rename_entity(project_id, entity_id,
                                                        payload.name, payload.expected_revision))


@app.post("/api/projects/{project_id}/story-bible/entities/{entity_id}/aliases")
def story_bible_add_alias(project_id: str, entity_id: str, payload: BibleAlias):
    return run(lambda: StoryBible(studio).add_alias(project_id, entity_id,
                                                    payload.alias, payload.expected_revision))


@app.post("/api/projects/{project_id}/story-bible/entities/{entity_id}/facts", status_code=201)
def story_bible_propose_fact(project_id: str, entity_id: str, payload: BibleFactProposal):
    return run(lambda: StoryBible(studio).propose_fact(project_id, entity_id, payload.key,
               payload.value, payload.scope, payload.origin, payload.source_note))


@app.post("/api/projects/{project_id}/story-bible/facts/{fact_id}/decision")
def story_bible_decide_fact(project_id: str, fact_id: str, payload: BibleFactDecision):
    return run(lambda: StoryBible(studio).decide_fact(project_id, fact_id,
        payload.decision, payload.expected_entity_revision, payload.replaces_fact_id))


@app.post("/api/projects/{project_id}/story-bible/entities/{entity_id}/scene-links")
def story_bible_link_scene(project_id: str, entity_id: str, payload: BibleSceneLink):
    return run(lambda: StoryBible(studio).link_scene(project_id, entity_id,
        payload.scene_id, payload.expected_entity_revision, payload.note))


@app.post("/api/projects/{project_id}/story-bible/changes/{change_id}/acknowledge")
def story_bible_ack_change(project_id: str, change_id: str, payload: BibleAcknowledge):
    return run(lambda: StoryBible(studio).acknowledge_change(
        project_id, change_id, payload.expected_screenplay_revision))

# Chronology belongs to the NVP film domain, not Lu or the model runtime.
from backend.nvp_story_timeline import StoryTimeline


class TimelinePrecedence(BaseModel):
    before_id: str = Field(min_length=1, max_length=64)
    after_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=0)
    note: str = Field(default="", max_length=1000)


class TimelineSceneAnchor(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    phase: str
    expected_revision: int = Field(ge=0)
    note: str = Field(default="", max_length=1000)


class TimelineKnowledgeProposal(BaseModel):
    character_id: str = Field(min_length=1, max_length=64)
    fact_id: str = Field(min_length=1, max_length=64)
    learned_at_event_id: str | None = Field(default=None, max_length=64)
    source_note: str = Field(default="", max_length=1000)


class TimelineKnowledgeDecision(BaseModel):
    decision: str
    expected_revision: int = Field(ge=0)


@app.get("/api/projects/{project_id}/timeline")
def timeline_snapshot(project_id: str, scene_id: str | None = None):
    return run(lambda: StoryTimeline(studio).snapshot(project_id, scene_id))


@app.post("/api/projects/{project_id}/timeline/precedence")
def timeline_add_order(project_id: str, payload: TimelinePrecedence):
    return run(lambda: StoryTimeline(studio).add_precedence(
        project_id, payload.before_id, payload.after_id, payload.expected_revision, payload.note))


@app.post("/api/projects/{project_id}/timeline/precedence/remove")
def timeline_remove_order(project_id: str, payload: TimelinePrecedence):
    return run(lambda: StoryTimeline(studio).remove_precedence(
        project_id, payload.before_id, payload.after_id, payload.expected_revision))


@app.put("/api/projects/{project_id}/timeline/scenes/{scene_id}")
def timeline_bind_scene(project_id: str, scene_id: str, payload: TimelineSceneAnchor):
    return run(lambda: StoryTimeline(studio).bind_scene(
        project_id, scene_id, payload.event_id, payload.phase, payload.expected_revision, payload.note))


@app.delete("/api/projects/{project_id}/timeline/scenes/{scene_id}")
def timeline_unbind_scene(project_id: str, scene_id: str, expected_revision: int):
    return run(lambda: StoryTimeline(studio).unbind_scene(project_id, scene_id, expected_revision))


@app.post("/api/projects/{project_id}/timeline/knowledge", status_code=201)
def timeline_propose_knowledge(project_id: str, payload: TimelineKnowledgeProposal):
    return run(lambda: StoryTimeline(studio).propose_knowledge(
        project_id, payload.character_id, payload.fact_id, payload.learned_at_event_id,
        payload.source_note))


@app.post("/api/projects/{project_id}/timeline/knowledge/{claim_id}/decision")
def timeline_decide_knowledge(project_id: str, claim_id: str,
                              payload: TimelineKnowledgeDecision):
    return run(lambda: StoryTimeline(studio).decide_knowledge(
        project_id, claim_id, payload.decision, payload.expected_revision))

# WR06: Film-domain epistemic records only. A statement is not objective truth,
# and a continuity-review decision cannot silently rewrite the screenplay.
from backend.nvp_scene_mind import SceneMind

class SceneBeatCreate(BaseModel):
    scene_id: str = Field(min_length=1, max_length=64)
    line_number: int = Field(ge=1, le=1000000)
    label: str = Field(min_length=1, max_length=150)
    expected_revision: int = Field(ge=0)
    note: str = Field(default="", max_length=1000)

class SceneBeatReanchor(BaseModel):
    line_number: int = Field(ge=1, le=1000000)
    expected_revision: int = Field(ge=0)

class SceneMindChangeCreate(BaseModel):
    beat_id: str = Field(min_length=1, max_length=64)
    character_id: str = Field(min_length=1, max_length=64)
    fact_id: str = Field(min_length=1, max_length=64)
    mode: str
    belief_value: str | None = Field(default=None, max_length=2000)
    note: str = Field(default="", max_length=1000)

class SceneStatementCreate(BaseModel):
    beat_id: str = Field(min_length=1, max_length=64)
    speaker_id: str = Field(min_length=1, max_length=64)
    audience_id: str = Field(min_length=1, max_length=64)
    fact_id: str = Field(min_length=1, max_length=64)
    claimed_value: str = Field(min_length=1, max_length=2000)
    intent: str
    note: str = Field(default="", max_length=1000)

class MindDecision(BaseModel):
    decision: str
    expected_revision: int = Field(ge=0)

class SuggestionDecision(MindDecision):
    resolution: str = ""
    review_note: str = Field(default="", max_length=1000)

@app.get("/api/projects/{project_id}/scene-mind")
def scene_mind(project_id: str, scene_id: str | None = None,
               at_beat_id: str | None = None, phase: str = "before"):
    return run(lambda: SceneMind(studio).snapshot(project_id, scene_id, at_beat_id, phase))

@app.post("/api/projects/{project_id}/scene-mind/beats", status_code=201)
def scene_mind_create_beat(project_id: str, payload: SceneBeatCreate):
    return run(lambda: SceneMind(studio).add_beat(
        project_id, payload.scene_id, payload.line_number, payload.label,
        payload.expected_revision, payload.note))

@app.put("/api/projects/{project_id}/scene-mind/beats/{beat_id}")
def scene_mind_reanchor(project_id: str, beat_id: str, payload: SceneBeatReanchor):
    return run(lambda: SceneMind(studio).reanchor_beat(
        project_id, beat_id, payload.line_number, payload.expected_revision))

@app.post("/api/projects/{project_id}/scene-mind/changes", status_code=201)
def scene_mind_propose_change(project_id: str, payload: SceneMindChangeCreate):
    return run(lambda: SceneMind(studio).propose_change(
        project_id, payload.beat_id, payload.character_id, payload.fact_id,
        payload.mode, payload.belief_value, payload.note))

@app.post("/api/projects/{project_id}/scene-mind/changes/{change_id}/decision")
def scene_mind_decide_change(project_id: str, change_id: str, payload: MindDecision):
    return run(lambda: SceneMind(studio).decide_change(
        project_id, change_id, payload.decision, payload.expected_revision))

@app.post("/api/projects/{project_id}/scene-mind/statements", status_code=201)
def scene_mind_propose_statement(project_id: str, payload: SceneStatementCreate):
    return run(lambda: SceneMind(studio).propose_statement(
        project_id, payload.beat_id, payload.speaker_id, payload.audience_id,
        payload.fact_id, payload.claimed_value, payload.intent, payload.note))

@app.post("/api/projects/{project_id}/scene-mind/statements/{statement_id}/decision")
def scene_mind_decide_statement(project_id: str, statement_id: str, payload: MindDecision):
    return run(lambda: SceneMind(studio).decide_statement(
        project_id, statement_id, payload.decision, payload.expected_revision))

@app.get("/api/projects/{project_id}/scene-mind/scenes/{scene_id}/suggestions")
def scene_mind_suggestions(project_id: str, scene_id: str):
    return run(lambda: SceneMind(studio).suggestions(project_id, scene_id))

@app.post("/api/projects/{project_id}/scene-mind/scenes/{scene_id}/suggestions/{suggestion_id}/decision")
def scene_mind_decide_suggestion(project_id: str, scene_id: str, suggestion_id: str,
                                 payload: SuggestionDecision):
    return run(lambda: SceneMind(studio).decide_suggestion(
        project_id, scene_id, suggestion_id, payload.decision, payload.expected_revision,
        payload.resolution, payload.review_note))


class ScreenplayReviewDecision(BaseModel):
    decision: str
    expected_review_revision: int = Field(ge=0)
    expected_screenplay_revision: int = Field(ge=0)
    resolution: str = ""
    note: str = Field(default="", max_length=1200)


@app.get("/api/projects/{project_id}/screenplay-review/scenes/{scene_id}")
def screenplay_review_scene(project_id: str, scene_id: str):
    return run(lambda: ScreenplayContinuityReview(studio).report(project_id, scene_id))


@app.post("/api/projects/{project_id}/screenplay-review/scenes/{scene_id}/suggestions/{suggestion_id}/decision")
def screenplay_review_decision(project_id: str, scene_id: str, suggestion_id: str,
                               payload: ScreenplayReviewDecision):
    return run(lambda: ScreenplayContinuityReview(studio).decide(
        project_id, scene_id, suggestion_id, payload.decision,
        payload.expected_review_revision, payload.expected_screenplay_revision,
        payload.resolution, payload.note))


@app.get("/api/projects/{project_id}/screenplay-review/history")
def screenplay_review_history(project_id: str, scene_id: str | None = None, limit: int = 100):
    return run(lambda: ScreenplayContinuityReview(studio).history(project_id, scene_id, limit))

# NVP-PROD-01: development-only deterministic 3D staging. This API never runs
# Blender itself; it exports a reviewer-approved, self-contained bpy script.
from backend.nvp_production_scene import ProductionScene


class ProductionAssetInput(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str
    dimensions: list[float]
    anchors: dict[str, list[float]] = Field(default_factory=dict)
    license: str = Field(default="creator_procedural", max_length=200)


class ProductionStageInput(BaseModel):
    room: list[float] = Field(default_factory=lambda: [8, 6, 3])


class ProductionInstanceInput(BaseModel):
    asset_id: str
    instance_id: str
    expected_plan_revision: int = Field(ge=0)
    wall: str | None = None
    attachment: dict | None = None


class ProductionRevisionInput(BaseModel):
    expected_plan_revision: int = Field(ge=0)


class ProductionSolveInput(ProductionRevisionInput):
    max_nodes: int = Field(default=100000, ge=1, le=100000)


@app.get("/api/projects/{project_id}/production/assets")
def prod_list_assets(project_id: str):
    return run(lambda: ProductionScene(studio).list_assets(project_id))


@app.post("/api/projects/{project_id}/production/assets", status_code=201)
def prod_create_asset(project_id: str, payload: ProductionAssetInput):
    return run(lambda: ProductionScene(studio).create_asset(project_id, payload.model_dump()))


@app.post("/api/projects/{project_id}/production/scenes/{scene_id}/stage", status_code=201)
def prod_stage(project_id: str, scene_id: str, payload: ProductionStageInput):
    return run(lambda: ProductionScene(studio).stage_scene(project_id, scene_id, payload.room))


@app.get("/api/projects/{project_id}/production/scenes/{scene_id}")
def prod_get_scene(project_id: str, scene_id: str):
    return run(lambda: ProductionScene(studio).get_plan(project_id, scene_id))


@app.post("/api/projects/{project_id}/production/scenes/{scene_id}/resync")
def prod_resync_scene(project_id: str, scene_id: str, payload: ProductionRevisionInput):
    return run(lambda: ProductionScene(studio).resync_scene(project_id, scene_id, payload.expected_plan_revision))


@app.post("/api/projects/{project_id}/production/scenes/{scene_id}/instances")
def prod_add_instance(project_id: str, scene_id: str, payload: ProductionInstanceInput):
    return run(lambda: ProductionScene(studio).add_instance(
        project_id, scene_id, payload.asset_id, payload.instance_id, payload.expected_plan_revision,
        wall=payload.wall, attachment=payload.attachment))


@app.post("/api/projects/{project_id}/production/scenes/{scene_id}/solve")
def prod_solve(project_id: str, scene_id: str, payload: ProductionSolveInput):
    return run(lambda: ProductionScene(studio).solve_scene(
        project_id, scene_id, payload.expected_plan_revision, payload.max_nodes))


@app.post("/api/projects/{project_id}/production/scenes/{scene_id}/approve")
def prod_approve(project_id: str, scene_id: str, payload: ProductionRevisionInput):
    return run(lambda: ProductionScene(studio).approve_scene(project_id, scene_id, payload.expected_plan_revision))


@app.get("/api/projects/{project_id}/production/scenes/{scene_id}/manifest")
def prod_manifest(project_id: str, scene_id: str):
    return run(lambda: ProductionScene(studio).export_manifest(project_id, scene_id))


@app.get("/api/projects/{project_id}/production/scenes/{scene_id}/blender-script")
def prod_blender(project_id: str, scene_id: str):
    return {"script": run(lambda: ProductionScene(studio).export_blender_script(project_id, scene_id)),
            "execution": "not_started", "note": "Export only. Blender must be run separately by the creator."}


@app.get("/api/projects/{project_id}/production/scenes/{scene_id}/history")
def prod_history(project_id: str, scene_id: str):
    return run(lambda: ProductionScene(studio).history(project_id, scene_id))

# NVP-PROD-02/03/04 — narrow, project-scoped production operations.
# No route accepts model-generated Python or an arbitrary server filesystem path.
from typing import Any
from fastapi import Request
from backend.nvp_world_state import WorldState
from backend.nvp_mesh_assets import MeshAssets, MAX_GLB
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_blender_acceptance import blender_available


class WorldEditInput(BaseModel):
    instance_id: str = Field(min_length=1, max_length=64)
    field: str = Field(min_length=1, max_length=64)
    value: Any
    expected_revision: int = Field(ge=0)
    locked: bool = True


class WorldLockInput(BaseModel):
    instance_id: str
    field: str
    locked: bool
    expected_revision: int = Field(ge=0)


class WorldProposalInput(WorldEditInput):
    rationale: str = Field(default='', max_length=1000)


class WorldRevisionInput(BaseModel):
    expected_revision: int = Field(ge=0)


class WorldDecisionInput(WorldRevisionInput):
    decision: str


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/world')
def production_world(project_id: str, scene_id: str):
    return run(lambda: WorldState(studio).read(project_id, scene_id))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/world/human')
def production_world_edit(project_id: str, scene_id: str, payload: WorldEditInput):
    return run(lambda: WorldState(studio).set_human(
        project_id, scene_id, payload.instance_id, payload.field,
        payload.value, payload.expected_revision, lock=payload.locked))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/world/lock')
def production_world_lock(project_id: str, scene_id: str, payload: WorldLockInput):
    return run(lambda: WorldState(studio).set_lock(
        project_id, scene_id, payload.instance_id, payload.field,
        payload.locked, payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/world/proposals', status_code=201)
def production_world_proposal(project_id: str, scene_id: str, payload: WorldProposalInput):
    return run(lambda: WorldState(studio).propose_ai(
        project_id,scene_id,payload.instance_id,payload.field,payload.value,
        payload.expected_revision,payload.rationale))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/world/proposals/{proposal_id}/decision')
def production_world_decide(project_id: str, scene_id: str, proposal_id: str, payload: WorldDecisionInput):
    return run(lambda: WorldState(studio).decide(
        project_id,scene_id,proposal_id,payload.decision,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/world/undo')
def production_world_undo(project_id: str, scene_id: str, payload: WorldRevisionInput):
    return run(lambda: WorldState(studio).undo(project_id,scene_id,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/world/rebase')
def production_world_rebase(project_id: str, scene_id: str, payload: WorldRevisionInput):
    return run(lambda: WorldState(studio).rebase(project_id,scene_id,payload.expected_revision))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/world/history')
def production_world_history(project_id: str, scene_id: str):
    return run(lambda: WorldState(studio).journal(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/world/blender-script')
def production_world_blender(project_id: str, scene_id: str):
    return {'script':run(lambda: WorldState(studio).export_blender_script(project_id,scene_id)),
            'execution':'not_started','note':'Requires a real local Blender installation'}


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/render-preflight')
def production_render_preflight(project_id: str, scene_id: str):
    # Read-only scene/source proof. This API is not an authenticated native
    # execution endpoint and cannot mint creator approval or launch a worker.
    return run(lambda: preflight_scene(studio, project_id, scene_id))


@app.get('/api/production/blender-availability')
def production_blender_availability():
    return blender_available()


@app.get('/api/projects/{project_id}/production/meshes')
def production_list_meshes(project_id: str):
    return run(lambda: MeshAssets(studio).list(project_id))


@app.post('/api/projects/{project_id}/production/assets/{asset_id}/mesh', status_code=201)
async def production_attach_glb(project_id: str, asset_id: str, request: Request,
                                license_code: str, attribution: str = '', source: str = ''):
    # Streaming byte budget applies even without a Content-Length header.
    payload=bytearray()
    async for part in request.stream():
        payload.extend(part)
        if len(payload)>MAX_GLB:
            raise HTTPException(status_code=413,detail='GLB exceeds the 32 MiB import limit')
    return run(lambda: MeshAssets(studio).register(
        project_id,asset_id,bytes(payload),license_code,attribution,source))


class DialogueDurationInput(BaseModel):
    duration_s: float = Field(gt=0,le=300)
    origin: str = 'director_measured'
    audio_sha256: str | None = None


class DialogueListenersInput(BaseModel):
    listeners: list[str] = Field(max_length=12)


class BlockingMarkInput(BaseModel):
    actor_instance_id: str
    target_xy_m: list[float]
    target_instance_id: str | None = None
    anchor_name: str | None = None
    max_gap_m: float = Field(default=1.5,gt=0,le=3)
    start_s: float = Field(default=0,ge=0)
    end_s: float = Field(default=5,ge=0)
    action: str = 'walk'
    facing_instance_id: str | None = None


class CameraShotInput(BaseModel):
    subjects: list[str] = Field(min_length=1,max_length=3)
    lens_mm: float = Field(default=50,ge=18,le=135)
    shot_size: str = 'medium'
    desired_positions: list[list[float]] | None = None


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/dialogue')
def production_dialogue(project_id: str, scene_id: str):
    return run(lambda: BlockingCamera(studio).dialogue(project_id,scene_id))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/dialogue/{line_id}/duration')
def production_dialogue_duration(project_id: str, scene_id: str, line_id: str, payload: DialogueDurationInput):
    return run(lambda: BlockingCamera(studio).set_dialogue_duration(
        project_id,scene_id,line_id,payload.duration_s,payload.origin,payload.audio_sha256))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/dialogue/{line_id}/listeners')
def production_dialogue_listeners(project_id: str, scene_id: str, line_id: str, payload: DialogueListenersInput):
    return run(lambda: BlockingCamera(studio).set_listeners(project_id,scene_id,line_id,payload.listeners))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/blocking')
def production_blocking(project_id: str, scene_id: str):
    return run(lambda: BlockingCamera(studio).marks(project_id,scene_id))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/blocking', status_code=201)
def production_add_blocking(project_id: str, scene_id: str, payload: BlockingMarkInput):
    return run(lambda: BlockingCamera(studio).add_mark(
        project_id,scene_id,payload.actor_instance_id,payload.target_xy_m,
        target_instance_id=payload.target_instance_id,anchor_name=payload.anchor_name,
        max_gap=payload.max_gap_m,start_s=payload.start_s,end_s=payload.end_s,
        action=payload.action,facing_instance_id=payload.facing_instance_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/cameras')
def production_cameras(project_id: str, scene_id: str):
    return run(lambda: BlockingCamera(studio).cameras(project_id,scene_id))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/cameras', status_code=201)
def production_solve_camera(project_id: str, scene_id: str, payload: CameraShotInput):
    return run(lambda: BlockingCamera(studio).solve_shot(
        project_id,scene_id,payload.subjects,lens_mm=payload.lens_mm,
        shot_size=payload.shot_size,desired_positions=payload.desired_positions))

# DA-06: old fixed-rate proxy production is READ-ONLY history only.
# The new camera timeline is /film/native-time-shots, and native OS approval
# freezes exact-time OpenUSD Takes. Never publish new frame-authoritative
# captures, clips, or Blender proxy scripts from the active NVP API.
def _retired_fixed_frame_authoring():
    raise HTTPException(status_code=410,detail=(
        "Legacy frame-based proxy authoring retired. Use exact Film Time "
        "OpenUSD shot revisions and native Digital Take freeze."))

# NVP-PROD-05: author-controlled, frame-accurate shot sequences.
from backend.nvp_shot_sequence import ShotSequence


class TakeShotInput(BaseModel):
    camera_id: str
    frames: int = Field(ge=1, le=14400)
    pattern: str = 'single'
    expected_revision: int = Field(ge=0)


class TakeCueInput(BaseModel):
    start_frame: int = Field(ge=1, le=14400)
    expected_revision: int = Field(ge=0)


class TakeRevisionInput(BaseModel):
    expected_revision: int = Field(ge=0)


class TakeWarningsInput(TakeRevisionInput):
    codes: list[str] = Field(max_length=128)


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence', status_code=201)
def prod05_create(project_id: str, scene_id: str):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).create(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/sequence')
def prod05_read(project_id: str, scene_id: str):
    return run(lambda: ShotSequence(studio).read(project_id,scene_id))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/shots')
def prod05_append(project_id: str, scene_id: str, payload: TakeShotInput):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).add_shot(project_id,scene_id,
        payload.camera_id,payload.frames,payload.pattern,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/shots/pop')
def prod05_remove_last_shot(project_id: str, scene_id: str, payload: TakeRevisionInput):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).remove_last_shot(project_id,scene_id,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/cues/{line_id}')
def prod05_place_cue(project_id: str, scene_id: str, line_id: str, payload: TakeCueInput):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).place_cue(project_id,scene_id,
        line_id,payload.start_frame,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/cues/{line_id}/clear')
def prod05_clear_cue(project_id: str, scene_id: str, line_id: str, payload: TakeRevisionInput):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).clear_cue(project_id,scene_id,
        line_id,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/warnings/acknowledge')
def prod05_acknowledge(project_id: str, scene_id: str, payload: TakeWarningsInput):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).acknowledge(project_id,scene_id,
        payload.codes,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/approve')
def prod05_approve(project_id: str, scene_id: str, payload: TakeRevisionInput):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).approve(project_id,scene_id,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/revision')
def prod05_revision(project_id: str, scene_id: str, payload: TakeRevisionInput):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).new_revision(project_id,scene_id,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/reset')
def prod05_reset(project_id: str, scene_id: str, payload: TakeRevisionInput):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).reset_draft(project_id,scene_id,payload.expected_revision))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/history')
def prod05_history(project_id: str, scene_id: str):
    return run(lambda: ShotSequence(studio).history(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/package')
def prod05_package(project_id: str, scene_id: str):
    _retired_fixed_frame_authoring()
    return run(lambda: ShotSequence(studio).export(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/sequence/blender-script')
def prod05_blender_script(project_id: str, scene_id: str):
    _retired_fixed_frame_authoring()
    return {'script':run(lambda: ShotSequence(studio).blender_script(project_id,scene_id)),
            'language':'python','runtime':'Blender 5.2+ bpy'}

# NVP-PROD-06A: reusable offline BVH/author-keyed motion, approval-gated.
from backend.nvp_rig_motion import RigMotion


class RegisterBVHMotion(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    license: str = Field(min_length=1,max_length=100)
    bvh: str = Field(min_length=1,max_length=1000000)
    mapping: dict[str,str] = Field(min_length=1,max_length=7)


class RegisterAuthoredMotion(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    license: str = Field(min_length=1,max_length=100)
    fps: int = Field(default=24,ge=10,le=120)
    frames: list[dict] = Field(min_length=2,max_length=2400)


class AttachMotion(BaseModel):
    actor_instance_id: str
    clip_id: str
    start_frame: int = Field(ge=1,le=14400)
    expected_revision: int = Field(ge=0)


class ActorMotionRevision(BaseModel):
    actor_instance_id: str
    expected_revision: int = Field(ge=0)


@app.get('/api/projects/{project_id}/production/motion-clips')
def prod06_clips(project_id:str):
    return run(lambda:RigMotion(studio).clips(project_id))


@app.post('/api/projects/{project_id}/production/motion-clips/bvh', status_code=201)
def prod06_register_bvh(project_id:str,payload:RegisterBVHMotion):
    _retired_fixed_frame_authoring()
    return run(lambda:RigMotion(studio).register(project_id,payload.name,payload.license,
                      bvh=payload.bvh,mapping=payload.mapping))


@app.post('/api/projects/{project_id}/production/motion-clips/authored', status_code=201)
def prod06_register_authored(project_id:str,payload:RegisterAuthoredMotion):
    _retired_fixed_frame_authoring()
    return run(lambda:RigMotion(studio).register(project_id,payload.name,payload.license,
                      frames=payload.frames,fps=payload.fps))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/rig-motion',status_code=201)
def prod06_create(project_id:str,scene_id:str):
    _retired_fixed_frame_authoring()
    return run(lambda:RigMotion(studio).create(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/rig-motion')
def prod06_read(project_id:str,scene_id:str):
    return run(lambda:RigMotion(studio).read(project_id,scene_id))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/rig-motion/attach')
def prod06_attach(project_id:str,scene_id:str,payload:AttachMotion):
    _retired_fixed_frame_authoring()
    return run(lambda:RigMotion(studio).attach(project_id,scene_id,
        payload.actor_instance_id,payload.clip_id,payload.start_frame,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/rig-motion/clear')
def prod06_clear(project_id:str,scene_id:str,payload:ActorMotionRevision):
    _retired_fixed_frame_authoring()
    return run(lambda:RigMotion(studio).clear(project_id,scene_id,
        payload.actor_instance_id,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/rig-motion/approve')
def prod06_approve(project_id:str,scene_id:str,payload:TakeRevisionInput):
    _retired_fixed_frame_authoring()
    return run(lambda:RigMotion(studio).approve(project_id,scene_id,payload.expected_revision))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/rig-motion/history')
def prod06_history(project_id:str,scene_id:str):
    return run(lambda:RigMotion(studio).history(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/rig-motion/blender-script')
def prod06_blender(project_id:str,scene_id:str):
    _retired_fixed_frame_authoring()
    return {'script':run(lambda:RigMotion(studio).blender_script(project_id,scene_id)),
            'language':'python','runtime':'Blender 5.2+ bpy','rig':'humanoid_preview_v1'}

# NVP-PROD-06B: director-approved weighted preview skin and explicit neutral-pose offsets.
from backend.nvp_skinning import SkinnedPerformance


class SkinCalibration(BaseModel):
    actor_instance_id: str = Field(min_length=1,max_length=80)
    role: str = Field(min_length=1,max_length=20)
    source_neutral_deg: list[float] = Field(min_length=3,max_length=3)
    target_neutral_deg: list[float] = Field(min_length=3,max_length=3)
    expected_revision: int = Field(ge=0)


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/skinning',status_code=201)
def prod06b_skin_create(project_id:str,scene_id:str):
    return run(lambda:SkinnedPerformance(studio).create(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/skinning')
def prod06b_skin_read(project_id:str,scene_id:str):
    return run(lambda:SkinnedPerformance(studio).read(project_id,scene_id))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/skinning/calibrate')
def prod06b_skin_calibrate(project_id:str,scene_id:str,payload:SkinCalibration):
    return run(lambda:SkinnedPerformance(studio).calibrate(project_id,scene_id,
           payload.actor_instance_id,payload.role,payload.source_neutral_deg,
           payload.target_neutral_deg,payload.expected_revision))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/skinning/approve')
def prod06b_skin_approve(project_id:str,scene_id:str,payload:TakeRevisionInput):
    return run(lambda:SkinnedPerformance(studio).approve(project_id,scene_id,payload.expected_revision))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/skinning/history')
def prod06b_skin_history(project_id:str,scene_id:str):
    return run(lambda:SkinnedPerformance(studio).history(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/skinning/blender-script')
def prod06b_skin_blender(project_id:str,scene_id:str):
    return {'script':run(lambda:SkinnedPerformance(studio).blender_script(project_id,scene_id)),
            'language':'python','runtime':'Blender 5.2+ bpy',
            'skin':'segmented_weighted_preview_v1'}

# NVP-PROD-06C — project-scoped, local-only rigged GLB import and approved retarget.
# This is a development harness; no Lu runtime or cloud services are invoked.
from backend.nvp_character_assets import CharacterAssets, MAX_GLB_BYTES
from fastapi.responses import Response
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
from io import BytesIO
from pathlib import Path


class CharacterBindingInput(BaseModel):
    actor_instance_id: str = Field(min_length=1,max_length=80)
    character_asset_id: str = Field(min_length=1,max_length=80)
    role_map: dict[str,str]
    expected_revision: int = Field(ge=0)
    uniform_scale: float = Field(default=1.0,gt=0,le=10)


@app.get('/api/projects/{project_id}/production/rigged-characters')
def prod06c_characters(project_id:str):
    return run(lambda: CharacterAssets(studio).list(project_id))


@app.post('/api/projects/{project_id}/production/rigged-characters',status_code=201)
async def prod06c_import_character(project_id:str,request:Request,
                                    license_code:str,attribution:str='',source:str=''):
    data=bytearray()
    async for part in request.stream():
        if len(data)+len(part)>MAX_GLB_BYTES:
            raise HTTPException(status_code=413,detail='Rigged character GLB exceeds 32 MiB')
        data.extend(part)
    return run(lambda:CharacterAssets(studio).register(
        project_id,bytes(data),license_code,attribution,source))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/rigged-characters',status_code=201)
def prod06c_create(project_id:str,scene_id:str):
    return run(lambda:CharacterAssets(studio).create(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/rigged-characters')
def prod06c_read(project_id:str,scene_id:str):
    return run(lambda:CharacterAssets(studio).read(project_id,scene_id))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/rigged-characters/bind')
def prod06c_bind(project_id:str,scene_id:str,payload:CharacterBindingInput):
    return run(lambda:CharacterAssets(studio).bind(project_id,scene_id,
           payload.actor_instance_id,payload.character_asset_id,payload.role_map,
           payload.expected_revision,payload.uniform_scale))


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/rigged-characters/approve')
def prod06c_approve(project_id:str,scene_id:str,payload:TakeRevisionInput):
    return run(lambda:CharacterAssets(studio).approve(project_id,scene_id,payload.expected_revision))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/rigged-characters/history')
def prod06c_history(project_id:str,scene_id:str):
    return run(lambda:CharacterAssets(studio).history(project_id,scene_id))


@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/rigged-characters/bundle')
def prod06c_bundle(project_id:str,scene_id:str):
    def build():
        with TemporaryDirectory(prefix='nvp_char_bundle_') as directory:
            folder=Path(directory)
            CharacterAssets(studio).export_bundle(project_id,scene_id,folder)
            stream=BytesIO()
            with ZipFile(stream,'w',ZIP_DEFLATED) as archive:
                for path in sorted(folder.rglob('*')):
                    if path.is_file():archive.write(path,path.relative_to(folder))
            return stream.getvalue()
    payload=run(build)
    return Response(payload,media_type='application/zip',headers={
        'Content-Disposition':f'attachment; filename="nvp_{scene_id}_rigged_characters.zip"',
        'Cache-Control':'no-store'})

# NVP-PROD-06D — immutable scene-scoped retarget calibration and native handoff.
from backend.nvp_retarget import RetargetCalibration, DEFAULT_LIMITS

class RetargetConfigurationInput(BaseModel):
    actor_instance_id: str = Field(min_length=1,max_length=80)
    expected_revision: int = Field(ge=0)
    joint_limits_deg: dict[str,float]
    contact_frames: list[int] = Field(min_length=1,max_length=32)
    contact_tolerance_m: float = Field(ge=0,le=0.5)
    max_ground_penetration_m: float = Field(ge=0,le=0.25)


@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/retarget',status_code=201)
def prod06d_create(project_id:str,scene_id:str):
    return run(lambda:RetargetCalibration(studio).create(project_id,scene_id))

@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/retarget')
def prod06d_read(project_id:str,scene_id:str):
    return run(lambda:RetargetCalibration(studio).read(project_id,scene_id))

@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/retarget/configure')
def prod06d_configure(project_id:str,scene_id:str,payload:RetargetConfigurationInput):
    return run(lambda:RetargetCalibration(studio).configure(
        project_id,scene_id,payload.actor_instance_id,payload.expected_revision,
        joint_limits_deg=payload.joint_limits_deg,contact_frames=payload.contact_frames,
        contact_tolerance_m=payload.contact_tolerance_m,
        max_ground_penetration_m=payload.max_ground_penetration_m))

@app.post('/api/projects/{project_id}/production/scenes/{scene_id}/retarget/approve')
def prod06d_approve(project_id:str,scene_id:str,payload:TakeRevisionInput):
    return run(lambda:RetargetCalibration(studio).approve(project_id,scene_id,payload.expected_revision))

@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/retarget/history')
def prod06d_history(project_id:str,scene_id:str):
    return run(lambda:RetargetCalibration(studio).history(project_id,scene_id))

@app.get('/api/projects/{project_id}/production/scenes/{scene_id}/retarget/bundle')
def prod06d_bundle(project_id:str,scene_id:str):
    def build():
        with TemporaryDirectory(prefix='nvp_retarget_bundle_') as directory:
            root=Path(directory)
            RetargetCalibration(studio).export_bundle(project_id,scene_id,root)
            buffer=BytesIO()
            with ZipFile(buffer,'w',ZIP_DEFLATED) as z:
                for file in sorted(root.rglob('*')):
                    if file.is_file():z.write(file,file.relative_to(root))
            return buffer.getvalue()
    return Response(run(build),media_type='application/zip',headers={
        'Content-Disposition':f'attachment; filename="nvp_{scene_id}_retarget_calibration.zip"',
        'Cache-Control':'no-store'})


# DA-06: Retire the old color subsystem only from the ACTIVE API. Its
# original indexed film data and previous revisions are preserved, but no
# frame-based EXR decode, old presentation export, external subprocess,
# codec discovery or FFmpeg-bound grading task is permitted to execute.
# Native data-first source grade controls are implemented separately.
def _retired_frame_color():
    raise HTTPException(status_code=410,detail=(
        "Frame-based color preview/mastering was retired by DA-06. "
        "Use the native OpenUSD presentation and data-first color controls."))

# NVP-GRADE-UI-01 — project-scoped, non-destructive grade version history.
# These endpoints do NOT approve a creative grade or export a final master.
from typing import Any as _GradeAny
from fastapi import Query as _GradeQuery
# Retired old EXR/frame-bound codec dependency: from_backend.nvp_grade_workspace import GradeWorkspace
# Retired old EXR/frame-bound codec dependency: from_backend.nvp_color_mastering import grade_recipe, validate_grade

class GradeWorkspaceSaveInput(BaseModel):
    source_exr_id: str = Field(min_length=1,max_length=80)
    grade_id: str = Field(min_length=1,max_length=80)
    expected_revision: int = Field(ge=0)
    source_primaries_declared: bool = False
    recipe: dict[str,_GradeAny]

@app.get('/api/projects/{project_id}/color-grading/sources')
def color_grade_sources(project_id:str):
    _retired_frame_color()
    return run(lambda:GradeWorkspace(studio).sources(project_id))

@app.get('/api/projects/{project_id}/color-grading/grades')
def color_grade_list(project_id:str,source_id:str|None=None):
    _retired_frame_color()
    return run(lambda:GradeWorkspace(studio).list_grades(project_id,source_id))

@app.post('/api/projects/{project_id}/color-grading/grades',status_code=201)
def color_grade_save(project_id:str,payload:GradeWorkspaceSaveInput):
    _retired_frame_color()
    if payload.source_primaries_declared is not True:
        raise HTTPException(status_code=422,detail='Confirm the source EXR color primaries declaration before saving a grade')
    return run(lambda:GradeWorkspace(studio).save(
        project_id,payload.source_exr_id,payload.grade_id,
        validate_grade(payload.recipe),payload.expected_revision))

@app.get('/api/projects/{project_id}/color-grading/grades/{grade_id}')
def color_grade_read(project_id:str,grade_id:str,revision:int|None=None):
    _retired_frame_color()
    record=run(lambda:GradeWorkspace(studio).reopen(project_id,grade_id,revision))
    return {'id':grade_id,'revision':record['record']['revision'],
            'source_exr_id':record['record']['data']['source_exr_id'],
            'recipe':record['recipe'],
            'sha256':record['record']['document_sha256'],
            'approval':'not_approved'}

@app.get('/api/projects/{project_id}/color-grading/grades/{grade_id}/history')
def color_grade_history(project_id:str,grade_id:str):
    _retired_frame_color()
    return run(lambda:GradeWorkspace(studio).history(project_id,grade_id))

@app.get('/api/projects/{project_id}/color-grading/sources/{source_id}/preview')
def color_grade_preview(
    project_id:str,source_id:str,
    frame:int=_GradeQuery(ge=1,le=48),
    mode:str=_GradeQuery(pattern='^(before|after)$'),
    exposure_stops:float=_GradeQuery(default=0.0,ge=-4,le=4),
    contrast:float=_GradeQuery(default=1.0,ge=0.5,le=2),
    saturation:float=_GradeQuery(default=1.0,ge=0,le=2),
    red_gain:float=_GradeQuery(default=1.0,ge=0.7,le=1.3),
    green_gain:float=_GradeQuery(default=1.0,ge=0.7,le=1.3),
    blue_gain:float=_GradeQuery(default=1.0,ge=0.7,le=1.3),
):
    _retired_frame_color()
    recipe=run(lambda:grade_recipe(
        **({} if mode=='before' else {
            'exposure_stops':exposure_stops,'contrast':contrast,'saturation':saturation,
            'red_gain':red_gain,'green_gain':green_gain,'blue_gain':blue_gain,
        })))
    result=run(lambda:GradeWorkspace(studio).preview(project_id,source_id,frame,recipe))
    return Response(result['bytes'],media_type='image/png',headers={
        'Cache-Control':'no-store, private',
        'X-NVP-Preview-Quality':'uncalibrated-display-preview-not-master',
        'X-NVP-Source-Frame':str(result['source_frame']),
    })


# GRADE-UI-02A — source-shot anchored advanced looks, measured post-ACES
# scopes and exact per-shot RGB preview, all without creative approval.
# Retired old EXR/frame-bound codec dependency: from_backend.nvp_grade_advanced import (

class AdvancedGradeSaveInput(BaseModel):
    source_id: str = Field(min_length=1,max_length=80)
    grade_id: str = Field(min_length=1,max_length=80)
    expected_revision: int = Field(ge=0)
    source_primaries_declared: bool = False
    plan: dict[str,_GradeAny]

class AdvancedGradePreviewInput(BaseModel):
    source_id: str = Field(min_length=1,max_length=80)
    frame: int = Field(ge=1,le=48)
    plan: dict[str,_GradeAny]

@app.get('/api/projects/{project_id}/color-grading/advanced/shots')
def grade_advanced_shots(project_id:str, source_id:str):
    _retired_frame_color()
    return run(lambda:AdvancedGradeWorkspace(studio).timeline(project_id,source_id))

@app.post('/api/projects/{project_id}/color-grading/advanced/grades',status_code=201)
def grade_advanced_save(project_id:str, payload:AdvancedGradeSaveInput):
    _retired_frame_color()
    if payload.source_primaries_declared is not True:
        raise HTTPException(status_code=422,detail='Declare the actual scene-linear EXR source primaries before saving a shot look')
    return run(lambda:AdvancedGradeWorkspace(studio).save_advanced(
        project_id,payload.source_id,payload.grade_id,payload.plan,payload.expected_revision))

@app.get('/api/projects/{project_id}/color-grading/advanced/grades/{grade_id}')
def grade_advanced_read(project_id:str,grade_id:str,revision:int|None=None):
    _retired_frame_color()
    result=run(lambda:AdvancedGradeWorkspace(studio).reopen_advanced(project_id,grade_id,revision))
    return {
        'id':grade_id,'revision':result['record']['revision'],
        'sha256':result['record']['document_sha256'],
        'source_id':result['record']['data']['source_id'],
        'plan':result['plan'],'timeline':result['timeline'],
        'approval':'not_approved',
    }

@app.post('/api/projects/{project_id}/color-grading/advanced/preview')
def grade_advanced_preview(project_id:str,payload:AdvancedGradePreviewInput):
    _retired_frame_color()
    return run(lambda:AdvancedGradeWorkspace(studio).render_scope_preview(
        project_id,payload.source_id,payload.frame,payload.plan))


# GRADE-UI-02B1: source-linked HDR EV tone curves and non-applying reference advice.
# Retired old EXR/frame-bound codec dependency: from_backend.nvp_grade_curves import CurveGradeWorkspace

class CurvePreviewInput(BaseModel):
    source_id: str = Field(min_length=1,max_length=80)
    frame: int = Field(ge=1,le=48)
    plan: dict[str,_GradeAny]

class CurveSaveInput(BaseModel):
    source_id: str = Field(min_length=1,max_length=80)
    grade_id: str = Field(min_length=1,max_length=80)
    expected_revision: int = Field(ge=0)
    source_primaries_declared: bool = False
    plan: dict[str,_GradeAny]

class MatchReferenceInput(BaseModel):
    source_id: str = Field(min_length=1,max_length=80)
    target_frame: int = Field(ge=1,le=48)
    reference_frame: int = Field(ge=1,le=48)
    base_plan: dict[str,_GradeAny]

@app.post('/api/projects/{project_id}/color-grading/curves/preview')
def grade_curve_preview(project_id:str,payload:CurvePreviewInput):
    _retired_frame_color()
    return run(lambda:CurveGradeWorkspace(studio).render_curve_preview(
        project_id,payload.source_id,payload.frame,payload.plan))

@app.post('/api/projects/{project_id}/color-grading/curves/reference-suggestion')
def grade_curve_reference(project_id:str,payload:MatchReferenceInput):
    _retired_frame_color()
    return run(lambda:CurveGradeWorkspace(studio).compare_reference(
        project_id,payload.source_id,payload.target_frame,
        payload.reference_frame,payload.base_plan))

@app.post('/api/projects/{project_id}/color-grading/curves/grades',status_code=201)
def grade_curve_save(project_id:str,payload:CurveSaveInput):
    _retired_frame_color()
    if payload.source_primaries_declared is not True:
        raise HTTPException(status_code=422,detail='Declare the original source EXR primaries before saving a curve draft')
    return run(lambda:CurveGradeWorkspace(studio).save_curve(
        project_id,payload.source_id,payload.grade_id,
        payload.plan,payload.expected_revision))

@app.get('/api/projects/{project_id}/color-grading/curves/grades/{grade_id}')
def grade_curve_reopen(project_id:str,grade_id:str,revision:int|None=None):
    _retired_frame_color()
    row=run(lambda:CurveGradeWorkspace(studio).reopen_curve(
        project_id,grade_id,revision))
    return {'id':grade_id,'revision':row['record']['revision'],
            'sha256':row['record']['document_sha256'],
            'source_id':row['record']['data']['source_id'],
            'plan':row['plan'],'approval':'not_approved'}


# SLATE-08: READ-ONLY versioned OpenUSD source camera discovery/selection.
# No browser-visible approval, render launch, Take commit or arbitrary path route.
from fastapi import Query as _FilmCameraQuery
from backend.nvp_film_index import FilmIndex as _FilmCameraIndex
from backend.nvp_slate08_desktop_read import FilmCameraReadBridge as _FilmCameraReadBridge

@app.get('/api/projects/{project_id}/film/camera-scenes')
def film_camera_source_list(project_id: str):
    return run(lambda: _FilmCameraReadBridge(_FilmCameraIndex(studio)).scenes(project_id))

@app.get('/api/projects/{project_id}/film/camera-scenes/{scene_id}/snapshot')
def film_camera_source_snapshot(
    project_id: str, scene_id: str,
    revision: int = _FilmCameraQuery(ge=1, le=1000000),
    source_tick: int = _FilmCameraQuery(ge=0, le=1000000000),
    camera_path: str = _FilmCameraQuery(min_length=1, max_length=240),
):
    return run(lambda: _FilmCameraReadBridge(_FilmCameraIndex(studio)).snapshot(
        project_id,scene_id,revision,tick=source_tick,camera_path=camera_path))

# DA-01 — New native scene authoring is exact Film Time, never 24 fps.
# This is an EDITORIAL source-revision writer, not an implicit Digital Take
# freeze or approved final 2D presentation. Frozen Take approval is available
# exclusively through the trusted native desktop bridge.
from backend.nvp_exact_time_shots import ExactTimeShotSequence as _NativeShots

class NativeTimeShot(BaseModel):
    shot_id: str = Field(min_length=1,max_length=80)
    camera_path: str = Field(min_length=1,max_length=240)
    start_tick: str = Field(min_length=1,max_length=20)
    end_tick: str = Field(min_length=1,max_length=20)
    pattern: str = Field(min_length=1,max_length=40)

class NativeTimeShotRevision(BaseModel):
    scene_id: str = Field(min_length=1,max_length=80)
    scene_revision: int = Field(ge=1,le=1000000)
    expected_revision: int = Field(ge=0,le=1000000)
    duration_tick: str = Field(min_length=1,max_length=20)
    shots: list[NativeTimeShot] = Field(min_length=1,max_length=128)

@app.post('/api/projects/{project_id}/film/native-time-shots/{timeline_id}')
def native_time_shots_publish(project_id: str,timeline_id: str,
                              payload: NativeTimeShotRevision):
    return run(lambda:_NativeShots(_FilmCameraIndex(studio)).publish(
        project_id,timeline_id,
        scene_id=payload.scene_id,
        scene_revision=payload.scene_revision,
        expected_revision=payload.expected_revision,
        duration_tick=payload.duration_tick,
        shots=[s.model_dump() for s in payload.shots]))

@app.get('/api/projects/{project_id}/film/native-time-shots/{timeline_id}')
def native_time_shots_read(project_id: str,timeline_id: str,
                           revision: int|None = _FilmCameraQuery(default=None,ge=1,le=1000000)):
    def resolved():
        index=_FilmCameraIndex(studio)
        target=revision if revision is not None else index.read_revision(
            project_id,timeline_id)["revision"]
        return _NativeShots(index).read(project_id,timeline_id,target)
    return run(resolved)

# DA-06 — color grading is structured non-destructive source/presentation
# data. Old fixed-frame EXR/MOV grading APIs above are deliberately 410.
from backend.nvp_native_color_decisions import NativeColorDecisions as _NativeColor

class NativeColorPlanInput(BaseModel):
    take_id: str = Field(min_length=1,max_length=80)
    take_sha256: str = Field(min_length=64,max_length=64)
    expected_revision: int = Field(ge=0,le=1000000)
    parameters: dict[str,float]

@app.post('/api/projects/{project_id}/film/native-color/{grade_id}')
def native_color_publish(project_id:str,grade_id:str,
                         payload:NativeColorPlanInput):
    return run(lambda:_NativeColor(_FilmCameraIndex(studio)).publish(
        project_id,grade_id,take_id=payload.take_id,
        take_sha256=payload.take_sha256,
        expected_revision=payload.expected_revision,
        parameters=payload.parameters))

@app.get('/api/projects/{project_id}/film/native-color/{grade_id}')
def native_color_read(project_id:str,grade_id:str,
                      revision:int|None=_FilmCameraQuery(default=None,ge=1,le=1000000)):
    return run(lambda:_NativeColor(_FilmCameraIndex(studio)).read(
        project_id,grade_id,revision))

# G06 director-only film workspace. Separate route component reuses all G03
# project access checks, and does not introduce a technical UI.
from backend.nvp_g06_routes import mount_g06_routes
mount_g06_routes(app,studio,live_films,COOKIE)

# G07 editor is a separate director-facing Post-Production workspace. These
# routes retain G03 host project/key checks and do not authorize rendering.
from backend.nvp_g07_routes import mount_g07_routes
mount_g07_routes(app,studio,live_films,COOKIE)

# G08 first-party export route and OS-custodied worker manager. Fixed
# software renderer/AVI container is not a legacy FFmpeg/ProRes pipeline.
from backend.nvp_g08_routes import mount_g08_routes
_g08_controller=mount_g08_routes(app,studio,film_access,live_films,COOKIE)

# G09-A production looks live in the same director-reviewed film project,
# not a separate technical tool or Blender authorization endpoint.
from backend.nvp_g09_routes import mount_g09_routes
mount_g09_routes(app,studio,live_films,COOKIE)

# G09-B director-driven actor performances; ActorID, original voice and
# non-destructive animation share the existing G03 unlock/session boundary.
from backend.nvp_g09_actor_routes import mount_g09_actor_routes
mount_g09_actor_routes(app,studio,live_films,COOKIE)

# G09-C source-time spatial picture and authentic original-sound playback,
# guarded by the existing G03 project unlock and director-session middleware.
from backend.nvp_g09c_routes import mount_g09c_routes
mount_g09c_routes(app,studio,live_films,COOKIE)
