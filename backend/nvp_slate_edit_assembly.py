"""SLATE-02 — non-destructive source segment assembly and explicit edit commit.

Merely browsing/focusing a parallel Take does not change the active cut.
A draft sequence can splice exact time intervals from different frozen
Take/shot branches in any order. Only a trusted host's explicit editor
action commits a new immutable FilmIndex edit revision.

No performance data, original USD, source Takes, or shot opinion is copied,
modified, silently retimed, or turned into final render authorization.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_temporal_ledger import _int, MAX_TICK

FORMAT="nvp.slate.sequence_assembly.v1"
DRAFT_FORMAT="nvp.slate.sequence_draft.v1"
MAX_SEGMENTS=500
SEGMENT_KEYS=frozenset(("segment_id","branch_id","source_in_tick",
                        "source_out_tick"))
EDIT_COMMANDS=frozenset(("insert_before","insert_after","replace","remove",
                         "trim","move_before","move_after","split",
                         "paste_before","paste_after"))


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


class SlateSequenceAssembly:
    def __init__(self, slate:DigitalSlateBranches, *, verify_editor_action):
        if (not isinstance(slate,DigitalSlateBranches) or
            not callable(verify_editor_action)):
            raise TypeError("Trusted source slate and explicit editor policy required")
        self.slate=slate
        self.index=slate.index
        self.approve=verify_editor_action

    def _validate(self,project_id,graph_id,graph_revision,segments):
        graph=self.slate.open_graph(project_id,graph_id,graph_revision)
        if type(segments) is not list or not 1<=len(segments)<=MAX_SEGMENTS:
            raise ValueError("Sequence must have 1..500 bounded segments")
        nodes={node["branch_id"]:node for node in graph["data"]["nodes"]}
        used=set()
        ordered=[]
        position=0
        prev=None
        for raw in segments:
            if type(raw) is not dict or set(raw)!=SEGMENT_KEYS:
                raise ValueError("Assembly segment requires exact source reference fields")
            seg_id=_id(raw["segment_id"],"edit segment ID")
            branch_id=_id(raw["branch_id"],"source branch")
            if seg_id in used or branch_id not in nodes:
                raise ValueError("Duplicate segment or unknown source branch")
            used.add(seg_id)
            node=nodes[branch_id]
            start=_int(raw["source_in_tick"],"source segment inpoint")
            end=_int(raw["source_out_tick"],"source segment outpoint")
            if not node["source_start_tick"]<=start<end<=node["source_end_tick"]:
                raise ValueError("Source trim escapes original branch interval")
            duration=end-start
            if position+duration>MAX_TICK:
                raise ValueError("Assembled editorial duration exceeds film tick range")
            take=self.index.read_revision(project_id,node["take_id"],1)
            if take["document_sha256"]!=node["take_document_sha256"]:
                raise RuntimeError("Frozen performance changed after slate capture")
            if node["shot_id"] is not None:
                shot=self.index.read_revision(
                    project_id,node["shot_id"],node["shot_revision"])
                if shot["document_sha256"]!=node["shot_document_sha256"]:
                    raise RuntimeError("Shot presentation changed after slate capture")
            transition={
                "type":"hard_cut" if prev is not None else "start",
                "requires_continuity_review":bool(
                    prev is not None and (
                        prev["source_take_id"]!=node["take_id"] or
                        prev["source_shot_id"]!=node["shot_id"])),
                "automatic_morph_or_retime":False,
                "audio_sync_verified":False,
            }
            ordered.append({
                "segment_id":seg_id,
                "branch_id":branch_id,
                "parallel_group_id":node["group_id"],
                "source_take_id":node["take_id"],
                "source_take_revision":1,
                "source_take_document_sha256":node["take_document_sha256"],
                "source_shot_id":node["shot_id"],
                "source_shot_revision":node["shot_revision"],
                "source_shot_document_sha256":node["shot_document_sha256"],
                "source_in_tick":start,
                "source_out_tick":end,
                "timeline_start_tick":position,
                "timeline_end_tick":position+duration,
                "incoming_transition":transition,
                "source_data_copied":False,
            })
            position+=duration
            prev=ordered[-1]
        return graph,ordered,position

    def preview(self,project_id,graph_id,graph_revision,segments,*,
                inspect_branch_id=None,active_edit_id=None,
                active_edit_revision=None):
        """Validate local draft and report original committed cut separately.

        Choosing an inspect branch does not publish and does not recolor
        committed active paths. The UI may outline it in yellow/blue.
        """
        graph,ordered,duration=self._validate(
            project_id,graph_id,graph_revision,segments)
        if inspect_branch_id is not None:
            _id(inspect_branch_id,"inspected branch")
            if inspect_branch_id not in {
                    n["branch_id"] for n in graph["data"]["nodes"]}:
                raise ValueError("Cannot inspect an unknown source branch")
        active=None
        if (active_edit_id is None)!=(active_edit_revision is None):
            raise ValueError("Active edit needs exact ID and version")
        if active_edit_id is not None:
            active=self.open_edit(
                project_id,active_edit_id,active_edit_revision)
            if active["data"]["graph_document_sha256"]!=graph["document_sha256"]:
                raise RuntimeError("Draft is based on a different source slate graph")
        active_segments=active["data"]["segments"] if active else []
        active_by_branch={}
        for segment in active_segments:
            active_by_branch.setdefault(segment["branch_id"],[]).append({
                "timeline_start_tick":segment["timeline_start_tick"],
                "timeline_end_tick":segment["timeline_end_tick"],
                "source_in_tick":segment["source_in_tick"],
                "source_out_tick":segment["source_out_tick"],
            })
        return {
            "format":DRAFT_FORMAT,
            "project_id":project_id,"graph_id":graph_id,
            "graph_revision":graph_revision,
            "graph_document_sha256":graph["document_sha256"],
            "draft_sha256":_digest(segments),
            "segments":ordered,"duration_tick":duration,
            "inspection_only_branch_id":inspect_branch_id,
            "active_edit_id":active_edit_id,
            "active_edit_revision":active_edit_revision,
            "active_edit_document_sha256":(
                active["document_sha256"] if active else None),
            "active_segments_by_branch":active_by_branch,
            "draft_uncommitted":True,
            "selection_changes_active_cut":False,
            "source_performance_modified":False,
            "render_approved":False,
        }

    def edit_draft(self,segments,*,operation,segment=None,
                   target_segment_id=None,new_segment_id=None,
                   trim_in_tick=None,trim_out_tick=None,split_tick=None,
                   second_segment_id=None):
        """Pure local copy/insert/trim/move operations; NEVER commits the cut."""
        if type(segments) is not list or operation not in EDIT_COMMANDS:
            raise ValueError("Unknown draft assembly edit operation")
        items=[dict(entry) for entry in segments]
        for raw in items:
            if type(raw) is not dict or set(raw)!=SEGMENT_KEYS:
                raise ValueError("Invalid draft source segment")
        targets=[i for i,x in enumerate(items)
                 if x["segment_id"]==target_segment_id]
        if operation in ("insert_before","insert_after","replace","remove",
                         "trim","move_before","move_after","split",
                         "paste_before","paste_after") and (
                         len(targets)!=1):
            raise ValueError("Target segment not found exactly once")
        index=targets[0]
        if operation in ("insert_before","insert_after","replace",
                         "paste_before","paste_after"):
            # Paste copies ONLY a source-data reference. Its segment ID
            # must be distinct, even when Take/shot/time are identical.
            if operation.startswith("paste_") and segment is not None:
                segment=dict(segment)
            if type(segment) is not dict or set(segment)!=SEGMENT_KEYS:
                raise ValueError("Insert/paste requires exact source branch reference")
            if segment["segment_id"] in {x["segment_id"] for x in items}:
                raise ValueError("A pasted clip requires a new segment ID")
            pos=index+(1 if operation in ("insert_after","paste_after") else 0)
            if operation=="replace":
                items[index]=dict(segment)
            else:
                items.insert(pos,dict(segment))
        elif operation=="split":
            original=dict(items[index])
            point=_int(split_tick,"split point in original source Film Time")
            if not original["source_in_tick"]<point<original["source_out_tick"]:
                raise ValueError("Split must occur inside original source data interval")
            _id(second_segment_id,"new right-half segment ID")
            if second_segment_id in {x["segment_id"] for x in items}:
                raise ValueError("Split needs a new unique right-half ID")
            left={**original,"source_out_tick":point}
            right={**original,"segment_id":second_segment_id,"source_in_tick":point}
            items[index:index+1]=[left,right]
        elif operation=="remove":
            items.pop(index)
        elif operation=="trim":
            edited=dict(items[index])
            if trim_in_tick is not None:
                edited["source_in_tick"]=_int(trim_in_tick,"new source inpoint")
            if trim_out_tick is not None:
                edited["source_out_tick"]=_int(trim_out_tick,"new source outpoint")
            items[index]=edited
        else:
            if type(new_segment_id) is not str:
                raise ValueError("Move requires existing segment identity")
            moving=[i for i,x in enumerate(items)
                    if x["segment_id"]==new_segment_id]
            if len(moving)!=1 or new_segment_id==target_segment_id:
                raise ValueError("Move source missing or self-targeted")
            obj=items.pop(moving[0])
            target=next(i for i,x in enumerate(items)
                        if x["segment_id"]==target_segment_id)
            items.insert(target+(operation=="move_after"),obj)
        if not 1<=len(items)<=MAX_SEGMENTS:
            raise ValueError("Draft sequence must retain at least one clip")
        return items

    def commit(self,project_id,edit_id,*,graph_id,graph_revision,
               segments,editor_event,expected_revision=0):
        """Explicit Make Active/Commit Edit — immutable revision and approval."""
        _require_pid(project_id)
        _id(edit_id,"assembled edit")
        _int(expected_revision,"expected assembly revision")
        graph,ordered,duration=self._validate(
            project_id,graph_id,graph_revision,segments)
        if expected_revision:
            previous=self.open_edit(project_id,edit_id,expected_revision)
            if (previous["data"]["graph_document_sha256"]!=
                graph["document_sha256"]):
                raise RuntimeError("Cannot silently change source slate graph")
        dependencies=[{"object_id":graph_id,"revision":graph_revision,
                       "role":"presentation"}]
        scope={
            "operation":"nvp.slate.commit_assembled_edit.v1",
            "project_id":project_id,"edit_id":edit_id,
            "expected_revision":expected_revision,
            "graph_id":graph_id,"graph_revision":graph_revision,
            "graph_document_sha256":graph["document_sha256"],
            "ordered_segment_sha256":_digest(ordered),
            "duration_tick":duration,
            "segment_count":len(ordered),
            "final_render_approval":False,
        }
        if self.approve(editor_event,dict(scope)) is not True:
            raise PermissionError("Editor has not activated the exact draft sequence")
        document={
            "format":FORMAT,
            "graph_id":graph_id,"graph_revision":graph_revision,
            "graph_document_sha256":graph["document_sha256"],
            "segments":ordered,"ordered_segment_sha256":scope["ordered_segment_sha256"],
            "duration_tick":duration,
            "explicit_editor_commit":True,
            "source_performance_modified":False,
            "render_approved":False,
            "retimed":False,
        }
        # Source retirement cannot silently break an older cut or be bypassed
        # by referring to a previously published catalog root. Check every
        # actual selected Take/shot under FilmIndex's SAME writer transaction.
        def guard(db):
            table=db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='nvp_film_source_retirements'""").fetchone()
            if table is None:
                return
            referenced={(segment["source_take_id"]) for segment in ordered}
            referenced.update(segment["source_shot_id"] for segment in ordered
                              if segment["source_shot_id"] is not None)
            for source_id in referenced:
                if db.execute("""SELECT 1 FROM nvp_film_source_retirements
                    WHERE project_id=? AND object_id=?
                    AND state!='RESTORED'""",
                    (project_id,source_id)).fetchone():
                    raise RuntimeError(
                        "Cannot activate a new cut using a retired source Take/shot")
        # FilmIndex expected_revision enforces optimistic concurrency and
        # prevents a stale editor window from silently replacing an active cut.
        return self.index.register_revision(
            project_id,edit_id,"edit",document,
            expected_revision=expected_revision,dependencies=dependencies,
            precommit_guard=guard)

    def open_edit(self,project_id,edit_id,revision):
        result=self.index.read_revision(project_id,edit_id,revision)
        d=result["data"]
        if result["kind"]!="edit" or d.get("format")!=FORMAT or (
                d.get("explicit_editor_commit") is not True):
            raise RuntimeError("Not an approved assembled editorial revision")
        graph,segments,duration=self._validate(
            project_id,d["graph_id"],d["graph_revision"],
            [{k:s[k] for k in SEGMENT_KEYS} for s in d["segments"]])
        if (graph["document_sha256"]!=d["graph_document_sha256"] or
            segments!=d["segments"] or
            duration!=d["duration_tick"] or
            _digest(segments)!=d["ordered_segment_sha256"]):
            raise RuntimeError("Committed edit changed relative to frozen source slate")
        return result

    def active_view(self,project_id,graph_id,graph_revision,*,edit_id,
                    edit_revision,inspection_branch_id=None):
        active=self.open_edit(project_id,edit_id,edit_revision)
        if (active["data"]["graph_id"]!=graph_id or
            active["data"]["graph_revision"]!=graph_revision):
            raise RuntimeError("An edit cannot apply to a different slate graph")
        graph=self.slate.view(project_id,graph_id,graph_revision)
        if inspection_branch_id is not None and inspection_branch_id not in {
                n["branch_id"] for group in graph["parallel_groups"].values()
                for n in group}:
            raise ValueError("Unknown inspected slate take")
        by_branch={}
        for seg in active["data"]["segments"]:
            by_branch.setdefault(seg["branch_id"],[]).append({
                "segment_id":seg["segment_id"],
                "source_in_tick":seg["source_in_tick"],
                "source_out_tick":seg["source_out_tick"],
                "timeline_start_tick":seg["timeline_start_tick"],
                "timeline_end_tick":seg["timeline_end_tick"],
            })
        active_by_group={}
        for group_id,group in graph["parallel_groups"].items():
            active_by_group[group_id]=[]
            for node in group:
                node["selected"]=node["branch_id"] in by_branch
                node["display_color"]="green" if node["selected"] else "gray"
                node["active_source_ranges"]=by_branch.get(node["branch_id"],[])
                node["inspection_focus"]=node["branch_id"]==inspection_branch_id
                if node["selected"]:
                    active_by_group[group_id].append(node["branch_id"])
        # A mixed cut can legitimately use two (or more) alternatives
        # in the SAME group; SLATE-01's singular default-selection model
        # is replaced by segment-level green selections for this view.
        graph.pop("selected_by_group",None)
        return {
            **graph,"format":"nvp.slate.assembled_edit_view.v1",
            "active_branches_by_group":active_by_group,
            "edit_id":edit_id,"edit_revision":edit_revision,
            "edit_document_sha256":active["document_sha256"],
            "duration_tick":active["data"]["duration_tick"],
            "sequence":active["data"]["segments"],
            "inspection_only_branch_id":inspection_branch_id,
            "active_selection_changes_on_inspect":False,
            "source_performance_modified":False,
            "render_approved":False,
        }
