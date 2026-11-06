"""INDEX-TIME-07 — edit the assembly, never the footage.

A trusted native desktop controller provides typed non-destructive cut/copy/
move/trim/remove/insert/gap/restore operations over exact original PTS
placements. Preview is metadata-only; commit requires native OS confirmation
and a compare-and-swap immutable FilmIndex revision. This reuses the existing
FilmTimeEditorialPublisher; no render, arbitrary file write or HTTP mutation.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_film_time_editorial import (
    FilmTimeEditorialPublisher, MAX_CLIPS)
from backend.nvp_film_index import _id,_require_pid,_sha
from backend.nvp_temporal_ledger import _int, MAX_TICK

FORMAT = "nvp.index_time07.assembly_plan.v1"
MAX_ASSEMBLY_CLIPS = 256
MAX_BROWSE = 100
DECIMAL_FIELDS = (
    "source_in_frame_zero","source_out_frame_zero","film_start_tick",
    "film_end_tick","gap_before_tick",
)


def _int_decimal(value, label, *, minimum=0, maximum=MAX_TICK):
    """JavaScript >2^53 integer values MUST come as decimal strings."""
    if (type(value) is not str or not value.isascii() or
        not value.isdecimal() or len(value)>19):
        raise ValueError(label+" requires a nonnegative exact decimal string")
    numeric=int(value)
    _int(numeric,label,minimum=minimum,maximum=maximum)
    return numeric


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


class IndexedFootageAssembler:
    def __init__(self,publisher:FilmTimeEditorialPublisher):
        if not isinstance(publisher,FilmTimeEditorialPublisher):
            raise TypeError("Actual indexed Film Time publisher required")
        self.publisher=publisher

    def _head(self,pid,edit_id,revision,sha):
        _require_pid(pid)
        _id(edit_id,"indexed edit ID")
        _int(revision,"indexed edit revision",minimum=1,maximum=1000000)
        _sha(sha)
        record=self.publisher._revision(pid,edit_id,revision)
        head=self.publisher.index.read_revision(pid,edit_id)
        if (record["document_sha256"]!=sha or
            head["revision"]!=revision or
            head["document_sha256"]!=sha):
            raise RuntimeError("Indexed edit head changed; reload before committing")
        self.publisher.verify_revision(pid,edit_id,revision)
        return record

    def _rows(self,pid,edit_id,revision,*,sha=None):
        doc=self.publisher._revision(pid,edit_id,revision)
        if sha is not None and doc["document_sha256"]!=sha:
            raise RuntimeError("Selected source edit SHA was changed")
        proof=self.publisher.verify_revision(pid,edit_id,revision)
        if proof["clips"]>MAX_ASSEMBLY_CLIPS:
            raise ValueError("This bounded desktop assembly supports at most 256 source clips")
        rows=[]
        after=-1
        while len(rows)<proof["clips"]:
            page=self.publisher.clips(pid,edit_id,revision,
                                      after_ordinal=after,limit=MAX_BROWSE)
            if (page["edit_document_sha256"]!=doc["document_sha256"] or
                not page["clips"]):
                raise RuntimeError("Source edit changed during bounded browse")
            rows.extend(page["clips"])
            after=rows[-1]["ordinal"]
        if len(rows)!=proof["clips"]:
            raise RuntimeError("Source edit clip count changed")
        previous=0
        strips=[]
        for row in rows:
            gap=row["film_start_tick"]-previous
            if gap<0:
                raise RuntimeError("Overlapping imported source strips")
            strips.append({
                "source_id":row["source_id"],
                "source_revision":row["source_revision"],
                "source_in_frame_zero":row["source_in_frame_zero"],
                "source_out_frame_zero":row["source_out_frame_zero"],
                "rounding":row["rounding_policy"],
                "gap_before_tick":gap,
            })
            previous=row["film_end_tick"]
        return strips

    def _apply(self,pid,edit_id,revision,sha,change):
        if type(change) is not dict or "operation" not in change:
            raise ValueError("Typed editor operation required")
        op=change["operation"]
        accepted={
            "move":{"operation","index","target"},
            "copy":{"operation","index","target"},
            "remove":{"operation","index"},
            "trim":{"operation","index","source_in_frame_zero","source_out_frame_zero"},
            "split":{"operation","index","source_frame_zero"},
            "set_gap":{"operation","index","gap_before_tick"},
            "insert":{"operation","target","source_edit_id","source_edit_revision",
                      "source_edit_sha256","source_ordinal"},
            "restore":{"operation","from_revision"},
        }
        if op not in accepted or set(change)!=accepted[op]:
            raise ValueError("Unknown or extra editable source fields")
        rows=self._rows(pid,edit_id,revision,sha=sha)
        original=_canonical(rows)
        def existing(value):
            _int(value,"source clip ordinal",minimum=0,maximum=len(rows)-1)
            return value
        def target(value):
            _int(value,"source insertion slot",minimum=0,maximum=len(rows))
            return value

        if op in ("move","copy"):
            at=existing(change["index"])
            dest=target(change["target"])
            if op=="move":
                row=rows.pop(at)
                # target is an insertion boundary in the original list.
                if dest>at:dest-=1
                rows.insert(dest,row)
            else:
                if len(rows)>=MAX_ASSEMBLY_CLIPS:
                    raise ValueError("Source assembly clip limit exceeded")
                rows.insert(dest,dict(rows[at]))
        elif op=="remove":
            existing(change["index"])
            if len(rows)<=1:
                raise ValueError("An imported edit cannot lose its final source clip")
            rows.pop(change["index"])
        elif op=="trim":
            at=existing(change["index"])
            row=rows[at]
            lower=_int_decimal(change["source_in_frame_zero"],
                               "source trim in frame")
            upper=_int_decimal(change["source_out_frame_zero"],
                               "source trim out frame")
            if (not row["source_in_frame_zero"]<=lower<upper<=
                row["source_out_frame_zero"]):
                raise ValueError("Trim must be within the existing original source range")
            row["source_in_frame_zero"]=lower
            row["source_out_frame_zero"]=upper
        elif op=="split":
            at=existing(change["index"])
            if len(rows)>=MAX_ASSEMBLY_CLIPS:
                raise ValueError("Source assembly clip limit exceeded")
            cut=_int_decimal(change["source_frame_zero"],"original cut frame")
            left=rows[at]
            if not left["source_in_frame_zero"]<cut<left["source_out_frame_zero"]:
                raise ValueError("Split must lie strictly within original frame bounds")
            # A split creates two adjacent references to the SAME immutable
            # original. Their in/out and PTS are recalculated by _source_bound,
            # never by assuming frames per second. The second placement has
            # no artificial film gap between the new cuts.
            right=dict(left)
            right["source_in_frame_zero"]=cut
            right["gap_before_tick"]=0
            left["source_out_frame_zero"]=cut
            rows.insert(at+1,right)
        elif op=="set_gap":
            at=existing(change["index"])
            rows[at]["gap_before_tick"]=_int_decimal(
                change["gap_before_tick"],"film gap duration")
        elif op=="insert":
            dest=target(change["target"])
            _id(change["source_edit_id"],"imported source edit")
            _int(change["source_edit_revision"],"source edit revision",
                 minimum=1,maximum=1000000)
            _sha(change["source_edit_sha256"])
            original_rows=self._rows(
                pid,change["source_edit_id"],change["source_edit_revision"],
                sha=change["source_edit_sha256"])
            _int(change["source_ordinal"],"source insert ordinal",
                 minimum=0,maximum=len(original_rows)-1)
            if len(rows)>=MAX_ASSEMBLY_CLIPS:
                raise ValueError("Source assembly clip limit exceeded")
            row=dict(original_rows[change["source_ordinal"]])
            row["gap_before_tick"]=0
            rows.insert(dest,row)
        elif op=="restore":
            prior=change["from_revision"]
            _int(prior,"prior imported edit revision",minimum=1,
                 maximum=revision-1)
            rows=self._rows(pid,edit_id,prior)
        if not rows or len(rows)>MAX_ASSEMBLY_CLIPS:
            raise ValueError("Source assembly must keep 1..256 referenced clips")
        if _canonical(rows)==original:
            raise ValueError("Editorial operation did not change the source assembly")
        return rows

    def prepare(self,pid,edit_id,revision,expected_edit_sha256,change):
        """Read-only sealed before/after plan, with exact PTS-derived duration.

        The expensive per-clip indexed PTS source validation is intentional:
        a preview is never authorized from guessed clip durations or FPS.
        """
        old=self._head(pid,edit_id,revision,expected_edit_sha256)
        rows=self._apply(pid,edit_id,revision,expected_edit_sha256,change)
        position=0
        clips=[]
        for ordinal,row in enumerate(rows):
            position+=row["gap_before_tick"]
            if position>MAX_TICK:
                raise ValueError("Film Time exceeds bounded 64-bit range")
            spec={
                "source_id":row["source_id"],
                "source_revision":row["source_revision"],
                "source_in_frame_zero":row["source_in_frame_zero"],
                "source_out_frame_zero":row["source_out_frame_zero"],
                "film_in_tick":position,
                "rounding":row["rounding"],
            }
            bound=self.publisher._source_bound(pid,spec)
            if (bound["film_start_tick"]!=position or
                bound["film_end_tick"]<=position):
                raise RuntimeError("Source PTS yielded invalid Film Time clip")
            clips.append(spec)
            position=bound["film_end_tick"]
        plan={
            "format":FORMAT,"project_id":pid,"edit_id":edit_id,
            "source_revision":revision,
            "source_document_sha256":old["document_sha256"],
            "next_revision":revision+1,
            "operation":change["operation"],
            "clip_count":len(clips),
            "duration_tick":str(position),
            "placements":clips,
            "original_sources_modified":False,
            "native_events_modified":False,
            "picture_rendered":False,
            "approved_final_master":False,
        }
        digest=hashlib.sha256(_canonical(plan)).hexdigest()
        # Do not expose 64-bit integers as JS Numbers.
        return {
            **{k:v for k,v in plan.items() if k!="placements"},
            "placements":[{
                "ordinal":i,"source_id":c["source_id"],
                "source_revision":c["source_revision"],
                "source_in_frame_zero":str(c["source_in_frame_zero"]),
                "source_out_frame_zero":str(c["source_out_frame_zero"]),
                "film_start_tick":str(c["film_in_tick"]),
                "rounding_policy":c["rounding"],
            } for i,c in enumerate(clips)],
            "plan_sha256":digest,
            "_commit_placements":clips,
        }

    def commit(self,pid,edit_id,revision,expected_edit_sha256,
               change,expected_plan_sha256,*,confirm):
        """Native OS physical confirmation, exact plan check, CAS FilmIndex."""
        _sha(expected_plan_sha256)
        if not callable(confirm):
            raise TypeError("Trusted native approval callback required")
        draft=self.prepare(pid,edit_id,revision,expected_edit_sha256,change)
        if draft["plan_sha256"]!=expected_plan_sha256:
            raise RuntimeError("Proposed assembly changed after director preview")
        prompt=(
            "Save ONE NEW, non-destructive imported-video edit revision?\n"+
            "Film edit: "+edit_id+" revision "+str(revision)+
            " -> "+str(revision+1)+"\n"+
            "Operation: "+change["operation"]+"\n"+
            "Clips: "+str(draft["clip_count"])+
            "  Film duration: "+draft["duration_tick"]+" exact ticks\n"+
            "Plan SHA256: "+expected_plan_sha256+"\n"+
            "Original footage and all older revisions remain untouched.\n"+
            "This is editorial metadata, NOT an approved movie.")
        if confirm(prompt) is not True:
            return {
                "format":FORMAT,"status":"DENIED",
                "source_revision":revision,
                "original_sources_modified":False,
                "approved_final_master":False,
            }
        checked=self.prepare(pid,edit_id,revision,expected_edit_sha256,change)
        if checked["plan_sha256"]!=expected_plan_sha256:
            raise RuntimeError("Film Time assembly changed during native consent")
        published=self.publisher.publish(
            pid,edit_id,checked["_commit_placements"],
            expected_revision=revision)
        return {
            "format":FORMAT,"status":"SAVED_NEW_EDIT_REVISION",
            "project_id":pid,"edit_id":edit_id,
            "revision":published["revision"],
            "edit_document_sha256":published["document_sha256"],
            "clip_count":checked["clip_count"],
            "duration_tick":checked["duration_tick"],
            "original_sources_modified":False,
            "previous_revision_preserved":True,
            "approved_final_master":False,
        }
