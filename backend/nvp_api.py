"""Truthful local NVP planning API and optional local screenplay-writing proposals."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from backend.nvp_studio import Studio
from backend.nvp_idea_pipeline import IdeaPipeline, LocalModelUnavailable, STAGES, local_llm_endpoint
from backend.nvp_model_service import discover_models, writer_for

app = FastAPI(title="NVP — Your movie, your way", version="0.3.0-creative-foundation")
studio = Studio()


class NewProject(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    idea: str = Field(default="", max_length=10000)


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
                             "3d_renderer": "not_connected", "voice": "not_connected"}}


@app.get("/api/projects")
def projects():
    return studio.list_projects()


@app.post("/api/projects", status_code=201)
def create_project(payload: NewProject):
    return run(lambda: studio.create_project(payload.title, payload.idea))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return run(lambda: studio.get_project(project_id))


@app.put("/api/projects/{project_id}/screenplay")
def save_screenplay(project_id: str, payload: ScreenplayUpdate):
    return run(lambda: studio.save_screenplay(project_id, payload.screenplay, payload.expected_revision))


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
    try:
        return run(lambda: IdeaPipeline(studio, llm=(writer_for(payload.model_id, payload.model_port) if payload.model_id else None)).generate(
            project_id, payload.stage, payload.instructions, payload.scene_id))
    except LocalModelUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


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
