"""AUDIO-01K distribution filesystem and creator-custody tests."""
from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from backend.nvp_audio01j_final_av import FORMAT as AV_FORMAT
from backend.nvp_audio01k_native_host import NativeAudio01KHost
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


class Index:
    def __init__(self,sha):
        self.records={"masterav":{"kind":"master","revision":1,
            "document_sha256":"b"*64,
            "data":{"format":AV_FORMAT,"final_master":True,
                    "director_approved":True,"dcp_delivered":False,
                    "rendered_mov_sha256":sha,"frames":24},
            "dependencies":[]}}

    def read_revision(self,pid,identity,revision=None):
        if identity not in self.records:raise KeyError(identity)
        return self.records[identity]

    def register_revision(self,pid,identity,kind,doc,*,
                          expected_revision,dependencies):
        if identity in self.records:raise RuntimeError("duplicate")
        sha=hashlib.sha256(repr(doc).encode()).hexdigest()
        self.records[identity]={"kind":kind,"revision":1,"data":doc,
                                "document_sha256":sha,"dependencies":dependencies}
        return {"document_sha256":sha}


class FinalAV:
    allowed=True
    def verify_published(self,*args,**kwargs):
        if not self.allowed:raise PermissionError("Source no longer approved")
        return {"status":"VERIFIED_FINAL_AV_MASTER","final_master":True}


class DistributionTests(unittest.TestCase):
    def make(self,root):
        raw=b"reference audio and picture payload"*300
        origin=root/"source"
        origin.mkdir()
        (origin/"final_picture_sound.mov").write_bytes(raw)
        index=Index(hashlib.sha256(raw).hexdigest())
        av=FinalAV()
        ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
            0,16000,12000,0,tuple()))
        host=NativeAudio01KHost(Mock(index=index),ledger,av_host=av,
            verify_creator_action=lambda event,scope:event=="approved-action")
        return host,av,origin,raw

    def test_exact_copy_and_replay_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            host,av,origin,raw=self.make(root)
            target=root/"package"
            result=host.publish("a"*32,"masterav","delivery",origin,
                 root,root,target,"approved-action")
            self.assertFalse(result["dcp_delivered"])
            self.assertEqual((target/"feature_master.mov").read_bytes(),raw)
            self.assertEqual(host.verify("a"*32,"delivery",target,origin,root,root)[
                "status"],"VERIFIED_MEZZANINE_DISTRIBUTION")
            with self.assertRaises(PermissionError):
                host.publish("a"*32,"masterav","another",origin,
                    root,root,root/"other","approved-action")
            with (target/"feature_master.mov").open("ab") as file:
                file.write(b"changed")
            with self.assertRaises(RuntimeError):
                host.verify("a"*32,"delivery",target,origin,root,root)

    def test_revocation_denial_and_orphan(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            host,av,origin,_=self.make(root)
            av.allowed=False
            with self.assertRaises(PermissionError):
                host.publish("a"*32,"masterav","delivery",origin,
                    root,root,root/"package","approved-action")
            av.allowed=True
            with self.assertRaises(PermissionError):
                host.publish("a"*32,"masterav","delivery",origin,
                    root,root,root/"package","unapproved-action")
            (root/".package.audio01k.stage").mkdir()
            with self.assertRaises(RuntimeError):
                host.publish("a"*32,"masterav","delivery",origin,
                    root,root,root/"package","approved-action")


if __name__=="__main__":
    unittest.main()
