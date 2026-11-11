"""G02's host-scoped Lu contract, NOT an installed Lu or actual-GGUF test."""
from __future__ import annotations

import unittest
from hashlib import sha256
from unittest.mock import patch

from backend.nvp_lu_g02_port import LuG02FilmPort
from backend.nvp_lu_workspace import LuHostError, NvpLuWorkspace


MODEL = "m-0123456789abcdef0123456789abcdef"
SESSION = "s-1234567890abcdef1234567890abcdef"
GEN = "g-1234567890abcdef1234567890abcdef"
TEXT = "INT. KITCHEN - NIGHT\n\nALEX\nI can see the lantern."


class TrustedHostDouble:
    """Source-only stand-in: the genuine Rust Lu host is not installed here."""

    def __init__(self):
        self.scope = object()
        self.authorized = True
        self.project = {
            "id": "MovieA", "title": "Lantern", "idea": "Two friends meet",
            "screenplay": "", "scenes": [], "revision": 0}
        self.claim = {"module": "nvp.film", "workspace": "NvpWindow01",
                      "project": "MovieA", "epoch": "a"*32, "state": "active"}
        self.runtime = {"modelRef": MODEL, "sessionId": SESSION,
                        "generationId": None, "phase": "Ready", "pid": 321}
        self.available = 1
        self.generated = TEXT
        self.events = None
        self.receipts = []
        self.saved = []
        self.consumed_sha256 = set()
        self.accept_receipt = True
        self.cancel_calls = 0
        self.verify_calls = []
        self.deny_after_events = 0
        self.event_counter = 0
        self.change_revision_in_generation = False

    def verify_scope(self, scope, operation):
        self.verify_calls.append(operation)
        if scope is not self.scope or not self.authorized:
            raise LuHostError("Host denied inactive, foreign or revoked scope")
        if self.deny_after_events and self.event_counter >= self.deny_after_events:
            raise LuHostError("Lu grant revoked mid-inference")
        return dict(self.claim)

    def read_runtime(self, scope):
        self.verify_scope(scope, "host_read_runtime")
        return dict(self.runtime)

    def catalog_count(self, scope):
        self.verify_scope(scope, "host_catalog")
        return self.available

    def read_project(self, scope):
        self.verify_scope(scope, "host_read_project")
        return dict(self.project)

    def _event(self, sequence, kind, **more):
        return {"v":1,"workspace":self.claim["workspace"],
                "project":self.claim["project"], "epoch":self.claim["epoch"],
                "modelRef":MODEL,"sessionId":SESSION,"generationId":GEN,
                "sequence":sequence,"kind":kind,**more}

    def generate_events(self, scope, system, user, max_new_tokens):
        assert "NVP" in system
        assert "Original creator idea" in user
        assert max_new_tokens == 2800
        if self.change_revision_in_generation:
            self.project["revision"] += 1
        events = self.events if self.events is not None else [
            self._event(1,"chunk",text=self.generated),
            self._event(2,"finished",cancelled=False)]
        for event in events:
            self.event_counter += 1
            yield dict(event)

    def record_generation(self, scope, receipt):
        self.verify_scope(scope, "host_record_generation")
        if not self.accept_receipt:
            return {"status":"pending"}
        self.receipts.append(dict(receipt))
        return {"status":"recorded",
                "request_sha256":receipt["request_sha256"],
                "generated_sha256":receipt["generated_sha256"],
                "proposal_sha256":receipt["proposal_sha256"]}

    def save_proposal(self, scope, *, stage, content, instructions, expected_revision):
        self.verify_scope(scope,"host_save_proposal")
        if expected_revision != self.project["revision"]:
            raise LuHostError("stale project cannot save proposal")
        digest=sha256(content.encode("utf8")).hexdigest()
        if (digest in self.consumed_sha256 or
                not any(x["proposal_sha256"]==digest for x in self.receipts)):
            raise LuHostError("missing or replayed completed-generation receipt")
        self.consumed_sha256.add(digest)
        self.saved.append(dict(stage=stage, content=content, status="proposed"))
        return {"status":"proposed","stage":stage,"content":content,
                "consumed_proposal_sha256":digest,"source_mutated":False}

    def cancel_active(self, scope):
        self.verify_scope(scope,"host_cancel")
        self.cancel_calls += 1
        return True


