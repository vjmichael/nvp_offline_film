"""Original native approval-flow diagnostic; never mints or bypasses consent.

The test instruments only the private host approval verifier, and reports
source line numbers for a denied typed spec. It preserves host policy,
one-use approval identity, SHA checks, no-worker-on-refusal and all guards.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.nvp_slate_preview_cache import SlatePreviewCache
from tests.test_nvp_slate06_geometry_native import Slate06NativeTests
from tests.test_nvp_slate07_skinned_camera import RealCharacterAndLens


class NativePreviewApprovalReconciliation(unittest.TestCase):
    def _verify(self, fixture_class, method):
        fixture=fixture_class(methodName="runTest")
        fixture.setUp()
        calls=[]
        old=fixture.host.dispatcher.bindings.approval_check

        def diagnostic(frame,event,arg):
            if (frame.f_code.co_filename.endswith("nvp_slate_preview_host.py") and
                frame.f_code.co_name in ("_approval_check","_camera_approval_check")):
                if event=="return" and arg is False:
                    calls.append(("denied",frame.f_code.co_name,frame.f_lineno))
                elif event=="exception":
                    et,exc,_=arg
                    calls.append(("exception",frame.f_code.co_name,
                                  frame.f_lineno,et.__name__,str(exc)[:180]))
            return diagnostic

        def instrument(*args):
            prev=sys.gettrace()
            try:
                sys.settrace(diagnostic)
                return old(*args)
            finally:
                sys.settrace(prev)

        fixture.host.dispatcher.bindings.approval_check=instrument
        try:
            try:
                output=method(fixture)
            except (PermissionError,RuntimeError,ValueError) as exc:
                self.fail("Exact native approval rejected valid creator intent: "+
                          str(exc)+"; original verifier traces="+repr(calls[:14]))
            self.assertEqual(output["status"],"QUEUED",
                             "Expected pending, not an auto-started worker")
            self.assertTrue(calls==[], "Verifier produced a false decision: "+repr(calls))
            self.assertFalse(output.get("picture_generated",False))
        finally:
            fixture.doCleanups()

    def test_pending_reservation_is_durable_and_failed_writer_rolls_back(self):
        """An independent connection must see PENDING before OS admission.

        Atomicity cannot depend on sqlite3.close() committing: close()
        actually rolls back a still-active BEGIN IMMEDIATE transaction.
        """
        with TemporaryDirectory(prefix="nvp-preview-durable-") as root:
            project="a"*32
            cache=SlatePreviewCache(Path(root)/"cache",max_ready=1)
            key="b"*64
            source="c"*64
            recipe="d"*64
            registered=cache.reserve(
                project,key,job_id="original_preview_001",
                source_sha256=source,recipe_sha256=recipe,
                width=320,height=180)
            self.assertEqual(registered["status"],"PENDING")
            fresh=SlatePreviewCache(Path(root)/"cache",max_ready=1)
            self.assertEqual(fresh._job("original_preview_001")["state"],"PENDING")
            self.assertEqual(fresh.reserve(
                project,key,job_id="never_admitted_duplicate",
                source_sha256=source,recipe_sha256=recipe,
                width=320,height=180)["status"],"ALREADY_PENDING")
            with self.assertRaises(RuntimeError):
                with cache._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("UPDATE slate_preview_cache SET state='READY' "
                               "WHERE job_id=?",("original_preview_001",))
                    raise RuntimeError("Unverified writer died before commit")
            self.assertEqual(fresh._job("original_preview_001")["state"],"PENDING")
            cache.fail("original_preview_001",state="INTERRUPTED")
            self.assertEqual(fresh._job("original_preview_001")["state"],"INTERRUPTED")
            retry=cache.reserve(
                project,key,job_id="original_preview_002",
                source_sha256=source,recipe_sha256=recipe,
                width=320,height=180)
            self.assertEqual(retry["status"],"PENDING")
            with self.assertRaises(KeyError):
                fresh._job("original_preview_001")
            self.assertEqual(fresh._job("original_preview_002")["state"],"PENDING")

    def test_authorized_original_geometry_source(self):
        self._verify(Slate06NativeTests,
                     lambda fixture:fixture.request(camera_path="/World/Camera"))

    def test_authorized_original_pre_take_camera(self):
        self._verify(RealCharacterAndLens,
                     lambda fixture:fixture._preview())
