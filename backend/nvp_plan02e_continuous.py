"""PLAN-02-E: 30-second continuous data-first OpenUSD + original PCM reader.

This is an ON-DEMAND source film, not a PNG sequence, video decoder, or WAV
master. Frame/sample cadence belongs only to the presentation device. Every
request revalidates an immutable frozen Digital Take and exact source hashes.
A timeline with a gap, overlapping camera shots, missing source PCM, or
incomplete duration is rejected instead of filling it with fabricated media.

The original mono PCM may be recorded by a real capture worker. Synthetic PCM
used by dedicated acceptance fixtures is NOT evidence of physical microphone
capture, sound hardware, or director permission.
"""
from __future__ import annotations

from bisect import bisect_right
from hashlib import sha256
import base64
import struct

from backend.nvp_data_av_scene import FrozenSceneAV, MAX_SAMPLES
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film_index import FilmIndex, _require_pid, _id, _sha
from backend.nvp_native_cpu_raster import NativeSourceRaster
from backend.nvp_temporal_ledger import (
    TemporalLedger, TICKS_PER_SECOND, tick_from_frame, _int,
)

FORMAT = "nvp.plan02e.continuous_original_usd_pcm.v1"
SECONDS = 30
RATE = 48_000
FRAMES_PER_SECOND = 24
DURATION_TICK = TICKS_PER_SECOND * SECONDS
AUDIO_SAMPLES = SECONDS * RATE
FRAME_COUNT = SECONDS * FRAMES_PER_SECOND
TICKS_PER_SAMPLE = TICKS_PER_SECOND // RATE
TICKS_PER_FRAME = TICKS_PER_SECOND // FRAMES_PER_SECOND
MAX_EVENTS = 64


