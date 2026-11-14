"""NVP B7: real Studio/source, durable native grants, memory admission and denial."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_native_proxy_render import NativeApprovedProxyRender
from backend.nvp_production_scene import ProductionScene
from backend.nvp_render_preflight import preflight_scene
from backend.nvp_render_source_stage import stage_proxy_render_source
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState


def measured():
    return ResourceSnapshot(1,32768,25000,0,())

def insufficient():
    return ResourceSnapshot(1,16384,900,0,())


class NativeProxyRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        root=Path(self.tmp.name)
        self.studio=Studio(root/"studio.sqlite3")
        self.pid=self.studio.create_project("Original Film","")["id"]
        self.sid=self.studio.save_screenplay(
            self.pid,"INT. STUDIO - DAY\n\nMARA\nReady.\n",0)["scenes"][0]["id"]
        prod=ProductionScene(self.studio)
        prod.create_asset(self.pid,{"name":"MARA","category":"character",
                                    "dimensions":[.4,.4,1.7]})
        p=prod.stage_scene(self.pid,self.sid,[8,6,3])
        p=prod.solve_scene(self.pid,self.sid,p["plan_revision"])
        prod.approve_scene(self.pid,self.sid,p["plan_revision"])
        self.ledger=TaskLedger(root/"activity",sampler=measured)
        binary=Path(sys.executable).resolve()
        self.worker=BlenderWorkerSupervisor(root/"native",blender_executable=binary,
                 blender_sha256=sha_file(binary),blender_version="Blender Test",
                 activity_ledger=self.ledger)
        self.proof=preflight_scene(self.studio,self.pid,self.sid)
        self.staged=stage_proxy_render_source(
            self.studio,self.worker,self.proof,ram_mb=2048)
        self.trusted_event=object()
        self.events=[]
        def actual_native_verifier(event,ctx):
            self.events.append(ctx)
            return event is self.trusted_event and ctx["project_id"]==self.pid
        self.host=NativeApprovedProxyRender(self.studio,self.worker,self.ledger,
                             verify_creator_action=actual_native_verifier)

    def tearDown(self):
        self.tmp.cleanup()

    def approve(self):
        return self.host.consent_from_trusted_native_action(
            self.staged,self.proof,self.trusted_event)

    def queue(self):
        receipt=self.approve()
        ticket=self.host.enqueue_approved(
            self.staged,self.proof,receipt["approval_id"],lane="interactive")
        self.assertEqual(ticket["state"],"QUEUED")
        return receipt,ticket

    def test_no_event_identity_cannot_mint_host_render_consent(self):
        with self.assertRaises(PermissionError):
            self.host.consent_from_trusted_native_action(
                self.staged,self.proof,{"clicked":True})
        with self.ledger._db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM native_proxy_render_consents").fetchone()[0],0)
        self.assertEqual(self.ledger.snapshot()["tasks"],[])
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_exact_trusted_approval_queue_low_ram_then_admit_and_run(self):
        self.ledger.sampler=insufficient
        receipt,ticket=self.queue()
        self.assertEqual(receipt["document_sha256"],ticket["spec_sha256"])
        self.assertEqual(self.events[-1]["world_sha256"],self.proof["world_sha256"])
        with patch.object(self.worker,"_run_worker",side_effect=AssertionError("No RAM")) as execute:
            blocked=self.host.run_next()
            self.assertFalse(blocked["admitted"])
            self.assertEqual(blocked["state"],"QUEUED")
            execute.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.ledger.sampler=measured
        done={"id":self.staged["operation"].job_id,"state":"SUCCEEDED","error":None}
        with patch.object(self.worker,"_run_worker",return_value=done) as execute, \
             patch.object(self.worker,"inspect",return_value=done), \
             patch.object(self.worker,"verify_completed",return_value=done) as verify:
            self.assertEqual(self.host.run_next()["state"],"SUCCEEDED")
            execute.assert_called_once_with(self.staged["operation"])
            verify.assert_called_once_with(self.staged["operation"].job_id)
        row=self.ledger.get_task(ticket["task_id"])
        self.assertEqual(row["state"],"SUCCEEDED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_source_edit_invalidates_queued_approval_without_spawning(self):
        receipt,ticket=self.queue()
        world=WorldState(self.studio).read(self.pid,self.sid)
        actor=world["manifest"]["instances"][0]["instance_id"]
        WorldState(self.studio).set_human(
            self.pid,self.sid,actor,"visible",False,world["revision"])
        with patch.object(self.worker,"_run_worker") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertEqual(self.ledger.get_task(ticket["task_id"])["state"],"QUEUED")

    def test_tampered_staged_bytes_denied_before_admission(self):
        receipt,ticket=self.queue()
        path=self.staged["stage_dir"]/"approved_manifest.json"
        path.write_bytes(path.read_bytes()+b"corrupt")
        with patch.object(self.worker,"_run_worker") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_revocation_cancels_queued_only_and_survives_restart(self):
        receipt,ticket=self.queue()
        status=self.host.revoke_from_trusted_native_action(
            receipt["approval_id"],self.trusted_event)
        self.assertTrue(status["revoked"])
        self.assertTrue(status["queued_work_cancelled"])
        self.assertEqual(self.ledger.get_task(ticket["task_id"])["state"],"CANCELLED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        again=NativeApprovedProxyRender(self.studio,self.worker,self.ledger,
                                        verify_creator_action=lambda *_:False)
        with patch.object(self.worker,"_run_worker") as worker:
            self.assertIsNone(again.run_next())
            worker.assert_not_called()

    def test_grant_expires_and_cannot_dispatch(self):
        receipt,ticket=self.queue()
        with self.ledger._db() as db:
            db.execute("UPDATE native_proxy_render_consents SET expires_at=0 WHERE approval_id=?",
                       (receipt["approval_id"],))
        with patch.object(self.worker,"_run_worker") as worker:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            worker.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_resource_job_substitution_denied(self):
        receipt,ticket=self.queue()
        with self.ledger._db() as db:
            db.execute("""UPDATE authorized_task_specs
                       SET spec_json=? WHERE task_id=?""",
                       ('{"kind":"blender","task_id":"hijacked"}',ticket["task_id"]))
        with patch.object(self.worker,"_run_worker") as worker:
            with self.assertRaises(RuntimeError):
                self.host.run_next()
            worker.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_recreated_host_checks_approved_source_and_durable_consent(self):
        receipt,ticket=self.queue()
        restarted=NativeApprovedProxyRender(self.studio,self.worker,self.ledger,
                                            verify_creator_action=lambda *_:False)
        self.assertTrue(restarted._approval_check(receipt["approval_id"],
            receipt["document_sha256"],{
                "task_id":ticket["task_id"],"kind":"blender",
                "operation":__import__("json").loads(self.staged["operation"].canonical())}))
        with patch.object(self.worker,"_run_worker",return_value={
            "id":self.staged["operation"].job_id,"state":"SUCCEEDED","error":None}),\
             patch.object(self.worker,"inspect",return_value={"state":"SUCCEEDED","error":None}),\
             patch.object(self.worker,"verify_completed",return_value={"state":"SUCCEEDED"}):
            self.assertEqual(restarted.run_next()["state"],"SUCCEEDED")

    def test_last_moment_native_grant_refusal_never_starts_worker(self):
        receipt,ticket=self.queue()
        with patch.object(self.host.dispatcher,"pre_worker_check",
                          side_effect=PermissionError("revoked immediately")) as verify,\
             patch.object(self.worker,"_run_worker") as worker:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            verify.assert_called_once()
            worker.assert_not_called()
        # Conservative: ACTIVE reservation retained when dispatch was
        # interrupted at the trust boundary; not silently cleaned up.
        self.assertEqual(self.ledger.get_task(ticket["task_id"])["state"],"ACTIVE")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],2048)

    def test_revoke_requires_distinct_authenticated_creator_event(self):
        receipt,ticket=self.queue()
        with self.assertRaises(PermissionError):
            self.host.revoke_from_trusted_native_action(receipt["approval_id"],{"revoke":True})
        self.assertEqual(self.ledger.get_task(ticket["task_id"])["state"],"QUEUED")
        self.assertTrue(self.host.revoke_from_trusted_native_action(
            receipt["approval_id"],self.trusted_event)["queued_work_cancelled"])


if __name__=="__main__":
    unittest.main()
