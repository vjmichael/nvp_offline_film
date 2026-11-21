"""B7 independent native Blender audit refuses unverifiable or unauthorized builds."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_native_proxy_render import NativeApprovedProxyRender
from backend.nvp_native_proxy_audit import NativeProxySceneAuditor
from backend.nvp_production_scene import ProductionScene
from backend.nvp_render_preflight import preflight_scene
from backend.nvp_render_source_stage import stage_proxy_render_source
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio


def measured():
    return ResourceSnapshot(1,32768,25000,0,())


class NativeSceneAuditRefusalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        root=Path(self.tmp.name)
        self.studio=Studio(root/"film.sqlite3")
        self.pid=self.studio.create_project("Film","")["id"]
        self.sid=self.studio.save_screenplay(
            self.pid,"INT. SET - DAY\n\nMARA\nOkay.\n",0)["scenes"][0]["id"]
        prod=ProductionScene(self.studio)
        prod.create_asset(self.pid,{"name":"MARA","category":"character",
                                    "dimensions":[.4,.4,1.7]})
        p=prod.stage_scene(self.pid,self.sid,[8,6,3])
        p=prod.solve_scene(self.pid,self.sid,p["plan_revision"])
        prod.approve_scene(self.pid,self.sid,p["plan_revision"])
        self.ledger=TaskLedger(root/"resources",sampler=measured)
        binary=Path(sys.executable).resolve()
        self.worker=BlenderWorkerSupervisor(root/"worker",
               blender_executable=binary,blender_sha256=sha_file(binary),
               blender_version="Blender Test",activity_ledger=self.ledger)
        self.proof=preflight_scene(self.studio,self.pid,self.sid)
        self.staged=stage_proxy_render_source(self.studio,self.worker,self.proof,ram_mb=2048)
        self.event=object()
        self.host=NativeApprovedProxyRender(self.studio,self.worker,self.ledger,
              verify_creator_action=lambda incoming,ctx:incoming is self.event)
        self.auditor=NativeProxySceneAuditor(self.host)

    def tearDown(self):
        self.tmp.cleanup()

    def approve(self):
        approval=self.host.consent_from_trusted_native_action(
                 self.staged,self.proof,self.event)
        self.host.enqueue_approved(self.staged,self.proof,approval["approval_id"])
        return approval["approval_id"]

    def test_unknown_or_untrusted_audit_consent_never_spawns_worker(self):
        with self.assertRaises(PermissionError):
            self.auditor.reopen_and_verify("nvp_render_unissued")
        with self.ledger._db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM native_proxy_scene_audits").fetchone()[0],0)

    def test_queued_build_cannot_generate_fake_audit_success(self):
        approval_id=self.approve()
        with self.assertRaisesRegex(RuntimeError,"not verified successful"):
            self.auditor.reopen_and_verify(approval_id)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_revoked_build_consent_cannot_launch_independent_audit(self):
        approval_id=self.approve()
        self.host.revoke_from_trusted_native_action(approval_id,self.event)
        with self.assertRaises(PermissionError):
            self.auditor.reopen_and_verify(approval_id)
        with self.ledger._db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM native_proxy_scene_audits").fetchone()[0],0)

    def test_unbounded_audit_budget_refused_even_with_valid_source(self):
        approval_id=self.approve()
        for budget in (0,True,65537):
            with self.subTest(budget=budget):
                with self.assertRaises(ValueError):
                    self.auditor.reopen_and_verify(approval_id,ram_mb=budget)


if __name__=="__main__":
    unittest.main()
