"""NVP-AI-03 trusted read boundary: no model-supplied authority or side effects."""
import hashlib
import json

import pytest

from backend.nvp_ai_read_host import NativeAiReadHost, TrustedReadScope
from backend.nvp_studio import Studio


def fixture(tmp_path):
    studio = Studio(tmp_path / "studio.sqlite3")
    project = studio.create_project("Authorized film", "Local test")
    project = studio.save_screenplay(
        project["id"], "INT. ROOM - DAY\n\nADA\nHello.", project["revision"]
    )
    scope = TrustedReadScope("creator_1", project["id"], "turn_1")
    request = {
        "capability_id": "nvp.context.assemble.v1",
        "project_id": project["id"],
        "source_revision": project["revision"],
        "task": "screenplay_review",
        "max_lines": 2,
    }
    return studio, project, scope, request


def test_denied_policy_blocks_before_read(tmp_path):
    studio, project, scope, request = fixture(tmp_path)
    calls = []
    host = NativeAiReadHost(
        studio, authorize_read=lambda *args: calls.append(args) or False
    )
    with pytest.raises(PermissionError):
        host.execute_read(scope, request)
    assert len(calls) == 1


def test_scope_mismatch_fails_before_policy(tmp_path):
    studio, _, scope, request = fixture(tmp_path)
    calls = []
    host = NativeAiReadHost(
        studio, authorize_read=lambda *args: calls.append(args) or True
    )
    request["project_id"] = "another_project"
    with pytest.raises(PermissionError, match="Cross-project"):
        host.execute_read(scope, request)
    assert calls == []


def test_exact_digest_and_authorized_result(tmp_path):
    studio, project, scope, request = fixture(tmp_path)
    seen = []
    def verify(native_scope, capability, digest, spec):
        seen.append((native_scope, capability, digest, spec))
        return native_scope.actor_id == "creator_1"

    host = NativeAiReadHost(studio, authorize_read=verify)
    receipt = host.execute_read(scope, request)
    raw = json.dumps(request, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    assert receipt["request_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["result"]["source"]["lines_omitted"] > 0
    assert receipt["authority_granted_to_model"] is False
    assert receipt["creator_approval_granted"] is False
    assert receipt["durable_execution_record"] is False
    assert len(seen) == 1
    assert seen[0][2] == receipt["request_sha256"]


def test_read_rejects_mutation_or_unrecognized_fields(tmp_path):
    studio, _, scope, request = fixture(tmp_path)
    host = NativeAiReadHost(studio, authorize_read=lambda *_: True)
    with pytest.raises(ValueError):
        host.execute_read(scope, {**request, "capability_id": "nvp.film.approve.v1"})
    with pytest.raises(ValueError):
        host.execute_read(scope, {**request, "approval": True})


def test_revocation_on_next_call_and_stale_source(tmp_path):
    studio, project, scope, request = fixture(tmp_path)
    allowed = {"value": True}
    host = NativeAiReadHost(studio, authorize_read=lambda *_: allowed["value"])
    host.execute_read(scope, request)
    allowed["value"] = False
    with pytest.raises(PermissionError):
        host.execute_read(scope, request)
    allowed["value"] = True
    studio.save_screenplay(project["id"], "INT. ROOM - NIGHT", project["revision"])
    with pytest.raises(RuntimeError, match="changed"):
        host.execute_read(scope, request)


def test_read_lines_cannot_request_stale_history(tmp_path):
    studio, project, scope, _ = fixture(tmp_path)
    host = NativeAiReadHost(studio, authorize_read=lambda *_: True)
    with pytest.raises(ValueError, match="mandatory"):
        host.execute_read(scope, {
            "capability_id": "nvp.screenplay.read_lines.v1",
            "project_id": scope.project_id,
            "source_revision": project["revision"],
            "require_current": False,
        })
