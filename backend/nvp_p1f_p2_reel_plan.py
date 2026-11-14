"""P1-F / P2 exact-source reel scheduler on the accepted P1-D/E conform.

Source-plan only: creates no picture, soundtrack, encoding, worker permission,
installed feature-length movie or successful production receipt. A genuine
Cycles/approved native renderer and separate verified reel publisher must
supply those before production completion can be claimed.

A plan is an immutable FilmIndex presentation revision, not a proxy film.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, _int
from backend.nvp_p1de_edit_audio import P1DEConform, SAMPLE_TICK

FORMAT = "nvp.p1f.p2.source_reel_plan.v1"
FPS = 24
SAMPLES_PER_FRAME = 48000 // FPS
TICKS_PER_FRAME = TICKS_PER_SECOND // FPS
FRAMES_PER_REEL = FPS * 10
MAX_FILM_SECONDS = 3 * 60 * 60
MAX_REELS = (MAX_FILM_SECONDS + 9) // 10


def reel_layout(duration_tick):
    """Pure exact source clock; 30min=180 reels, 3h=1080 reels.

    The last output frame must be complete. Frame rate is a derived,
    explicitly selected export cadence, never the original source clock.
    """
    duration = _int(duration_tick, "source-edited film duration", minimum=1)
    if duration > MAX_FILM_SECONDS * TICKS_PER_SECOND:
        raise ValueError("Source film exceeds the three-hour native scheduler cap")
    if duration % TICKS_PER_FRAME:
        raise ValueError("A 24fps production needs a complete final picture instant")
    frame_count = duration // TICKS_PER_FRAME
    sample_count = duration // SAMPLE_TICK
    if sample_count != frame_count * SAMPLES_PER_FRAME:
        raise RuntimeError("Picture and source-PCM clocks disagree")
    result = []
    for ordinal, first_frame in enumerate(
            range(0, frame_count, FRAMES_PER_REEL)):
        if ordinal >= MAX_REELS:
            raise ValueError("Too many verified output reel slots")
        frames = min(FRAMES_PER_REEL, frame_count - first_frame)
        first = first_frame * SAMPLES_PER_FRAME
        n = frames * SAMPLES_PER_FRAME
        result.append({
            "reel_index": ordinal,
            "first_frame": first_frame, "frame_count": frames,
            "first_sample": first, "sample_count": n,
            "start_tick": first * SAMPLE_TICK,
            "end_tick": (first + n) * SAMPLE_TICK,
            "status": "UNRENDERED",
        })
    if not result or result[-1]["end_tick"] != duration:
        raise RuntimeError("Incomplete exact film-time reel coverage")
    return result


class P1FReelPlan:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Trusted canonical FilmIndex is required")
        self.index = index
        # A read-only editor never grants new creator consent or execution.
        self.editor = P1DEConform(index, approve_edit=lambda *_: False)

    def publish(self, pid, plan_id, *, edit_id, edit_revision,
                expected_edit_document_sha256):
        _require_pid(pid)
        _id(plan_id, "source production plan")
        _id(edit_id, "approved edit identity")
        _int(edit_revision, "approved edit revision", minimum=1)
        _sha(expected_edit_document_sha256)
        edit = self.editor.read(pid, edit_id, edit_revision)
        if edit["document_sha256"] != expected_edit_document_sha256:
            raise RuntimeError("Original approved edit revision no longer matches plan")
        reels = reel_layout(edit["data"]["duration_tick"])
        data = {
            "format": FORMAT, "edit_id": edit_id, "edit_revision": edit_revision,
            "edit_document_sha256": edit["document_sha256"],
            "source_edit_sha256": edit["source_edit_sha256"],
            "ticks_per_second": TICKS_PER_SECOND,
            "fps_num": FPS, "fps_den": 1,
            "sample_rate": 48000, "channels": 2,
            "duration_tick": edit["data"]["duration_tick"],
            "frame_count": sum(x["frame_count"] for x in reels),
            "sample_count": sum(x["sample_count"] for x in reels),
            "reels": reels,
            "state": "PLANNED_ONLY", "published_reels": 0,
            "picture_rendered": False, "audio_mastered": False,
            "portable_film_created": False,
            "creator_worker_authorized": False,
        }
        return self.index.register_revision(
            pid, plan_id, "presentation", data, expected_revision=0,
            dependencies=[{
                "object_id": edit_id, "revision": edit_revision, "role": "timeline"
            }])

    def read(self, pid, plan_id):
        record = self.index.read_revision(pid, plan_id, 1)
        doc = record["data"]
        if record["kind"] != "presentation" or doc.get("format") != FORMAT:
            raise RuntimeError("Not an NVP P1-F/P2 source reel plan")
        edit = self.editor.read(pid, doc["edit_id"], doc["edit_revision"])
        expected = reel_layout(edit["data"]["duration_tick"])
        if (record["dependencies"] != [{
                 "object_id": doc["edit_id"],
                 "revision": doc["edit_revision"], "role": "timeline"
             }] or
                doc.get("edit_document_sha256") != edit["document_sha256"] or
                doc.get("source_edit_sha256") != edit["source_edit_sha256"] or
                doc.get("reels") != expected or
                doc.get("duration_tick") != edit["data"]["duration_tick"] or
                doc.get("frame_count") != sum(x["frame_count"] for x in expected) or
                doc.get("sample_count") != sum(x["sample_count"] for x in expected) or
                doc.get("state") != "PLANNED_ONLY" or
                doc.get("published_reels") != 0 or
                doc.get("picture_rendered") is not False or
                doc.get("audio_mastered") is not False or
                doc.get("portable_film_created") is not False or
                doc.get("creator_worker_authorized") is not False):
            raise RuntimeError("Production source schedule claims an unverified film")
        return record

    def picture_instant(self, pid, plan_id, reel_index, frame_offset):
        """Map requested output picture time to one authentic source Take tick."""
        plan = self.read(pid, plan_id)
        reels = plan["data"]["reels"]
        n = _int(reel_index, "reel index")
        if n >= len(reels):
            raise IndexError("Reel not in approved source plan")
        reel = reels[n]
        f = _int(frame_offset, "frame offset")
        if f >= reel["frame_count"]:
            raise IndexError("Picture instant beyond finite reel")
        output_sample = reel["first_sample"] + f * SAMPLES_PER_FRAME
        exact = self.editor.plan(
            pid, plan["data"]["edit_id"], plan["data"]["edit_revision"],
            first_sample=output_sample, count=1)
        if len(exact["slices"]) != 1:
            raise RuntimeError("Frame-to-source mapping is ambiguous")
        sl = exact["slices"][0]
        return {
            "reel_index": n, "output_frame": reel["first_frame"] + f,
            "output_tick": output_sample * SAMPLE_TICK,
            "source_take_id": sl["take_id"],
            "source_take_sha256": sl["take_sha256"],
            "source_tick": sl["source_first_sample"] * SAMPLE_TICK,
            "source_camera": sl["listener_path"],
            "edit_document_sha256": plan["data"]["edit_document_sha256"],
            "rendered": False
        }

    def audio_window(self, pid, plan_id, reel_index, *, first_sample, count):
        """Reference actual actor PCM, but never publish a movie from a plan."""
        plan = self.read(pid, plan_id)
        reels = plan["data"]["reels"]
        n = _int(reel_index, "reel index")
        if n >= len(reels):
            raise IndexError("Reel not found")
        reel = reels[n]
        start = _int(first_sample, "global audio cursor")
        size = _int(count, "finite audio cursor", minimum=1, maximum=4096)
        if (start < reel["first_sample"] or
                start + size > reel["first_sample"] + reel["sample_count"]):
            raise ValueError("Window cannot escape its source reel")
        return self.editor.audio_window(
            pid, plan["data"]["edit_id"], plan["data"]["edit_revision"],
            first_sample=start, count=size)
