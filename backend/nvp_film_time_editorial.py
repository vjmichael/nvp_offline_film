"""INDEX-TIME-02 — revisioned film-time placements of imported video.

This is an *editorial metadata* publisher, not an editing/rendering worker,
creator authorization, a video decoder, or a full-media custody check.
NVP's Temporal Ledger and OpenUSD remain the authoritative native film.

Source in/out and placement are backed by exact native indexed PTS. An
out-exclusive frame MUST exist in the index: its PTS defines a non-guessed
end boundary. This initial single-lane contract refuses overlap/retiming.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_native_frame_index import NVPFrameIndex
from backend.nvp_source_film_bridge import SourceFilmBridge, FORMAT as SOURCE_FORMAT
from backend.nvp_source_pts_film_time import (
    IndexedSourceFilmTime, pts_to_film_tick, ROUNDING)
from backend.nvp_source_window_decode import _read_sources
from backend.nvp_temporal_ledger import _int, MAX_TICK

FORMAT = "nvp.edit.imported_film_time.v1"
MAX_CLIPS = 10000
MAX_PAGE = 250
COLUMNS = (
    "ordinal", "source_id", "source_revision", "source_document_sha256",
    "source_sha256", "source_in_frame_zero", "source_out_frame_zero",
    "source_in_pts", "source_out_pts", "time_base_num", "time_base_den",
    "film_start_tick", "film_end_tick", "rounding_policy"
)
DDL_COLUMNS = """
    ordinal INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    source_document_sha256 TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_in_frame_zero INTEGER NOT NULL,
    source_out_frame_zero INTEGER NOT NULL,
    source_in_pts INTEGER NOT NULL,
    source_out_pts INTEGER NOT NULL,
    time_base_num INTEGER NOT NULL,
    time_base_den INTEGER NOT NULL,
    film_start_tick INTEGER NOT NULL,
    film_end_tick INTEGER NOT NULL,
    rounding_policy TEXT NOT NULL,
    row_sha256 TEXT NOT NULL
