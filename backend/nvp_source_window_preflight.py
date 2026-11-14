"""SCALE-03A: bounded, exact-FilmIndex source-window preflight.

Trusted native-host preparation only; NOT a creator grant or executable worker.
This does not decode frame content and must not be described as rendered media.
"""
from __future__ import annotations

from backend.nvp_bound_editorial import BoundEditorialPublisher
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_editorial_catalog import MAX_I64, _positive

FORMAT = "nvp.source_window.preflight.v1"
MAX_WINDOW_FRAMES = 96


class SourceWindowPreflight:
    def __init__(self, publisher: BoundEditorialPublisher, bridge: SourceFilmBridge):
        if not isinstance(publisher, BoundEditorialPublisher) or not isinstance(bridge, SourceFilmBridge):
            raise TypeError("Trusted bound editor and source FilmIndex bridge required")
        if publisher.index.studio.db_path.resolve() != bridge.index.studio.db_path.resolve():
            raise ValueError("Native source window requires same authoritative Studio")
        self.publisher, self.bridge = publisher, bridge

    def prepare(self, project_id, edit_id, revision, *, first_frame, frame_count,
                verify_original_bytes=True, integrity_policy="full"):
        """Map a small output interval to exact immutable source intervals.

        No full timeline/frame array is created. Repeated references to the
        same source are hashed only once per preflight. Missing/changed originals
        refuse execution; editorial metadata remains navigable independently.
        """
        _positive(first_frame, "output first frame")
        _positive(frame_count, "requested frames")
        if frame_count > MAX_WINDOW_FRAMES or first_frame > MAX_I64 - frame_count + 1:
            raise ValueError("Native source window must fit bounded frame policy")
        if verify_original_bytes is not True:
            raise PermissionError("Unverified byte bypass is not a supported policy")
        if integrity_policy not in ("full", "preview"):
            raise ValueError("Unknown source-integrity policy")
        # A preview status checks FilmIndex provenance and online state, but
        # is expressly NOT evidence that external content still hashes to
        # the ingest SHA. Final publication must use 'full'.
        checked = self.publisher.verify_revision(project_id, edit_id, revision)
        end = first_frame + frame_count
        if end - 1 > checked["total_frames"]:
            raise ValueError("Source window exceeds the committed edit")
        source_cache = {}
        slices = []
        cursor = first_frame
        while cursor < end:
            page = self.publisher.clips(project_id, edit_id, revision,
                                        first_frame=cursor, limit=100)
            if not page["clips"]:
                raise RuntimeError("Indexed editorial clip interval missing")
            advanced = False
            for clip in page["clips"]:
                begin = clip["output_first_frame"]
                stop = begin + clip["frame_count"]
                if stop <= cursor:
                    continue
                if begin > cursor:
                    raise RuntimeError("Editorial output contains a missing frame range")
                overlap_end = min(end, stop)
                sid, source_rev = clip["source_id"], clip["source_revision"]
                key = (sid, source_rev)
                if key not in source_cache:
                    current = self.bridge.resolve_source(
                        project_id, sid, source_rev,
                        verify_bytes=(integrity_policy == "full"))
                    valid_status = ("VERIFIED" if integrity_policy == "full"
                                    else "PRESENT_UNVERIFIED")
                    if (current["availability"] != valid_status or
                        (integrity_policy == "full" and
                         current["verified_bytes"] is not True) or
                        current["film_document_sha256"] != clip["source_document_sha256"]):
                        raise RuntimeError("Native source window refuses offline/invalid original")
                    source_cache[key] = current
                original = source_cache[key]
                source_first = clip["source_first_frame"] + cursor - begin
                slices.append({
                    "output_first_frame": cursor,
                    "frame_count": overlap_end - cursor,
                    "source_id": sid,
                    "source_revision": source_rev,
                    "source_document_sha256": original["film_document_sha256"],
                    "source_sha256": original["source_sha256"],
                    "source_first_frame": source_first,
                })
                cursor = overlap_end
                advanced = True
                if cursor == end:
                    break
            if not advanced:
                raise RuntimeError("Indexed source window made no progress")
        return {
            "format": FORMAT, "project_id": project_id, "edit_id": edit_id,
            "edit_revision": revision,
            "edit_document_sha256": checked["film_document_sha256"],
            "first_frame": first_frame, "frame_count": frame_count,
            "slices": slices,
            "source_preflight": ("VERIFIED_AT_PREPARATION"
                                 if integrity_policy == "full"
                                 else "PRESENT_UNVERIFIED_PREVIEW_ONLY"),
            "creator_approved": False, "frames_decoded": False,
            "native_worker_started": False, "final_master": False,
        }
