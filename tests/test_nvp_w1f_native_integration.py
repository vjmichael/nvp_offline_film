"""W1-F consolidated regression contracts.

This file has no physical microphone, creator approval or simulated OS
isolation success. Windows-only cases use the REAL Windows DPAPI + AES-GCM
G03 film vault, not a fake encryption provider. Linux asserts explicit denial
of private-film native worker admission until independent confinement exists.

Installed PyInstaller/AppContainer and 30-180-minute owner acceptance require
the separate native W1-F installed matrix, not a synthetic pass from here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.nvp_g03_live_store import LiveFilmStore,LiveFilmError
from backend.nvp_g09e_sealed_delivery import SealedFilmDelivery
from backend.nvp_g09e_sealed_worker import (
    ProtectedFilmReelError,ProtectedSealedReelWorker)
from backend.nvp_g09e_chunk import (
    FRAMES_PER_CHUNK,MAX_FRAMES,chunk_bounds)
from tools.nvp_w1e_sealed_reel_worker import main as fixed_child


PID="ee"*16
TOKEN="w1f-real-windows-director-session"
PASSWORD="W1F authentic encrypted source and native worker acceptance"
SOUND=b"\x16\x00\xff\x7f"*120000  # 5 seconds, 48 kHz mono int16
ORIGINAL_SHA=hashlib.sha256(SOUND).hexdigest()


class NativeACLReceiptContract(unittest.TestCase):
    def test_icacls_reports_success_even_with_zero_failed_files(self):
        from unittest.mock import Mock
        from backend.nvp_g03_windows_appcontainer import _acl
        with patch("backend.nvp_g03_windows_appcontainer.subprocess.run",
                   return_value=Mock(returncode=0,
                       stdout="Successfully processed 1 files; Failed processing 0 files",
                       stderr="")) as called:
            _acl("reviewed-worker.exe",
                 "S-1-15-2-100-200-300-400-500-600","R")
            self.assertTrue(called.called)

    def test_icacls_positive_failed_file_count_is_not_accepted(self):
        from unittest.mock import Mock
        from backend.nvp_g03_windows_appcontainer import _acl,AppContainerFailure
        with patch("backend.nvp_g03_windows_appcontainer.subprocess.run",
                   return_value=Mock(returncode=0,
                       stdout="Successfully processed 0 files; Failed processing 1 files",
                       stderr="")):
            with self.assertRaises(AppContainerFailure):
                _acl("reviewed-worker.exe",
                     "S-1-15-2-100-200-300-400-500-600","R")


class WindowsProfileEnvironmentContract(unittest.TestCase):
    def test_only_verified_host_localappdata_is_admitted(self):
        import tempfile
        from backend.nvp_g03_windows_appcontainer import _native_profile_environment
        with tempfile.TemporaryDirectory() as owned:
            result=_native_profile_environment(
                {"PATH":"reviewed", "LOCALAPPDATA":"ignored","TMP":"owned"},owned)
            self.assertEqual(result["LOCALAPPDATA"],str(Path(owned).resolve()))
            self.assertEqual(result["PATH"],"reviewed")
            self.assertEqual(result["TMP"],"owned")
            self.assertNotIn("NVP_HOME",result)

    def test_missing_host_localappdata_refuses_native_worker(self):
        from backend.nvp_g03_windows_appcontainer import (
            _native_profile_environment,AppContainerFailure)
        for missing in (None,"","missing-nvp-os-profile"):
            with self.assertRaises(AppContainerFailure):
                _native_profile_environment({"PATH":"reviewed"},missing)


class NativeDriveEnvironmentContract(unittest.TestCase):
    def test_fixed_windows_drive_entries_do_not_leak_workspace(self):
        from backend.nvp_g03_windows_appcontainer import _sanitized_drive_environment
        self.assertEqual(_sanitized_drive_environment(
            r"C:\hostedtoolcache\NVP.exe",r"D:\a\nvp-private-work"),
            ["=C:=C:\\","=D:=D:\\"])
        self.assertEqual(_sanitized_drive_environment(
            r"C:\Program Files\NVP\NVP.exe",r"C:\Users\owned-work"),
            ["=C:=C:\\"])

    def test_unc_paths_never_enter_private_worker_environment(self):
        from backend.nvp_g03_windows_appcontainer import (
            _sanitized_drive_environment,AppContainerFailure)
        with self.assertRaises(AppContainerFailure):
            _sanitized_drive_environment(
                r"\\other-host\unreviewed.exe",r"D:\approved-working")


class CrossPlatformSourceAndCustody(unittest.TestCase):
    def test_exact_reel_clock_and_nonzero_origin(self):
        self.assertEqual(chunk_bounds(MAX_FRAMES,0),(0,240))
        self.assertEqual(chunk_bounds(MAX_FRAMES,1),(240,480))
        self.assertEqual(chunk_bounds(MAX_FRAMES,MAX_FRAMES//240-1),
                         (MAX_FRAMES-240,MAX_FRAMES))
        self.assertEqual(FRAMES_PER_CHUNK,240)
        with self.assertRaises(ValueError):
            chunk_bounds(MAX_FRAMES,MAX_FRAMES//240)

    def test_child_cannot_run_client_selected_native_command(self):
        self.assertEqual(fixed_child(["--project",PID]),2)
        self.assertEqual(fixed_child(["--source","C:\\private.pcm"]),2)

    def test_cancelled_finalization_never_reads_original_or_writes_manifest(self):
        job=SealedFilmDelivery.__new__(SealedFilmDelivery)
        def no_read(*args,**kwargs):
            raise AssertionError("A cancelled job cannot read or publish anything")
        job._reels=no_read
        stop=threading.Event();stop.set()
        with self.assertRaises(InterruptedError):
            job._complete(PID,TOKEN,"aa"*16,{"total_chunks":1},stop)

    def test_private_worker_does_not_downgrade_linux_to_uncontained(self):
        if sys.platform!="linux":self.skipTest("Linux-specific refusal")
        class Locked:
            def _session(self,*args):
                raise AssertionError("No private source should be read")
        worker=ProtectedSealedReelWorker(Locked(),
            review_authority=lambda *args:True,
            os_isolation_attestor=lambda *args:True)
        with self.assertRaises(ProtectedFilmReelError):
            worker.render(PID,TOKEN,"aa"*16,0,1200,{}, {},
                          "review-"+("x"*32))


@unittest.skipUnless(sys.platform=="win32",
    "Actual encrypted G03 custody requires Windows DPAPI")
class WindowsAuthenticatedSealedSource(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="nvp-w1f-real-gcm-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"private"
        self.allowed={(PID,TOKEN)}
        self.host=LiveFilmStore(self.root,grant_checker=
            lambda pid,token:(pid,token) in self.allowed)
        self.host.create(PID,"Native W1F film","private idea",
            "INT. NATIVE SOURCE - DAY\n\nOne actor speaks.",PASSWORD)
        self.host.authorize(PID,PASSWORD,TOKEN)

    def assert_no_original_plaintext(self):
        for f in self.root.rglob("*"):
            if f.is_file():
                raw=f.read_bytes()
                self.assertNotIn(SOUND[:2048],raw)
                self.assertNotIn(b"INT. NATIVE SOURCE - DAY",raw)
                self.assertNotIn(b"private idea",raw)
                self.assertFalse(f.suffix in (".wav",".pcm",".db",".sqlite"))

    def test_real_aes_gcm_chunk_and_new_host_reopen(self):
        name="capture/test-w1f/chunk-0000.pcm16le"
        witness=self.host.put_original(PID,TOKEN,name,SOUND,
            media_type="audio/x-nvp-original-pcm16le")
        self.assertEqual(witness["sha256"],ORIGINAL_SHA)
        self.assertEqual(self.host.get_original(PID,TOKEN,name),SOUND)
        self.assert_no_original_plaintext()
        restarted=LiveFilmStore(self.root,grant_checker=
            lambda pid,token:(pid,token) in self.allowed)
        with self.assertRaises(LiveFilmError):
            restarted.get_original(PID,TOKEN,name)
        restarted.authorize(PID,PASSWORD,TOKEN)
        self.assertEqual(restarted.get_original(PID,TOKEN,name),SOUND)
        self.assert_no_original_plaintext()

    def test_real_worker_lease_one_use_and_revoke_before_publish(self):
        name="render/"+"a"*32+"/reel-00000-ci.avi"
        grant=self.host.worker_grant(PID,TOKEN,name,"write_original",
            human_approved=True)
        self.allowed.clear()
        with self.assertRaises(LiveFilmError):
            self.host.worker_execute(PID,grant,"write_original",name,
                data=b"Fake reel cannot be sealed")
        with self.assertRaises(LiveFilmError):
            self.host.worker_execute(PID,grant,"write_original",name,
                data=b"Replayed authority must fail")
        self.assertFalse(list((self.root/PID/"assets").glob("*.nvpsealed")))
        self.assert_no_original_plaintext()

    def test_unfinished_worker_receipt_is_not_promoted_on_restart(self):
        worker_id="d"*32
        self.host.worker_run_transition(PID,TOKEN,worker_id,
            "render/source-window",ORIGINAL_SHA,"RUNNING")
        resumed=LiveFilmStore(self.root,grant_checker=
            lambda pid,token:(pid,token) in self.allowed)
        resumed.authorize(PID,PASSWORD,TOKEN)
        changed=resumed.reconcile_interrupted_workers(PID,TOKEN)
        self.assertEqual(changed,[worker_id])
        rows=resumed.protected_worker_runs(PID,TOKEN)
        self.assertEqual(rows[0]["state"],"INTERRUPTED_UNVERIFIED")
        self.assertIsNone(rows[0]["output_sha256"])
        self.assert_no_original_plaintext()


if __name__=="__main__":
    unittest.main()
