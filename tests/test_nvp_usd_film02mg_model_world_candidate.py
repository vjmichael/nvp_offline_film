"""Source-only unit checks; NOT installed Windows or loaded GGUF acceptance."""
import hashlib
import json
import unittest

from backend.nvp_usd_film02m_g_model_world_candidate import (
    FORMAT, generate_model_world_candidate)
from backend.nvp_wo6_verified_local_model import FORMAT as PROVIDER_FORMAT

CATALOG={
    "format":"nvp.usd_film02m_f.native_source_catalog.v1",
    "project_id":"TestFilm",
    "source_buildings":[{
        "building_id":"TestBuilding","revision":1,
        "document_sha256":"a"*64}],
    "approved_districts":[],
}
PARAMS={
    "seed":7,
    "source_buildings":[{"building_id":"TestBuilding","revision":1}],
    "grid_cols":1,"grid_rows":1,"lot_spacing_m":30,
    "world_origin_m":[0,0,0],
    "source_triangle_budget":10000,"source_instance_budget":4,
}

class FakeCompletedProvider:
    def __init__(self, reply, valid_receipt=True):
        self.reply=reply
        self.valid_receipt=valid_receipt
        self.completion_receipt=None
    def complete(self,system,user):
        self.last_system=system
        self.last_user=json.loads(user)
        self.completion_receipt={
            "format":PROVIDER_FORMAT,
            "selected_model_id":"LocalTestModel",
            "provider_reported_model_id":"LocalTestModel",
            "generated_text_sha256":hashlib.sha256(
                self.reply.strip().encode()).hexdigest()
                if self.valid_receipt else "f"*64,
            "provider_reported_completion_tokens":22,
            "provider_self_report_not_attestation":True,
            "native_worker_authorized":False,
        }
        return self.reply

def run(reply, provider=None, catalog=CATALOG):
    return generate_model_world_candidate(
        catalog,project_id="TestFilm",district_id="District01",
        expected_revision=0,direction="Build a short original street",
        model_id="LocalTestModel",model=provider or FakeCompletedProvider(reply))

class CandidateTests(unittest.TestCase):
    def test_actual_host_adapter_required_and_no_approval(self):
        provider=FakeCompletedProvider(json.dumps({"params":PARAMS}))
        result=run(provider.reply,provider)
        self.assertEqual(result["format"],FORMAT)
        self.assertEqual(result["status"],"GENERATED_UNAPPROVED")
        self.assertFalse(result["proposal_durable"])
        self.assertFalse(result["creative_approval_granted"])
        self.assertFalse(result["worker_authorization_granted"])
        self.assertEqual(result["params"],PARAMS)
        self.assertEqual(provider.last_user["approved_source_buildings"][0]["document_sha256"],"a"*64)
    def test_real_writer_json_schema_is_only_format_guidance_not_authority(self):
        class ConstrainedProvider(FakeCompletedProvider):
            def complete_world_candidate(self,system,user,schema):
                self.schema=schema
                return super().complete(system,user)
        reply=json.dumps({"params":PARAMS})
        model=ConstrainedProvider(reply)
        result=run(reply,model)
        self.assertEqual(result["status"],"GENERATED_UNAPPROVED")
        self.assertEqual(set(model.schema),{
            "type","additionalProperties","properties","required"})
        self.assertEqual(model.schema["properties"]["params"]["properties"][
            "source_buildings"]["items"]["properties"][
            "building_id"]["enum"],["TestBuilding"])
        self.assertFalse(result["creative_approval_granted"])
        with self.assertRaises(ValueError):
            run('{"params":{}}',ConstrainedProvider('{"params":{}}'))

    def test_rejects_fenced_json_and_commands(self):
        for reply in (
            "Here is JSON: "+json.dumps({"params":PARAMS}),
            "```json\n"+json.dumps({"params":PARAMS})+"\n```",
            json.dumps({"params":PARAMS,"command":"delete"})):
            with self.subTest(reply=reply[:20]),self.assertRaises(ValueError):
                run(reply)
    def test_unapproved_building_and_nonfinite_coordinates(self):
        bad=json.loads(json.dumps(PARAMS))
        bad["source_buildings"][0]["building_id"]="NotApproved"
        with self.assertRaises(PermissionError):
            run(json.dumps({"params":bad}))
        bad=json.loads(json.dumps(PARAMS))
        bad["world_origin_m"][0]=float("nan")
        with self.assertRaises(ValueError):
            run(json.dumps({"params":bad}))
    def test_rejects_forged_or_missing_model_receipt(self):
        reply=json.dumps({"params":PARAMS})
        with self.assertRaises(PermissionError):
            run(reply,FakeCompletedProvider(reply,False))
    def test_rejects_stale_district(self):
        catalog=json.loads(json.dumps(CATALOG))
        catalog["approved_districts"]=[{
            "district_id":"District01","revision":2,
            "document_sha256":"b"*64}]
        with self.assertRaises(RuntimeError):
            run(json.dumps({"params":PARAMS}),catalog=catalog)

if __name__=="__main__":
    unittest.main()
