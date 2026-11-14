"""B8 preserved Digital Take lineage, native trust, source/input/admission denial."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_frozen_take_stage import stage_frozen_take,verify_frozen_stage,_source,TIMED,SCRIPT
from backend.nvp_frozen_take_render import NativeFrozenTakeRender
from backend.nvp_frozen_take_audit import NativeFrozenTakeAuditor
from backend.nvp_frozen_take_presentation import publish_verified_preview,verify_presentation
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_world_state import WorldState
from tools.nvp_stack02c3b8_real_frozen_take import prepare_capture


def measured():
    return ResourceSnapshot(1,32768,25000,0,())


def low_ram():
    return ResourceSnapshot(1,16384,800,0,())


class FrozenNativeTakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        root=Path(self.tmp.name)
        self.studio,self.capture,self.pid,self.sid,self.tid,self.actors=prepare_capture(root)
        self.ledger=TaskLedger(root/"resources",sampler=measured)
        binary=Path(sys.executable).resolve()
        self.worker=BlenderWorkerSupervisor(
            root/"native",blender_executable=binary,
            blender_sha256=sha_file(binary),blender_version="Blender Test",
            activity_ledger=self.ledger)
        self.stage=stage_frozen_take(self.capture,self.worker,
                                     self.pid,self.tid,ram_mb=2048)
        self.event=object()
        self.events=[]
        def creator(ev,ctx):
            self.events.append(ctx)
            return ev is self.event and ctx.get("project_id")==self.pid
        self.host=NativeFrozenTakeRender(self.capture,self.worker,self.ledger,
                                         verify_creator_action=creator)

    def tearDown(self):
        self.tmp.cleanup()

    def approve(self):
        grant=self.host.consent_from_trusted_native_action(self.stage,self.event)
        self.host.enqueue_approved(self.stage,grant["approval_id"])
        return grant

    def test_real_frozen_filmindex_motion_and_script_are_pinned(self):
        self.assertTrue(verify_frozen_stage(self.capture,self.worker,self.stage))
        original=_source(self.capture,self.pid,self.tid)
        self.assertEqual(self.stage["capture_sha256"],original["capture_sha256"])
        self.assertEqual(self.stage["frame_count"],120)
        self.assertEqual(self.stage["frame_rate"],24)
        self.assertEqual(self.stage["shot_count"],2)
        self.assertEqual(self.stage["actor_count"],2)
        timed=json.loads((self.stage["stage_dir"]/TIMED).read_text("utf8"))
        self.assertTrue(any(a["marks"] for a in timed["actors"]))
        self.assertTrue(any(a["audit_samples"] for a in timed["actors"]))
        script=(self.stage["stage_dir"]/SCRIPT).read_text("utf8")
        self.assertIn("timeline_markers.new",script)
        self.assertIn("keyframe_insert",script)
        self.assertIn("nvp_take_sha",script)
        self.assertEqual(sha_file(self.stage["stage_dir"]/SCRIPT),
                         self.stage["script_sha256"])
        self.assertEqual(self.ledger.snapshot()["tasks"],[])

    def test_original_capture_survives_later_director_edits(self):
        state=WorldState(self.studio).read(self.pid,self.sid)
        actor=self.actors["BOB"]["instance_id"]
        WorldState(self.studio).set_human(self.pid,self.sid,actor,
                                          "visible",False,state["revision"])
        with self.assertRaises(RuntimeError):
            from backend.nvp_shot_sequence import ShotSequence
            ShotSequence(self.studio).export(self.pid,self.sid)
        self.assertTrue(verify_frozen_stage(self.capture,self.worker,self.stage))
        self.assertEqual(self.stage["capture_sha256"],
                         self.capture.reopen(self.pid,self.tid)["record"]["document_sha256"])

    def test_other_film_identity_cannot_reopen_original_take(self):
        other=self.studio.create_project("Unrelated","")["id"]
        with self.assertRaises(KeyError):
            _source(self.capture,other,self.tid)

    def test_staged_timed_or_script_mutation_never_admitted(self):
        for name in (TIMED,SCRIPT):
            with self.subTest(name=name):
                original=(self.stage["stage_dir"]/name).read_bytes()
                (self.stage["stage_dir"]/name).write_bytes(original+b"\ncorrupt")
                with self.assertRaises(RuntimeError):
                    verify_frozen_stage(self.capture,self.worker,self.stage)
                (self.stage["stage_dir"]/name).write_bytes(original)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_model_or_web_event_does_not_create_native_approval(self):
        with self.assertRaises(PermissionError):
            self.host.consent_from_trusted_native_action(
                self.stage,{"model_says":"approved"})
        with self.ledger._db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM native_frozen_take_consents").fetchone()[0],0)
        self.assertEqual(self.ledger.snapshot()["tasks"],[])

    def test_current_native_creator_context_binds_frozen_identity_and_budgets(self):
        grant=self.approve()
        ctx=self.events[0]
        self.assertEqual(ctx["take_id"],self.tid)
        self.assertEqual(ctx["capture_sha256"],self.stage["capture_sha256"])
        self.assertEqual(ctx["frames"],120)
        self.assertEqual(ctx["shots"],2)
        self.assertEqual(ctx["document_sha256"],grant["document_sha256"])
        self.assertEqual(ctx["output_contract"],
            "timed_blend_plus_independent_camera_actor_frame_audit_png")

    def test_ram_denial_queues_without_process_then_verified_worker_boundary(self):
        grant=self.approve()
        self.ledger.sampler=low_ram
        with patch.object(self.worker,"_run_worker",side_effect=AssertionError("worker spawned")):
            result=self.host.run_next()
        self.assertEqual(result["state"],"QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.ledger.sampler=measured
        simulated={"id":self.stage["operation"].job_id,"state":"SUCCEEDED","error":None}
        with patch.object(self.worker,"_run_worker",return_value=simulated) as run,\
             patch.object(self.worker,"inspect",return_value=simulated),\
             patch.object(self.worker,"verify_completed",return_value=simulated):
            self.assertEqual(self.host.run_next()["state"],"SUCCEEDED")
            run.assert_called_once()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_revoked_and_expired_consent_deny_before_resource_admission(self):
        grant=self.approve()
        rejected=self.host.revoke_from_trusted_native_action(grant["approval_id"],self.event)
        self.assertTrue(rejected["queued_work_cancelled"])
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        with patch.object(self.worker,"_run_worker") as worker:
            self.assertIsNone(self.host.run_next())
            worker.assert_not_called()

    def test_expired_queued_consent_stays_queued_and_never_launches(self):
        grant=self.approve()
        with self.ledger._db() as db:
            db.execute("UPDATE native_frozen_take_consents SET expires_at=0 WHERE approval_id=?",
                       (grant["approval_id"],))
        with patch.object(self.worker,"_run_worker") as worker:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            worker.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_no_independent_audit_before_original_real_blend_exists(self):
        grant=self.approve()
        auditor=NativeFrozenTakeAuditor(self.host)
        with self.assertRaisesRegex(RuntimeError,"not verified successful"):
            auditor.reopen_and_verify(grant["approval_id"])
        with self.ledger._db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM native_frozen_take_audits").fetchone()[0],0)

    def test_recreated_native_host_reads_same_durable_grant(self):
        grant=self.approve()
        restarted=NativeFrozenTakeRender(self.capture,self.worker,self.ledger,
                                         verify_creator_action=lambda *_:False)
        row=self.host._meta(self.stage)
        doc={"task_id":grant["task_id"],"kind":"blender",
             "operation":json.loads(self.stage["operation"].canonical())}
        self.assertTrue(restarted._check(grant["approval_id"],
                                         grant["document_sha256"],doc))
        self.assertEqual(row["capture_sha256"],self.stage["capture_sha256"])

    def test_forged_stage_metadata_cannot_be_approved(self):
        for change in ({"capture_sha256":"a"*64},
                       {"frame_count":1},{"shot_count":1},
                       {"native_approval":"granted"},
                       {"resource_admission":"admitted"}):
            with self.subTest(change=change):
                with self.assertRaises((RuntimeError,PermissionError)):
                    self.host.consent_from_trusted_native_action(
                        {**self.stage,**change},self.event)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_unauthorized_grant_revocation_does_not_cancel(self):
        grant=self.approve()
        with self.assertRaises(PermissionError):
            self.host.revoke_from_trusted_native_action(
                grant["approval_id"],{"revoke":True})
        self.assertEqual(self.ledger.get_task(grant["task_id"])["state"],"QUEUED")

    def test_revoked_grant_cannot_generate_second_native_audit(self):
        grant=self.approve()
        self.host.revoke_from_trusted_native_action(grant["approval_id"],self.event)
        with self.assertRaises(PermissionError):
            NativeFrozenTakeAuditor(self.host).reopen_and_verify(grant["approval_id"])

    def test_unrendered_take_cannot_create_indexed_presentation(self):
        grant=self.approve()
        with self.assertRaisesRegex(RuntimeError,"not been executed"):
            publish_verified_preview(NativeFrozenTakeAuditor(self.host),grant["approval_id"])
        self.assertEqual(self.capture.index.list_objects(self.pid,kind="presentation"),[])

    def test_unknown_cross_project_presentation_reference_rejected(self):
        other=self.studio.create_project("Another feature","")["id"]
        with self.assertRaises(KeyError):
            verify_presentation(self.capture,other,"preview_nonexistent")
        self.assertEqual(self.capture.index.list_objects(self.pid,kind="presentation"),[])

    def test_native_review_budget_checked_before_any_blender_execution(self):
        grant=self.approve()
        auditor=NativeFrozenTakeAuditor(self.host)
        for budget in (0,True,65537):
            with self.subTest(budget=budget):
                with self.assertRaises(ValueError):
                    auditor.reopen_and_verify(grant["approval_id"],ram_mb=budget)


if __name__=="__main__":
    unittest.main()
