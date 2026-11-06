"""INDEX-TIME-05: read-only, data-first editor view of imported Film Time.

This is NOT a video decoder HTTP service, a creator consent service, or a
media/FilmIndex writer. Edits and clip pages use only SQLite and immutable
manifest records; an explicit seek routes through the existing indexed
native PTS resolver. Source paths, OS inode stamps and original bytes never
cross the browser boundary. 64-bit time/PTS/ordinal values travel as strings.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_film_time_editorial import (
    FORMAT as EDIT_FORMAT, _check_row, _encode, _fields,
    FilmTimeEditorialPublisher)
from backend.nvp_temporal_ledger import MAX_TICK
from backend.nvp_studio import Studio

FORMAT = "nvp.index_time05.editor_source_read.v1"
MAX_SCANNED_EDITS = 256
MAX_EDIT_CHOICES = 64
MAX_PAGE = 100
INT_FIELDS = frozenset({
    "source_in_frame_zero","source_out_frame_zero",
    "source_in_pts","source_out_pts",
    "film_start_tick","film_end_tick",
    "requested_film_tick","source_frame_zero","source_pts",
    "next_source_frame_zero","next_source_pts",
    "frame_film_start_tick","frame_film_end_tick",
    "clip_film_start_tick","clip_film_end_tick",
    "quantization_error_ticks",
})


def _ticks(row):
    """Make every 64-bit source coordinate exact in WebView2 JavaScript."""
    return {
        key:str(value) if key in INT_FIELDS and type(value) is int else value
        for key,value in row.items()
    }


class FilmTimeDesktopRead:
    def __init__(self, studio: Studio, *, ffprobe_path=None, index_root=None):
        if not isinstance(studio,Studio):
            raise TypeError("An actual project Studio is required")
        self.studio=studio
        self.index=FilmIndex(studio)
        self._ffprobe=ffprobe_path
        self._index_root=Path(index_root) if index_root else (
            studio.db_path.resolve().parent/"nvp_source_frame_indexes")
        if not self._index_root.is_absolute() or self._index_root.is_symlink():
            raise RuntimeError("Index cache root must be an approved absolute directory")
        self._publisher=None

    def _revision(self, project_id, edit_id, revision):
        _require_pid(project_id)
        _id(edit_id,"Film Time edit")
        if type(revision) is not int or not 1<=revision<=1_000_000:
            raise ValueError("Exact positive edit revision required")
        row=self.index.read_revision(project_id,edit_id,revision)
        if row["kind"]!="edit" or row["data"].get("format")!=EDIT_FORMAT:
            raise RuntimeError("Selected edit is not indexed imported video")
        return row

    def _audit(self, record, *, after_ordinal=None, limit=None):
        """Full bounded manifest audit and optional page in ONE read snapshot.

        An attacker or concurrent process cannot mutate a row between
        accepting the manifest and reading the page shown to the creator.
        """
        pid=record["project_id"]
        ident=record["object_id"]
        revision=record["revision"]
        expected=record["data"]
        digest=sha256()
        count=0
        end=0
        source_refs={}
        page=None
        with self.studio._connection() as db:
            db.execute("BEGIN")  # Stable SQLite snapshot for audit + page.
            rows=db.execute("""SELECT * FROM nvp_time_editorial_clips
                WHERE project_id=? AND edit_id=? AND revision=?
                ORDER BY ordinal""",(pid,ident,revision))
            for row in rows:
                if count>=10000:
                    raise RuntimeError("Indexed clip count exceeded published format")
                clip=_check_row(dict(row),ordinal=count,minimum_start=end)
                key=(clip["source_id"],clip["source_revision"])
                if key not in source_refs:
                    source_refs[key]=self.index.read_revision(pid,*key)
                source=source_refs[key]
                if (source["kind"]!="asset" or
                    source["document_sha256"]!=clip["source_document_sha256"]):
                    raise RuntimeError("Imported clip source revision changed")
                digest.update(_encode(_fields(clip)))
                end=clip["film_end_tick"]
                count+=1
            if after_ordinal is not None:
                page=db.execute("""SELECT * FROM nvp_time_editorial_clips
                    WHERE project_id=? AND edit_id=? AND revision=?
                      AND ordinal>? ORDER BY ordinal LIMIT ?""",
                    (pid,ident,revision,after_ordinal,limit+1)).fetchall()
        if (count!=expected["clip_count"] or
            end!=expected["duration_tick"] or
            digest.hexdigest()!=expected["clip_manifest_sha256"]):
            raise RuntimeError("Saved Film Time clip manifest changed")
        return count,page

    def edits(self, project_id):
        """Discover real indexed edits, not screenplay/planning impostors."""
        _require_pid(project_id)
        rows=self.index.list_objects(project_id,kind="edit")
        entries=[]
        for row in rows[:MAX_SCANNED_EDITS]:
            rec=self.index.read_revision(
                project_id,row["object_id"],row["head_revision"])
            if rec["data"].get("format")!=EDIT_FORMAT:
                continue
            entries.append({
                "edit_id":rec["object_id"],
                "revision":rec["revision"],
                "edit_document_sha256":rec["document_sha256"],
                "clip_count":rec["data"]["clip_count"],
                "duration_tick":str(rec["data"]["duration_tick"]),
            })
            if len(entries)>=MAX_EDIT_CHOICES:break
        return {
            "format":FORMAT,"project_id":project_id,"edits":entries,
            "truncated":len(rows)>MAX_SCANNED_EDITS or
                        len(entries)==MAX_EDIT_CHOICES,
            "original_media_read":False,"worker_started":False,
            "film_master_approved":False,
        }

    def clips(self, project_id, edit_id, revision, *,
              expected_edit_sha256, after_ordinal=-1, limit=40):
        record=self._revision(project_id,edit_id,revision)
        _sha(expected_edit_sha256)
        if record["document_sha256"]!=expected_edit_sha256:
            raise RuntimeError("Changed edit source: refresh before browsing")
        if (type(after_ordinal) is not int or
            not -1<=after_ordinal<10000 or
            type(limit) is not int or not 1<=limit<=MAX_PAGE):
            raise ValueError("Bounded clip pagination required")
        _,rows=self._audit(
            record,after_ordinal=after_ordinal,limit=limit)
        clips=[_ticks({k:r[k] for k in (
            "ordinal","source_id","source_revision",
            "source_document_sha256","source_in_frame_zero",
            "source_out_frame_zero","source_in_pts","source_out_pts",
            "film_start_tick","film_end_tick","rounding_policy"
        )}) for r in rows[:limit]]
        return {
            "format":FORMAT,"status":"INDEXED_EDIT_CLIPS",
            "project_id":project_id,"edit_id":edit_id,
            "edit_revision":revision,"edit_document_sha256":expected_edit_sha256,
            "clip_count":record["data"]["clip_count"],
            "duration_tick":str(record["data"]["duration_tick"]),
            "clips":clips,
            "next_after_ordinal":clips[-1]["ordinal"] if len(rows)>limit else None,
            "original_media_read":False,"worker_started":False,
            "film_master_approved":False,
        }

    def _seek_resolver(self):
        if self._publisher is None:
            from backend.nvp_external_media_catalog import ExternalMediaCatalog
            from backend.nvp_source_media_inventory import SourceMediaInventory
            from backend.nvp_source_film_bridge import SourceFilmBridge
            from backend.nvp_native_frame_index import NVPFrameIndex
            from backend.nvp_film_time_playback import FilmTimePlaybackResolver
            probe=Path(self._ffprobe or shutil.which("ffprobe") or "")
            if not probe.is_absolute() or probe.is_symlink() or not probe.is_file():
                raise RuntimeError("Trusted native FFprobe unavailable for indexed seek")
            catalog=ExternalMediaCatalog(self.studio)
            inventory=SourceMediaInventory(catalog)
            film_bridge=SourceFilmBridge(self.index,inventory)
            native=NVPFrameIndex(self._index_root,ffprobe=probe)
            self._publisher=FilmTimeEditorialPublisher(
                self.index,film_bridge,native)
            self._resolver=FilmTimePlaybackResolver(self._publisher)
        return self._resolver

    def seek(self, project_id, edit_id, revision, *,
             expected_edit_sha256, tick):
        record=self._revision(project_id,edit_id,revision)
        _sha(expected_edit_sha256)
        if record["document_sha256"]!=expected_edit_sha256:
            raise RuntimeError("Changed edit source: refresh before seeking")
        if type(tick) is not int or not 0<=tick<=MAX_TICK:
            raise ValueError("Film Time tick must be a bounded exact 64-bit integer")
        self._audit(record)
        original=self._seek_resolver().resolve(
            project_id,edit_id,revision,tick=tick)
        if (original["edit_document_sha256"]!=record["document_sha256"] or
            original["requested_film_tick"]!=tick or
            original["status"] not in (
                "INDEXED_SOURCE_FRAME_SELECTED","EMPTY_IMPORTED_VIDEO_GAP")):
            raise RuntimeError("Native source lookup changed during seek")
        # The native resolver returns device/inode/mtime stamps used to
        # reject changed files. Such internal host evidence stays private.
        fields={
            "status","edit_id","edit_revision","edit_document_sha256",
            "requested_film_tick","clip_ordinal","source_id",
            "source_revision","source_document_sha256",
            "source_frame_zero","source_pts",
            "next_source_frame_zero","next_source_pts",
            "frame_film_start_tick","frame_film_end_tick",
            "clip_film_start_tick","clip_film_end_tick",
            "source_integrity","source_sha_verified_this_operation",
            "review_task_started","picture_rendered",
            "frame_index_pts_reads","seek_kind","rounding_policy",
            "exact_time","quantization_error_ticks"
        }
        return {
            "format":FORMAT,"project_id":project_id,
            **_ticks({k:v for k,v in original.items() if k in fields}),
            "original_source_path_disclosed":False,
            "native_worker_started":False,"film_master_approved":False,
        }
