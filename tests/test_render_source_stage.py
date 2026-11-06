"""NVP B6 stage exact frozen Blender source without minting execution consent."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_production_scene import ProductionScene
from backend.nvp_render_preflight import preflight_scene
from backend.nvp_render_source_stage import (
    stage_proxy_render_source,verify_staged_proxy_source,
)
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState


def sample():
    return ResourceSnapshot(1,32768,24576,0,())


class FrozenSourceStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        root=Path(self.tmp.name)
        self.studio=Studio(root/"studio.sqlite3")
        self.pid=self.studio.create_project("Film","")["id"]
        self.sid=self.studio.save_screenplay(
            self.pid,"INT. SOUND STAGE - DAY\n\nMARA\nLet's begin.\n",0)["scenes"][0]["id"]
        self.prod=ProductionScene(self.studio)
        self.prod.create_asset(self.pid,{
            "name":"MARA","category":"character","dimensions":[.4,.4,1.7]})
        stage=self.prod.stage_scene(self.pid,self.sid,[8,6,3])
        solved=self.prod.solve_scene(self.pid,self.sid,stage["plan_revision"])
        self.prod.approve_scene(self.pid,self.sid,solved["plan_revision"])
        self.ledger=TaskLedger(root/"activity",sampler=sample)
        # The binary exists for supervisor pinning, but never runs in B6.
        import sys
        self.binary=Path(sys.executable).resolve()
        self.supervisor=BlenderWorkerSupervisor(
            root/"native-work",blender_executable=self.binary,
            blender_sha256=sha_file(self.binary),blender_version="Blender 5.2.3",
            activity_ledger=self.ledger)
        self.proof=preflight_scene(self.studio,self.pid,self.sid)

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_exact_script_and_manifest_staged_no_model_or_worker(self):
        with patch("backend.nvp_blender_worker.launch_contained",
                   side_effect=AssertionError("B6 cannot start Blender")) as launch:
            staged=stage_proxy_render_source(self.studio,self.supervisor,self.proof)
        op=staged["operation"]
        self.assertEqual(staged["native_approval"],"not_granted")
        self.assertEqual(staged["execution"],"not_started")
        self.assertEqual(staged["resource_admission"],"not_checked")
        self.assertEqual(op.script_sha256,self.proof["blender_script_sha256"])
        self.assertEqual(sha_file(staged["stage_dir"]/"trusted_scene_build.py"),
                         self.proof["blender_script_sha256"])
        self.assertEqual(sha_file(staged["stage_dir"]/"approved_manifest.json"),
                         self.proof["world_sha256"])
        self.assertEqual(op.outputs,{"approved_scene.blend":"blend"})
        self.assertEqual(op.gpu_memory_mb,0)
        self.assertTrue(verify_staged_proxy_source(self.studio,self.supervisor,staged,self.proof))
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertEqual(self.ledger.snapshot()["tasks"],[])
        launch.assert_not_called()

    def test_unapproved_or_altered_proof_creates_no_native_directory(self):
        wrong={**self.proof,"native_approval":"granted"}
        with self.assertRaises(RuntimeError):
            stage_proxy_render_source(self.studio,self.supervisor,wrong)
        self.assertEqual([p for p in self.supervisor.root.iterdir() if p.is_dir()],[])

    def test_staged_worker_script_or_manifest_tampering_denied(self):
        for name in ("trusted_scene_build.py","approved_manifest.json"):
            with self.subTest(name=name):
                staged=stage_proxy_render_source(self.studio,self.supervisor,self.proof)
                file=staged["stage_dir"]/name
                file.write_bytes(file.read_bytes()+b"\n#Tampered\n")
                with self.assertRaises(RuntimeError):
                    verify_staged_proxy_source(self.studio,self.supervisor,staged,self.proof)

    def test_director_edit_after_staging_blocks_dispatch(self):
        staged=stage_proxy_render_source(self.studio,self.supervisor,self.proof)
        current=WorldState(self.studio).read(self.pid,self.sid)
        actor=current["manifest"]["instances"][0]["instance_id"]
        WorldState(self.studio).set_human(
            self.pid,self.sid,actor,"visible",False,current["revision"])
        with self.assertRaises(RuntimeError):
            verify_staged_proxy_source(self.studio,self.supervisor,staged,self.proof)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_source_revision_modified_during_materialization_removes_stage(self):
        from backend import nvp_render_source_stage as stage
        actual=stage._write_exclusive
        invocations=[]
        def change_world(folder,name,content):
            result=actual(folder,name,content)
            invocations.append(name)
            if name=="approved_manifest.json":
                current=WorldState(self.studio).read(self.pid,self.sid)
                actor=current["manifest"]["instances"][0]["instance_id"]
                WorldState(self.studio).set_human(
                    self.pid,self.sid,actor,"visible",False,current["revision"])
            return result
        with patch.object(stage,"_write_exclusive",side_effect=change_world):
            with self.assertRaises(RuntimeError):
                stage_proxy_render_source(self.studio,self.supervisor,self.proof)
        self.assertEqual(invocations,["approved_manifest.json","trusted_scene_build.py"])
        self.assertEqual([p for p in self.supervisor.root.iterdir() if p.is_dir()],[])

    def test_unsafe_resource_settings_fail_before_staging(self):
        for kwargs in ({"ram_mb":128},{"ram_mb":True},
                       {"gpu_mb":1024},{"gpu_mb":True},
                       {"timeout_seconds":0},{"timeout_seconds":601},
                       {"require_linux_cgroup_v2":"yes"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    stage_proxy_render_source(self.studio,self.supervisor,self.proof,**kwargs)
        self.assertEqual([p for p in self.supervisor.root.iterdir() if p.is_dir()],[])

    def test_caller_cannot_forge_staged_permission_or_job_spec(self):
        staged=stage_proxy_render_source(self.studio,self.supervisor,self.proof)
        with self.assertRaises(PermissionError):
            verify_staged_proxy_source(self.studio,self.supervisor,
                {**staged,"native_approval":"granted"},self.proof)
        with self.assertRaises(PermissionError):
            verify_staged_proxy_source(self.studio,self.supervisor,
                {**staged,"resource_admission":"passed"},self.proof)
        with self.assertRaises(RuntimeError):
            verify_staged_proxy_source(self.studio,self.supervisor,
                {**staged,"operation":replace(staged["operation"],
                     arguments={"--output":"different.blend"})},self.proof)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_stage_job_ids_are_unique_and_never_overwrite_another_job(self):
        one=stage_proxy_render_source(self.studio,self.supervisor,self.proof)
        two=stage_proxy_render_source(self.studio,self.supervisor,self.proof)
        self.assertNotEqual(one["operation"].job_id,two["operation"].job_id)
        self.assertNotEqual(one["stage_dir"],two["stage_dir"])
        self.assertTrue(verify_staged_proxy_source(self.studio,self.supervisor,one,self.proof))
        self.assertTrue(verify_staged_proxy_source(self.studio,self.supervisor,two,self.proof))


if __name__=="__main__":
    unittest.main()
