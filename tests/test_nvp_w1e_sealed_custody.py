"""W1-E SOURCE contract fixtures; not native Windows/AppContainer acceptance.

These cases intentionally use a fake in-memory sealed-asset interface to
exercise original source identity. They do NOT claim to verify AES-GCM,
physical OS security, actual device capture, native worker isolation or AVI.
Native tests must independently cover those boundaries before release.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch

from backend.nvp_g06_sealed_capture import (
    _schema,VerifiedSealedPCM,original_identity,FORMAT)
from backend.nvp_g06_chunked_capture import FORMAT as TAKE_FORMAT
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class FakeSealedHost:
    def __init__(self,pid,assets):
        self.pid=pid
        self.assets=assets
        self.enabled=True
    def _session(self,pid,token):
        if not self.enabled or pid!=self.pid or token!="trusted-session":
            raise PermissionError("Sealed host is locked")
        return object()
    def get_original(self,pid,token,name):
        self._session(pid,token)
        return self.assets[name]


class SealedSourceReadbackTests(unittest.TestCase):
    def setUp(self):
        self.pid="a"*32;self.scene="SC_"+"b"*12
        self.recording="c"*32;self.clip="d"*32
        self.db=sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory=sqlite3.Row
        _schema(self.db)
        self.db.execute("""CREATE TABLE g06_original_pcm(
            id TEXT PRIMARY KEY,project_id TEXT,scene_id TEXT,
            actor_id TEXT,pcm_sha256 TEXT,sample_count INTEGER,pcm BLOB)""")
        self.first=b"\x01\x00"*1000
        self.last=b"\x02\x00"*1500
        whole=self.first+self.last
        parts=[{"clip_id":self.clip,"first_sample":0,"sample_count":2500,
                "pcm_sha256":digest(whole)}]
        doc={"format":TAKE_FORMAT,"recording_id":self.recording,
            "project_id":self.pid,"scene_id":self.scene,
            "actor_id":None,"sample_rate":48000,"channels":1,
            "sample_count":2500,"original_pcm_sha256":digest(whole),
            "segments":parts}
        manifest=json.dumps(doc,sort_keys=True,separators=(",",":"),
                            ensure_ascii=False,allow_nan=False)
        self.db.execute("""INSERT INTO g06_long_recording_manifests(
            recording_id,project_id,scene_id,actor_id,session_id,
            sample_count,original_sha256,segments_json,manifest_sha256,
            recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (self.recording,self.pid,self.scene,None,self.recording,
             2500,digest(whole),manifest,digest(manifest.encode()),"then"))
        self.db.execute("""INSERT INTO g06_original_pcm VALUES(?,?,?,?,?,?,?)""",
            (self.clip,self.pid,self.scene,None,digest(whole),2500,b""))
        self.db.execute("""INSERT INTO w1e_sealed_clip_members VALUES(?,?,?,?,?,?,?)""",
            (self.clip,self.recording,self.pid,self.scene,0,2500,digest(whole)))
        assets={}
        for index,(offset,piece) in enumerate([(0,self.first),(1000,self.last)]):
            name=f"capture/{self.recording}/chunk-{index:04d}.pcm16le"
            assets[name]=piece
            self.db.execute("""INSERT INTO w1e_capture_chunks VALUES(?,?,?,?,?,?,?)""",
                (self.pid,self.recording,index,offset,len(piece)//2,name,digest(piece)))
        self.host=FakeSealedHost(self.pid,assets)

    def test_original_samples_cross_encrypted_chunk_boundaries(self):
        pcm=VerifiedSealedPCM(self.host,"trusted-session",self.db,self.pid,
                              self.scene,self.clip)
        self.assertEqual(len(pcm),5000)
        self.assertEqual(pcm[:8],self.first[:8])
        self.assertEqual(pcm[1996:2004],self.first[-4:]+self.last[:4])
        self.assertEqual(pcm.verified_sha256,digest(self.first+self.last))
        self.assertEqual(original_identity(self.db,self.pid,self.scene,self.clip)[
            "recording_source_start_sample"],0)

    def test_sealed_source_cannot_become_silence_when_locked(self):
        pcm=VerifiedSealedPCM(self.host,"trusted-session",self.db,self.pid,
                              self.scene,self.clip)
        pcm[:2]
        self.host.enabled=False
        with self.assertRaises(PermissionError):
            _=pcm[:2]

    def test_modified_sealed_part_refused(self):
        pcm=VerifiedSealedPCM(self.host,"trusted-session",self.db,self.pid,
                              self.scene,self.clip)
        self.host.assets[f"capture/{self.recording}/chunk-0001.pcm16le"]=b"\x00"*3000
        with self.assertRaises(RuntimeError):
            _=pcm[1996:2004]

    def test_missing_group_member_refused(self):
        self.db.execute("""DELETE FROM w1e_sealed_clip_members
            WHERE clip_id=?""",(self.clip,))
        self.assertIsNone(original_identity(self.db,self.pid,self.scene,self.clip))
        with self.assertRaises(RuntimeError):
            VerifiedSealedPCM(self.host,"trusted-session",self.db,
                              self.pid,self.scene,self.clip)


class NativeScopedReviewTests(unittest.TestCase):
    def make_bridge(self):
        class NativeWindow:
            def __init__(self):self.url="http://127.0.0.1:54211/"
            def get_current_url(self):return self.url
            def create_confirmation_dialog(self,title,description):
                return "Source and approved decisions SHA-256" in description
        bridge=TrustedDesktopCameraBridge.__new__(TrustedDesktopCameraBridge)
        bridge.origin="http://127.0.0.1:54211"
        bridge.window=NativeWindow()
        bridge._closing=False
        bridge._lock=threading.RLock()
        bridge._private_film_grants={}
        return bridge

    def test_one_use_exact_film_scope(self):
        bridge=self.make_bridge()
        scope={"project_id":"a"*32,"edit_revision":4,
               "source_sha256":"b"*64,"total_frames":1200}
        proof=bridge.native_private_film_review(scope)
        self.assertTrue(proof["approved"])
        ticket=proof["native_approval_id"]
        self.assertFalse(bridge.consume_private_film_review(
            scope["project_id"],4,"c"*64,1200,ticket))
        self.assertFalse(bridge.consume_private_film_review(
            scope["project_id"],4,"b"*64,1200,ticket))
        receipt=bridge.native_private_film_review(scope)
        self.assertTrue(bridge.consume_private_film_review(
            scope["project_id"],4,"b"*64,1200,receipt["native_approval_id"]))
        self.assertFalse(bridge.consume_private_film_review(
            scope["project_id"],4,"b"*64,1200,receipt["native_approval_id"]))

    def test_cross_origin_approval_refused(self):
        bridge=self.make_bridge()
        bridge.window.url="https://example.invalid/"
        with self.assertRaises(PermissionError):
            bridge.native_private_film_review({
                "project_id":"a"*32,"edit_revision":2,
                "source_sha256":"b"*64,"total_frames":1200})


class PrivateWorkerAdmissionTests(unittest.TestCase):
    def test_windows_kernel_isolation_cannot_downgrade_to_uncontained_worker(self):
        from backend.nvp_g09e_sealed_worker import (
            ProtectedFilmReelError,ProtectedSealedReelWorker)
        class FakeLocked:
            def _session(self,*args):
                raise AssertionError("Never touch protected source without OS admission")
        worker=ProtectedSealedReelWorker(
            FakeLocked(),review_authority=lambda *x:True,
            os_isolation_attestor=lambda *x:True)
        with patch("backend.nvp_g09e_sealed_worker.sys.platform","linux"):
            with self.assertRaises(ProtectedFilmReelError):
                worker.render("a"*32,"token","b"*32,0,1200,
                              None,None,"ticket-"+("c"*32))

    def test_fixed_private_child_refuses_arbitrary_arguments(self):
        from tools.nvp_w1e_sealed_reel_worker import main
        self.assertEqual(main(["--script","user-project.py"]),2)

    def test_native_review_preview_is_an_exact_four_field_scope(self):
        from backend.nvp_g09e_sealed_delivery import SealedFilmDelivery
        from backend.nvp_g08_native_avi import TICKS_FRAME
        from backend.nvp_g09e_chunk import REQUIRED_DIGESTS
        class FakeAccess:
            def permitted(self,*args,**kwargs):return True
        class FakeLive:
            def exists(self,pid):return True
            def _session(self,pid,token):return b"not-a-real-key"
        store=SealedFilmDelivery(object(),FakeLive(),
            access=lambda:FakeAccess(),
            review_authority=lambda *args:True,
            os_isolation_attestor=lambda *args:True)
        assembly={"duration_tick":1200*TICKS_FRAME,
                  **{name:"a"*64 for name in REQUIRED_DIGESTS}}
        with patch("backend.nvp_g09e_sealed_delivery.G07Editor") as editor:
            editor.return_value.view.return_value={
                "revision":5,"duration_seconds":50,
                "missing_sources":[]}
            editor.return_value.native_assembly.return_value=assembly
            scope=store.preview("b"*32,"cookie",5)
        self.assertEqual(set(scope),{
            "project_id","edit_revision","source_sha256","total_frames"})
        self.assertEqual(scope["total_frames"],1200)
        self.assertEqual(scope["edit_revision"],5)


if __name__=="__main__":
    unittest.main()
