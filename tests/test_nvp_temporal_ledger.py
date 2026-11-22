"""DATA-TIME-01: authoritative sparse time events, not frame-driven film state."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import (
    TemporalLedger, TICKS_PER_SECOND, tick_from_frame, frame_at_tick)


class TemporalLedgerNativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.studio = Studio(Path(self.tmp.name) / "film.sqlite")
        self.pid = self.studio.create_project("Three-hour feature", "Data-first")["id"]
        self.index = FilmIndex(self.studio)
        self.ledger = TemporalLedger(self.index)
        self.scene = self.index.register_revision(
            self.pid, "scene_authority", "scene",
            {"format": "nvp.scene.unit.v1", "location": "soundstage"},
            expected_revision=0)
        self.camera = self.index.register_revision(
            self.pid, "camera_authority", "camera",
            {"format": "nvp.camera.unit.v1", "lens": "35mm"},
            expected_revision=0)

    def action(self, eid, start, end, *, source="scene_authority",
               kind="action", subject="actor_one", payload=None):
        return {"event_id": eid, "event_kind": kind, "subject_id": subject,
                "start_tick": start, "end_tick": end, "source_id": source,
                "source_revision": 1, "payload": payload or {"change": "walking"}}

    def test_three_hour_sparse_events_without_rendering_any_frame(self):
        total = TICKS_PER_SECOND * (3 * 3600 + 11)
        at_hour_3 = 3 * 3600 * TICKS_PER_SECOND
        self.ledger.publish(self.pid, "authored_film", [
            self.action("actor_enters", TICKS_PER_SECOND * 5, TICKS_PER_SECOND * 9),
            self.action("camera_moves", at_hour_3, at_hour_3 + 3*TICKS_PER_SECOND,
                        source="camera_authority", kind="camera",
                        subject="camera_a", payload={"path": "spline_08"}),
            self.action("dialogue_starts", at_hour_3 + TICKS_PER_SECOND,
                        at_hour_3 + TICKS_PER_SECOND, kind="dialogue",
                        payload={"line_id": "line_301"}),
        ], duration_tick=total)
        record = self.index.read_revision(self.pid, "authored_film", 1)
        self.assertEqual(record["kind"], "temporal")
        self.assertEqual(record["data"]["event_count"], 3)
        self.assertFalse(record["data"]["presentation_frames_rendered"])
        self.assertNotIn("fps_num", record["data"])
        active = self.ledger.events_at(
            self.pid, "authored_film", 1,
            tick=at_hour_3 + TICKS_PER_SECOND)
        self.assertEqual({e["event_id"] for e in active},
                         {"camera_moves", "dialogue_starts"})
        within = self.ledger.events_in(
            self.pid, "authored_film", 1,
            start_tick=at_hour_3, end_tick=at_hour_3+2*TICKS_PER_SECOND)
        self.assertEqual(len(within["events"]), 2)
        self.assertEqual(self.ledger.verify(
            self.pid, "authored_film", 1)["event_count"], 3)
        self.assertEqual(self.index.direct_dependents(
            self.pid, "camera_authority", 1),
            [{"object_id": "authored_film", "revision": 1}])

    def test_output_rate_and_audio_sample_grid_are_independent(self):
        self.assertEqual(tick_from_frame(24000, 24000, 1001),
                         TICKS_PER_SECOND * 1001)
        self.assertEqual(tick_from_frame(44100, 44100, 1),
                         TICKS_PER_SECOND)
        self.assertEqual(tick_from_frame(48000, 48000, 1),
                         TICKS_PER_SECOND)
        self.assertEqual(frame_at_tick(TICKS_PER_SECOND, 24, 1), 24)
        self.assertEqual(frame_at_tick(TICKS_PER_SECOND, 60, 1), 60)
        with self.assertRaises(ValueError):
            frame_at_tick(TICKS_PER_SECOND // 7, 24, 1, rounding="exact")
        with self.assertRaises(ValueError):
            tick_from_frame(1, 13, 1)

    def test_project_isolation_and_impossible_references(self):
        another = self.studio.create_project("Separate film", "")["id"]
        with self.assertRaises(KeyError):
            self.ledger.publish(another, "other_film", [
                self.action("intruder", 1, 2)
            ], duration_tick=100)
        with self.assertRaises(ValueError):
            self.ledger.publish(self.pid, "bad", [
                self.action("bad_action", 200, 100)
            ], duration_tick=400)

    def test_event_tamper_refused_without_changing_filmindex_revision(self):
        self.ledger.publish(self.pid, "events", [
            self.action("start", 3, 10)
        ], duration_tick=20)
        with self.studio._connection() as db:
            db.execute("""UPDATE nvp_temporal_events SET payload_json=?
                WHERE project_id=? AND timeline_id=?""",
                ('{"tampered":true}',self.pid,"events"))
        with self.assertRaises(RuntimeError):
            self.ledger.verify(self.pid, "events", 1)

    def test_transaction_rollback_after_rows_inserted(self):
        actual=self.index.register_revision

        def fault(*args,**kwargs):
            real_guard=kwargs["precommit_guard"]
            def after_write(db):
                real_guard(db)
                raise RuntimeError("injected after timed event rows")
            kwargs["precommit_guard"]=after_write
            return actual(*args,**kwargs)
        with patch.object(self.index,"register_revision",side_effect=fault):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.ledger.publish(self.pid,"failed_events",[
                    self.action("gesture", 0, 2)
                ], duration_tick=5)
        with self.studio._connection() as db:
            n=db.execute("""SELECT COUNT(*) FROM nvp_temporal_events
                WHERE project_id=? AND timeline_id=?""",
                (self.pid,"failed_events")).fetchone()[0]
        self.assertEqual(n,0)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"failed_events")

    def test_pages_large_sparse_film_without_materializing_frames(self):
        duration=3*3600*TICKS_PER_SECOND+1
        generated=(self.action(
            "event_%07d" % n, n*duration//10001,
            n*duration//10001 + 1000, payload={"actor_state":n%5})
            for n in range(10000))
        self.ledger.publish(self.pid,"very_long_film",
                            generated,duration_tick=duration)
        point=duration//2
        page=self.ledger.events_in(
            self.pid,"very_long_film",1,
            start_tick=point,end_tick=point+duration//100)
        self.assertGreater(len(page["events"]),0)
        self.assertLessEqual(len(page["events"]),100)
        self.assertEqual(self.ledger.verify(
            self.pid,"very_long_film",1)["event_count"],10000)


if __name__ == "__main__":
    unittest.main()
