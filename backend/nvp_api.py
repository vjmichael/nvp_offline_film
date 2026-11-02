"""Truthful local NVP planning API. Film rendering and AI are not connected yet."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from backend.nvp_studio import Studio

app = FastAPI(title="NVP — Your movie, your way", version="0.2.0-foundation")
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
