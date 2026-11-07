"""WO4 native real OpenUSD Take→graded XYZ12 + PCM24→DCP→full decode.

Runs only with real SHA-pinned OpenJPEG/asdcplib executables on dedicated
native Linux acceptance, not through a mock codec or invented file. Uses
three *different* approved image frames at 2K Flat resolution.
"""
import hashlib
import os
from pathlib import Path
import struct
import unittest

from test_nvp_wo3_native_delivery import WO3OriginalCinemaAuthoring
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary
from backend.nvp_wo3_independent_essence import decode_full_dcp_candidate
from backend.nvp_wo4_xyz12_master import encode_linear_rgb_d65_to_xyz12
from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_master_qc import evaluate_master_candidates
from backend.nvp_wo4_mastering_decision import register_mastering_decision
from backend.nvp_wo4_master_delivery import publish_mastered_dcp

NEEDED={
    "NVP_NATIVE_OPENJPEG":"OpenJPEG-opj_compress",
    "NVP_NATIVE_OPENJPEG_DECODE":"OpenJPEG-opj_decompress",
    "NVP_NATIVE_ASDCP_WRAP":"ASDCP-asdcp_wrap",
    "NVP_NATIVE_ASDCP_INFO":"ASDCP-asdcp_info",
    "NVP_NATIVE_ASDCP_UNWRAP":"ASDCP-asdcp_unwrap",
}


@unittest.skipUnless(all(os.environ.get(key) for key in NEEDED),
                     "Real reviewed native codec and wrapper binaries required")
class WO4RealMasterToCinema(unittest.TestCase):
    def codec(self,key):
        file=Path(os.environ[key]).resolve(strict=True)
        return ApprovedCodecBinary(file,product=NEEDED[key],
                                   sha256=hashlib.sha256(file.read_bytes()).hexdigest())

    def test_distinct_source_color_frames_real_mxf_full_decode(self):
        fixture=WO3OriginalCinemaAuthoring(
            "test_real_smpte_package_metadata_is_written_and_reopened")
        fixture.setUp()
        try:
            take_sha=fixture.sha
            images=[]
            # Real little-endian scene-linear source pixels; no stored J2K
            # frames or arbitrary movie/video inputs stand in for a Take.
            for rgb in ((0.05,0.08,0.02),(0.20,0.06,0.07),
                        (0.07,0.16,0.15)):
                original=struct.pack("<fff",*rgb)*(1998*1080)
                picture=encode_linear_rgb_d65_to_xyz12(
                    original,profile="2K_FLAT_24",
                    source_sha256=hashlib.sha256(original).hexdigest(),
                    original_take_sha256=take_sha,
                    creator_approved=True)
                images.append(picture)
            assert len({im["xyz12_sha256"] for im in images})==3
            audio=b"\x00\x00\x00\x00\x04\x00"*6000
            sound=master_pcm24_candidate(
                audio,source_sha256=hashlib.sha256(audio).hexdigest(),
                original_take_sha256=take_sha,cinema_frames=3,
                channel_layout="stereo",creator_approved=True)
            qc=evaluate_master_candidates(images[0],sound)
            decision=register_mastering_decision(
                fixture.index,fixture.pid,take_id="FrozenFixture",
                take_revision=1,take_sha256=take_sha,
                picture=images[0],ordered_pictures=images,
                sound=sound,qc=qc,decision_id="RealWO4NativeDecision",
                approve=lambda scope:scope["source_take_sha256"]==take_sha)
            self.assertEqual(decision["status"],"MASTERING_DECISION_RECORDED")
            delivery=publish_mastered_dcp(
                fixture.index,fixture.pid,take_id="FrozenFixture",
                take_revision=1,take_sha256=take_sha,
                mastering_decision_id="RealWO4NativeDecision",
                pictures=images,sound=sound,
                encoder=self.codec("NVP_NATIVE_OPENJPEG"),
                wrapper=self.codec("NVP_NATIVE_ASDCP_WRAP"),
                info=self.codec("NVP_NATIVE_ASDCP_INFO"),
                output_root=fixture.output,title="WO4 Native Master",
                approve_package=lambda scope:True)
            self.assertEqual(delivery["status"],
                             "STRUCTURAL_DCP_CANDIDATE_PUBLISHED")
            result=decode_full_dcp_candidate(
                delivery["dcp_receipt"]["destination"],
                unwrap=self.codec("NVP_NATIVE_ASDCP_UNWRAP"),
                decoder=self.codec("NVP_NATIVE_OPENJPEG_DECODE"),
                expected_picture_codestream_sha256=
                    delivery["picture_codestream_sha256"],
                expected_sound_pcm_sha256=sound["master_pcm_sha256"],
                profile="2K_FLAT_24",expected_frames=3)
            self.assertEqual(result["frames_decoded"],3)
            self.assertEqual(len(set(result["decoded_frame_sha256"])),3)
            self.assertTrue(result["pcm24_48000_sample_exact"])
            self.assertFalse(result["production_dcp_accepted"])
            self.assertEqual(fixture.index.read_revision(
                fixture.pid,"FrozenFixture",1)["document_sha256"],take_sha)
            print("WO4_REAL_DISTINCT_2K_MXF_MASTER:",{
                "take_sha256":take_sha,
                "decoded_frame_sha256":result["decoded_frame_sha256"],
                "exact_source_pcm":True,
                "full_cinema_compliance":False},flush=True)
        finally:
            fixture.tmp.cleanup()


if __name__=="__main__":
    unittest.main()
