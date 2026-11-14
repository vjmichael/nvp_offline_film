"""NVP B6 approved proxy-scene render preflight: immutable source, no execution."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import unittest

from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_production_scene import ProductionScene,blender_script,compact
from backend.nvp_render_preflight import (
    FORMAT,preflight_scene,verify_scene_preflight,
)
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState


class RenderPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.studio=Studio(Path(self.tmp.name)/"studio.sqlite3")
        self.pid=self.studio.create_project("Test feature","")["id"]
        project=self.studio.save_screenplay(
            self.pid,"INT. STUDIO - DAY\n\nMARA\nHello.\n",0)
        self.sid=project["scenes"][0]["id"]
        self.prod=ProductionScene(self.studio)
        self.asset=self.prod.create_asset(self.pid,{
            "name":"MARA","category":"character","dimensions":[.4,.4,1.7]})
        self.staged=False

    def tearDown(self):
        self.tmp.cleanup()

    def approve(self):
        stage=self.prod.stage_scene(self.pid,self.sid,[8,6,3])
        solved=self.prod.solve_scene(self.pid,self.sid,stage["plan_revision"])
        self.prod.approve_scene(self.pid,self.sid,solved["plan_revision"])
        self.staged=True

    def test_unapproved_source_never_returns_render_proof(self):
        # A never-staged scene is absent (KeyError); a staged but
        # unapproved scene is an invalid export state (RuntimeError).
        with self.assertRaises(KeyError):
            preflight_scene(self.studio,self.pid,self.sid)
        self.prod.stage_scene(self.pid,self.sid,[8,6,3])
        with self.assertRaises(RuntimeError):
            preflight_scene(self.studio,self.pid,self.sid)

    def test_approved_scene_produces_exact_deterministic_script_evidence(self):
        self.approve()
        one=preflight_scene(self.studio,self.pid,self.sid)
        two=preflight_scene(self.studio,self.pid,self.sid)
        self.assertEqual(one,two)
        self.assertEqual(one["format"],FORMAT)
        self.assertEqual(one["execution"],"not_started")
        self.assertEqual(one["native_approval"],"not_granted")
        self.assertEqual(one["resource_admission"],"not_checked")
        self.assertEqual(one["source_kind"],"director_approved_proxy_world_only")
        self.assertEqual(one["project_id"],self.pid)
        self.assertEqual(one["scene_id"],self.sid)
        expected=WorldState(self.studio).export_manifest(self.pid,self.sid)
        self.assertEqual(one["world_sha256"],hashlib.sha256(
            compact(expected).encode("utf8")).hexdigest())
        script=blender_script(expected)
        self.assertEqual(one["blender_script_sha256"],hashlib.sha256(
            script.encode("utf8")).hexdigest())
        self.assertTrue(verify_scene_preflight(self.studio,one))

    def test_human_world_edit_invalidates_old_preflight(self):
        self.approve()
        before=preflight_scene(self.studio,self.pid,self.sid)
        current=WorldState(self.studio).read(self.pid,self.sid)
        actor=current["manifest"]["instances"][0]["instance_id"]
        WorldState(self.studio).set_human(
            self.pid,self.sid,actor,"visible",False,current["revision"])
        with self.assertRaisesRegex(RuntimeError,"Production source changed"):
            verify_scene_preflight(self.studio,before)
        after=preflight_scene(self.studio,self.pid,self.sid)
        self.assertNotEqual(before["blender_script_sha256"],after["blender_script_sha256"])
        # Generated Blender must actually honor the director's hidden object,
        # not merely encode a changed metadata hash.
        updated_script=blender_script(WorldState(self.studio).export_manifest(self.pid,self.sid))
        self.assertIn('"visible":false',updated_script)
        self.assertIn('obj.hide_render = hidden',updated_script)
        self.assertIn('obj.hide_viewport = hidden',updated_script)
        self.assertGreater(after["world_revision"],before["world_revision"])
        self.assertTrue(verify_scene_preflight(self.studio,after))

    def test_screenplay_revision_change_invalidates_source(self):
        self.approve()
        proof=preflight_scene(self.studio,self.pid,self.sid)
        current=self.studio.get_project(self.pid)
        self.studio.save_screenplay(
            self.pid,"INT. STUDIO - DAY\n\nMARA\nA different line.\n",current["revision"])
        with self.assertRaises(RuntimeError):
            verify_scene_preflight(self.studio,proof)

    def test_cross_project_and_missing_scene_denied(self):
        self.approve()
        other=self.studio.create_project("Other","")["id"]
        with self.assertRaises(KeyError):
            preflight_scene(self.studio,other,self.sid)
        with self.assertRaises(KeyError):
            preflight_scene(self.studio,self.pid,"SC_unknown")

    def test_between_source_reads_race_blocks_preflight(self):
        self.approve()
        actual=preflight_scene(self.studio,self.pid,self.sid)
        from backend import nvp_render_preflight as source
        internal=source._capture(self.studio,self.pid,self.sid)
        changed=dict(internal,world_revision=internal["world_revision"]+1)
        with patch.object(source,"_capture",side_effect=[internal,changed]):
            with self.assertRaisesRegex(RuntimeError,"modified during preflight"):
                preflight_scene(self.studio,self.pid,self.sid)
        self.assertTrue(verify_scene_preflight(self.studio,actual))

    def test_forged_native_approval_and_output_metadata_fail_source_verifier(self):
        self.approve()
        original=preflight_scene(self.studio,self.pid,self.sid)
        for change in ({"native_approval":"granted"},
                       {"execution":"rendered"},
                       {"instance_count":999},
                       {"resource_admission":"safe"},
                       {"limitations":[]}):
            altered={**original,**change}
            with self.subTest(change=change):
                with self.assertRaisesRegex(RuntimeError,"evidence was altered"):
                    verify_scene_preflight(self.studio,altered)

    def test_source_proof_cannot_be_treated_as_creator_permission(self):
        self.approve()
        with patch("backend.nvp_worker_containment.launch_contained",
                   side_effect=AssertionError("Native worker must not launch")) as launch:
            out=preflight_scene(self.studio,self.pid,self.sid)
            self.assertNotIn("approval_id",out)
            self.assertNotIn("executable",out)
            self.assertNotIn("output_file",out)
            launch.assert_not_called()

    def test_real_fastapi_preflight_route_returns_read_only_evidence(self):
        self.approve()
        old=nvp_api.studio
        nvp_api.studio=self.studio
        try:
            with TestClient(nvp_api.app) as client:
                url=f"/api/projects/{self.pid}/production/scenes/{self.sid}/render-preflight"
                response=client.get(url)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()["execution"],"not_started")
                self.assertEqual(response.json()["native_approval"],"not_granted")
                self.assertEqual(client.post(url).status_code,405)
        finally:
            nvp_api.studio=old


if __name__=="__main__":
    unittest.main()
