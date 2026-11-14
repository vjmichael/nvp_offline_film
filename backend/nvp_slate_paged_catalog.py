"""SLATE-03: paged, SHA-pinned digital Take catalog for large native shoots.

Pages are physical FilmIndex presentation revisions, NOT fake parents.
A catalog root references immutable pages; each page has <=64 real Take/
SHOT source dependency pairs. True ancestry is a branch_id reference and
can cross catalog-page boundaries. One root currently indexes up to 4096
branches; further scale is a manifest hierarchy, not a forged lineage.

AI observations are UNREVIEWED proposals, never approvals or source facts.
This catalogs *film data*, not imported flat video frames.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_temporal_ledger import _int
from backend.nvp_digital_slate_branches import (
    DigitalSlateBranches, GRAPH_FORMAT, NODE_KEYS, SLATE_KEYS, _label, _note)
from backend.nvp_openusd_take import FORMAT as TAKE_FORMAT
from backend.nvp_openusd_shot_overrides import FORMAT as SHOT_FORMAT

CATALOG_FORMAT="nvp.slate.paged_scene_catalog.v1"
PAGE_FORMAT="nvp.slate.catalog_page.v1"
PAGE_SIZE=64
MAX_PAGES=64
MAX_BRANCHES=PAGE_SIZE*MAX_PAGES
MAX_LOOKUP=100
MAX_OBSERVATIONS=8
SHOTS=frozenset(("unknown","master","wide","medium","closeup",
                 "extreme_closeup","reaction","insert","over_shoulder","tracking"))
TECHNICAL=frozenset(("unknown","acceptable","needs_review","rejected"))
META_KEYS=frozenset(("beat_ids","character_ids","action_tags","emotion_tags",
                     "dialogue_ids","moment_cues",
                     "shot_type","director_rating","director_notes",
                     "technical_status","continuity_flags","ai_observations"))
MOMENT_KEYS=frozenset(("source_in_tick","source_out_tick","beat_ids",
                       "character_ids","dialogue_ids","emotion_tags",
                       "action_tags","origin"))
OBS_KEYS=frozenset(("model_id","summary","confidence","source_in_tick",
                    "source_out_tick","status"))
OBS_STATUS="UNREVIEWED_AI_PROPOSAL"


def _canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _labels(values,maximum=16):
    if type(values) is not list or len(values)>maximum:
        raise ValueError("Slate semantic list exceeds bounded length")
    normalized=[_label(x,"AI-indexable semantic tag") for x in values]
    if len(normalized)!=len(set(normalized)):
        raise ValueError("Duplicate semantic tag")
    return sorted(normalized)


def _metadata(raw,start,end):
    if raw is None:
        raw={}
    if type(raw) is not dict or not set(raw)<=META_KEYS:
        raise ValueError("Unknown AI/editor metadata attributes")
    fields={
        "beat_ids":_labels(raw.get("beat_ids",[])),
        "character_ids":_labels(raw.get("character_ids",[])),
        "dialogue_ids":_labels(raw.get("dialogue_ids",[])),
        "action_tags":_labels(raw.get("action_tags",[])),
        "emotion_tags":_labels(raw.get("emotion_tags",[])),
        "shot_type":raw.get("shot_type","unknown"),
        "director_rating":raw.get("director_rating"),
        "director_notes":_note(raw.get("director_notes","")),
        "technical_status":raw.get("technical_status","unknown"),
        "continuity_flags":_labels(raw.get("continuity_flags",[])),
    }
    if fields["shot_type"] not in SHOTS or fields["technical_status"] not in TECHNICAL:
        raise ValueError("Unknown shot type or technical acceptance status")
    rating=fields["director_rating"]
    if rating is not None and (
        type(rating) is not int or rating<1 or rating>5):
        raise ValueError("Director rating is 1 to 5 or unknown")
    # Time-addressed source DATA cues help an AI/editor identify WHICH
    # portion of a Take carries a beat, dialogue or expression. Unlike
    # source frames, these spans do not depend on output sampling FPS.
    moments=raw.get("moment_cues",[])
    if type(moments) is not list or len(moments)>32:
        raise ValueError("At most 32 source-time editorial cue spans per branch")
    fields["moment_cues"]=[]
    for moment in moments:
        if type(moment) is not dict or set(moment)!=MOMENT_KEYS:
            raise ValueError("Cue span requires exact data-time evidence fields")
        low=_int(moment["source_in_tick"],"cue source inpoint")
        high=_int(moment["source_out_tick"],"cue source outpoint")
        if not start<=low<high<=end:
            raise ValueError("Cue span must fit the frozen source segment")
        if moment["origin"] not in ("editor_tag","script_note"):
            raise PermissionError("AI observations cannot self-approve editorial cue spans")
        fields["moment_cues"].append({
            "source_in_tick":low,"source_out_tick":high,
            "origin":moment["origin"],
            "beat_ids":_labels(moment["beat_ids"]),
            "character_ids":_labels(moment["character_ids"]),
            "dialogue_ids":_labels(moment["dialogue_ids"]),
            "action_tags":_labels(moment["action_tags"]),
            "emotion_tags":_labels(moment["emotion_tags"]),
        })
    fields["moment_cues"].sort(
        key=lambda x:(x["source_in_tick"],x["source_out_tick"],x["origin"]))
    observations=raw.get("ai_observations",[])
    if type(observations) is not list or len(observations)>MAX_OBSERVATIONS:
        raise ValueError("Only bounded AI observations are accepted")
    fields["ai_observations"]=[]
    for item in observations:
        if type(item) is not dict or set(item)!=OBS_KEYS:
            raise ValueError("AI suggestion requires exact provenance fields")
        _label(item["model_id"],"model identity")
        _note(item["summary"])
        confidence=item["confidence"]
        if (type(confidence) not in (int,float) or
            not math.isfinite(confidence) or not 0<=confidence<=1):
            raise ValueError("AI suggestion confidence must be finite 0..1")
        low=_int(item["source_in_tick"],"observation inpoint")
        high=_int(item["source_out_tick"],"observation outpoint")
        if not start<=low<high<=end:
            raise ValueError("AI observation lacks valid source-time evidence")
        if item["status"]!=OBS_STATUS:
            raise PermissionError("AI observations cannot self-approve")
        fields["ai_observations"].append({
            **item,"confidence":float(confidence)})
    return fields


class SlatePagedCatalog:
    """Scene-level pages; no artificial parent/child to evade a quota."""

    def __init__(self,index:FilmIndex,*,verify_catalog_action):
        if not isinstance(index,FilmIndex) or not callable(verify_catalog_action):
            raise TypeError("Trusted FilmIndex and capture policy required")
        self.index=index
        self.approve=verify_catalog_action
        self.slate=DigitalSlateBranches(
            index,verify_editor_action=lambda *_:False)

    def _normalized(self,project_id,scene_id,scene_label,records):
        _require_pid(project_id)
        _id(scene_id,"canonical film scene")
        _label(scene_label,"slate scene label")
        if type(records) is not list or not 1<=len(records)<=MAX_BRANCHES:
            raise ValueError("Expected 1 to 4096 actual source branches")
        lookup={}
        groups={}
        defaults={}
        normalized=[]
        cached_takes={}
        cached_shots={}
        for i,rec in enumerate(records):
            if (type(rec) is not dict or
                set(rec)!=NODE_KEYS|{"semantic"}):
                raise ValueError("Paged slate node has unknown/missing typed fields")
            bid=_id(rec["branch_id"],"branch identifier")
            group=_id(rec["group_id"],"parallel group")
            if bid in lookup:
                raise ValueError("Duplicate branch identity across catalog pages")
            kind=rec["kind"]
            if kind not in ("performance","coverage"):
                raise ValueError("Unknown slate branch type")
            primary=rec["primary"]
            if type(primary) is not bool:
                raise ValueError("Parallel default must be explicit boolean")
            tid=_id(rec["take_id"],"source Digital Take")
            source_start=_int(rec["source_start_tick"],"source range start")
            source_end=_int(rec["source_end_tick"],"source range end")
            if source_end<=source_start:
                raise ValueError("Invalid source interval")
            if tid not in cached_takes:
                cached_takes[tid]=self.slate._take(project_id,tid,scene_id)
            take=cached_takes[tid]
            if source_end>take["data"]["duration_tick"]:
                raise ValueError("Branch interval exceeds its immutable Take")
            parent=rec["parent_id"]
            fork=rec["fork_tick"]
            if i==0:
                if (kind!="performance" or parent is not None or
                    fork is not None or source_start!=0):
                    raise ValueError("First page starts with one original parent Take")
            else:
                if type(parent) is not str or parent not in lookup:
                    raise ValueError("Branch parent must precede child; page boundary does not matter")
                _int(fork,"parent-relative fork tick")
                ancestor=lookup[parent]
                if not ancestor["source_start_tick"]<=fork<ancestor["source_end_tick"]:
                    raise ValueError("Child fork must belong to parent performance interval")
                if kind=="coverage" and (
                    ancestor["kind"]!="performance" or
                    ancestor["take_id"]!=tid):
                    raise ValueError("Coverage must observe its true parent performance")
                if kind=="performance" and ancestor["kind"]!="performance":
                    raise ValueError("Alternate performance must descend from a performance")
            sid=rec["shot_id"]
            srev=rec["shot_revision"]
            shot_sha=None
            if sid is None:
                if srev is not None:
                    raise ValueError("Shot revision without source shot identity")
            else:
                _id(sid,"shot coverage")
                _int(srev,"source SHOT-01 revision",minimum=1)
                if kind!="coverage":
                    raise ValueError("Only camera coverage may select an existing shot")
                key=(sid,srev)
                if key not in cached_shots:
                    cached_shots[key]=self.slate._shot(
                        project_id,sid,srev,tid,source_start,source_end)
                shot_record=cached_shots[key]
                shot_sha=shot_record["document_sha256"]
                shot_info=shot_record["data"]
                if (shot_info["take_id"]!=tid or
                    shot_info["start_tick"]>source_start or
                    shot_info["end_tick"]<source_end):
                    raise ValueError(
                        "Shared coverage shot does not include this source interval")
            slate=rec["slate"]
            if (type(slate) is not dict or set(slate)!=SLATE_KEYS or
                slate["scene"]!=scene_label):
                raise ValueError("Exact digital slate metadata required")
            for field in ("setup","shot","camera","script_revision"):
                _label(slate[field],field)
            _int(slate["take_number"],"slate take number",minimum=1,maximum=99999)
            if type(slate["wild"]) is not bool or (
                slate["wild"] and kind!="performance"):
                raise ValueError("Invalid wild-take classification")
            _note(slate["notes"])
            if primary:
                if group in defaults:
                    raise ValueError("Parallel group has multiple default candidates")
                defaults[group]=bid
            groups.setdefault(group,[]).append(bid)
            node={
                **{k:rec[k] for k in NODE_KEYS},
                "take_document_sha256":take["document_sha256"],
                "shot_document_sha256":shot_sha,
                "semantic":_metadata(rec["semantic"],source_start,source_end),
            }
            lookup[bid]=node
            normalized.append(node)
        if set(groups)!=set(defaults):
            raise ValueError("Every group must have one source default")
        return normalized,defaults

    def _page_id(self,catalog_id,next_revision,page):
        fingerprint=hashlib.sha256(
            (catalog_id+"|"+str(next_revision)+"|"+str(page)).encode()).hexdigest()
        return "slatepage_"+fingerprint[:32]

    def publish(self,project_id,catalog_id,*,scene_id,scene_label,records,
                capture_event,expected_revision=0):
        """Pages are immutable before root publication. Unreferenced failed pages
        are harmless staged artifacts, never a visible authoritative catalog."""
        _id(catalog_id,"paged slate root")
        _int(expected_revision,"expected root revision")
        nodes,defaults=self._normalized(
            project_id,scene_id,scene_label,records)
        full_digest=_sha(nodes)
        scope={
            "operation":"nvp.slate.publish_paged_catalog.v1",
            "project_id":project_id,"catalog_id":catalog_id,
            "expected_revision":expected_revision,
            "scene_id":scene_id,"scene_label":scene_label,
            "branch_count":len(nodes),
            "ordered_branches_sha256":full_digest,
            "final_render_approval":False,
        }
        if self.approve(capture_event,dict(scope)) is not True:
            raise PermissionError("Creator did not authorize exact slate catalog publication")
        root_pages=[]
        rev=expected_revision+1
        for start in range(0,len(nodes),PAGE_SIZE):
            number=start//PAGE_SIZE
            payload=nodes[start:start+PAGE_SIZE]
            page_id=self._page_id(catalog_id,rev,number)
            if page_id==catalog_id:
                raise RuntimeError("Catalog page ID conflict")
            deps={}
            for item in payload:
                deps[(item["take_id"],1,"source_take")]=True
                if item["shot_id"] is not None:
                    deps[(item["shot_id"],item["shot_revision"],"presentation")]=True
            if len(deps)>128:
                raise RuntimeError("Catalog page exceeded the trusted source dependency budget")
            page={
                "format":PAGE_FORMAT,"catalog_id":catalog_id,
                "catalog_revision":rev,"scene_id":scene_id,
                "page_number":number,"start_index":start,
                "nodes":payload,"ordered_nodes_sha256":_sha(payload),
            }
            stored=self.index.register_revision(
                project_id,page_id,"presentation",page,
                expected_revision=0,dependencies=[
                    {"object_id":oid,"revision":r,"role":role}
                    for oid,r,role in sorted(deps)])
            root_pages.append({
                "page_id":page_id,"page_revision":1,
                "page_document_sha256":stored["document_sha256"],
                "start_index":start,"count":len(payload),
                "group_ids":sorted(set(x["group_id"] for x in payload)),
            })
        root={
            "format":CATALOG_FORMAT,"scene_id":scene_id,
            "scene_label":scene_label,
            "branch_count":len(nodes),"page_count":len(root_pages),
            "ordered_branches_sha256":full_digest,
            "group_defaults":defaults,"pages":root_pages,
            "ai_observations_authoritative":False,
            "frozen_takes_modified":False,
            "final_render_approved":False,
        }
        return self.index.register_revision(
            project_id,catalog_id,"presentation",root,
            expected_revision=expected_revision,
            dependencies=[
                {"object_id":p["page_id"],"revision":1,"role":"presentation"}
                for p in root_pages])

    def open_catalog(self,project_id,catalog_id,revision):
        root=self.index.read_revision(project_id,catalog_id,revision)
        doc=root["data"]
        if (root["kind"]!="presentation" or
            doc.get("format")!=CATALOG_FORMAT or
            type(doc.get("pages")) is not list or
            not 1<=len(doc["pages"])<=MAX_PAGES or
            doc["page_count"]!=len(doc["pages"]) or
            doc["branch_count"]>MAX_BRANCHES or
            doc["ai_observations_authoritative"] is not False):
            raise RuntimeError("Not a valid immutable paged slate catalog")
        pos=0
        for p in doc["pages"]:
            if p["start_index"]!=pos or (
                p["count"]<=0 or p["count"]>PAGE_SIZE):
                raise RuntimeError("Paged branch ranges overlap or have gaps")
            pos+=p["count"]
        if pos!=doc["branch_count"]:
            raise RuntimeError("Paged source count differs from root")
        return root

    def _page(self,project_id,root,page):
        data=root["data"]
        if type(page) is not int or not 0<=page<len(data["pages"]):
            raise ValueError("Invalid catalog page ordinal")
        ref=data["pages"][page]
        actual=self.index.read_revision(
            project_id,ref["page_id"],ref["page_revision"])
        doc=actual["data"]
        if (actual["kind"]!="presentation" or
            actual["document_sha256"]!=ref["page_document_sha256"] or
            doc.get("format")!=PAGE_FORMAT or
            doc["catalog_id"]!=root["object_id"] or
            doc["catalog_revision"]!=root["revision"] or
            doc["scene_id"]!=data["scene_id"] or
            doc["page_number"]!=page or
            doc["start_index"]!=ref["start_index"] or
            len(doc["nodes"])!=ref["count"] or
            _sha(doc["nodes"])!=doc["ordered_nodes_sha256"]):
            raise RuntimeError("Catalog page no longer matches pinned root")
        return doc["nodes"]

    def page(self,project_id,catalog_id,revision,*,after_index=-1,limit=64,
             group_id=None,beat_id=None,character_id=None,emotion_tag=None,
             shot_type=None,technical_status=None):
        """Stable global source offset paging; filters narrow evidence only.

        Performance is bounded by the 4096 entry root in this milestone,
        without copying any Take and without needing imported source frames.
        """
        root=self.open_catalog(project_id,catalog_id,revision)
        if type(after_index) is not int or after_index<-1:
            raise ValueError("Invalid branch page cursor")
        _int(limit,"catalog page size",minimum=1,maximum=MAX_LOOKUP)
        for name,value in (("group",group_id),("beat",beat_id),
                           ("character",character_id),("emotion",emotion_tag)):
            if value is not None:
                _id(value,name+" search identity")
        if shot_type is not None and shot_type not in SHOTS:
            raise ValueError("Unknown shot type filter")
        if technical_status is not None and technical_status not in TECHNICAL:
            raise ValueError("Unknown technical status filter")
        items=[]
        has_more=False
        for page_no,reference in enumerate(root["data"]["pages"]):
            if reference["start_index"]+reference["count"]-1<=after_index:
                continue
            if group_id is not None and group_id not in reference["group_ids"]:
                continue
            for offset,node in enumerate(self._page(project_id,root,page_no)):
                index=reference["start_index"]+offset
                if index<=after_index:
                    continue
                m=node["semantic"]
                moments=m["moment_cues"]
                if (group_id is not None and node["group_id"]!=group_id or
                    beat_id is not None and beat_id not in m["beat_ids"] and
                      not any(beat_id in cue["beat_ids"] for cue in moments) or
                    character_id is not None and character_id not in m["character_ids"] and
                      not any(character_id in cue["character_ids"] for cue in moments) or
                    emotion_tag is not None and emotion_tag not in m["emotion_tags"] and
                      not any(emotion_tag in cue["emotion_tags"] for cue in moments) or
                    shot_type is not None and shot_type!=m["shot_type"] or
                    technical_status is not None and
                    technical_status!=m["technical_status"]):
                    continue
                if len(items)==limit:
                    has_more=True
                    break
                items.append({"catalog_index":index,**node})
            if has_more:
                break
        return {
            "format":"nvp.slate.catalog_page_read.v1",
            "catalog_id":catalog_id,"catalog_revision":revision,
            "catalog_document_sha256":root["document_sha256"],
            "branch_count":root["data"]["branch_count"],
            "items":items,
            "next_after_index":items[-1]["catalog_index"] if has_more else None,
            "ai_observations_authoritative":False,
            "editing_source_data_modified":False,
        }

    def all_nodes(self,project_id,catalog_id,revision):
        """Bridge to legacy assembly; use page() for efficient desktop views."""
        root=self.open_catalog(project_id,catalog_id,revision)
        nodes=[]
        for number in range(root["data"]["page_count"]):
            nodes.extend(self._page(project_id,root,number))
        if len(nodes)!=root["data"]["branch_count"] or (
            _sha(nodes)!=root["data"]["ordered_branches_sha256"]):
            raise RuntimeError("Pausable catalog snapshot does not match sealed ordering")
        return root,nodes


class PagedSlateAssemblyAdapter(DigitalSlateBranches):
    """Use existing SLATE-02 assembled-cut engine on a SHA-pinned catalog.

    The FilmIndex catalog is a virtual immutable graph for the legacy API.
    Only actual parent_id links determine lineage; catalog page membership
    never becomes a fictitious genealogy edge.
    """
    def __init__(self,catalog:SlatePagedCatalog):
        if not isinstance(catalog,SlatePagedCatalog):
            raise TypeError("Expected immutable paged slate catalog")
        super().__init__(
            catalog.index,verify_editor_action=lambda *_:False)
        self.catalog=catalog

    def open_graph(self,project_id,graph_id,revision):
        root,nodes=self.catalog.all_nodes(project_id,graph_id,revision)
        return {
            **root,
            "data":{
                "format":GRAPH_FORMAT,
                "scene_id":root["data"]["scene_id"],
                "scene_label":root["data"]["scene_label"],
                "nodes":nodes,
                "group_defaults":root["data"]["group_defaults"],
            },
        }
