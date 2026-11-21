"""SLATE-01: versioned digital slate, parallel-take DAG and editor selections.

Structured data only: one scene with different camera presentations of the
SAME performance and alternative/wild performances with different Take SHAs.
The branch graph records relationships; an independent FilmIndex edit
revision records the green (chosen) path. No Take/scene/shot is modified.
"""
from __future__ import annotations

import re

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_temporal_ledger import _int
from backend.nvp_openusd_take import FORMAT as TAKE_FORMAT
from backend.nvp_openusd_shot_overrides import FORMAT as SHOT_FORMAT

GRAPH_FORMAT="nvp.slate.branch_graph.v1"
SELECTION_FORMAT="nvp.slate.branch_selection.v1"
MAX_BRANCHES=256
MAX_GROUPS=64
MAX_NOTE=512
KINDS=frozenset(("performance","coverage"))
SLATE_KEYS=frozenset(("scene","setup","shot","camera","take_number",
                      "wild","script_revision","notes"))
NODE_KEYS=frozenset(("branch_id","kind","parent_id","fork_tick",
                     "group_id","primary","take_id","source_start_tick",
                     "source_end_tick","shot_id","shot_revision","slate"))
SLATE_VALUE=re.compile(r"[a-zA-Z0-9][a-zA-Z0-9 ._:/-]{0,47}\Z")


def _label(value,description):
    if type(value) is not str or not SLATE_VALUE.fullmatch(value):
        raise ValueError("Invalid digital slate "+description)
    return value


def _note(value):
    if type(value) is not str or len(value)>MAX_NOTE:
        raise ValueError("Invalid digital slate notes")
    return value


