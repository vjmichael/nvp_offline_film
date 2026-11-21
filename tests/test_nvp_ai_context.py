"""Regression checks for the internal NVP-AI-02 read-only context layer."""
import pytest

from backend.nvp_ai_context import assemble_task_context, discover_capabilities
from backend.nvp_studio import Studio


def _studio(tmp_path):
    studio = Studio(tmp_path / "film.sqlite3")
    project = studio.create_project("Test film", "One-room test")
    script = "INT. ROOM - DAY\n\nADA\nHello.\n\nEXT. STREET - NIGHT\n\nBOB\nGoodbye."
    project = studio.save_screenplay(project["id"], script, project["revision"])
    return studio, project


def test_discovery_never_grants_execution():
    discovered = discover_capabilities()
    assert discovered["authorization_provided"] is False
    assert all(c["effect"] == "read" for c in discovered["capabilities"])
    assert all(c["executable_by_model"] is False for c in discovered["capabilities"])
    assert all(c["requires_host_authorization"] for c in discovered["capabilities"])


def test_context_pins_source_and_limits_excerpt(tmp_path):
    studio, project = _studio(tmp_path)
    context = assemble_task_context(
        studio, project["id"], project["revision"], "screenplay_review", max_lines=2
    )
    assert context["proposal_only"] is True
    assert context["side_effects_performed"] is False
    assert context["source"]["returned_end_line"] == 2
    assert context["source"]["next_line"] == 3
    assert len(context["scene_manifest"]) == 2
    assert context["source_sha256"] == context["source"]["source_sha256"]


def test_scene_context_only_includes_selected_lines(tmp_path):
    studio, project = _studio(tmp_path)
    scene = project["scenes"][1]
    packet = assemble_task_context(
        studio, project["id"], project["revision"], "scene_coverage",
        scene_id=scene["id"],
    )
    assert packet["selected_scene"]["id"] == scene["id"]
    assert packet["source"]["returned_start_line"] == scene["start_line"]
    assert packet["source"]["scene_id"] == scene["id"]
    assert packet["shots"] == []


def test_stale_revision_fails_closed(tmp_path):
    studio, project = _studio(tmp_path)
    old_rev = project["revision"]
    studio.save_screenplay(project["id"], "INT. ROOM - NIGHT\nChanged.", old_rev)
    with pytest.raises(RuntimeError, match="changed"):
        assemble_task_context(studio, project["id"], old_rev, "screenplay_review")


def test_invalid_task_and_missing_scene_fail_closed(tmp_path):
    studio, project = _studio(tmp_path)
    with pytest.raises(ValueError, match="Unsupported"):
        assemble_task_context(studio, project["id"], project["revision"], "render_movie")
    with pytest.raises(ValueError, match="selected scene"):
        assemble_task_context(studio, project["id"], project["revision"], "shot_review")
    with pytest.raises(KeyError):
        assemble_task_context(
            studio, project["id"], project["revision"], "scene_coverage",
            scene_id="SC_nonexistent",
        )
