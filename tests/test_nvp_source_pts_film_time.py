"""INDEX-TIME-01: exact imported PTS -> NVP film ticks; no CFR assumption."""
import unittest

from backend.nvp_native_frame_index import NVPFrameIndex
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_source_pts_film_time import (
    IndexedSourceFilmTime, pts_to_film_tick)

T=TICKS_PER_SECOND


class IndexedPTSFixture(NVPFrameIndex):
    """Metadata-only fixture; real FFmpeg integration has its own test."""
    def __init__(self, pts, time_base=(1,90000)):
        self.pts=list(pts)
        self.num,self.den=time_base
        self.calls=0

    def window(self, project, asset, source_sha, source, *, first_zero, count):
        self.calls+=1
        selected=self.pts[first_zero:first_zero+count]
        if len(selected)!=count:
            raise ValueError("Frame outside indexed source")
        return {
            "index_path":"/test/index.sqlite3",
            "source_stamp":{"device":5,"inode":1,"size":100,
                            "mtime_ns":25,"ctime_ns":30},
            "index_status":"REUSED_SOURCE_STAMP_UNVERIFIED",
            "time_base_num":self.num,"time_base_den":self.den,
            "frames":[{"ordinal":first_zero+i,"pts":p,
                       "keyframe":i==0,"packet_pos":i*99}
                       for i,p in enumerate(selected)]}


class NativeFilmTimeBridgeTests(unittest.TestCase):
    def test_variable_frame_rate_and_nonzero_pts_origin(self):
        # Start at 3.000s in source, and deliberately drop/twist CFR slots.
        pts=[270000,273750,277500,285000,288750,296250,300000]
        bridge=IndexedSourceFilmTime(IndexedPTSFixture(pts))
        result=bridge.map_window(
            "a"*32,"take_vfr","b"*64,"/test/source.mov",
            source_in_frame_zero=2,film_in_tick=10*T,
            first_zero=3,count=4)
        self.assertEqual([x["source_frame_zero"] for x in result["frames"]],
                         [3,4,5,6])
        # An inpoint at 277500 is mapped to tick 10s, regardless
        # of source media's 3.08s original timestamp origin.
        self.assertEqual(result["frames"][0]["time_tick"],
                         10*T+(285000-277500)*T//90000)
        self.assertEqual(result["frames"][-1]["time_tick"],
                         10*T+(300000-277500)*T//90000)
        self.assertTrue(all(x["exactly_representable"]
                            for x in result["frames"]))
        self.assertFalse(result["source_sha_verified_this_operation"])
        self.assertTrue(result["imported_media_is_observation_only"])
        self.assertFalse(result["rendered_frames"])

    def test_odd_source_timebase_requires_explicit_quantization(self):
        exact=dict(source_pts=1,source_in_pts=0,
                   time_base_num=1,time_base_den=11,
                   film_in_tick=15*T)
        with self.assertRaises(ValueError):
            pts_to_film_tick(**exact)
        floor=pts_to_film_tick(**exact,rounding="floor")
        ceil=pts_to_film_tick(**exact,rounding="ceil")
        near=pts_to_film_tick(**exact,rounding="nearest")
        self.assertEqual(ceil["time_tick"]-floor["time_tick"],1)
        self.assertEqual(near["time_tick"],floor["time_tick"])
        self.assertFalse(near["exactly_representable"])
        self.assertEqual(
            near["quantization_error_ticks"],
            {"numerator":-5,"denominator":11})
        self.assertEqual(
            near["source_elapsed_seconds"],
            {"numerator":1,"denominator":11})
        # Source samples never carry a false exactness claim.
        result=IndexedSourceFilmTime(IndexedPTSFixture([0,1,2],(1,11)))
        with self.assertRaises(ValueError):
            result.map_window("a"*32,"movie","b"*64,"/source.mov",
                              source_in_frame_zero=0,film_in_tick=0,
                              first_zero=0,count=3)
        mapped=result.map_window(
            "a"*32,"movie","b"*64,"/source.mov",
            source_in_frame_zero=0,film_in_tick=0,
            first_zero=0,count=3,rounding="nearest")
        self.assertFalse(mapped["frames"][1]["exactly_representable"])

    def test_no_incremental_rounding_drift_thousands_of_frames(self):
        base=100000
        frames=[base+i*1001 for i in range(96)]
        index=IndexedPTSFixture(frames,(1,30000))
        result=IndexedSourceFilmTime(index).map_window(
            "a"*32,"source","b"*64,"/video.mkv",
            source_in_frame_zero=0,first_zero=0,count=96,
            film_in_tick=5000000)
        # Each timestamp is mapped directly from the original inpoint,
        # NOT by adding individually rounded frame durations.
        for i,item in enumerate(result["frames"]):
            self.assertEqual(item["time_tick"],
                             5000000+i*1001*T//30000)

    def test_invalid_clip_scope_and_bad_index_metadata_rejected(self):
        index=IndexedPTSFixture([0,3000,6000,9000])
        bridge=IndexedSourceFilmTime(index)
        base=dict(project="a"*32,asset="movie",source_sha="b"*64,
                  source="/safe/movie.mov",source_in_frame_zero=1,
                  film_in_tick=0,first_zero=2,count=2)
        with self.assertRaises(ValueError):
            bridge.map_window(**{**base,"first_zero":0})
        with self.assertRaises(ValueError):
            bridge.map_window(**{**base,"count":97})
        with self.assertRaises(ValueError):
            bridge.map_window(**{**base,"rounding":"unspecified"})
        with self.assertRaises(ValueError):
            bridge.map_window(**{**base,"film_in_tick":True})
        with self.assertRaises(ValueError):
            pts_to_film_tick(source_pts=-1,source_in_pts=0,
                             time_base_num=1,time_base_den=90000,
                             film_in_tick=0)
        with self.assertRaises(ValueError):
            pts_to_film_tick(source_pts=10,source_in_pts=0,
                             time_base_num=1,time_base_den=90000,
                             film_in_tick=2**63-1)
        corrupted=IndexedSourceFilmTime(
            IndexedPTSFixture([0,3000,3000,9000]))
        with self.assertRaises(RuntimeError):
            corrupted.map_window("a"*32,"movie","b"*64,"/movie.mov",
                source_in_frame_zero=0,film_in_tick=0,
                first_zero=1,count=2)

    def test_two_positions_share_source_without_mutating_native_clock(self):
        frames=[270000,274500,279000,283500]
        bridge=IndexedSourceFilmTime(IndexedPTSFixture(frames))
        common=dict(project="a"*32,asset="clip",source_sha="b"*64,
                    source="/video.mov",source_in_frame_zero=0,
                    first_zero=0,count=4)
        first=bridge.map_window(**common,film_in_tick=0)
        second=bridge.map_window(**common,film_in_tick=90*T)
        self.assertEqual(
            [b["time_tick"]-a["time_tick"]
             for a,b in zip(first["frames"],second["frames"])],
            [90*T]*4)
        self.assertEqual(
            [a["source_pts"] for a in first["frames"]],
            [a["source_pts"] for a in second["frames"]])


if __name__=="__main__":
    unittest.main()
