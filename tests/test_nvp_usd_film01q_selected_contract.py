"""USD-FILM-01Q pure contract regression: only selected frames/immutable edits.

No accepted Cycles pixels or fake native worker success are produced here.
"""
import unittest

from backend.nvp_usd_film01q_selected_view_host import chunk_job_id
from backend.nvp_usd_film01q_selected_view_edit import (
    FRAMES,CHUNK,CHUNKS,EDIT_FORMAT,RENDER_PLAN_FORMAT)
from backend.nvp_usd_film01p_source_multicam_film_conform import (
    even_camera_coverage_edl,_validate_edl)


class OriginalSelectedViewContractTest(unittest.TestCase):
    def test_nine_camera_edit_has_720_final_not_6480_full_roll_frames(self):
        views=[f"Cam_{angle}_{size}" for angle in "ABC"
               for size in ("wide","medium","close")]
        cuts=even_camera_coverage_edl(views)
        self.assertEqual(len(cuts),9)
        self.assertEqual(sum(
            x["edit_out_frame"]-x["edit_in_frame"] for x in cuts),720)
        self.assertEqual(_validate_edl(cuts,views),cuts)
        self.assertEqual(CHUNKS,90)
        self.assertEqual(CHUNK*CHUNKS,FRAMES)

    def test_unconventional_camera_shots_can_be_selected(self):
        views=["RearOTS","DroneAbove","UnderStage","VirtualWallPass"]
        cuts=even_camera_coverage_edl(views)
        self.assertEqual(len(cuts),4)
        self.assertEqual(cuts[0]["camera_id"],"RearOTS")
        self.assertEqual(cuts[-1]["camera_id"],"VirtualWallPass")
        self.assertEqual(cuts[-1]["edit_out_frame"],720)

    def test_cross_chunk_or_inside_chunk_original_camera_cut(self):
        edits=[
            {"camera_id":"Wide","source_in_frame":0,
             "source_out_frame":4,"edit_in_frame":0,"edit_out_frame":4},
            {"camera_id":"OTS","source_in_frame":4,
             "source_out_frame":720,"edit_in_frame":4,
             "edit_out_frame":720}]
        self.assertEqual(_validate_edl(edits,["Wide","OTS"]),edits)
        self.assertEqual(edits[0]["edit_out_frame"],4)
        self.assertLess(edits[0]["edit_out_frame"],CHUNK)

    def test_source_timeline_gap_or_unauthored_camera_rejected(self):
        edits=[
            {"camera_id":"Wide","source_in_frame":0,
             "source_out_frame":4,"edit_in_frame":0,"edit_out_frame":4},
            {"camera_id":"NotReal","source_in_frame":4,
             "source_out_frame":720,"edit_in_frame":4,
             "edit_out_frame":720}]
        with self.assertRaises(PermissionError):
            _validate_edl(edits,["Wide","OTS"])
        edits[1]["camera_id"]="OTS"
        edits[1]["source_in_frame"]=5
        with self.assertRaises(PermissionError):
            _validate_edl(edits,["Wide","OTS"])

    def test_per_attempt_identity_is_bound_to_edit_and_exact_chunk(self):
        sha="a"*64
        self.assertNotEqual(chunk_job_id(sha,0,1),
                            chunk_job_id(sha,0,2))
        self.assertNotEqual(chunk_job_id(sha,0,1),
                            chunk_job_id(sha,8,1))
        self.assertNotEqual(chunk_job_id(sha,0,1),
                            chunk_job_id("b"*64,0,1))
        for start,attempt in ((4,1),(720,1),(-8,1),(0,0),(0,100)):
            with self.assertRaises(ValueError):
                chunk_job_id(sha,start,attempt)

if __name__=="__main__":
    unittest.main()
