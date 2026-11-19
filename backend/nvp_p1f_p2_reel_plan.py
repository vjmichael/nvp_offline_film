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
from backend.nvp_p1de_hierarchy import MAX_SOURCE_TICK

FORMAT = "nvp.p1f.p2.source_reel_plan.v1"
FPS = 24
SAMPLES_PER_FRAME = 48000 // FPS
TICKS_PER_FRAME = TICKS_PER_SECOND // FPS
FRAMES_PER_REEL = FPS * 10

LEGACY_FILM_SECONDS = 3 * 60 * 60
MAX_FILM_SECONDS = MAX_SOURCE_TICK // TICKS_PER_SECOND
MAX_REELS = (MAX_SOURCE_TICK // TICKS_PER_FRAME + FRAMES_PER_REEL-1) // FRAMES_PER_REEL
FORMAT_COMPACT = "nvp.p1f.p2.source_reel_plan.v2"
MAX_PAGE = 64


class ReelLayout:
    """Implicit exact clock index; no full output reel array for long films."""
    def __init__(self, duration_tick):
        self.duration = _int(duration_tick, "source-edited film duration", minimum=1,
                             maximum=MAX_SOURCE_TICK)
        if self.duration % TICKS_PER_FRAME:
            raise ValueError("A 24fps production needs a complete final picture instant")
        self.frames = self.duration // TICKS_PER_FRAME
        self.samples = self.duration // SAMPLE_TICK
        if self.samples != self.frames * SAMPLES_PER_FRAME:
            raise RuntimeError("Picture and source-PCM clocks disagree")
        self.count = (self.frames + FRAMES_PER_REEL-1) // FRAMES_PER_REEL

    def __len__(self):
        return self.count

    def __getitem__(self, ordinal):
        if type(ordinal) is not int:
            raise TypeError("Reel index must be an integer; use bounded page for ranges")
        if ordinal < 0:
            ordinal += self.count
        if not 0 <= ordinal < self.count:
            raise IndexError("Reel outside exact original source plan")
        first_frame = ordinal * FRAMES_PER_REEL
        frames = min(FRAMES_PER_REEL, self.frames-first_frame)
        first = first_frame * SAMPLES_PER_FRAME
        n = frames * SAMPLES_PER_FRAME
        return {"reel_index": ordinal, "first_frame": first_frame, "frame_count": frames,
                "first_sample": first, "sample_count": n, "start_tick": first*SAMPLE_TICK,
                "end_tick": (first+n)*SAMPLE_TICK, "status": "UNRENDERED"}

    def __iter__(self):
        for i in range(self.count):
            yield self[i]

    def page(self, first_index, limit):
        if (type(first_index) is not int or not 0 <= first_index < self.count or
                type(limit) is not int or not 1 <= limit <= MAX_PAGE):
            raise ValueError("Bounded exact reel page required")
        return [self[i] for i in range(first_index, min(first_index+limit, self.count))]

    def manifest(self):
        return {"format": "nvp.p1f.exact_clock_reel_index.v1", "reel_count": self.count,
                "frames_per_reel": FRAMES_PER_REEL, "page_limit": MAX_PAGE}


def reel_layout(duration_tick):
    return ReelLayout(duration_tick)


def reel_at(data, reel_index):
    """Only for a source record independently verified by P1FReelPlan.read."""
    n = _int(reel_index, "reel index")
    return reel_layout(data["duration_tick"])[n]


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
        legacy = reels.duration <= LEGACY_FILM_SECONDS * TICKS_PER_SECOND
        data = {
            "format": FORMAT if legacy else FORMAT_COMPACT, "edit_id": edit_id, "edit_revision": edit_revision,
            "edit_document_sha256": edit["document_sha256"],
            "source_edit_sha256": edit["source_edit_sha256"],
            "ticks_per_second": TICKS_PER_SECOND,
            "fps_num": FPS, "fps_den": 1,
            "sample_rate": 48000, "channels": 2,
            "duration_tick": edit["data"]["duration_tick"],
            "frame_count": reels.frames, "sample_count": reels.samples,
            **({"reels": list(reels)} if legacy else {"reel_manifest": reels.manifest()}),
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
        if record["kind"] != "presentation" or doc.get("format") not in (FORMAT, FORMAT_COMPACT):
            raise RuntimeError("Not an NVP P1-F/P2 source reel plan")
        edit = self.editor.read(pid, doc["edit_id"], doc["edit_revision"])
        expected = reel_layout(edit["data"]["duration_tick"])
        legacy = doc["format"] == FORMAT
        layout_valid = (expected.duration <= LEGACY_FILM_SECONDS*TICKS_PER_SECOND and
                        doc.get("reels") == list(expected) and "reel_manifest" not in doc
                        if legacy else doc.get("reel_manifest") == expected.manifest() and
                        "reels" not in doc)
        if (not layout_valid or record["dependencies"] != [{
                 "object_id": doc["edit_id"],
                 "revision": doc["edit_revision"], "role": "timeline"
             }] or
                doc.get("edit_document_sha256") != edit["document_sha256"] or
                doc.get("source_edit_sha256") != edit["source_edit_sha256"] or
                doc.get("duration_tick") != edit["data"]["duration_tick"] or
                doc.get("frame_count") != expected.frames or
                doc.get("sample_count") != expected.samples or
                doc.get("ticks_per_second") != TICKS_PER_SECOND or
                doc.get("fps_num") != FPS or doc.get("fps_den") != 1 or
                doc.get("sample_rate") != 48000 or doc.get("channels") != 2 or
                doc.get("state") != "PLANNED_ONLY" or
                doc.get("published_reels") != 0 or
                doc.get("picture_rendered") is not False or
                doc.get("audio_mastered") is not False or
                doc.get("portable_film_created") is not False or
                doc.get("creator_worker_authorized") is not False):
            raise RuntimeError("Production source schedule claims an unverified film")
        return record

    def page(self, pid, plan_id, *, first_index, limit=MAX_PAGE):
        record = self.read(pid, plan_id)
        layout = reel_layout(record["data"]["duration_tick"])
        rows = layout.page(first_index, limit)
        end = first_index + len(rows)
        return {"plan_document_sha256": record["document_sha256"], "reels": rows,
                "next_index": end if end < len(layout) else None,
                "total_reels": len(layout), "master_approved": False}

    def picture_instant(self, pid, plan_id, reel_index, frame_offset):
        """Map requested output picture time to one authentic source Take tick."""
        plan = self.read(pid, plan_id)
        n = _int(reel_index, "reel index")
        reel = reel_at(plan["data"], n)
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
        n = _int(reel_index, "reel index")
        reel = reel_at(plan["data"], n)
        start = _int(first_sample, "global audio cursor")
        size = _int(count, "finite audio cursor", minimum=1, maximum=4096)
        if (start < reel["first_sample"] or
                start + size > reel["first_sample"] + reel["sample_count"]):
            raise ValueError("Window cannot escape its source reel")
        return self.editor.audio_window(
            pid, plan["data"]["edit_id"], plan["data"]["edit_revision"],
            first_sample=start, count=size)

    def iter_audio_windows(self, pid, plan_id, reel_index, *, window_samples=4096,
                           cancelled=lambda: False):
        """Yield finite derived PCM windows, never a full-film WAV or master."""
        size = _int(window_samples, "bounded audio window", minimum=1, maximum=4096)
        if not callable(cancelled):
            raise TypeError("Trusted audio cancellation required")
        plan = self.read(pid, plan_id)
        reel = reel_at(plan["data"], reel_index)
        stop = reel["first_sample"] + reel["sample_count"]
        for start in range(reel["first_sample"], stop, size):
            if cancelled():
                raise InterruptedError("Creator cancelled finite original audio traversal")
            count = min(size, stop-start)
            result = self.audio_window(pid, plan_id, reel_index, first_sample=start, count=count)
            if result["first_sample"] != start or result["sample_count"] != count:
                raise RuntimeError("Original audio cursor changed")
            if self.read(pid, plan_id)["document_sha256"] != plan["document_sha256"]:
                raise RuntimeError("Original reel source changed during audio traversal")
            yield result
