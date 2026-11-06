"""INDEX-TIME-04 — reverse seek on the authored film clock.

Resolve an arbitrary NVP film-time tick to the currently visible imported
source video frame, using the original indexed presentation timestamps.

This is a read-only preview-selection capability, NOT source authorization,
FFmpeg execution, full original SHA verification or film-master publication.
The existing INDEX-TIME-03 native review host is the only authorized worker
path; the source index remains separate from the Temporal Ledger.
"""
from __future__ import annotations

from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
from backend.nvp_source_pts_film_time import pts_to_film_tick
from backend.nvp_source_window_decode import _read_sources
from backend.nvp_temporal_ledger import _int

FORMAT = "nvp.film_time.imported_frame_selection.v1"
MAX_FRAME_LOOKUPS = 64


class FilmTimePlaybackResolver:
    """O(log frame count) read-only seek through one existing SQLite index.

    Querying frame ordinals via the primary key requires no second time index
    or new FFprobe pass. Quantized film ticks are computed independently
    from original absolute source PTS for every midpoint; no FPS estimate.
    """
    def __init__(self, publisher: FilmTimeEditorialPublisher):
        if not isinstance(publisher,FilmTimeEditorialPublisher):
            raise TypeError("Authoritative versioned film-time editor required")
        self.publisher=publisher

    def resolve(self, project_id, edit_id, revision, *, tick):
        """Return the held source frame at tick, or an explicit empty gap.

        A source frame is held on [mapped_frame_tick, mapped_next_tick).
        The saved out-exclusive source PTS determines the final clip boundary,
        so no guessed final-frame duration or fractional FPS enters the path.
        """
        _int(tick,"requested authored film-time tick")
        record=self.publisher._revision(project_id,edit_id,revision)
        clip=self.publisher.at(project_id,edit_id,revision,tick=tick)
        base={
            "format":FORMAT,"project_id":project_id,"edit_id":edit_id,
            "edit_revision":revision,
            "edit_document_sha256":record["document_sha256"],
            "requested_film_tick":tick,
            "source_sha_verified_this_operation":False,
            "source_integrity":"SOURCE_STAMP_UNVERIFIED",
            "native_film_events_modified":False,
            "picture_rendered":False,
        }
        if clip is None:
            return {
                **base,"status":"EMPTY_IMPORTED_VIDEO_GAP",
                "clip_ordinal":None,"source_frame_zero":None,
                "review_task_started":False,
            }
        source_id=clip["source_id"]
        source_sha=clip["source_sha256"]
        original=self.publisher.index.read_revision(
            project_id,source_id,clip["source_revision"])
        if (original["kind"]!="asset" or
            original["document_sha256"]!=clip["source_document_sha256"] or
            original["data"].get("content_sha256")!=source_sha):
            raise RuntimeError("Imported video FilmIndex source revision changed")
        live=self.publisher.bridge.resolve_source(
            project_id,source_id,clip["source_revision"],verify_bytes=False)
        if (live["availability"]!="PRESENT_UNVERIFIED" or
            live["film_document_sha256"]!=clip["source_document_sha256"] or
            live["source_sha256"]!=source_sha):
            raise RuntimeError("Current original no longer matches saved source")
        path=_read_sources(self.publisher.index.studio,project_id,source_id)
        idx=self.publisher.frame_index
        info=idx.ensure(project_id,source_id,source_sha,path)
        lower=clip["source_in_frame_zero"]
        upper=clip["source_out_frame_zero"]
        if (upper>=info["frame_count"] or
            info["time_base_num"]!=clip["time_base_num"] or
            info["time_base_den"]!=clip["time_base_den"]):
            raise RuntimeError("Original index no longer covers saved clip")
        queried=0
        # SQLite holds a consistent index snapshot during the binary search.
        with idx._open_readonly(info["path"]) as db:
            def read(at):
                nonlocal queried
                queried+=1
                if queried>MAX_FRAME_LOOKUPS:
                    raise RuntimeError("Indexed film-time seek exceeded bounded work")
                result=db.execute(
                    "SELECT ordinal,pts FROM frames WHERE ordinal=?",(at,)
                ).fetchone()
                if result is None or result[0]!=at or type(result[1]) is not int:
                    raise RuntimeError("Source frame ordinal/PTS missing from index")
                return result[1]
            # Anchor the source and final boundary to FilmIndex exact PTS.
            if (read(lower)!=clip["source_in_pts"] or
                read(upper)!=clip["source_out_pts"]):
                raise RuntimeError("Saved source in/out boundaries no longer match index")
            def mapped(pts):
                return pts_to_film_tick(
                    source_pts=pts,source_in_pts=clip["source_in_pts"],
                    time_base_num=clip["time_base_num"],
                    time_base_den=clip["time_base_den"],
                    film_in_tick=clip["film_start_tick"],
                    rounding=clip["rounding_policy"])["time_tick"]
            lo,hi=lower,upper
            while lo<hi:
                middle=(lo+hi)//2
                if mapped(read(middle))<=tick:
                    lo=middle+1
                else:
                    hi=middle
            selected=lo-1
            if selected<lower or selected>=upper:
                raise RuntimeError("Requested tick cannot map to an indexed clip frame")
            source_pts=read(selected)
            next_pts=read(selected+1)
            start_tick=mapped(source_pts)
            end_tick=mapped(next_pts)
            if selected>lower:
                previous_pts=read(selected-1)
                if (previous_pts>=source_pts or
                    mapped(previous_pts)>=start_tick):
                    raise RuntimeError("Ambiguous or non-increasing source frame interval")
            if (source_pts>=next_pts or
                start_tick>tick or tick>=end_tick or
                end_tick>clip["film_end_tick"] or
                start_tick<clip["film_start_tick"] or
                end_tick<=start_tick):
                raise RuntimeError("Source index has ambiguous frame display intervals")
        # Reapply INDEX-TIME-02's authoritative source version, original
        # inpoint/outpoint, current stamp and quantization checks. A binary
        # search is never itself proof that a mutable cache is trustworthy.
        checked=self.publisher.map_clip_window(
            project_id,edit_id,revision,clip_ordinal=clip["ordinal"],
            first_zero=selected,count=1)
        frame=checked["frames"][0]
        if (checked["source_stamp"]!=info["source_stamp"] or
            checked["source_sha256_at_original_ingest"]!=source_sha or
            checked["edit_document_sha256"]!=base["edit_document_sha256"] or
            frame["source_pts"]!=source_pts or
            frame["time_tick"]!=start_tick):
            raise RuntimeError("Selected imported frame changed after indexed lookup")
        result={
            **base,
            "status":"INDEXED_SOURCE_FRAME_SELECTED",
            "clip_ordinal":clip["ordinal"],
            "source_id":source_id,
            "source_revision":clip["source_revision"],
            "source_document_sha256":clip["source_document_sha256"],
            "source_sha256_at_original_ingest":source_sha,
            "source_frame_zero":selected,
            "source_pts":source_pts,
            "next_source_frame_zero":selected+1,
            "next_source_pts":next_pts,
            "frame_film_start_tick":start_tick,
            "frame_film_end_tick":end_tick,
            "clip_film_start_tick":clip["film_start_tick"],
            "clip_film_end_tick":clip["film_end_tick"],
            "rounding_policy":clip["rounding_policy"],
            "exact_time":frame["exactly_representable"],
            "quantization_error_ticks":frame["quantization_error_ticks"],
            "source_time_base_num":clip["time_base_num"],
            "source_time_base_den":clip["time_base_den"],
            "seek_kind":"SQLITE_ORDINAL_BINARY_SEARCH",
            "frame_index_pts_reads":queried,
            "source_stamp":checked["source_stamp"],
            "review_task_started":False,
        }
        return result

    def stage_review_at(self, host, project_id, edit_id, revision, *,
                        tick,destination,creator_event,mode="preview",
                        ram_mb=1024,duration_s=1800):
        """Optionally enqueue selected frame via the *existing* native host.

        No automatic approval is manufactured: the host independently checks
        creator policy, plan SHA, exact source revision and frame PTS.
        """
        from backend.nvp_film_time_window_host import NativeFilmTimeWindowHost
        if not isinstance(host,NativeFilmTimeWindowHost):
            raise TypeError("Existing authorized native film-time host required")
        if (host.preflight.publisher.index.studio.db_path.resolve()!=
                self.publisher.index.studio.db_path.resolve()):
            raise RuntimeError("Source selector and approved worker use different Studio")
        selected=self.resolve(project_id,edit_id,revision,tick=tick)
        if selected["status"]=="EMPTY_IMPORTED_VIDEO_GAP":
            return {**selected,"task_id":None}
        task=host.stage_and_approve(
            project_id,edit_id,revision,
            clip_ordinal=selected["clip_ordinal"],
            first_zero=selected["source_frame_zero"],count=1,
            mode=mode,destination=destination,creator_event=creator_event,
            ram_mb=ram_mb,duration_s=duration_s)
        if task["edit_document_sha256"]!=selected["edit_document_sha256"]:
            raise RuntimeError("Native approval used a different FilmIndex edit")
        return {**selected,
                "status":"INDEXED_REVIEW_TASK_QUEUED",
                "review_task_started":False,
                "task_id":task["task_id"],
                "task_state":task["state"],
                "requested_preview_mode":mode}
