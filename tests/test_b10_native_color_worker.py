"""B10 host-only native color approval and resource-denial regression.

A synthetic OpenEXR source stands in for B9 in these POLICY tests; the
separate real Blender CI verifies actual rendered source and its FilmIndex.
"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_b10_color_worker import NativeOCIOColorWorker,SOURCE
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio


def low():
    return ResourceSnapshot(1,16384,1000,0,())


def plenty():
    return ResourceSnapshot(1,16384,12000,0,())


class NativeOCIOWorkerContracts(unittest.TestCase):
    def setUp(self):
        import OpenEXR
        import Imath
        import numpy as np
        self.tmp=TemporaryDirectory()
        root=Path(self.tmp.name)
        self.studio=Studio(root/"film.sqlite3")
        self.pid=self.studio.create_project("Color unit only","")["id"]
        self.capture=DigitalCapture(self.studio)
        self.take="unit_take"
        take=self.capture.index.register_revision(
            self.pid,self.take,"take",{"format":"unit.fake.not_rendered.v1"})
        self.take_sha=take["document_sha256"]
        raw=root/"unit_float.exr"
        h,w=64,96
        pixel=Imath.PixelType(Imath.PixelType.FLOAT)
        header=OpenEXR.Header(w,h)
        header["channels"]={c:Imath.Channel(pixel) for c in "RGBA"}
        x=np.linspace(.01,.95,w*h,dtype=np.float32)
        channels={"R":x.tobytes(),"G":(x*.8).tobytes(),
                  "B":(x*.4).tobytes(),"A":np.ones_like(x).tobytes()}
        writer=OpenEXR.OutputFile(str(raw),header)
        try:writer.writePixels(channels)
        finally:writer.close()
        self.sha=self.capture.index.put_media_file(self.pid,raw,"image/x-exr")["sha256"]
        self.presentation="unit_only_b9"
        self.capture.index.register_revision(
            self.pid,self.presentation,"presentation",
            {"format":"nvp.presentation.scene_linear_float32_exr_sequence.v1",
             "source_take_id":self.take,"source_take_sha256":self.take_sha,
             "view_transform":"Raw","render_engine":"BLENDER_WORKBENCH",
             "frames":[{"frame":1,"sha256":self.sha}]},
            dependencies=[{"object_id":self.take,"revision":1,"role":"source_take"}])
        self.event=object()
        self.scopes=[]
        self.ledger=TaskLedger(root/"resources",sampler=low)
        def creator(signal,scope):
            self.scopes.append(scope)
            return signal is self.event
        self.host=NativeOCIOColorWorker(
            self.capture,self.ledger,root/"native",verify_creator_action=creator)
        self.fake=patch(
            "backend.nvp_b10_color_worker.verify_indexed_exr_sequence",
            return_value={"frames":1,"width":96,"height":64,
                          "source_take_id":self.take,
                          "source_take_sha256":self.take_sha})
        self.fake.start()

    def tearDown(self):
        self.fake.stop()
        self.tmp.cleanup()

    def approve(self):
        return self.host.stage_and_approve(self.pid,self.presentation,1,
                                           self.event,ram_mb=2048)

    def test_browser_and_model_action_never_approve_native_color_work(self):
        with self.assertRaises(PermissionError):
            self.host.stage_and_approve(self.pid,self.presentation,1,
                                        {"browser_clicked":True},ram_mb=2048)
        self.assertEqual(self.ledger.snapshot()["tasks"],[])
        token=self.approve()
        self.assertEqual(token["state"],"QUEUED")
        self.assertFalse(token["native_worker_started"])
        self.assertEqual(self.scopes[-1]["target_color_space"],"ACEScg")
        self.assertEqual(self.scopes[-1]["input_exr_sha256"],self.sha)

    def test_low_ram_refuses_process_and_reservation(self):
        self.approve()
        with patch("backend.nvp_b10_color_worker.launch_contained",
                   side_effect=AssertionError("Color worker must not start")) as launch:
            outcome=self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(outcome["state"],"QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_tampered_staged_exr_denied_before_admission(self):
        token=self.approve()
        frame=self.host.root/token["job_id"]/SOURCE
        frame.write_bytes(frame.read_bytes()+b"modified")
        with patch("backend.nvp_b10_color_worker.launch_contained") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_unknown_os_launcher_cleanup_holds_active_reservation(self):
        token=self.approve()
        self.ledger.sampler=plenty
        with patch("backend.nvp_b10_color_worker.launch_contained",
                   side_effect=RuntimeError("launcher lost kernel handle")):
            with self.assertRaisesRegex(RuntimeError,"kernel handle"):
                self.host.run_next()
        task=self.ledger.get_task(token["job_id"])
        self.assertEqual(task["state"],"ACTIVE")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],2048)

    def test_expired_exact_creator_grant_cannot_spawn_worker(self):
        token=self.approve()
        with self.ledger._db() as db:
            db.execute("UPDATE native_b10_color_jobs SET expires_at=0 WHERE job_id=?",
                       (token["job_id"],))
        with patch("backend.nvp_b10_color_worker.launch_contained") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)


if __name__=="__main__":
    unittest.main()
