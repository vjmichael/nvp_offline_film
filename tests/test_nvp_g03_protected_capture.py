"""G03-F2: protected microphone contract, cancellation and consent refusal.

Unattended CI never records real audio or makes a synthetic microphone look
physical. Positive hardware acceptance requires an explicit owner-operated
Windows microphone permission, and must preserve original PCM encrypted.
"""
from __future__ import annotations

import secrets
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.nvp_g03_protected_capture_worker import _validate
from backend.nvp_g03_protected_capture_supervisor import (
    ProtectedCaptureSupervisor,ProtectedCaptureError)
from backend.nvp_g03_live_store import LiveFilmStore


class CaptureProtocolTests(unittest.TestCase):
    def test_exact_request_contract_and_bounded_sample_count(self):
        self.assertEqual(_validate({
            "device_id":-1,"channels":1,"frames":48000})["frames"],48000)
        for request in (
            {"device_id":0,"channels":2,"frames":48000,"path":"x.pcm"},
            {"device_id":0,"channels":1,"frames":48000,"key":"secret"},
            {"device_id":0,"channels":1,"frames":48000,"script":"cmd"},
            {"device_id":0,"channels":1,"frames":500000},
            {"device_id":0,"channels":1,"frames":0},
            {"device_id":0,"channels":3,"frames":1000},
            {"device_id":"0","channels":1,"frames":1000},
            {"device_id":0,"channels":1,"frames":float("nan")},
        ):
            with self.subTest(request=str(request)),self.assertRaises(ValueError):
                _validate(request)


@unittest.skipUnless(sys.platform=="win32","Requires real Windows DPAPI")
class NativeCaptureConsentWindows(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="g03-capture-refusal-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"secured"
        self.store=LiveFilmStore(self.root)
        self.pid=secrets.token_hex(16)
        self.token="nvp-trusted-owner-"+secrets.token_hex(24)
        self.password="G03 test-only opt-in microphone capture phrase"
        self.store.create(self.pid,"Native microphone","", "",self.password)
        self.store.authorize(self.pid,self.password,self.token)
        self.ticket="reviewed-microphone-request-"+secrets.token_hex(20)

    def test_native_refusal_prevents_worker_launch_and_pcm(self):
        observed=[]
        host=ProtectedCaptureSupervisor(
            self.store,review_authority=lambda *scope:scope[-1]==self.ticket,
            native_os_prompt=lambda *scope:observed.append(scope) or False)
        with patch("backend.nvp_g03_protected_capture_supervisor.launch_contained",
                   side_effect=AssertionError("denied recording launched")):
            with self.assertRaisesRegex(ProtectedCaptureError,"refused"):
                host.capture(self.pid,self.token,"original/mic.pcm16le",
                             self.ticket,device_id=-1,channels=1,frames=48000)
        self.assertEqual(len(observed),1)
        self.assertEqual(observed[0][0],self.pid)
        self.assertEqual(self.store.read(self.pid,self.token)["source_assets"],[])
        self.assertEqual(self.store.protected_worker_runs(self.pid,self.token),[])
        self.assertEqual(list((self.root/self.pid/"assets").glob("*.nvpsealed")),[])

    def test_review_refusal_and_revoked_host_session_prevent_launch(self):
        host=ProtectedCaptureSupervisor(
            self.store,review_authority=lambda *scope:False,
            native_os_prompt=lambda *scope:(_ for _ in ()).throw(
                AssertionError("OS microphone prompt despite denied review")))
        with self.assertRaisesRegex(ProtectedCaptureError,"review"):
            host.capture(self.pid,self.token,"original/mic.pcm16le",
                         self.ticket,device_id=-1,channels=1,frames=48000)
        allowed=ProtectedCaptureSupervisor(
            self.store,review_authority=lambda *scope:True,
            native_os_prompt=lambda *scope:True)
        self.store.revoke(self.pid)
        with patch("backend.nvp_g03_protected_capture_supervisor.launch_contained",
                   side_effect=AssertionError("locked movie launched audio")):
            with self.assertRaisesRegex(Exception,"locked|unavailable"):
                allowed.capture(self.pid,self.token,"original/mic.pcm16le",
                                self.ticket,device_id=-1,channels=1,frames=48000)
        self.assertFalse(self.store.exists(self.pid) is False)


if __name__=="__main__":
    unittest.main()