"""


def _encode(values):
    return (json.dumps(list(values),separators=(",",":"),sort_keys=True,
                       ensure_ascii=True,allow_nan=False)+"\n").encode("ascii")


def _row_sha(values):
    return hashlib.sha256(_encode(values)).hexdigest()


def _fields(row):
    return tuple(row[name] for name in COLUMNS)


def _check_row(row, ordinal=None, minimum_start=0):
    values=_fields(row)
    if ordinal is not None and row["ordinal"]!=ordinal:
        raise RuntimeError("Imported film-time clip ordinal changed")
    if (type(row["film_start_tick"]) is not int or
        type(row["film_end_tick"]) is not int or
        row["film_start_tick"]<minimum_start or
        row["film_end_tick"]<=row["film_start_tick"] or
        row["film_end_tick"]>MAX_TICK or
        type(row["source_in_frame_zero"]) is not int or
        type(row["source_out_frame_zero"]) is not int or
        row["source_in_frame_zero"]<0 or
        row["source_out_frame_zero"]<=row["source_in_frame_zero"] or
        row["source_out_pts"]<=row["source_in_pts"] or
        row["rounding_policy"] not in ROUNDING or
        _row_sha(values)!=row["row_sha256"]):
        raise RuntimeError("Indexed film-time editorial row damaged or reordered")
    end=pts_to_film_tick(
        source_pts=row["source_out_pts"],
        source_in_pts=row["source_in_pts"],
        time_base_num=row["time_base_num"],
        time_base_den=row["time_base_den"],
        film_in_tick=row["film_start_tick"],
        rounding=row["rounding_policy"])["time_tick"]
    if end!=row["film_end_tick"]:
        raise RuntimeError("Film-time clip duration disagrees with exact source PTS")
    return {name:row[name] for name in COLUMNS}


class FilmTimeEditorialPublisher:
    """Small bounded source-stamp queries, durable SQLite placement manifest.

    Existing fixed-FPS BoundEditorialPublisher is unchanged. This is a
    separate FilmIndex "edit" data format and independently versioned source
    binding table, so old edits and source recordings remain untouched.
    """

    def __init__(self, index: FilmIndex, bridge: SourceFilmBridge,
                 frame_index: NVPFrameIndex):
        if (not isinstance(index,FilmIndex) or
            not isinstance(bridge,SourceFilmBridge) or
            not isinstance(frame_index,NVPFrameIndex)):
            raise TypeError("Trusted FilmIndex, source bridge and frame index required")
        if index.studio.db_path.resolve()!=bridge.index.studio.db_path.resolve():
            raise ValueError("Source and editorial FilmIndex must use the same Studio")
        self.index=index
        self.bridge=bridge
        self.frame_index=frame_index
        self.mapper=IndexedSourceFilmTime(frame_index)
        with index.studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS
                nvp_time_editorial_clips (
            """+DDL_COLUMNS+""",
            PRIMARY KEY(project_id,edit_id,revision,ordinal)
            )""".replace("nvp_time_editorial_clips (\n","nvp_time_editorial_clips (\n"
                "    project_id TEXT NOT NULL,\n"
                "    edit_id TEXT NOT NULL,\n"
                "    revision INTEGER NOT NULL,\n"))
            db.execute("""CREATE INDEX IF NOT EXISTS
                nvp_time_editorial_seek ON nvp_time_editorial_clips
                (project_id,edit_id,revision,film_start_tick)""")
            db.execute("""CREATE INDEX IF NOT EXISTS
                nvp_time_editorial_dependents ON nvp_time_editorial_clips
                (project_id,source_id,source_revision,edit_id,revision)""")

    def _source_bound(self, project_id, clip):
        sid=_id(clip["source_id"],"external film source ID")
        revision=_int(clip["source_revision"],"source revision",minimum=1)
        start=_int(clip["source_in_frame_zero"],"source inpoint ordinal")
        out=_int(clip["source_out_frame_zero"],"source outpoint ordinal")
        film=_int(clip["film_in_tick"],"film placement tick")
        rounding=clip["rounding"]
        if rounding not in ROUNDING or out<=start:
            raise ValueError("A source clip must have increasing in/out ordinals")
        source_record=self.index.read_revision(project_id,sid,revision)
        if (source_record["kind"]!="asset" or
            source_record["data"].get("format")!=SOURCE_FORMAT):
            raise RuntimeError("Source clip must reference indexed external video")
        snapshot=self.bridge.resolve_source(
            project_id,sid,revision,verify_bytes=False)
        if (snapshot["availability"]!="PRESENT_UNVERIFIED" or
            snapshot["film_document_sha256"]!=source_record["document_sha256"] or
            snapshot["source_sha256"]!=source_record["data"]["content_sha256"] or
            source_record["data"]["media_type"] not in (
                "video/mp4","video/quicktime","video/x-matroska",
                "video/webm","application/octet-stream")):
            raise RuntimeError("Original source not present with exact project identity")
        # Source locator comes from the trusted inventory, never a model
        # generated path or a stored source identity in the edit manifest.
        path=_read_sources(self.index.studio,project_id,sid)
        first=self.frame_index.window(
            project_id,sid,snapshot["source_sha256"],path,
            first_zero=start,count=1)
        end=self.frame_index.window(
            project_id,sid,snapshot["source_sha256"],path,
            first_zero=out,count=1)
        if any(first[k]!=end[k] for k in (
                "index_path","source_stamp","time_base_num","time_base_den")):
            raise RuntimeError("Indexed original changed across source in/out reads")
        in_pts=first["frames"][0]["pts"]
        out_pts=end["frames"][0]["pts"]
        if out_pts<=in_pts:
            raise RuntimeError("Source outpoint time precedes inpoint")
        mapped_end=pts_to_film_tick(
            source_pts=out_pts,source_in_pts=in_pts,
            time_base_num=first["time_base_num"],
            time_base_den=first["time_base_den"],film_in_tick=film,
            rounding=rounding)["time_tick"]
        if mapped_end<=film:
            raise ValueError("Source clip interval collapsed on NVP Film Time")
        return {
            "source_id":sid,"source_revision":revision,
            "source_document_sha256":source_record["document_sha256"],
            "source_sha256":snapshot["source_sha256"],
            "source_in_frame_zero":start,"source_out_frame_zero":out,
            "source_in_pts":in_pts,"source_out_pts":out_pts,
            "time_base_num":first["time_base_num"],
            "time_base_den":first["time_base_den"],
            "film_start_tick":film,"film_end_tick":mapped_end,
            "rounding_policy":rounding,
        }

    def publish(self, project_id, edit_id, clips, *,
                expected_revision=0):
        """Commit complete immutable edit revision and normalized clip rows.

        The FilmIndex manifest and all source bindings share one SQLite
        transaction. A failed or interrupted guarded commit publishes no
        executable editorial revision, even if source caches were generated.
        """
        _require_pid(project_id)
        _id(edit_id,"film-time edit ID")
        _int(expected_revision,"expected edit revision")
        rev=expected_revision+1
        with tempfile.TemporaryDirectory(prefix="nvp-time-edit-") as tmp:
            staged=sqlite3.connect(Path(tmp)/"source_clips.sqlite3")
            staged.row_factory=sqlite3.Row
            try:
                staged.execute("CREATE TABLE rows ("+DDL_COLUMNS+
                               ", PRIMARY KEY(ordinal))")
                seen=0
                last_end=0
                total=0
                digest=hashlib.sha256()
                for clip in clips:
                    if seen>=MAX_CLIPS:
                        raise ValueError("Film-time clip manifest exceeds indexed bound")
                    if type(clip) is not dict or set(clip)!={
                            "source_id","source_revision","source_in_frame_zero",
                            "source_out_frame_zero","film_in_tick","rounding"}:
                        raise ValueError("Expected exact source and film-time clip fields")
                    item=self._source_bound(project_id,clip)
                    if item["film_start_tick"]<last_end:
                        raise ValueError("Overlapping imported-media clips require a later mixer")
                    row={"ordinal":seen,**item}
                    values=_fields(row)
                    sha=_row_sha(values)
                    staged.execute(
                        "INSERT INTO rows VALUES ("+",".join("?" for _ in range(15))+")",
                        (*values,sha))
                    digest.update(_encode(values))
                    seen+=1
                    last_end=item["film_end_tick"]
                    total=max(total,last_end)
                if not seen:
                    raise ValueError("Film-time edit must contain at least one clip")
                staged.commit()
                summary={
                    "format":FORMAT,"clip_count":seen,
                    "duration_tick":total,
                    "clip_manifest_sha256":digest.hexdigest(),
                    "source_mode":"indexed_original_pts_no_source_fps_assumption",
                    "single_video_lane_no_retime":True,
                    "imported_source_custody":"STAMP_UNVERIFIED_FOR_PREVIEW",
                    "creator_approved":False,
                    "native_film_events_modified":False,
                    "presentation_frames_rendered":False,
                }
                def guard(db):
                    found=0
                    actual=hashlib.sha256()
                    for row in staged.execute("SELECT * FROM rows ORDER BY ordinal"):
                        fields=_fields(row)
                        if _row_sha(fields)!=row["row_sha256"]:
                            raise RuntimeError("Source-time staging modified")
                        src=self.index._read_revision(
                            db,project_id,row["source_id"],row["source_revision"])
                        if (src is None or src["kind"]!="asset" or
                            src["document_sha"]!=row["source_document_sha256"]):
                            raise RuntimeError("Immutable source binding changed before commit")
                        db.execute("""INSERT INTO nvp_time_editorial_clips
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (project_id,edit_id,rev,*fields,row["row_sha256"]))
                        actual.update(_encode(fields))
                        found+=1
                    if found!=seen or actual.hexdigest()!=digest.hexdigest():
                        raise RuntimeError("Source placement staging manifest changed")
                return self.index.register_revision(
                    project_id,edit_id,"edit",summary,
                    expected_revision=expected_revision,
                    dependencies=[],precommit_guard=guard)
            finally:
                staged.close()

    def _revision(self, project_id, edit_id, revision):
        doc=self.index.read_revision(project_id,edit_id,revision)
        if doc["kind"]!="edit" or doc["data"].get("format")!=FORMAT:
            raise RuntimeError("Not a versioned imported-media film-time edit")
        return doc

    def clips(self, project_id, edit_id, revision, *,
              after_ordinal=-1,limit=100):
        """Browse saved placements offline; source bytes are NOT verified."""
        record=self._revision(project_id,edit_id,revision)
        if type(after_ordinal) is not int or after_ordinal < -1:
            raise ValueError("Invalid clip continuation cursor")
        _int(limit,"clip page size",minimum=1,maximum=MAX_PAGE)
        with self.index.studio._connection() as db:
            rows=db.execute("""SELECT * FROM nvp_time_editorial_clips
                WHERE project_id=? AND edit_id=? AND revision=?
                  AND ordinal>? ORDER BY ordinal LIMIT ?""",
                (project_id,edit_id,revision,after_ordinal,limit+1)).fetchall()
        page=[]
        for row in rows[:limit]:
            page.append(_check_row(dict(row)))
        return {
            "edit_document_sha256":record["document_sha256"],
            "revision":revision,
            "clip_count":record["data"]["clip_count"],
            "duration_tick":record["data"]["duration_tick"],
            "clips":page,
            "next_after_ordinal":page[-1]["ordinal"] if len(rows)>limit else None,
            "source_bytes_verified":False,
        }

    def at(self, project_id, edit_id, revision, *, tick):
        """One placed source clip, or None in an intentional editorial gap."""
        record=self._revision(project_id,edit_id,revision)
        _int(tick,"film-time position")
        if tick>=record["data"]["duration_tick"]:
            return None
        with self.index.studio._connection() as db:
            rows=db.execute("""SELECT * FROM nvp_time_editorial_clips
                WHERE project_id=? AND edit_id=? AND revision=?
                    AND film_start_tick<=? AND film_end_tick>?
                ORDER BY film_start_tick LIMIT 2""",
                (project_id,edit_id,revision,tick,tick)).fetchall()
        if len(rows)>1:
            raise RuntimeError("Editorial imported-media timeline overlaps")
        return _check_row(dict(rows[0])) if rows else None

    def verify_revision(self, project_id, edit_id, revision):
        """Full source-revision/manifest audit; valid even if originals offline.

        This does not hash external footage and is NOT master-media approval.
        """
        record=self._revision(project_id,edit_id,revision)
        doc=record["data"]
        digest=hashlib.sha256()
        count=0
        end=0
        source_refs={}
        with self.index.studio._connection() as db:
            rows=db.execute("""SELECT * FROM nvp_time_editorial_clips
                WHERE project_id=? AND edit_id=? AND revision=?
                ORDER BY ordinal""",(project_id,edit_id,revision))
            for row in rows:
                item=_check_row(dict(row),ordinal=count,minimum_start=end)
                key=(item["source_id"],item["source_revision"])
                if key not in source_refs:
                    source_refs[key]=self.index._read_revision(
                        db,project_id,*key)
                src=source_refs[key]
                if src is None or src["kind"]!="asset" or (
                        src["document_sha"]!=item["source_document_sha256"]):
                    raise RuntimeError("Referenced immutable original revision changed")
                digest.update(_encode(_fields(item)))
                end=item["film_end_tick"]
                count+=1
        if (count!=doc["clip_count"] or end!=doc["duration_tick"] or
            digest.hexdigest()!=doc["clip_manifest_sha256"]):
            raise RuntimeError("Film-time edit SQLite rows disagree with FilmIndex")
        return {
            "status":"VERIFIED_FILMINDEX_IMPORTED_PLACEMENTS",
            "edit_document_sha256":record["document_sha256"],
            "revision":revision,"clips":count,
            "duration_tick":end,
            "source_bytes_verified":False,"native_events_modified":False,
        }

    def map_clip_window(self, project_id, edit_id, revision, *,
                        clip_ordinal, first_zero, count):
        """Reopen actual original PTS and verify against saved immutable clip."""
        _int(clip_ordinal,"editorial clip ordinal")
        _int(first_zero,"source first frame ordinal")
        _int(count,"bounded source window frames",minimum=1,maximum=96)
        rec=self._revision(project_id,edit_id,revision)
        with self.index.studio._connection() as db:
            row=db.execute("""SELECT * FROM nvp_time_editorial_clips
                WHERE project_id=? AND edit_id=? AND revision=? AND ordinal=?""",
                (project_id,edit_id,revision,clip_ordinal)).fetchone()
        if row is None:
            raise KeyError("Film-time clip not present in this edit revision")
        clip=_check_row(dict(row),ordinal=clip_ordinal)
        if first_zero<clip["source_in_frame_zero"] or (
                first_zero+count>clip["source_out_frame_zero"]):
            raise ValueError("Requested source frame window exceeds saved clip")
        record=self.index.read_revision(
            project_id,clip["source_id"],clip["source_revision"])
        if (record["kind"]!="asset" or
            record["data"].get("format")!=SOURCE_FORMAT or
            record["document_sha256"]!=clip["source_document_sha256"] or
            record["data"]["content_sha256"]!=clip["source_sha256"]):
            raise RuntimeError("FilmIndex original identity differs from saved placement")
        snapshot=self.bridge.resolve_source(
            project_id,clip["source_id"],clip["source_revision"],verify_bytes=False)
        if snapshot["availability"]!="PRESENT_UNVERIFIED":
            raise RuntimeError("Indexed original offline or changed; placement remains saved")
        path=_read_sources(self.index.studio,project_id,clip["source_id"])
        mapped=self.mapper.map_window(
            project_id,clip["source_id"],clip["source_sha256"],path,
            source_in_frame_zero=clip["source_in_frame_zero"],
            film_in_tick=clip["film_start_tick"],first_zero=first_zero,
            count=count,rounding=clip["rounding_policy"])
        if (mapped["source_in_pts"]!=clip["source_in_pts"] or
            mapped["frames"][0]["source_time_base_num"]!=clip["time_base_num"] or
            mapped["frames"][0]["source_time_base_den"]!=clip["time_base_den"] or
            mapped["source_sha256_at_original_ingest"]!=clip["source_sha256"] or
            any(x["time_tick"]>=clip["film_end_tick"] for x in mapped["frames"])):
            raise RuntimeError("Restarted indexed source no longer matches saved edit")
        return {**mapped,
                "edit_document_sha256":rec["document_sha256"],
                "edit_revision":revision,"clip_ordinal":clip_ordinal,
                "source_document_sha256":clip["source_document_sha256"],
                "verified_original_bytes":False}
