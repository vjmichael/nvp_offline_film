"""INT-02B exact original-Take editorial assembly and native export contracts."""
import base64
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.nvp_int02_edited_film import (
    NativeEditedFilm30s, verify_edited_film, DURATION_TICKS,
)
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly, FORMAT
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from test_nvp_final_2d_native import png


class FakeOriginalTake:
    def __init__(self, index, project_id, take_id, *, expected_take_sha256,
                 listener_path):
        self.take_id = take_id
        self.sha = expected_take_sha256
        self.closed = False
        self.roles = {"/World/Camera": "camera"}
        self.data = {"timeline_id": "OriginalCamera", "timeline_revision": 1}
        self.timeline = Mock()
        self.timeline.events_at.return_value = [
            {"payload": {"usd_prim_path": "/World/Camera"}}]

    def snapshot(self, tick):
        if self.closed:
            raise RuntimeError("Original Take reader was closed")
        return {"time_tick": tick}

    def audio_window(self, first, count):
        byte = b"\x01" if self.take_id == "SourceA" else b"\x02"
        return {"pcm_base64": base64.b64encode(byte*count*4).decode("ascii"),
                "take_document_sha256": self.sha}

    def close(self):
        self.closed = True


class CommittedEditedThirtySecondFilm(TestCase):
    def setUp(self):
        self.root = TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.parent = Path(self.root.name)
        self.pid = "OriginalProject"
        self.assembly = object.__new__(SlateSequenceAssembly)
        self.assembly.index = Mock()
        self.takes = {
            "SourceA": "a"*64, "SourceB": "b"*64,
        }
        def open_take(pid, object_id, revision=1):
            if object_id not in self.takes:
                raise KeyError(object_id)
            return {"kind": "take", "document_sha256": self.takes[object_id],
                    "data": {"frozen": True,
                             "format": "nvp.digital_take.openusd_temporal.v1",
                             "duration_tick": DURATION_TICKS,
                             "scene_document_sha256": "c"*64,
                             "timeline_document_sha256": "d"*64}}
        self.assembly.index.read_revision.side_effect = open_take
        self.rows = [{
            "segment_id": "FirstScene", "source_take_id": "SourceA",
            "source_take_document_sha256": "a"*64,
            "source_shot_id": None, "source_in_tick": 0,
            "source_out_tick": 15*T,
            "timeline_start_tick": 0, "timeline_end_tick": 15*T,
        }, {
            "segment_id": "SecondScene", "source_take_id": "SourceB",
            "source_take_document_sha256": "b"*64,
            "source_shot_id": None, "source_in_tick": 0,
            "source_out_tick": 15*T,
            "timeline_start_tick": 15*T, "timeline_end_tick": 30*T,
        }]
        self.edit = {
            "kind": "edit", "document_sha256": "e"*64,
            "data": {"format": FORMAT, "explicit_editor_commit": True,
                     "render_approved": False, "retimed": False,
                     "duration_tick": DURATION_TICKS, "segments": self.rows}}
        self.assembly.open_edit = Mock(return_value=self.edit)
        self.renderer_calls = []
        def renderer(*, scope, tick, camera_path, source_snapshot):
            self.renderer_calls.append((scope["source_take_id"], tick, camera_path))
            return png()
        self.renderer = renderer

    def exporter(self, approval=True):
        return NativeEditedFilm30s(
            self.assembly,
            native_creator_approval=lambda exact: approval,
            render_png=self.renderer)

    def test_read_only_preflight_binds_both_original_performances(self):
        plan = self.exporter().preflight(self.pid, "EditedFilm", 1)
        self.assertEqual(plan["frame_count"], 720)
        self.assertEqual(plan["pcm_samples"], 1440000)
        self.assertEqual([x["source_take_id"] for x in plan["segments"]],
                         ["SourceA", "SourceB"])
        self.assertFalse(plan["render_approved"])

    def test_real_source_cut_render_audio_and_independent_reopen(self):
        with patch("backend.nvp_int02_edited_film.FrozenSceneAV", FakeOriginalTake):
            result = self.exporter().export(
                self.pid, "EditedFilm", 1, "EditDerivative",
                self.parent, listener_path="/World/Camera")
            self.assertEqual(result["independent_reopen_status"],
                             "VERIFIED_EDITED_ORIGINAL_30S")
            self.assertEqual(len(self.renderer_calls), 720)
            self.assertEqual(self.renderer_calls[0][0], "SourceA")
            self.assertEqual(self.renderer_calls[360][0], "SourceB")
            delivered = Path(result["directory"])
            receipt = verify_edited_film(
                self.assembly, self.pid, "EditedFilm", 1, delivered)
            self.assertEqual(receipt["original_pcm_samples"], 1440000)
            target = delivered/"pictures"/"0000361.png"
            target.write_bytes(target.read_bytes()+b"tampered")
            with self.assertRaisesRegex(RuntimeError, "SHA mismatch"):
                verify_edited_film(self.assembly, self.pid, "EditedFilm", 1,
                                   delivered)

    def test_no_source_shot_layer_loss_or_unauthorized_delivery(self):
        self.rows[1]["source_shot_id"] = "DirectorOverride"
        with self.assertRaisesRegex(RuntimeError, "shot override composition"):
            self.exporter().preflight(self.pid, "EditedFilm", 1)
        self.rows[1]["source_shot_id"] = None
        with self.assertRaises(PermissionError):
            self.exporter(approval=False).export(
                self.pid, "EditedFilm", 1, "Refused",
                self.parent, listener_path="/World/Camera")
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_off_frame_cut_is_not_silently_rounded(self):
        self.rows[0]["timeline_end_tick"] += T//100
        with self.assertRaisesRegex(RuntimeError, "shifted or retimed"):
            self.exporter().preflight(self.pid, "EditedFilm", 1)

    def test_cancel_does_not_publish_partial_package(self):
        with patch("backend.nvp_int02_edited_film.FrozenSceneAV", FakeOriginalTake):
            exporter = NativeEditedFilm30s(
                self.assembly, native_creator_approval=lambda exact: True,
                render_png=self.renderer, cancelled=lambda: len(self.renderer_calls)>=2)
            with self.assertRaises(InterruptedError):
                exporter.export(
                    self.pid, "EditedFilm", 1, "Cancelled",
                    self.parent, listener_path="/World/Camera")
            self.assertFalse(any(p.name.startswith("NVPEdit30_")
                                 for p in self.parent.iterdir()))
