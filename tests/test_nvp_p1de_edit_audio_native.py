"""P1-D/E native integration: real OpenUSD, FilmIndex SQLite, original PCM.

Exercises genuine source evaluation, not mocked presentation or synthetic
approval receipts. Approval callback is a local trusted-host test fixture;
physical creator consent, OS custody and sustained rendering are separate.
"""
import base64
import hashlib
import math
from pathlib import Path
import struct
import tempfile
import unittest

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_p1de_edit_audio import P1DEConform, SAMPLE_TICK

T = TICKS_PER_SECOND


class NativeEditActorAudioTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="nvp-p1de-original-")
        self.addCleanup(scratch.cleanup)
        self.path = Path(scratch.name) / "studio.sqlite3"
        self.studio = Studio(self.path)
        self.pid = self.studio.create_project(
            "Original actor performance", "Verify source-bound edits")["id"]
        self.index = FilmIndex(self.studio)
        self.original = b"".join(struct.pack(
            "<h", int(9000 * math.sin(2 * math.pi * 330 * i / 48000))
        ) for i in range(48000))
        self.pcm = RecordedSoundSources(self.index).publish(
            self.pid, "actor_pcm", [self.original[:32000], self.original[32000:]])
        OpenUSDSceneBridge(self.index).publish(
            self.pid, "original_world",
            prims=[
                {"path": "/World/Actor", "role": "actor", "position": [5, 0, 0]},
                {"path": "/World/ListenerLeft", "role": "camera",
                 "position": [0, 0, 0]},
                {"path": "/World/ListenerRight", "role": "anchor",
                 "position": [10, 0, 0]}
            ], curves=[], native_schemas=True)
        self.timeline = TemporalLedger(self.index).publish(
            self.pid, "source_sound_time", [{
                "event_id": "actor_dialogue", "event_kind": "dialogue",
                "subject_id": "Actor", "start_tick": 0, "end_tick": T,
                "source_id": "actor_pcm", "source_revision": 1,
                "payload": {"usd_prim_path": "/World/Actor",
                            "original_recording": True, "gain": 1.0}
            }], duration_tick=2*T)
        self.take = OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda event, scope:
            event == "original_approved" and
            scope["operation"] == "nvp.freeze.usd_temporal_take.v1"
        ).freeze(
            self.pid, "frozen_take", scene_id="original_world",
            scene_revision=1, timeline_id="source_sound_time",
            timeline_revision=1, sample_ticks=[0, T],
            creator_event="original_approved")
        self.engine = P1DEConform(
            self.index, approve_edit=lambda event, scope:
            event == "edit_approved" and
            scope["operation"] == "nvp.p1de.publish_source_edit.v1" and
            scope["project_id"] == self.pid and
            len(scope["source_edit_sha256"]) == 64)

    def segment(self, *, a=0, b=T, listener="/World/ListenerLeft",
                actor="Actor", source_sha=None, gain=1.0, enabled=True):
        return {
            "take_id": "frozen_take",
            "take_sha256": self.take["document_sha256"],
            "in_tick": a, "out_tick": b,
            "listener_path": listener,
            "audio": [{
                "event_id": "actor_dialogue", "actor_id": actor,
                "source_id": "actor_pcm", "source_revision": 1,
                "source_sha256": (self.pcm["document_sha256"]
                                  if source_sha is None else source_sha),
                "enabled": enabled, "gain": gain
            }]
        }

    def publish(self, edit_id, segments, *, expected_revision=0,
                approval="edit_approved"):
        return self.engine.publish(
            self.pid, edit_id, segments, expected_revision=expected_revision,
            creator_event=approval)

    def test_real_openusd_actor_audio_changes_with_approved_listener(self):
        left = self.publish("edit_left", [self.segment()])
        right = self.publish("edit_right", [
            self.segment(listener="/World/ListenerRight")])
        a = self.engine.audio_window(
            self.pid, "edit_left", left["revision"], first_sample=120, count=768)
        b = self.engine.audio_window(
            self.pid, "edit_right", right["revision"], first_sample=120, count=768)
        x = base64.b64decode(a["pcm_base64"])
        y = base64.b64decode(b["pcm_base64"])
        self.assertEqual(len(x), 768 * 4)
        self.assertNotEqual(x, y)
        self.assertNotEqual(x, bytes(len(x)))
        self.assertEqual(hashlib.sha256(x).hexdigest(), a["pcm_sha256"])
        self.assertFalse(a["source_modified"])
        self.assertFalse(a["master_approved"])
        self.assertEqual(RecordedSoundSources(self.index).read(
            self.pid, "actor_pcm", 1, 0, 768), self.original[:768*2])

    def test_edit_trim_reorder_cross_cut_exact_pcm_and_restart(self):
        old_sha = self.take["document_sha256"]
        edit = self.publish("edit_conform", [
            self.segment(a=0, b=T//2),
            self.segment(a=T//4, b=3*T//4)])
        plan = self.engine.plan(self.pid, "edit_conform", edit["revision"],
                                first_sample=24000-128, count=512)
        self.assertEqual([p["sample_count"] for p in plan["slices"]], [128, 384])
        self.assertEqual(plan["slices"][0]["source_first_sample"], 24000-128)
        self.assertEqual(plan["slices"][1]["source_first_sample"], 12000)
        rendered = self.engine.audio_window(
            self.pid, "edit_conform", edit["revision"],
            first_sample=24000-128, count=512)
        self.assertEqual(len(base64.b64decode(rendered["pcm_base64"])), 2048)
        restarted = P1DEConform(
            FilmIndex(Studio(self.path)),
            approve_edit=lambda *_: False)
        reopened = restarted.read(self.pid, "edit_conform", 1)
        self.assertEqual(reopened["source_edit_sha256"],
                         edit["source_edit_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid, "frozen_take", 1)["document_sha256"], old_sha)
        self.assertEqual(self.pcm["document_sha256"],
                         self.index.read_revision(
                             self.pid, "actor_pcm", 1)["document_sha256"])

    def test_revisions_preserve_source_and_previous_edit(self):
        first = self.publish("edited_history", [self.segment()])
        second = self.publish("edited_history", [
            self.segment(gain=0.5)], expected_revision=1)
        self.assertNotEqual(first["document_sha256"], second["document_sha256"])
        self.assertEqual(self.engine.read(
            self.pid, "edited_history", 1)["data"]["segments"][0][
                "audio"][0]["gain"], 1.0)
        self.assertEqual(self.engine.read(
            self.pid, "edited_history", 2)["data"]["segments"][0][
                "audio"][0]["gain"], 0.5)
        with self.assertRaises(RuntimeError):
            self.publish("edited_history", [
                self.segment(gain=0.7)], expected_revision=1)

    def test_wrong_actor_audio_take_or_human_refusal_cannot_publish(self):
        with self.assertRaises(RuntimeError):
            self.publish("spoofed_actor", [self.segment(actor="Intruder")])
        with self.assertRaises(RuntimeError):
            self.publish("spoofed_pcm", [
                self.segment(source_sha="0"*64)])
        with self.assertRaises(PermissionError):
            self.publish("human_refused", [self.segment()],
                         approval="refused")
        bad = self.segment()
        bad["take_sha256"] = "0"*64
        with self.assertRaises(RuntimeError):
            self.publish("spoofed_take", [bad])
        bad = self.segment()
        bad["in_tick"] = SAMPLE_TICK // 2
        with self.assertRaises(ValueError):
            self.publish("fractional_sample", [bad])
        for edit_id in ("spoofed_actor", "spoofed_pcm",
                        "human_refused", "spoofed_take", "fractional_sample"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid, edit_id)

    def test_muted_actor_and_out_of_bounds_native_window(self):
        edit = self.publish("muted_edit", [self.segment(enabled=False)])
        silent = self.engine.audio_window(
            self.pid, "muted_edit", edit["revision"],
            first_sample=120, count=512)
        self.assertEqual(base64.b64decode(silent["pcm_base64"]), bytes(2048))
        with self.assertRaises(ValueError):
            self.engine.audio_window(self.pid, "muted_edit", 1,
                                     first_sample=48000-10, count=50)
        with self.assertRaises(ValueError):
            self.engine.audio_window(self.pid, "muted_edit", 1,
                                     first_sample=0, count=4097)


    def test_p1f_reel_plan_binds_real_source_and_restart(self):
        from backend.nvp_p1f_p2_reel_plan import P1FReelPlan
        edit = self.publish("film_edit", [self.segment()])
        scheduler = P1FReelPlan(self.index)
        receipt = scheduler.publish(
            self.pid, "film_source_plan", edit_id="film_edit",
            edit_revision=1,
            expected_edit_document_sha256=edit["document_sha256"])
        plan = scheduler.read(self.pid, "film_source_plan")["data"]
        self.assertEqual(plan["state"], "PLANNED_ONLY")
        self.assertEqual(plan["published_reels"], 0)
        self.assertFalse(plan["picture_rendered"])
        self.assertEqual(plan["frame_count"], 24)
        self.assertEqual(plan["sample_count"], 48000)
        self.assertEqual(len(plan["reels"]), 1)
        source = scheduler.picture_instant(self.pid, "film_source_plan", 0, 12)
        self.assertEqual(source["source_take_id"], "frozen_take")
        self.assertEqual(source["source_tick"], T//2)
        self.assertEqual(source["output_tick"], T//2)
        derived = scheduler.audio_window(
            self.pid, "film_source_plan", 0, first_sample=120, count=512)
        self.assertEqual(len(base64.b64decode(derived["pcm_base64"])), 2048)
        restarted = P1FReelPlan(FilmIndex(Studio(self.path)))
        self.assertEqual(
            restarted.read(self.pid, "film_source_plan")["document_sha256"],
            receipt["document_sha256"])
        with self.assertRaises(RuntimeError):
            scheduler.publish(
                self.pid, "stale_film_plan", edit_id="film_edit",
                edit_revision=1, expected_edit_document_sha256="0"*64)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "stale_film_plan")

    def test_p2_30_minute_and_three_hour_exact_source_clock(self):
        from backend.nvp_p1f_p2_reel_plan import reel_layout
        first = reel_layout(30*60*T)
        self.assertEqual(len(first), 180)
        self.assertEqual(sum(x["frame_count"] for x in first), 43200)
        self.assertEqual(sum(x["sample_count"] for x in first), 86400000)
        self.assertEqual(first[-1]["end_tick"], 30*60*T)
        feature = reel_layout(3*60*60*T)
        self.assertEqual(len(feature), 1080)
        self.assertEqual(sum(x["frame_count"] for x in feature), 259200)
        self.assertEqual(sum(x["sample_count"] for x in feature), 518400000)
        self.assertEqual(feature[-1]["end_tick"], 3*60*60*T)
        self.assertTrue(all(x["status"] == "UNRENDERED" for x in feature))
        with self.assertRaises(ValueError):
            reel_layout(3*60*60*T + T)
        with self.assertRaises(ValueError):
            reel_layout(T + SAMPLE_TICK)


    def test_p1f_refuses_to_render_placeholder_actor_or_claim_finished_movie(self):
        from backend.nvp_p1f_p2_reel_plan import P1FReelPlan
        from backend.nvp_p1f_cycles_source_admission import (
            admit_original_frame, RenderSourceNotReady)
        edit = self.publish("genuine_actor_edit", [self.segment()])
        plan = P1FReelPlan(self.index)
        receipt = plan.publish(
            self.pid, "genuine_actor_plan", edit_id="genuine_actor_edit",
            edit_revision=1,
            expected_edit_document_sha256=edit["document_sha256"])
        old_take = self.index.read_revision(
            self.pid, "frozen_take", 1)["document_sha256"]
        with self.assertRaisesRegex(
                RenderSourceNotReady, "imported actor mesh"):
            admit_original_frame(
                self.index, self.pid, "genuine_actor_plan", 0, 0)
        # A synthetic source fixture must not become a claimed Cycles output.
        reopened = plan.read(self.pid, "genuine_actor_plan")
        self.assertEqual(reopened["document_sha256"],
                         receipt["document_sha256"])
        self.assertFalse(reopened["data"]["picture_rendered"])
        self.assertEqual(reopened["data"]["published_reels"], 0)
        self.assertEqual(self.index.read_revision(
            self.pid, "frozen_take", 1)["document_sha256"], old_take)


if __name__ == "__main__":
    unittest.main()
