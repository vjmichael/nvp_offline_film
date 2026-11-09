"""01O/01P pure editorial and journal-identity refusal contract tests.

No mock renderer frames or synthesized accepted film. These tests validate
source-time editorial decisions, bounded chunk IDs and rejection semantics.
"""
import unittest

from backend.nvp_usd_film01o_recoverable_camera_roll_host import (
    chunk_id,CHUNK,CHUNKS_PER_ROLL)
from backend.nvp_usd_film01p_source_multicam_film_conform import (
    even_camera_coverage_edl,_validate_edl)


class OriginalFilmRollContract(unittest.TestCase):
    def test_nine_cameras_are_full_720frame_source_rolls(self):
        cameras=[f"Cam_{x}_{y}" for x in "ABC"
                 for y in ("wide","medium","close")]
        edl=even_camera_coverage_edl(cameras)
        self.assertEqual(len(edl),9)
        self.assertEqual(len(set(x["camera_id"] for x in edl)),9)
        self.assertEqual([x["source_out_frame"]-x["source_in_frame"]
                          for x in edl],[80]*9)
        self.assertEqual(_validate_edl(edl,cameras),edl)
        self.assertEqual(CHUNK*CHUNKS_PER_ROLL,720)

    def test_arbitrary_13_camera_edit_is_allowed(self):
        names=[f"DirectorCamera{i}" for i in range(13)]
        edl=even_camera_coverage_edl(names)
        self.assertEqual(len(edl),13)
        self.assertEqual(sum(x["source_out_frame"]-x["source_in_frame"]
                             for x in edl),720)
        self.assertEqual(_validate_edl(edl,names),edl)

    def test_intercut_must_not_restage_or_skip_original_film_time(self):
        names=["Wide","OTS","Drone"]
        good=even_camera_coverage_edl(names)
        broken=[dict(x) for x in good]
        broken[1]["source_in_frame"]+=1
        with self.assertRaises(PermissionError):
            _validate_edl(broken,names)
        broken=[dict(x) for x in good]
        broken[1]["edit_in_frame"]+=1
        with self.assertRaises(PermissionError):
            _validate_edl(broken,names)
        broken=[dict(x) for x in good]
        broken.pop()
        with self.assertRaises(RuntimeError):
            _validate_edl(broken,names)

    def test_resumable_chunk_id_is_attempt_and_camera_scoped(self):
        source="a"*64
        self.assertNotEqual(chunk_id(source,"Wide",0,1),
                            chunk_id(source,"Wide",0,2))
        self.assertNotEqual(chunk_id(source,"Wide",0,1),
                            chunk_id(source,"Wide",8,1))
        self.assertNotEqual(chunk_id(source,"Wide",0,1),
                            chunk_id(source,"Drone",0,1))
        for kwargs in [
            ("Wide",1,1),("Wide",720,1),("Wide",0,0),("Wide",0,100),
        ]:
            with self.assertRaises(ValueError):
                chunk_id(source,*kwargs)


if __name__=="__main__":
    unittest.main()
