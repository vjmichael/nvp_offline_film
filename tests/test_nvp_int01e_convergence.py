"""INT-01E source/authority convergence negatives, NOT installed acceptance.

The filmmaker GUI must not silently route unsupported creative generation to
LM Studio/OpenAI-compatible ports or a second model process. Manual sources
remain operational, while G06/G07 original Take checks continue separately.
"""
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
import pytest

from backend.nvp_int01e_lu_policy import refuse_unported_lu_operation
from backend.nvp_g06_routes import mount_g06_routes
from backend.nvp_g07_routes import mount_g07_routes


@pytest.mark.parametrize("op",[
    "creative_draft","scene_ideas","scene_objects",
    "performance_notes","editorial_ideas"])
def test_unported_native_lu_operation_fails_closed(op):
    with pytest.raises(HTTPException) as e:
        refuse_unported_lu_operation(op)
    assert e.value.status_code==503
    assert "Lu Workspace" in e.value.detail
    assert "independent model backend" in e.value.detail


def test_unknown_operation_cannot_be_claimed_ready():
    with pytest.raises(ValueError,match="Unknown"):
        refuse_unported_lu_operation("load_a_second_gguf")


def test_g06_hosted_performance_generation_never_contacts_old_writer():
    app=FastAPI()
    with patch("backend.nvp_g06_routes.G06Filming") as filming:
        mount_g06_routes(app,object(),lambda:None,"nvp_film_access")
        route=next(x for x in app.routes
            if getattr(x,"path",None)==
                "/api/projects/{project_id}/film/scene/{scene_id}/notes/suggest")
        with pytest.raises(HTTPException) as raised:
            route.endpoint("a"*32,"SC_test",None,None)
    assert raised.value.status_code==503
    filming.assert_not_called()


def test_g07_editorial_generation_never_constructs_model_service():
    app=FastAPI()
    with patch("backend.nvp_g07_routes.G07Editor") as editor:
        mount_g07_routes(app,object(),lambda:None,"nvp_film_access")
        route=next(x for x in app.routes
            if getattr(x,"path",None)==
                "/api/projects/{project_id}/edit/ideas")
        with pytest.raises(HTTPException) as raised:
            route.endpoint("a"*32,None,None)
    assert raised.value.status_code==503
    editor.assert_not_called()


def test_unported_g04_g05_and_legacy_drafts_do_not_invoke_model():
    from backend import nvp_api as api
    with patch("backend.nvp_model_service.writer_for",
               side_effect=AssertionError("Second model backend called")) as writer:
        for invoke in (
            lambda:api.g04_ask_ai("a"*32,"SC_test",None),
            lambda:api.g05_stage_ai_ideas("a"*32,"SC_test",None),
            lambda:api.generate_creative_draft("a"*32,None),
        ):
            with pytest.raises(HTTPException) as raised:
                invoke()
            assert raised.value.status_code==503
        writer.assert_not_called()
    details=api.creative_models()
    assert details["state"]=="unavailable"
    assert details["models"]==[]
    assert details["model_loading_authorized"] is False
    assert details["source"]=="lu-native-workspace-required"


def test_int01e_native_installed_import_probe_is_a_separate_opt_in_role():
    from tools.nvp_desktop_alpha import main
    with patch("sys.argv",["NVP","--int01e-source-selfcheck"]):
        # This is source-only: never claim an installed Windows/Linux result.
        result=main()
    assert result==0
