"""INDEX-TIME-03 — sealed preflight for versioned imported-film-time windows.

No decoder, OS process or creator authority is introduced here. It derives a
bounded source-frame review plan from INDEX-TIME-02 immutable FilmIndex edits.
An exact source PTS maps to an authored NVP tick; output preview filenames
are merely sequential review slots, not authoritative source film frames.
"""
from __future__ import annotations

from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
from backend.nvp_temporal_ledger import _int

FORMAT = "nvp.film_time.source_window.plan.v1"
MAX_WINDOW = 96
MODES = frozenset(("preview", "conform_prepare"))


class FilmTimeWindowPreflight:
    def __init__(self, publisher: FilmTimeEditorialPublisher):
        if not isinstance(publisher, FilmTimeEditorialPublisher):
            raise TypeError("Trusted indexed film-time editorial publisher required")
        self.publisher = publisher

    def prepare(self, project_id, edit_id, revision, *, clip_ordinal,
                first_zero, count, mode="preview"):
        _int(clip_ordinal, "imported clip ordinal")
        _int(first_zero, "original first source frame")
        _int(count, "bounded source review window", minimum=1,
             maximum=MAX_WINDOW)
        if mode not in MODES:
            raise ValueError("Unknown imported-video integrity mode")

        verified = self.publisher.verify_revision(
            project_id, edit_id, revision)
        page = self.publisher.clips(
            project_id, edit_id, revision,
            after_ordinal=clip_ordinal-1, limit=1)
        if len(page["clips"]) != 1 or page["clips"][0]["ordinal"] != clip_ordinal:
            raise KeyError("Exact imported clip ordinal not in saved edit")
        clip = page["clips"][0]
        if first_zero < clip["source_in_frame_zero"] or (
                first_zero + count > clip["source_out_frame_zero"]):
            raise ValueError("Native review window exceeds saved film-time placement")
        observation = self.publisher.map_clip_window(
            project_id, edit_id, revision, clip_ordinal=clip_ordinal,
            first_zero=first_zero, count=count)
        original = self.publisher.bridge.resolve_source(
            project_id, clip["source_id"], clip["source_revision"],
            verify_bytes=(mode == "conform_prepare"))
        required = "VERIFIED" if mode == "conform_prepare" else "PRESENT_UNVERIFIED"
        if (original["availability"] != required or
            original["film_document_sha256"] != clip["source_document_sha256"] or
            original["source_sha256"] != clip["source_sha256"] or
            (mode == "conform_prepare" and original["verified_bytes"] is not True)):
            raise RuntimeError("Original source custody cannot support this job")
        if (verified["edit_document_sha256"] != observation["edit_document_sha256"]
            or observation["source_in_pts"] != clip["source_in_pts"]
            or observation["source_sha256_at_original_ingest"] != clip["source_sha256"]):
            raise RuntimeError("Sealed editorial source/time identity changed")
        frames = []
        last = -1
        for i, row in enumerate(observation["frames"]):
            if (row["source_frame_zero"] != first_zero+i or
                row["source_pts"] >= clip["source_out_pts"] or
                row["time_tick"] < clip["film_start_tick"] or
                row["time_tick"] >= clip["film_end_tick"] or
                row["time_tick"] <= last):
                raise RuntimeError("Imported indexed source frame no longer maps to saved film time")
            last = row["time_tick"]
            frames.append({
                "review_frame": i+1,
                "source_frame_zero": row["source_frame_zero"],
                "source_pts": row["source_pts"],
                "film_time_tick": row["time_tick"],
                "exact_time": row["exactly_representable"],
                "quantization_error_ticks": row["quantization_error_ticks"],
            })
        return {
            "format": FORMAT,
            "project_id": project_id,
            "edit_id": edit_id, "edit_revision": revision,
            "edit_document_sha256": verified["edit_document_sha256"],
            "clip_ordinal": clip_ordinal,
            "source_id": clip["source_id"],
            "source_revision": clip["source_revision"],
            "source_document_sha256": clip["source_document_sha256"],
            "source_sha256_at_original_ingest": clip["source_sha256"],
            "source_in_frame_zero": clip["source_in_frame_zero"],
            "source_out_frame_zero": clip["source_out_frame_zero"],
            "source_in_pts": clip["source_in_pts"],
            "source_out_pts": clip["source_out_pts"],
            "source_time_base_num": clip["time_base_num"],
            "source_time_base_den": clip["time_base_den"],
            "film_clip_start_tick": clip["film_start_tick"],
            "film_clip_end_tick": clip["film_end_tick"],
            "rounding_policy": clip["rounding_policy"],
            "source_stamp": observation["source_stamp"],
            "first_source_frame_zero": first_zero,
            "frame_count": count,
            "frames": frames,
            "mode": mode,
            "source_integrity": (
                "FULL_SHA_VERIFIED_AT_PREFLIGHT" if mode == "conform_prepare"
                else "STAMP_UNVERIFIED_PREVIEW"),
            "creator_approved": False, "rendered_frames": False,
            "approved_final": False, "native_worker_started": False,
        }