class Continuous30SecondFilm:
    """Read-only film projection of one author-approved, immutable source Take."""

    def __init__(self, index: FilmIndex, project_id, take_id, take_sha, *,
                 listener_path):
        if not isinstance(index, FilmIndex):
            raise TypeError("Authoritative FilmIndex required")
        _require_pid(project_id)
        _id(take_id, "frozen film Take")
        _sha(take_sha)
        self.index = index
        self.project_id = project_id
        self.take_id = take_id
        self.take_sha = take_sha
        self.source = FrozenSceneAV(
            index, project_id, take_id,
            expected_take_sha256=take_sha, listener_path=listener_path,
        )
        self.listener_path = listener_path
        self.ledger = TemporalLedger(index)
        self.audio = RecordedSoundSources(index)
        if self.source.duration != DURATION_TICK:
            raise RuntimeError("Film is not exactly thirty seconds of original Film Time")
        data = self.source.data
        self.scene_id = data["scene_id"]
        self.timeline_id = data["timeline_id"]
        self.timeline_revision = data["timeline_revision"]
        page = self.ledger.events_in(
            project_id, self.timeline_id, self.timeline_revision,
            start_tick=0, end_tick=DURATION_TICK, limit=MAX_EVENTS + 1,
        )
        if page["next_cursor"] is not None or len(page["events"]) > MAX_EVENTS:
            raise RuntimeError("Incomplete source event partition")
        cameras = sorted(
            (item for item in page["events"] if item["event_kind"] == "camera"),
            key=lambda item: (item["start_tick"], item["event_id"]),
        )
        if not cameras:
            raise RuntimeError("No original authored film cameras")
        self.segments = []
        cursor = 0
        for event in cameras:
            camera_path = event["payload"].get("usd_prim_path")
            if (event["start_tick"] != cursor
                    or event["end_tick"] <= cursor
                    or event["end_tick"] > DURATION_TICK
                    or event["source_id"] != self.scene_id
                    or event["source_document_sha256"]
                       != data["scene_document_sha256"]
                    or self.source.roles.get(camera_path) != "camera"):
                raise RuntimeError("Film camera gap, overlap, or stale source")
            self.segments.append((cursor, event["end_tick"], camera_path))
            cursor = event["end_tick"]
        if cursor != DURATION_TICK:
            raise RuntimeError("Film ends without an authored camera")
        self._ends = [end for _, end, _ in self.segments]
        sounds = [
            item for item in page["events"]
            if item["event_kind"] in ("dialogue", "sound")
        ]
        if not sounds:
            raise RuntimeError("Thirty-second film has no original PCM source")
        # A continuous source event proves there is no unrecorded transition
        # at a picture cut. Other events may overlap, but the principal
        # recording must cover the complete original film duration.
        entire = []
        for item in sounds:
            record = self.audio.describe(
                project_id, item["source_id"], item["source_revision"])
            if record["document_sha256"] != item["source_document_sha256"]:
                raise RuntimeError("Sound event references a stale PCM revision")
            if (item["start_tick"] == 0
                    and item["end_tick"] == DURATION_TICK
                    and record["data"]["sample_count"] >= AUDIO_SAMPLES
                    and self.source.roles.get(
                        item["payload"].get("usd_prim_path")) is not None):
                entire.append(item)
        if not entire:
            raise RuntimeError("Original PCM does not cover all thirty seconds")
        self.source_audio_ids = [e["source_id"] for e in entire]
        self.raster = NativeSourceRaster(index, project_id)
        self._closed = False

    def close(self):
        self._closed = True
        self.source.close()

    def _guard(self):
        if self._closed:
            raise PermissionError("Continuous film read closed")
        if self.index.read_revision(
                self.project_id, self.take_id, 1)["document_sha256"] != self.take_sha:
            raise RuntimeError("Frozen film Take identity changed")

    def camera_at(self, tick):
        self._guard()
        _int(tick, "film playback tick", maximum=DURATION_TICK - 1)
        i = bisect_right(self._ends, tick)
        if i >= len(self.segments):
            raise RuntimeError("Film camera coverage incomplete")
        start, end, path = self.segments[i]
        if not start <= tick < end:
            raise RuntimeError("Invalid source camera transition")
        return {"camera_path": path, "start_tick": str(start),
                "end_tick": str(end), "source_tick": str(tick)}

    def picture_at_frame(self, frame):
        """Render a genuine transient USD geometry sample; do not store it."""
        self._guard()
        _int(frame, "presentation frame", maximum=FRAME_COUNT - 1)
        tick = tick_from_frame(frame, FRAMES_PER_SECOND, 1)
        camera = self.camera_at(tick)
        snapshot = self.source.snapshot(tick)
        png = self.raster.render_png(
            scope={"scene_document_sha256": self.source.data[
                "scene_document_sha256"]},
            tick=tick, camera_path=camera["camera_path"],
            source_snapshot=snapshot,
        )
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Real source camera did not render native PNG")
        return {"frame": frame, "source_tick": str(tick),
                "camera_path": camera["camera_path"],
                "png_sha256": sha256(png).hexdigest(),
                "png_bytes": len(png),
                "source_modified": False, "frame_is_authoritative": False}

    def audio_window(self, first_sample, count):
        self._guard()
        _int(first_sample, "original film sample",
             maximum=AUDIO_SAMPLES - 1)
        _int(count, "bounded native audio window",
             minimum=1, maximum=MAX_SAMPLES)
        if first_sample + count > AUDIO_SAMPLES:
            raise ValueError("Audio window crosses thirty-second source end")
        result = self.source.audio_window(first_sample, count)
        if (result["take_document_sha256"] != self.take_sha
                or result["first_sample"] != first_sample
                or result["sample_count"] != count
                or result["next_tick"] != str(
                    (first_sample + count) * TICKS_PER_SAMPLE)
                or result["source_modified"] is not False
                or result["frame_based_playback"] is not False):
            raise RuntimeError("Film PCM was not synchronized to source Film Time")
        raw = base64.b64decode(result["pcm_base64"], validate=True)
        if len(raw) != count * 4 or sha256(raw).hexdigest() != result["audio_sha256"]:
            raise RuntimeError("Native PCM buffer changed or was truncated")
        return result

    def verify_continuity(self, *, read_all_audio=False):
        """Exhaust the exact film duration with bounded windows if requested.

        This independently counts all 720 24fps presentation instants and
        the full 1,440,000 original 48k samples. Picture tests are explicit
        probes, not a false claim of 720 frames rendered or real-time device IO.
        """
        self._guard()
        counts = {path: 0 for _, _, path in self.segments}
        for frame in range(FRAME_COUNT):
            tick = tick_from_frame(frame, FRAMES_PER_SECOND, 1)
            counts[self.camera_at(tick)["camera_path"]] += 1
        if any(count == 0 for count in counts.values()):
            raise RuntimeError("Authoring produced a zero-frame camera segment")
        probe_frames = sorted(set((
            0, FRAME_COUNT - 1,
            *(f for start, end, _ in self.segments
              for f in (start // TICKS_PER_FRAME,
                        max(0, end // TICKS_PER_FRAME - 1)))
        )))
        pictures = [self.picture_at_frame(i) for i in probe_frames]
        digest = sha256()
        total = 0
        non_silent_windows = 0
        if read_all_audio:
            while total < AUDIO_SAMPLES:
                size = min(MAX_SAMPLES, AUDIO_SAMPLES - total)
                page = self.audio_window(total, size)
                block = base64.b64decode(page["pcm_base64"], validate=True)
                if any(block):
                    non_silent_windows += 1
                digest.update(block)
                total += size
            if total != AUDIO_SAMPLES or non_silent_windows == 0:
                raise RuntimeError("Continuous PCM output is missing or silent")
        return {
            "format": FORMAT, "status": "NATIVE_SOURCE_CONTINUITY_VERIFIED",
            "take_document_sha256": self.take_sha,
            "scene_document_sha256": self.source.data["scene_document_sha256"],
            "timeline_document_sha256": self.source.data["timeline_document_sha256"],
            "duration_tick": str(DURATION_TICK),
            "picture_cadence": "24/1",
            "picture_sample_instants_checked": FRAME_COUNT,
            "actual_native_png_probes": pictures,
            "camera_sample_counts": counts,
            "audio_sample_rate": RATE,
            "audio_samples_evaluated": total,
            "audio_pcm_sha256": digest.hexdigest() if read_all_audio else None,
            "non_silent_audio_windows": non_silent_windows,
            "ffmpeg_used": False, "original_source_modified": False,
            "picture_sequence_persisted": False,
            "flattened_soundtrack_persisted": False,
            "realtime_device_playback_attested": False,
            "human_approval_attested": False,
        }
