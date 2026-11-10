"""PLAN-02-E: actual OpenUSD 30s source and exact 48k PCM playback contracts.

Only ephemeral authored native film/PCM fixtures; not production mic, real
speakers or a human OS approval record. Full 1,440,000-sample exhaustive
streaming is run separately INSIDE the installed Windows NVP.exe gate.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from backend.nvp_data_av_desktop import TrustedDataAVController
from backend.nvp_film_index import FilmIndex
from backend.nvp_plan02e_continuous import (
    Continuous30SecondFilm, AUDIO_SAMPLES, DURATION_TICK, FRAME_COUNT,
)
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from tools.nvp_plan02e_installed_acceptance import (
    create, _verify_original, CAMERAS, TAKE_ID,
)


class ThirtySecondNativeFilmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="nvp-plan02e-test-")
        cls.db = Path(cls.temp.name) / "studio.sqlite3"
        cls.studio = Studio(cls.db)
        cls.pid = cls.studio.create_project(
            "Original 30 second film", "Native source acceptance",
        )["id"]
        cls.index = FilmIndex(cls.studio)
        cls.receipt = create(cls.index, cls.pid)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def film(self):
        return Continuous30SecondFilm(
            self.index, self.pid, TAKE_ID, self.receipt["take_sha256"],
            listener_path=CAMERAS[1],
        )

    def test_three_original_camera_shots_cover_entire_30_seconds(self):
        reader = self.film()
        try:
            report = reader.verify_continuity(read_all_audio=False)
            self.assertEqual(report["duration_tick"], str(DURATION_TICK))
            self.assertEqual(report["picture_sample_instants_checked"], FRAME_COUNT)
            self.assertEqual(
                [report["camera_sample_counts"][name] for name in CAMERAS],
                [240, 240, 240],
            )
            self.assertGreaterEqual(len(report["actual_native_png_probes"]), 6)
            self.assertFalse(report["original_source_modified"])
            self.assertFalse(report["ffmpeg_used"])
            self.assertFalse(report["picture_sequence_persisted"])
            self.assertFalse(report["flattened_soundtrack_persisted"])
            self.assertFalse(report["realtime_device_playback_attested"])
            self.assertEqual(reader.camera_at(10 * T - 1)["camera_path"], CAMERAS[0])
            self.assertEqual(reader.camera_at(10 * T)["camera_path"], CAMERAS[1])
            self.assertEqual(reader.camera_at(20 * T)["camera_path"], CAMERAS[2])
            self.assertEqual(reader.camera_at(DURATION_TICK - 1)["camera_path"], CAMERAS[2])
            a = reader.picture_at_frame(0)
            b = reader.picture_at_frame(719)
            self.assertNotEqual(a["png_sha256"], b["png_sha256"])
            with self.assertRaises(ValueError):
                reader.camera_at(DURATION_TICK)
            with self.assertRaises(ValueError):
                reader.audio_window(AUDIO_SAMPLES - 8, 16)
            self.assertFalse(self.receipt["human_os_consent_observed"])
        finally:
            reader.close()
        with self.assertRaises(PermissionError):
            reader.camera_at(0)
        _verify_original(self.index, self.receipt)

    def test_real_native_controller_binds_camera_to_audio_sample_clock(self):
        # Test-only native approval stand-in; actual human dialog is a
        # separate physical Windows acceptance gate.
        questions = []
        controller = TrustedDataAVController(
            self.index, native_window=lambda: True,
            ask_native=lambda message: questions.append(message) is None,
        )
        try:
            response = controller.begin({
                "project_id": self.pid,
                "take_id": TAKE_ID,
                "take_document_sha256": self.receipt["take_sha256"],
                "listener_path": CAMERAS[1],
                "first_sample": 0,
                "direction": "forward",
            })
            self.assertEqual(response["status"], "READY")
            ticket = response["session_id"]
            for tick, expected in (
                (0, CAMERAS[0]),
                (10 * T - 1, CAMERAS[0]),
                (10 * T, CAMERAS[1]),
                (20 * T - 1, CAMERAS[1]),
                (20 * T, CAMERAS[2]),
                (DURATION_TICK - 1, CAMERAS[2]),
            ):
                observed = controller.scene_at(ticket, tick)
                self.assertEqual(
                    observed["active_source_camera"]["camera_path"], expected,
                )
                self.assertEqual(
                    observed["active_source_camera"]["source_tick"], str(tick),
                )
                self.assertFalse(observed["original_modified"])
                self.assertEqual(
                    observed["take_document_sha256"], self.receipt["take_sha256"],
                )
            window = controller.read_audio(ticket, 10 * 48_000 - 32, 128)
            self.assertEqual(window["sample_count"], 128)
            self.assertEqual(window["first_sample"], 479_968)
            self.assertIn("OriginalContinuousSound", window["audible_event_ids"])
            self.assertEqual(len(questions), 1)
            self.assertEqual(controller.stop(ticket)["status"], "STOPPED")
            with self.assertRaises(PermissionError):
                controller.scene_at(ticket, 20 * T)
        finally:
            controller.close()
        _verify_original(self.index, self.receipt)

    def test_wrong_sha_denied_without_source_or_project_mutation(self):
        with self.assertRaises(RuntimeError):
            Continuous30SecondFilm(
                self.index, self.pid, TAKE_ID, "0" * 64,
                listener_path=CAMERAS[1],
            )
        self.assertEqual(
            self.index.read_revision(self.pid, TAKE_ID, 1)["document_sha256"],
            self.receipt["take_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