class LuG02FilmContractTests(unittest.TestCase):
    def setUp(self):
        self.host = TrustedHostDouble()
        self.port = LuG02FilmPort(self.host)
        self.workspace = NvpLuWorkspace(self.port)

    def test_real_lu_host_required_not_a_browser_lambda(self):
        with self.assertRaises(TypeError):
            LuG02FilmPort(object())

    def test_status_distinguishes_unloaded_missing_ready_and_busy(self):
        self.assertEqual(self.port.status(self.host.scope)["state"],"ready")
        self.host.runtime.update(modelRef=None,sessionId=None,pid=None,phase="Idle")
        self.assertEqual(self.port.status(self.host.scope)["state"],"available_unloaded")
        self.host.available=0
        self.assertEqual(self.port.status(self.host.scope)["state"],"no_model")
        self.host.runtime.update(modelRef=MODEL,sessionId=SESSION,phase="Generating",
                                 generationId=GEN,pid=321)
        self.assertEqual(self.port.status(self.host.scope)["state"],"busy")
        self.assertFalse(self.port.status(self.host.scope)["weights_verified_here"])

    def test_timeout_is_not_misreported_as_no_model(self):
        with patch.object(self.host,"read_runtime",side_effect=TimeoutError):
            self.assertEqual(self.port.status(self.host.scope)["state"],"timed_out")
        with patch.object(self.host,"read_runtime",side_effect=ConnectionError):
            self.assertEqual(self.port.status(self.host.scope)["state"],"disconnected")

    def test_host_invalid_status_cannot_forge_readiness(self):
        self.host.runtime["sessionId"]=None
        self.assertEqual(self.port.status(self.host.scope)["state"],"unavailable")
        self.host.runtime["phase"]="PretendReady"
        self.assertEqual(self.port.status(self.host.scope)["state"],"unavailable")

    def test_foreign_revoked_suspended_workspace_denied_before_data_read(self):
        with self.assertRaises(LuHostError):
            self.port.read_project(object())
        self.host.claim["state"]="suspended"
        with self.assertRaises(LuHostError):
            self.port.status(self.host.scope)
        self.host.claim["state"]="active"
        self.host.authorized=False
        with self.assertRaises(LuHostError):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.saved,[])

    def test_project_id_cannot_switch_under_same_lu_scope(self):
        self.host.project["id"]="OtherMovie"
        with self.assertRaises(LuHostError):
            self.port.read_project(self.host.scope)

    def test_existing_nvp_workspace_uses_lu_completion_and_proposal_only(self):
        with patch.dict("os.environ",{"NVP_LLM_URL":"https://bad.example.org"}):
            result=self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(result["status"],"proposed")
        self.assertEqual(len(self.host.receipts),1)
        self.assertEqual(len(self.host.saved),1)
        self.assertFalse(self.host.receipts[0]["source_mutation_authorized"])
        self.assertFalse(self.host.receipts[0]["tool_execution_authorized"])
        self.assertEqual(self.host.project["screenplay"],"")
        self.assertTrue(self.host.verify_calls.count("generate")>=3)

    def test_whitespace_normalization_keeps_raw_and_proposal_provenance(self):
        self.host.generated = "  " + TEXT + "\n\n"
        self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(len(self.host.saved),1)
        self.assertEqual(self.host.saved[0]["content"],TEXT)
        self.assertNotEqual(self.host.receipts[0]["generated_sha256"],
                            self.host.receipts[0]["proposal_sha256"])
        self.assertEqual(self.host.receipts[0]["proposal_sha256"],
                         sha256(TEXT.encode("utf8")).hexdigest())

    def test_direct_proposal_write_without_completed_generation_is_denied(self):
        with self.assertRaisesRegex(LuHostError,"missing or replayed"):
            self.port.save_proposal(self.host.scope,stage="screenplay",
                                    content=TEXT,instructions="",expected_revision=0)
        self.assertEqual(self.host.saved,[])

    def test_replayed_completed_generation_receipt_cannot_save_twice(self):
        self.workspace.propose(self.host.scope,stage="screenplay")
        with self.assertRaisesRegex(LuHostError,"missing or replayed"):
            self.port.save_proposal(self.host.scope,stage="screenplay",
                                    content=TEXT,instructions="",expected_revision=0)
        self.assertEqual(len(self.host.saved),1)

    def test_host_mismatched_receipt_evidence_is_rejected_by_adapter(self):
        def forged(scope, **kw):
            return {"status":"proposed","consumed_proposal_sha256":"0"*64,
                    "source_mutated":False}
        self.host.save_proposal=forged
        with self.assertRaisesRegex(LuHostError,"exact completed-generation"):
            self.workspace.propose(self.host.scope,stage="screenplay")

    def test_busy_model_denied_before_generation(self):
        self.host.runtime.update(phase="Generating",generationId=GEN)
        with self.assertRaisesRegex(LuHostError,"not ready"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.receipts,[])

    def test_truncated_stream_cannot_publish_partial_screenplay(self):
        self.host.events=[self.host._event(1,"chunk",text=TEXT)]
        with self.assertRaisesRegex(LuHostError,"without verified"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.saved,[])

    def test_cancelled_stream_never_saves_proposal(self):
        self.host.events=[self.host._event(1,"chunk",text=TEXT),
                          self.host._event(2,"finished",cancelled=True)]
        with self.assertRaisesRegex(LuHostError,"cancelled"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.saved,[])

    def test_sequence_replay_and_wrong_generation_rejected(self):
        self.host.events=[self.host._event(1,"chunk",text=TEXT),
                          self.host._event(1,"finished",cancelled=False)]
        with self.assertRaisesRegex(LuHostError,"unbound"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.host.events=[self.host._event(1,"chunk",text=TEXT),
                          {**self.host._event(2,"finished",cancelled=False),
                           "generationId":"g-other"}]
        with self.assertRaisesRegex(LuHostError,"changed mid-stream"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.saved,[])

    def test_foreign_scope_in_event_rejected(self):
        self.host.events=[
            {**self.host._event(1,"chunk",text=TEXT),"project":"OtherMovie"},
            self.host._event(2,"finished",cancelled=False)]
        with self.assertRaisesRegex(LuHostError,"unbound"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.saved,[])

    def test_stream_revocation_before_terminal_disallows_proposal(self):
        self.host.deny_after_events=1
        with self.assertRaisesRegex(LuHostError,"revoked"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.receipts,[])
        self.assertEqual(self.host.saved,[])

    def test_non_durable_host_receipt_blocks_publication(self):
        self.host.accept_receipt=False
        with self.assertRaisesRegex(LuHostError,"durably journal"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.saved,[])

    def test_host_revision_cas_rejects_edit_during_generation(self):
        self.host.change_revision_in_generation=True
        with self.assertRaisesRegex(LuHostError,"stale project"):
            self.workspace.propose(self.host.scope,stage="screenplay")
        self.assertEqual(self.host.saved,[])

    def test_cancel_returns_request_not_false_worker_termination(self):
        reply=self.port.cancel(self.host.scope)
        self.assertEqual(reply["state"],"cancellation_requested")
        self.assertFalse(reply["terminal_verified"])
        self.assertFalse(reply["model_unloaded"])
        self.assertEqual(self.host.cancel_calls,1)


if __name__=="__main__":
    unittest.main()
