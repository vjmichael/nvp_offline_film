"""G03-F1: genuine Windows contained native OpenUSD staging acceptance.

These tests MUST run with real pywin32 Job Objects and pxr; no fake process,
no mocked renderer, no disk-plaintext fallback. On Linux they are skipped
because the encrypted host currently requires Windows DPAPI and Job custody.
"""
import hashlib
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_g03_live_store import LiveFilmStore, LiveFilmError
from backend.nvp_g03_protected_scene_supervisor import (
    ProtectedSceneSupervisor, ProtectedWorkerError, SYNTHETIC_SCENE_CI_USDA
)

PID="a2"*16
PASS="G03 native protected production worker test passphrase"
SOURCE=b'#usda 1.0\n\ndef Xform "Original" {}\n'


@unittest.skipUnless(sys.platform=="win32","Requires Windows DPAPI + actual Job Object")
class ProtectedSceneTests(unittest.TestCase):
    def setUp(self):
        from pxr import Sdf
        import win32job
        self.temp=tempfile.TemporaryDirectory(prefix="g03-native-scene-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"secured"
        self.sessions=set()
        self.store=LiveFilmStore(
            self.root,grant_checker=lambda pid,token:(pid,token) in self.sessions)
        self.store.create(PID,"Protected scene","", "",PASS)
        self.token="trusted-host-scene-"+("3"*32)
        self.sessions.add((PID,self.token))
        self.store.authorize(PID,PASS,self.token)
        self.store.put_original(PID,self.token,"original/scene.usda",SOURCE)
        self.tickets={"approved-native-"+("1"*32)}
        def check(pid,source,target,ticket):
            if (pid!=PID or source!="original/scene.usda" or
                target!="review/camera-coverage.usda" or ticket not in self.tickets):
                return False
            self.tickets.remove(ticket)
            return True
        self.supervisor=ProtectedSceneSupervisor(self.store,review_authority=check)

    @unittest.skipUnless(os.environ.get("NVP_G03_NATIVE_SANDBOX_PROBE"),
                         "Native MSVC kernel sandbox probe required")
    def test_real_appcontainer_native_scene_reopens_encrypted_output(self):
        native=ProtectedSceneSupervisor(
            self.store,review_authority=self.supervisor.review_authority,
            os_isolation_attestor=lambda pid,source,target:True)
        result=native.run(
            PID,self.token,"original/scene.usda",
            "review/camera-coverage.usda","approved-native-"+("1"*32))
        self.assertEqual(result["state"],"SUCCEEDED")
        self.assertEqual(result["frames_rendered"],0)
        self.assertTrue(result["encrypted_output"])
        self.assertTrue(result["native_job_tree_exited"])
        scene=self.store.get_original(PID,self.token,"review/camera-coverage.usda")
        from pxr import Sdf,Usd
        stage_layer=Sdf.Layer.CreateAnonymous("kernel-verified-scene.usda")
        self.assertTrue(stage_layer.ImportFromString(scene.decode("utf8")))
        stage=Usd.Stage.Open(stage_layer)
        for view in ("Wide","Medium","CloseUp"):
            self.assertTrue(stage.GetPrimAtPath("/NVP_Coverage/"+view))
        self.assertEqual(self.store.get_original(PID,self.token,"original/scene.usda"),SOURCE)
        self.assertEqual(self.store.protected_worker_runs(PID,self.token)[0]["state"],
                         "SUCCEEDED")

    def test_private_scene_refused_before_worker_and_source_grants(self):
        self.assertEqual(SOURCE, SYNTHETIC_SCENE_CI_USDA)
        with patch("backend.nvp_g03_protected_scene_supervisor.launch_contained",
                   side_effect=AssertionError("Unconfined private worker spawned")):
            with self.assertRaisesRegex(ProtectedWorkerError,"AppContainer"):
                self.supervisor.run(
                    PID,self.token,"original/scene.usda",
                    "review/camera-coverage.usda",
                    "approved-native-"+("1"*32))
        self.assertEqual(len(self.tickets),1)
        self.assertEqual(self.store.protected_worker_runs(PID,self.token),[])
        self.assertEqual(len(self.store.read(PID,self.token)["source_assets"]),1)

    @unittest.skipUnless(os.environ.get("GITHUB_ACTIONS")=="true",
                         "Only exact public synthetic fixture in CI until AppContainer")
    def test_real_native_openusd_job_delivers_encrypted_staging_and_receipts(self):
        result=self.supervisor.run(
            PID,self.token,"original/scene.usda",
            "review/camera-coverage.usda","approved-native-"+("1"*32),
            synthetic_ci_only=True)
        self.assertEqual(result["state"],"SUCCEEDED")
        self.assertTrue(result["native_job_tree_exited"])
        self.assertTrue(result["encrypted_output"])
        self.assertEqual(result["frames_rendered"],0)
        src=self.store.get_original(PID,self.token,"original/scene.usda")
        staged=self.store.get_original(PID,self.token,"review/camera-coverage.usda")
        self.assertEqual(src,SOURCE)
        from pxr import Sdf,Usd
        layer=Sdf.Layer.CreateAnonymous("verified.usda")
        self.assertTrue(layer.ImportFromString(staged.decode("utf8")))
        stage=Usd.Stage.Open(layer)
        for camera in ("Wide","Medium","CloseUp"):
            self.assertTrue(stage.GetPrimAtPath("/NVP_Coverage/"+camera))
        runs=self.store.protected_worker_runs(PID,self.token)
        self.assertEqual(len(runs),1)
        self.assertEqual(runs[0]["state"],"SUCCEEDED")
        self.assertEqual(runs[0]["output_sha256"],hashlib.sha256(staged).hexdigest())
        self.assertNotIn(b'NVP_Coverage',b"".join(
            x.read_bytes() for x in self.root.rglob("*") if x.is_file()))
        self.assertNotIn(b'Original',b"".join(
            x.read_bytes() for x in self.root.rglob("*") if x.is_file()))
        with self.assertRaises(ProtectedWorkerError):
            self.supervisor.run(
                PID,self.token,"original/scene.usda","review/camera-coverage.usda",
                "approved-native-"+("1"*32),synthetic_ci_only=True)

    @unittest.skipUnless(os.environ.get("GITHUB_ACTIONS")=="true",
                         "Only exact public synthetic fixture in CI until AppContainer")
    def test_real_os_cancellation_kills_job_and_publishes_no_output(self):
        from backend import nvp_g03_protected_scene_supervisor as module
        real_launch=module.launch_contained
        cancelled=threading.Event()
        def launch_and_cancel(*args,**kwargs):
            # This is still an actual CREATE_SUSPENDED -> AssignJob ->
            # ResumeThread child. Only notification is injected.
            proc=real_launch(*args,**kwargs)
            cancelled.set()
            return proc
        with patch.object(module,"launch_contained",side_effect=launch_and_cancel):
            with self.assertRaisesRegex(ProtectedWorkerError,"cancel"):
                self.supervisor.run(
                    PID,self.token,"original/scene.usda",
                    "review/camera-coverage.usda",
                    "approved-native-"+("1"*32),cancel=cancelled,
                    synthetic_ci_only=True)
        runs=self.store.protected_worker_runs(PID,self.token)
        self.assertEqual(len(runs),1)
        self.assertEqual(runs[0]["state"],"CANCELLED")
        self.assertEqual(self.store.read(PID,self.token)["source_assets"],
                         [{"name":"original/scene.usda","sha256":hashlib.sha256(SOURCE).hexdigest(),
                           "size_bytes":len(SOURCE),"media_type":"application/octet-stream"}])
        self.assertEqual(len(list((self.root/PID/"assets").glob("*.nvpsealed"))),1)

    @unittest.skipUnless(os.environ.get("GITHUB_ACTIONS")=="true",
                         "Only exact public synthetic fixture in CI until AppContainer")
    def test_lock_invalidates_native_grants_without_replay(self):
        self.sessions.clear()
        with self.assertRaisesRegex(LiveFilmError,"permission"):
            self.supervisor.run(
                PID,self.token,"original/scene.usda",
                "review/camera-coverage.usda",
                "approved-native-"+("1"*32),synthetic_ci_only=True)
        self.assertEqual(len(list((self.root/PID/"assets").glob("*.nvpsealed"))),1)

    def test_recover_running_worker_does_not_fake_process_tree_exit(self):
        sha=hashlib.sha256(SOURCE).hexdigest()
        run="2"*32
        self.store.worker_run_transition(
            PID,self.token,run,"original/scene.usda",sha,"RUNNING")
        cold=LiveFilmStore(
            self.root,grant_checker=lambda pid,t:(pid,t) in self.sessions)
        cold.authorize(PID,PASS,self.token)
        self.assertEqual(cold.reconcile_interrupted_workers(PID,self.token),[run])
        records=cold.protected_worker_runs(PID,self.token)
        self.assertEqual(records[0]["state"],"INTERRUPTED_UNVERIFIED")
        self.assertEqual(cold.reconcile_interrupted_workers(PID,self.token),[])


if __name__=="__main__":
    unittest.main()
