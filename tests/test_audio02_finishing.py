"""AUDIO-02: real deterministic automation, measured loudness and creator approval."""
from pathlib import Path
import struct
import tempfile
import unittest
import wave
from unittest.mock import patch

from backend.nvp_audio02a_automation import automate_stem,sum_automated_stems
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

    def test_automated_multistem_composite_and_source_preservation(self):
        original=self.source.read_bytes()
        stem_a=self.root/"stem_a.wav"
        stem_b=self.root/"stem_b.wav"
        unity=[{"sample":0,"gain_milli":1000},
               {"sample":self.samples-1,"gain_milli":1000}]
        automate_stem(self.source,stem_a,unity)
        automate_stem(self.source,stem_b,unity)
        mixed=self.root/"mix.wav"
        report=sum_automated_stems([stem_a,stem_b],mixed)
        self.assertEqual(report["stems"],2)
        self.assertFalse(report["final_master"])
        with wave.open(str(mixed),"rb") as wav:
            self.assertEqual(wav.getnframes(),self.samples)
            self.assertEqual(struct.unpack("<hh",wav.readframes(1)),(2000,-2000))
        self.assertEqual(self.source.read_bytes(),original)
        with self.assertRaises(RuntimeError):
            sum_automated_stems([stem_a,stem_a],self.root/"duplicate.wav")

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

    def test_real_ffmpeg_qc_then_creator_approval_after_restart(self):
        import math
        import shutil
        if not shutil.which("ffmpeg"):
            self.skipTest("Real FFmpeg required")
        tone=self.root/"real_mix.wav"
        with wave.open(str(tone),"wb") as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
            payload=bytearray()
            for i in range(48000*3):
                value=int(6500*math.sin(2*math.pi*440*i/48000))
                payload.extend(struct.pack("<hh",value,value))
            w.writeframes(bytes(payload))
        qc=measure_mix(tone,target_lufs=-16.0,ceiling_dbtp=-1.0)
        self.assertTrue(qc["qc_passed"],
            "Reference stereo sine must satisfy measured technical QC")
        capture=DigitalCapture(Studio(self.root/"actual_qc.sqlite3"))
        project=capture.studio.create_project("Genuine mix","QC then approve")["id"]
        capture.index.register_revision(project,"originalmix","audio",
            {"format":"nvp.test.unapproved_mix","final_master":False},
            expected_revision=0,dependencies=[])
        event=object()
        result=approve_final_mix(capture,project,"originalmix",tone,qc,
            "genuineapprovedmix",event,
            verify_creator_action=lambda e,scope: e is event and
                scope["operation"]=="nvp.native.audio.final_mix_creator_approval")
        self.assertTrue(result["final_mix"])
        reopened=DigitalCapture(Studio(self.root/"actual_qc.sqlite3"))
        self.assertEqual(
            verify_final_mix_approval(reopened,project,"genuineapprovedmix",tone)
            ["status"],"VERIFIED_CREATOR_APPROVED_FINAL_MIX")

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
        with patch("backend.nvp_audio02c_mix_approval.measure_mix",return_value=qc):
            with self.assertRaises(PermissionError):
                approve_final_mix(capture,pid,"rawmix",self.source,qc,"approvedmix",
                    event,verify_creator_action=lambda *_:False)
        # Isolate the creator decision from costly FFmpeg in this unit;
        # the separate native QC test measures a real source through FFmpeg.
        with patch("backend.nvp_audio02c_mix_approval.measure_mix",return_value=qc):
            result=approve_final_mix(capture,pid,"rawmix",self.source,qc,"approvedmix",
                event,verify_creator_action=lambda got,scope:
                got is event and scope["final_master"] is False)
        with patch("backend.nvp_audio02c_mix_approval.measure_mix",
                   return_value={**qc,"qc_passed":False}):
            with self.assertRaisesRegex(RuntimeError,"does not match"):
                approve_final_mix(capture,pid,"rawmix",self.source,qc,
                    "anotherapproval",event,
                    verify_creator_action=lambda *_:True)
        self.assertEqual(result["status"],"CREATOR_APPROVED_FINAL_MIX")
        self.assertFalse(result["final_master"])
        reopened=DigitalCapture(Studio(self.root/"studio.sqlite3"))
        verified=verify_final_mix_approval(reopened,pid,"approvedmix",self.source)
        self.assertTrue(verified["final_mix"])
        self.assertFalse(verified["final_master"])


if __name__=="__main__":
    unittest.main()