class DigitalSlateBranches:
    def __init__(self,index:FilmIndex,*,verify_editor_action):
        if not isinstance(index,FilmIndex) or not callable(verify_editor_action):
            raise TypeError("Digital slate requires FilmIndex and trusted editor policy")
        self.index=index
        self.approve=verify_editor_action

    def _take(self,project_id,identifier,scene_id):
        doc=self.index.read_revision(project_id,identifier,1)
        data=doc["data"]
        if (doc["kind"]!="take" or data.get("format")!=TAKE_FORMAT or
            data.get("frozen") is not True or data.get("scene_id")!=scene_id):
            raise RuntimeError("Branch must reference a frozen Take from this scene")
        return doc

    def _shot(self,project_id,shot_id,revision,take_id,begin,end):
        doc=self.index.read_revision(project_id,shot_id,revision)
        data=doc["data"]
        if (doc["kind"]!="presentation" or
            data.get("format")!=SHOT_FORMAT or
            data.get("take_id")!=take_id or
            data.get("start_tick")>begin or
            data.get("end_tick")<end):
            raise RuntimeError("Camera coverage must bind a compatible shot override")
        return doc

    def _validate_nodes(self,project_id,scene_id,scene_label,nodes):
        _id(scene_id,"canonical scene identity")
        _label(scene_label,"scene label")
        if type(nodes) is not list or not 1<=len(nodes)<=MAX_BRANCHES:
            raise ValueError("Digital slate requires a bounded branch DAG")
        result=[]
        lookup={}
        primaries={}
        groups={}
        sources={}
        shots={}
        for node in nodes:
            if type(node) is not dict or set(node)!=NODE_KEYS:
                raise ValueError("Digital slate branch needs exact typed fields")
            bid=_id(node["branch_id"],"parallel branch identity")
            group=_id(node["group_id"],"parallel editorial group")
            kind=node["kind"]
            if bid in lookup or kind not in KINDS:
                raise ValueError("Duplicate branch or invalid branch kind")
            primary=node["primary"]
            if type(primary) is not bool:
                raise ValueError("Explicit original/default choice required")
            parent_id=node["parent_id"]
            fork=node["fork_tick"]
            source_start=_int(node["source_start_tick"],"branch source inpoint")
            source_end=_int(node["source_end_tick"],"branch source outpoint",minimum=1)
            if source_end<=source_start:
                raise ValueError("Empty alternative performance or coverage interval")
            if not lookup:
                if kind!="performance" or parent_id is not None or fork is not None:
                    raise ValueError("First branch must be original root performance")
            else:
                if type(parent_id) is not str or parent_id not in lookup:
                    raise ValueError("Branch parent must precede its child in DAG")
                _int(fork,"fork at parent Film Time")
                parent=lookup[parent_id]
                if not parent["source_start_tick"]<=fork<parent["source_end_tick"]:
                    raise ValueError("Fork does not occur inside parent source interval")
                if kind=="coverage":
                    if parent["kind"]!="performance" or (
                            parent["take_id"]!=node["take_id"]):
                        raise ValueError("Coverage angle must observe its parent's Take")
                elif parent["kind"]!="performance":
                    raise ValueError("Alternative performance must descend from a Take")
            tid=_id(node["take_id"],"Digital Take")
            take=self._take(project_id,tid,scene_id)
            if source_end>take["data"]["duration_tick"]:
                raise ValueError("Slate interval exceeds frozen performance duration")
            if not lookup and source_start!=0:
                raise ValueError("Original root starts at source tick zero")
            sid=node["shot_id"]
            srev=node["shot_revision"]
            sha=None
            if sid is None:
                if srev is not None:
                    raise ValueError("Shot revision without shot ID")
            else:
                _id(sid,"shot-specific camera coverage")
                _int(srev,"shot revision",minimum=1)
                if kind!="coverage":
                    raise ValueError("Only coverage nodes may bind a shot override")
                sd=self._shot(project_id,sid,srev,tid,source_start,source_end)
                sha=sd["document_sha256"]
                shots[(sid,srev)]=sha
            slate=node["slate"]
            if type(slate) is not dict or set(slate)!=SLATE_KEYS:
                raise ValueError("Slate must include exact source/clapper fields")
            if slate["scene"]!=scene_label:
                raise ValueError("Slate scene and graph scene labels disagree")
            for key in ("setup","shot","camera","script_revision"):
                _label(slate[key],key)
            take_number=_int(slate["take_number"],"slate take number",minimum=1,
                             maximum=99999)
            if type(slate["wild"]) is not bool:
                raise ValueError("Explicit wild-take flag must be boolean")
            if slate["wild"] and kind!="performance":
                raise ValueError("Wild take must reference an alternative performance")
            _note(slate["notes"])
            if primary:
                if group in primaries:
                    raise ValueError("More than one original/default in parallel group")
                primaries[group]=bid
            groups.setdefault(group,[]).append(bid)
            normalized={
                **node,
                "take_document_sha256":take["document_sha256"],
                "shot_document_sha256":sha,
            }
            sources[tid]=take["document_sha256"]
            lookup[bid]=normalized
            result.append(normalized)
        if len(groups)>MAX_GROUPS or set(primaries)!=set(groups):
            raise ValueError("Each editorial group needs exactly one default branch")
        return result,primaries,sources,shots

    def publish_graph(self,project_id,graph_id,*,scene_id,scene_label,nodes,
                      expected_revision=0):
        """Trusted capture metadata, not a director render/master approval."""
        _require_pid(project_id)
        _id(graph_id,"slate branch graph")
        _int(expected_revision,"expected slate graph revision")
        normalized,primaries,takes,shots=self._validate_nodes(
            project_id,scene_id,scene_label,nodes)
        if graph_id in takes or any(graph_id==x[0] for x in shots):
            raise ValueError("Slate graph cannot reuse a captured source ID")
        document={
            "format":GRAPH_FORMAT,"scene_id":scene_id,
            "scene_label":scene_label,"nodes":normalized,
            "group_defaults":primaries,"source_take_count":len(takes),
            "source_shot_count":len(shots),
            "creator_final_render_approved":False,
            "original_performances_modified":False,
        }
        dependencies=[
            {"object_id":tid,"revision":1,"role":"source_take"}
            for tid in sorted(takes)]
        dependencies += [
            {"object_id":sid,"revision":rev,"role":"presentation"}
            for sid,rev in sorted(shots)]
        if len(dependencies)>128:
            raise ValueError("Slate exceeds FilmIndex source dependency budget")
        return self.index.register_revision(
            project_id,graph_id,"presentation",document,
            expected_revision=expected_revision,dependencies=dependencies)

    def open_graph(self,project_id,graph_id,revision):
        doc=self.index.read_revision(project_id,graph_id,revision)
        if doc["kind"]!="presentation" or doc["data"].get("format")!=GRAPH_FORMAT:
            raise RuntimeError("Not a native digital slate branch graph")
        data=doc["data"]
        # Reading back is not trusting an arbitrary stale JSON graph.
        raw=[{k:item[k] for k in NODE_KEYS} for item in data["nodes"]]
        nodes,primaries,takes,shots=self._validate_nodes(
            project_id,data["scene_id"],data["scene_label"],raw)
        if nodes!=data["nodes"] or primaries!=data["group_defaults"]:
            raise RuntimeError("Slate links no longer match immutable source SHAs")
        return doc

    def choose(self,project_id,edit_id,*,graph_id,graph_revision,
               group_id,branch_id,editor_event,expected_revision=0):
        """EXPLICIT editorial commit (never called just for UI preview).

        New mixed-take assembly code may use multiple source branches in
        one edited sequence. This legacy single-choice API is retained for
        simple single-branch parallel-group edits only.
        """
        _require_pid(project_id)
        _id(edit_id,"slate edit")
        _id(group_id,"parallel choice group")
        _id(branch_id,"chosen branch")
        _int(expected_revision,"expected slate selection revision")
        graph=self.open_graph(project_id,graph_id,graph_revision)
        data=graph["data"]
        options={item["branch_id"]:item for item in data["nodes"]
                 if item["group_id"]==group_id}
        if branch_id not in options:
            raise ValueError("Selected branch must belong to that parallel group")
        if expected_revision:
            prior=self.index.read_revision(project_id,edit_id,expected_revision)
            if (prior["kind"]!="edit" or
                prior["data"].get("format")!=SELECTION_FORMAT or
                prior["data"]["graph_document_sha256"]!=graph["document_sha256"]):
                raise RuntimeError("Existing edit belongs to a different slate graph")
            selected=dict(prior["data"]["selections"])
        else:
            selected=dict(data["group_defaults"])
        selected[group_id]=branch_id
        payload={
            "format":SELECTION_FORMAT,"graph_id":graph_id,
            "graph_revision":graph_revision,
            "graph_document_sha256":graph["document_sha256"],
            "selections":selected,"chosen_group":group_id,
            "chosen_branch":branch_id,
            "creator_selection_approved":True,
            "render_approved":False,
            "source_performances_modified":False,
        }
        scope={
            "operation":"nvp.slate.choose_branch.v1",
            "project_id":project_id,"edit_id":edit_id,
            "expected_revision":expected_revision,
            "graph_id":graph_id,"graph_revision":graph_revision,
            "graph_document_sha256":graph["document_sha256"],
            "group_id":group_id,"branch_id":branch_id,
            "resulting_selection":dict(sorted(selected.items())),
            "final_render_approval":False,
        }
        if self.approve(editor_event,scope) is not True:
            raise PermissionError("Creator did not approve exact editorial branch choice")
        return self.index.register_revision(
            project_id,edit_id,"edit",payload,
            expected_revision=expected_revision,
            dependencies=[{"object_id":graph_id,"revision":graph_revision,
                           "role":"presentation"}])

    def view(self,project_id,graph_id,revision,*,edit_id=None,
             edit_revision=None,group_id=None):
        """Renderer-independent green/gray graph read model for desktop UI."""
        graph=self.open_graph(project_id,graph_id,revision)
        data=graph["data"]
        selected=dict(data["group_defaults"])
        edit_sha=None
        if (edit_id is None)!=(edit_revision is None):
            raise ValueError("Need both edit ID and revision or neither")
        if edit_id is not None:
            edit=self.index.read_revision(project_id,edit_id,edit_revision)
            doc=edit["data"]
            if (edit["kind"]!="edit" or doc.get("format")!=SELECTION_FORMAT or
                doc["graph_document_sha256"]!=graph["document_sha256"] or
                set(doc["selections"])!=set(selected)):
                raise RuntimeError("Selection references a different slate source")
            selected=dict(doc["selections"])
            edit_sha=edit["document_sha256"]
        groups={}
        for node in data["nodes"]:
            group=node["group_id"]
            if group_id is not None and group_id!=group:
                continue
            chosen=selected[group]
            if chosen not in {x["branch_id"] for x in data["nodes"]
                              if x["group_id"]==group}:
                raise RuntimeError("Missing selected parallel branch")
            baseline=next(x for x in data["nodes"]
                          if x["branch_id"]==data["group_defaults"][group])
            original_duration=(baseline["source_end_tick"]-
                               baseline["source_start_tick"])
            duration=node["source_end_tick"]-node["source_start_tick"]
            groups.setdefault(group,[]).append({
                **node,"selected":node["branch_id"]==chosen,
                "display_color":"green" if node["branch_id"]==chosen else "gray",
                "is_default":node["branch_id"]==data["group_defaults"][group],
                "duration_delta_from_default_tick":duration-original_duration,
                "requires_cut_or_retime_decision":duration!=original_duration,
            })
        if group_id is not None and group_id not in groups:
            raise KeyError("Unknown editorial parallel group")
        return {
            "format":"nvp.slate.branch_read_model.v1",
            "project_id":project_id,"scene_id":data["scene_id"],
            "scene_label":data["scene_label"],
            "graph_id":graph_id,"graph_revision":revision,
            "graph_document_sha256":graph["document_sha256"],
            "selection_edit_document_sha256":edit_sha,
            "selected_by_group":selected,
            "parallel_groups":groups,
            "scene_or_take_mutated":False,
            "render_approved":False,
            "frames_rendered":False,
        }
