"""CONV-06/11 exact-source camera cuts, longform clocks and worker admission.

Pure negative/shape cases do not count as installed or genuine Cycles proof.
"""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path

from backend.nvp_usd_film01i_ninecam_take import (
    _checked_original_camera_cuts, FRAMES_PER_CAMERA)
from backend.nvp_p2_longform_source_plan import (
    _sequence, FRAME_TICKS, LONGFORM_FRAMES)
from backend.nvp_rig_motion import run_motion_acceptance


class SourceFilmConvergenceTests(unittest.TestCase):
    def rig(self):
        return {"cameras": [
            {"camera_shot_id": "Camera"+str(i),
             "camera_shot_sha256": format(i+1,"064x")}
            for i in range(9)]}

    def cut(self, start, stop, camera=0):
        return {"start_frame": start, "stop_frame": stop,
                "camera_shot_id": "Camera"+str(camera),
                "camera_shot_sha256": format(camera+1,"064x")}

    def test_nine_camera_edit_exact_source_shot_without_retime(self):
        cuts = _checked_original_camera_cuts(self.rig(), [
            self.cut(0,240), self.cut(240,480,3),
            self.cut(480,FRAMES_PER_CAMERA,8)])
        self.assertEqual(cuts[-1]["stop_frame"],720)
        self.assertEqual([c["camera_shot_id"] for c in cuts],
                         ["Camera0","Camera3","Camera8"])

    def test_camera_source_sha_and_frame_continuity_fail_closed(self):
        good=[self.cut(0,240),self.cut(240,720,2)]
        for broken in ([self.cut(0,241),self.cut(240,720,2)],
                       [self.cut(0,239),self.cut(240,720,2)],
                       [self.cut(0,240)],
                       [self.cut(0,720,9)],
                       [{**good[0],"camera_shot_sha256":"f"*64},good[1]]):
            with self.subTest(broken=broken):
                with self.assertRaises((ValueError,PermissionError)):
                    _checked_original_camera_cuts(self.rig(),broken)

    def test_30_minute_original_reel_exact_source_frame_and_pcm_clock(self):
        duration=LONGFORM_FRAMES*FRAME_TICKS
        segment={"segment_id":"source_original","timeline_start_tick":0,
                 "timeline_end_tick":duration,"source_in_tick":0,
                 "source_out_tick":duration,"source_take_id":"original_take",
                 "source_take_document_sha256":"a"*64,
                 "source_shot_id":"director_shot",
                 "source_shot_document_sha256":"b"*64}
        rows=list(_sequence([segment]))
        self.assertEqual(len(rows),1800)
        self.assertEqual(sum(x["frame_count"] for x in rows),43200)
        self.assertEqual(sum(x["frame_count"]*2000 for x in rows),
                         30*60*48000)
        for i,row in enumerate(rows):
            self.assertEqual(row["first_frame"],i*24)
            self.assertEqual(row["source_start_tick"],str(i*24*FRAME_TICKS))
            self.assertEqual(row["frame_count"],24)

    def test_reel_gap_overlap_or_hidden_retime_fails_closed(self):
        step=24*FRAME_TICKS
        a={"segment_id":"s0","timeline_start_tick":0,
           "timeline_end_tick":step,"source_in_tick":0,
           "source_out_tick":step,"source_take_id":"take",
           "source_take_document_sha256":"a"*64,
           "source_shot_id":None,"source_shot_document_sha256":None}
        for invalid in (
            {**a,"timeline_start_tick":1},
            {**a,"source_out_tick":step+FRAME_TICKS},
        ):
            with self.assertRaises(RuntimeError):
                list(_sequence([invalid]))
        for begin in (step-1,step+1):
            second={**a,"segment_id":"s1",
                    "timeline_start_tick":begin,
                    "timeline_end_tick":begin+step,
                    "source_in_tick":step,
                    "source_out_tick":2*step}
            with self.assertRaises(RuntimeError):
                list(_sequence([a,second]))

    def test_motion_must_refuse_unsupervised_process_even_if_blender_exists(self):
        class ApprovedMotion:
            def export(self,*_):
                return {"motion":{"approval_sha":"original","plan":{"actors":[]},"clips":{}}}
            def blender_script(self,*_):
                return "print('source-only')"
        with TemporaryDirectory() as tmp:
            with patch("backend.nvp_rig_motion.blender_available",
                       return_value={"available":True,"path":"/bin/false",
                                     "version":"untrusted"}):
                outcome=run_motion_acceptance(
                    ApprovedMotion(),"project","scene",Path(tmp)/"audit")
            self.assertEqual(outcome["status"],"blocked_protected_host_required")
            self.assertFalse((Path(tmp)/"audit"/"motion.blend").exists())


if __name__ == "__main__":
    unittest.main()
