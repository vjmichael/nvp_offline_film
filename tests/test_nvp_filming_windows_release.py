"""DA-03 filming is actually release-fenced on Windows; never PID admission.

These native fixtures launch a real Python recording worker in a genuine
suspended->assigned Windows Job, hold the original filming host lease,
then verify shutdown-before-source publication and all-slots upgrade denial.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_filming_windows_session import launch_windows_filming_session
from backend.nvp_filming_host_bridge import finish_windows_recording_and_freeze
from backend.nvp_w1g_release_gate import WindowsReleaseMutationGate


class FakeOriginalCapture:
    def __init__(self):
        self.events=[]
    def capture(self,project_id,take_id,*,recordings,**options):
        self.events.append(("publish",project_id,take_id,options))
        chunks=list(recordings[0]["pcm_chunks"])
        if chunks!=[b"\x12\x34"]:
            raise RuntimeError("Original PCM stream lost during OS shutdown")
        return {"status":"SOURCE_PUBLICATION_FIXTURE_ONLY",
                "original_pcm_verified":True,
                "real_film_index_published":False}


@unittest.skipUnless(os.name=="nt","Native Windows original filmmaking kernel acceptance")
class WindowsOriginalFilmingCustodyTests(unittest.TestCase):
    def launch(self,root,out,err):
        return launch_windows_filming_session(
            root, [sys.executable,"-S","-c","import time;time.sleep(45)"],
            cwd=root,stdout=out,stderr=err,memory_mb=512)

    def test_native_job_release_gate_and_frozen_pcm_publication_order(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with (root/"stdout").open("wb") as out,(root/"stderr").open("wb") as err:
                session=self.launch(root,out,err)
                try:
                    self.assertIsNone(session.process.poll())
                    with self.assertRaises(PermissionError):
                        with WindowsReleaseMutationGate():
                            self.fail("Live original filming process must block release swap")
                    capture=FakeOriginalCapture()
                    with patch("backend.nvp_filming_host_bridge.NativeSceneSoundCapture",FakeOriginalCapture):
                        result=finish_windows_recording_and_freeze(
                            session,capture,"project","take",
                            recordings=lambda:[{"pcm_chunks":iter((b"\x12\x34",)),
                                                "start_tick":0}],
                            scene_id="source_scene")
                    self.assertTrue(result["original_pcm_verified"])
                    self.assertEqual(capture.events[0][0],"publish")
                    self.assertTrue(session._stopped and session._closed)
                    self.assertIsNone(session.process._job)
                    self.assertIsNone(session.process._release_slot)
                    with WindowsReleaseMutationGate() as claim:
                        self.assertTrue(claim.held)
                finally:
                    session.close()

    def test_broken_capture_still_kills_tree_and_releases_lease(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with (root/"out").open("wb") as out,(root/"err").open("wb") as err:
                session=self.launch(root,out,err)
                with self.assertRaisesRegex(TypeError,"capture service"):
                    finish_windows_recording_and_freeze(
                        session,object(),"project","take",recordings=lambda:[])
                self.assertTrue(session._closed and session._stopped)
                with WindowsReleaseMutationGate() as gate:
                    self.assertTrue(gate.held)

    def test_losing_original_host_lease_never_reconstructs_ownership(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with (root/"out").open("wb") as out,(root/"err").open("wb") as err:
                session=self.launch(root,out,err)
                try:
                    with self.assertRaises(RuntimeError):
                        self.launch(root,out,err)
                    self.assertIsNone(session.process.poll())
                finally:
                    session.close()


if __name__=="__main__":
    unittest.main()
