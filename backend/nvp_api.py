"""Truthful local NVP planning API and optional local screenplay-writing proposals."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from backend.nvp_studio import Studio
from backend.nvp_screenplay_review import ScreenplayContinuityReview
from backend.nvp_story_bible import StoryBible
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
                             "3d_renderer": "not_connected", "voice": "not_connected",
                             "3d_stage_planning": "deterministic_proxies_ready",
                             "blender_export": "bpy_script_only_not_executed"}}


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
