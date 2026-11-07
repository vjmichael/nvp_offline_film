"""WO4-03 meaningful native master QC with no simulated cinema calibration."""
from hashlib import sha256
import unittest
from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_master_qc import evaluate_master_candidates

class MasterQCTests(unittest.TestCase):
    def setUp(self):
        self.source=b"\x00\x00\x00\x10\x00\x00" * 6000
        self.sound=master_pcm24_candidate(
            self.source,source_sha256=sha256(self.source).hexdigest(),
            original_take_sha256="a"*64,cinema_frames=3,
            channel_layout="stereo",creator_approved=True)
        self.rgb=b"\x00\x00\x00\x00\x0f\x00\x00\x00\xff\x0f\x00\x00"
        self.picture={
            "format":"nvp.wo4.xyz12_master_candidate.v1",
            "original_take_sha256":"a"*64,"xyz12":self.rgb,
            "xyz12_sha256":sha256(self.rgb).hexdigest(),
            "source_modified":False,
            "width":2,"height":1,"profile":"2K_FLAT_24"
        }

    def test_actual_waveform_and_pixel_metrics(self):
        result=evaluate_master_candidates(self.picture,self.sound)
        self.assertEqual(result["picture_pixel_count"],2)
        self.assertEqual(result["xyz12_component_max"],[4095,15,0])
        self.assertEqual(result["sound_frames"],3)
        self.assertGreater(result["sound_rms_fraction_full_scale"],0)
        self.assertFalse(result["sound_loudness_lufs_measured"])
        self.assertFalse(result["production_master_accepted"])

    def test_tampering_in_either_derived_master_refused(self):
        pic=dict(self.picture,xyz12=self.rgb[:-2]+b"\x01\x00")
        with self.assertRaises(PermissionError):
            evaluate_master_candidates(pic,self.sound)
        snd=dict(self.sound,original_take_sha256="b"*64)
        with self.assertRaises(PermissionError):
            evaluate_master_candidates(self.picture,snd)
        snd=dict(self.sound,master_pcm_sha256="f"*64)
        with self.assertRaises(PermissionError):
            evaluate_master_candidates(self.picture,snd)

    def test_signed_pcm_bounds_are_enforced(self):
        pic=dict(self.picture,xyz12=b"\xff\xff"+self.rgb[2:],
                 xyz12_sha256=sha256(b"\xff\xff"+self.rgb[2:]).hexdigest())
        with self.assertRaises(ValueError):
            evaluate_master_candidates(pic,self.sound)

if __name__=="__main__":
    unittest.main()
