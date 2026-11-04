"""AUDIO-02: real deterministic automation, measured loudness and creator approval."""
from pathlib import Path
import struct
import tempfile
import unittest
import wave
from unittest.mock import patch

from backend.nvp_audio02a_automation import automate_stem
from backend.nvp_audio02b_loudness_qc import measure_mix,FORMAT as QC_FORMAT
from backend.nvp_audio02c_mix_approval import (
    approve_final_mix,verify_final_mix_approval,
)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


class AudioFinishing(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.source=self.root/"source.wav"
        self.samples=48000
        with wave.open(str(self.source),"wb") as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000)
            f.writeframes(struct.pack("<hh",1000,-1000)*self.samples)

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_sample_accurate_keyframes_and_immutable_source(self):
        raw=self.source.read_bytes()
        target=self.root/"automated.wav"
        evidence=automate_stem(self.source,target,[
            {"sample":0,"gain_milli":0},
            {"sample":47999,"gain_milli":1000},
        ])
        self.assertEqual(self.source.read_bytes(),raw)
        with wave.open(str(target),"rb") as f:
            self.assertEqual(f.getnframes(),self.samples)
            first=struct.unpack("<hh",f.readframes(1))
            f.setpos(self.samples-1)
            last=struct.unpack("<hh",f.readframes(1))
        self.assertEqual(first,(0,0))
        self.assertEqual(last,(1000,-1000))
        self.assertFalse(evidence["final_master"])

    def test_invalid_automation_no_source_change(self):
        with self.assertRaises(ValueError):
            automate_stem(self.source,self.root/"bad.wav",[
                {"sample":0,"gain_milli":1000},
                {"sample":48000,"gain_milli":1000}])
        self.assertFalse((self.root/"bad.wav").exists())

    def test_loudness_measurement_native_ffmpeg(self):
        import shutil
        if not shutil.which("ffmpeg"):
            self.skipTest("FFmpeg required")
        before=self.source.read_bytes()
        result=measure_mix(self.source)
        self.assertEqual(result["format"],QC_FORMAT)
        self.assertIn("integrated_lufs",result)
        self.assertIn("true_peak_dbtp",result)
        self.assertTrue(result["measured_not_normalized"])
        self.assertEqual(self.source.read_bytes(),before)

    def test_approval_requires_real_qc_and_explicit_creator(self):
        capture=DigitalCapture(Studio(self.root/"studio.sqlite3"))
        pid=capture.studio.create_project("Mix approval","Source")["id"]
        capture.index.register_revision(pid,"rawmix","audio",
            {"final_master":False,"format":"unapproved.audio.fixture"},
            expected_revision=0,dependencies=[])
        import hashlib
        with self.source.open("rb") as f:
            sha=hashlib.file_digest(f,"sha256").hexdigest()
        qc={"format":QC_FORMAT,"source_sha256":sha,"qc_passed":True,
            "measured_not_normalized":True,"director_approved":False,
            "final_master":False}
        event=object()
        with self.assertRaises(PermissionError):
            approve_final_mix(capture,pid,"rawmix",self.source,qc,"approvedmix",
                event,verify_creator_action=lambda *_:False)
        result=approve_final_mix(capture,pid,"rawmix",self.source,qc,"approvedmix",
            event,verify_creator_action=lambda got,scope:
            got is event and scope["final_master"] is False)
        self.assertEqual(result["status"],"CREATOR_APPROVED_FINAL_MIX")
        self.assertFalse(result["final_master"])
        reopened=DigitalCapture(Studio(self.root/"studio.sqlite3"))
        verified=verify_final_mix_approval(reopened,pid,"approvedmix",self.source)
        self.assertTrue(verified["final_mix"])
        self.assertFalse(verified["final_master"])


if __name__=="__main__":
    unittest.main()
