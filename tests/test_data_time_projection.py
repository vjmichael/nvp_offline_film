"""DATA-TIME-01: same authored gesture, different output sample rates."""
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_temporal_projection import TemporalProjection

class TimeProjectionTests(unittest.TestCase):
    def test_same_authoritative_event_at_24_and_60_fps(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio=Studio(Path(tmp)/"film.sqlite")
            pid=studio.create_project("Timeline test","")["id"]
            idx=FilmIndex(studio)
            idx.register_revision(pid,"actor_source","performance",
                {"format":"nvp.performance.unit","rig":"A"},expected_revision=0)
            source=TemporalLedger(idx)
            source.publish(pid,"source_timeline",[{
                "event_id":"gesture_one","event_kind":"gesture",
                "subject_id":"actor_a","start_tick":TICKS_PER_SECOND,
                "end_tick":2*TICKS_PER_SECOND,
                "source_id":"actor_source","source_revision":1,
                "payload":{"gesture":"wave"}}
            ],duration_tick=3*TICKS_PER_SECOND)
            projection=TemporalProjection(source)
            common=dict(project_id=pid,timeline_id="source_timeline",
                revision=1,start_tick=TICKS_PER_SECOND,end_tick=2*TICKS_PER_SECOND)
            a=projection.prepare(**common,fps_num=24,fps_den=1)
            b=projection.prepare(**common,fps_num=60,fps_den=1)
            self.assertEqual(len(a["presentation_samples"]),24)
            self.assertEqual(len(b["presentation_samples"]),60)
            self.assertEqual(a["active_source_events"],b["active_source_events"])
            self.assertEqual(a["timeline_document_sha256"],b["timeline_document_sha256"])
            self.assertEqual(a["output"],"NOT_RENDERED_EVENT_DATA_ONLY")
            with self.assertRaises(ValueError):
                projection.prepare(**{**common,"start_tick":0,
                    "end_tick":3*TICKS_PER_SECOND},fps_num=60,fps_den=1)

if __name__=="__main__":
    unittest.main()
