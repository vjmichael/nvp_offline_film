"""WO4-04/05 real FilmIndex source-custody and delivery denial tests."""
from hashlib import sha256
import unittest
from unittest.mock import patch
from pathlib import Path
from test_nvp_wo3_native_delivery import WO3OriginalCinemaAuthoring
from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_master_qc import evaluate_master_candidates
from backend.nvp_wo4_mastering_decision import register_mastering_decision
from backend.nvp_wo4_master_delivery import publish_mastered_dcp


class WO4SourceCustody(unittest.TestCase):
    def setUp(self):
        fixture=WO3OriginalCinemaAuthoring(
            "test_real_smpte_package_metadata_is_written_and_reopened")
        fixture.setUp()
        self.addCleanup(fixture.tmp.cleanup)
        self.f=fixture
        self.src=b"\x00\x00\x00\x18\x00\x00" * 6000
        self.sound=master_pcm24_candidate(
            self.src,source_sha256=sha256(self.src).hexdigest(),
            original_take_sha256=fixture.sha,cinema_frames=3,
            channel_layout="stereo",creator_approved=True)
        xyz=b"\x00\x00\x00\x00\x00\x00" * 2
        self.picture={
            "format":"nvp.wo4.xyz12_master_candidate.v1",
            "original_take_sha256":fixture.sha,
            "xyz12":xyz,"xyz12_sha256":sha256(xyz).hexdigest(),
            "source_modified":False,"production_picture_accepted":False,
            "profile":"2K_FLAT_24","width":2,"height":1
        }
        self.qc=evaluate_master_candidates(self.picture,self.sound)

    def authorize(self,**change):
        fields=dict(index=self.f.index,pid=self.f.pid,
                    take_id="FrozenFixture",take_revision=1,
                    take_sha256=self.f.sha,picture=self.picture,
                    sound=self.sound,qc=self.qc,
                    decision_id="ApprovedCinemaMaster",
                    approve=lambda _:True)
        fields.update(change)
        return register_mastering_decision(**fields)

    def test_creator_decision_is_new_immutable_take_bound_presentation(self):
        result=self.authorize()
        self.assertEqual(result["status"],"MASTERING_DECISION_RECORDED")
        saved=self.f.index.read_revision(self.f.pid,"ApprovedCinemaMaster",1)
        self.assertEqual(saved["kind"],"presentation")
        self.assertEqual(saved["dependencies"][0]["role"],"source_take")
        self.assertEqual(saved["data"]["source_take_sha256"],self.f.sha)
        self.assertFalse(saved["data"]["production_master_accepted"])
        self.assertEqual(self.f.index.read_revision(
            self.f.pid,"FrozenFixture",1)["document_sha256"],self.f.sha)

    def test_denied_decision_never_registers_presentation(self):
        result=self.authorize(approve=lambda _:False)
        self.assertEqual(result["status"],"DENIED")
        self.assertNotIn("ApprovedCinemaMaster", [
            r["object_id"] for r in self.f.index.list_objects(self.f.pid,
                                                               kind="presentation")])

    def test_successful_bridge_passes_exact_master_bytes_to_native_interfaces(self):
        self.authorize()
        frames_seen=[]
        with patch("backend.nvp_wo4_master_delivery.encode_xyz12_frame",
                   side_effect=lambda _encoder,xyz,**opts:(
                       frames_seen.append(xyz) or
                       {"codestream_sha256":"1"*64})) as encoded, \
             patch("backend.nvp_wo4_master_delivery.wrap_cinema_picture",
                   return_value={"sha256":"2"*64}) as wrapped_picture, \
             patch("backend.nvp_wo4_master_delivery.wrap_cinema_pcm",
                   return_value={"sha256":"3"*64}) as wrapped_audio, \
             patch("backend.nvp_wo4_master_delivery.publish_dcp_candidate",
                   return_value={"status":"STRUCTURAL_DCP_CANDIDATE_PUBLISHED"}) as package:
            output=publish_mastered_dcp(
                self.f.index,self.f.pid,take_id="FrozenFixture",
                take_revision=1,take_sha256=self.f.sha,
                mastering_decision_id="ApprovedCinemaMaster",
                pictures=[self.picture]*3,sound=self.sound,
                encoder=None,wrapper=None,info=None,
                output_root=self.f.output,title="Verified Film",
                approve_package=lambda _:True)
        self.assertEqual(frames_seen,[self.picture["xyz12"]]*3)
        self.assertEqual(encoded.call_count,3)
        self.assertEqual(wrapped_audio.call_args.kwargs["wav_bytes"]
                         if "wav_bytes" in wrapped_audio.call_args.kwargs
                         else wrapped_audio.call_args.args[2],
                         self.sound["wav_bytes"])
        self.assertTrue(package.called)
        self.assertEqual(output["picture_codestream_sha256"],["1"*64]*3)
        self.assertFalse(output["production_master_accepted"])

    def test_delivery_requires_authorized_decision_and_pcm_sha(self):
        base=dict(index=self.f.index,pid=self.f.pid,
                  take_id="FrozenFixture",take_revision=1,
                  take_sha256=self.f.sha,
                  mastering_decision_id="ApprovedCinemaMaster",
                  pictures=[self.picture]*3,sound=self.sound,
                  encoder=None,wrapper=None,info=None,
                  output_root=self.f.output,
                  title="Verified Film",approve_package=lambda _:True)
        with self.assertRaises(KeyError):
            publish_mastered_dcp(**base)
        self.authorize()
        modified=dict(self.sound,master_pcm_sha256="f"*64)
        with self.assertRaises(PermissionError):
            publish_mastered_dcp(**dict(base,sound=modified))
        changed=dict(self.picture,xyz12_sha256="0"*64)
        with self.assertRaises(PermissionError):
            publish_mastered_dcp(**dict(base,pictures=[changed]*3))


if __name__=="__main__":
    unittest.main()
