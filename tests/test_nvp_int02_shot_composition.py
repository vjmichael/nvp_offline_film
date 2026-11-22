"""INT-02C real SHOT-01 OpenUSD shot-layer composition at original Film Time."""
import unittest

from backend.nvp_int02_shot_composition import (
    validate_source_shot, compose_shot_snapshot,
)
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from test_nvp_openusd_shot_overrides_native import DirectorOpenUSDShotNativeTests


class Int02NativeDirectorLayerTests(unittest.TestCase):
    def setUp(self):
        # Reuse genuine FilmIndex/pxr/OpenUSD fixture without inheriting its
        # complete test suite or relying on fabricated USD metadata.
        DirectorOpenUSDShotNativeTests.setUp(self)

    def test_visibility_is_composed_from_actual_stronger_usd_layer(self):
        shot=DirectorOpenUSDShotNativeTests.publish(
            self,"INT02InvisibleChair",changes=[
                {"path":"/World/Chair","property":"visibility","value":False}
            ])
        original=OpenUSDTimeState(self.index).evaluate(
            self.project,"scene",1,"timeline",1,tick=T//2)
        take=self.index.read_revision(self.project,"frozen_take",1)
        composed=compose_shot_snapshot(
            self.index,self.project,
            take_id="frozen_take",take_sha256=take["document_sha256"],
            shot_id="INT02InvisibleChair",shot_revision=1,
            shot_sha256=shot["document_sha256"],tick=T//2,
            source_snapshot=original,listener_path="/World/Camera")
        self.assertTrue(composed["shot_composed"])
        self.assertFalse(any(x["path"]=="/World/Chair" for x in composed["objects"]))
        self.assertTrue(any(x["path"]=="/World/Chair" for x in original["objects"]))
        self.assertEqual(composed["scene_document_sha256"],
                         original["scene_document_sha256"])
        self.assertEqual(self.index.read_revision(
            self.project,"frozen_take",1)["document_sha256"],
            take["document_sha256"])

    def test_original_pcm_emitter_translation_cannot_be_falsely_mixed(self):
        shot=DirectorOpenUSDShotNativeTests.publish(
            self,"INT02MovingActor",changes=[
                {"path":"/World/Actor","property":"translation_offset",
                 "value":[1,0,0]}
            ])
        take=self.index.read_revision(self.project,"frozen_take",1)
        with self.assertRaisesRegex(RuntimeError,"acoustic"):
            validate_source_shot(
                self.index,self.project,take_id="frozen_take",
                take_sha256=take["document_sha256"],
                shot_id="INT02MovingActor",shot_revision=1,
                shot_sha256=shot["document_sha256"],
                source_in=0,source_out=T,
                listener_path="/World/Camera")

    def test_unknown_editorial_intention_is_not_silently_animated(self):
        shot=DirectorOpenUSDShotNativeTests.publish(
            self,"INT02Eyeline",changes=[
                {"path":"/World/Actor","property":"eyeline_target",
                 "value":[1,2,3]}
            ])
        take=self.index.read_revision(self.project,"frozen_take",1)
        with self.assertRaisesRegex(RuntimeError,"Unimplemented director opinion"):
            validate_source_shot(
                self.index,self.project,take_id="frozen_take",
                take_sha256=take["document_sha256"],
                shot_id="INT02Eyeline",shot_revision=1,
                shot_sha256=shot["document_sha256"],
                source_in=0,source_out=T)
