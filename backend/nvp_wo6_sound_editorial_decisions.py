"""WO6-07D: native data-first sound-cue and original-slate editorial assembly.

Both operations are immutable *authored source decisions*, not audio DSP,
mix/master approval, frame rendering or movie release. Model text cannot be
interpreted here. Human-typed values and WO6 host-sealed task are required.
"""
from __future__ import annotations

import math
from hashlib import sha256
from backend.nvp_approved_tasks import canonical_bytes

from backend.nvp_data_av_source import RecordedSoundSources, FORMAT as PCM_FORMAT
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_film_index import FilmIndex, _id, _sha
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly, SEGMENT_KEYS, _digest
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND, _int
from backend.nvp_wo6_native_take_action import _exact_source

MAX_SOUND_SOURCE_EVENTS=128
SOUND_KEYS=frozenset((
    "cue_id","subject_id","start_tick","end_tick",
    "recorded_sound_id","recorded_sound_revision",
    "recorded_sound_sha256","first_sample","gain",
))


def _slate(index):
    graph=DigitalSlateBranches(index,verify_editor_action=lambda *_:False)
    return SlateSequenceAssembly(graph,verify_editor_action=lambda *_:False)


def _source_events(index,project_id,source_id,source_rev):
    ledger=TemporalLedger(index)
    record=index.read_revision(project_id,source_id,source_rev)
    if record["kind"]!="temporal":
        raise PermissionError("Only an original indexed native event timeline may be copied")
    if record["data"].get("event_count",0)>MAX_SOUND_SOURCE_EVENTS:
        raise RuntimeError("Sound-cue copy would truncate the original source events")
    ledger.verify(project_id,source_id,source_rev)
    events=ledger.events_in(
        project_id,source_id,source_rev,start_tick=0,
        end_tick=record["data"]["duration_tick"],
        limit=MAX_SOUND_SOURCE_EVENTS+1)["events"]
    if len(events)!=record["data"]["event_count"]:
        raise RuntimeError("Original timed events could not be copied without omission")
    return record,events


def preflight_sound_cue(index, spec):
    pid=spec["project_id"]
    _exact_source(index,pid,spec["source_id"],spec["source_revision"],
                  spec["source_sha256"],"temporal")
    timeline,original_events=_source_events(
        index,pid,spec["source_id"],spec["source_revision"])
    duration=timeline["data"]["duration_tick"]
    if (spec["duration_tick"]!=str(duration) or
            type(spec["payload"]) is not dict or
            set(spec["payload"])!=SOUND_KEYS):
        raise ValueError("Exact sound cue fields and original duration required")
    p=spec["payload"]
    _id(p["cue_id"],"new sound event")
    _id(p["subject_id"],"sound subject")
    _id(p["recorded_sound_id"],"recorded PCM source")
    _sha(p["recorded_sound_sha256"])
    if type(p["recorded_sound_revision"]) is not int or p["recorded_sound_revision"]<1:
        raise ValueError("Exact recorded audio revision required")
    if any(x["event_id"]==p["cue_id"] for x in original_events):
        raise PermissionError("An original sound cue ID cannot be overwritten")
    start=_int(p["start_tick"],"sound cue start")
    end=_int(p["end_tick"],"sound cue end",minimum=1)
    offset=_int(p["first_sample"],"recorded PCM first sample")
    if (not start<end<=duration or type(p["gain"]) not in (int,float) or
            not math.isfinite(p["gain"]) or not 0<=p["gain"]<=2):
        raise ValueError("Invalid sound timing or finite gain")
    samples,nrem=divmod((end-start)*48000,TICKS_PER_SECOND)
    if nrem or samples<1:
        raise ValueError("Sound cue must span a whole number of native PCM samples")
    original=RecordedSoundSources(index).describe(
        pid,p["recorded_sound_id"],p["recorded_sound_revision"])
    if original["document_sha256"]!=p["recorded_sound_sha256"] or (
            offset+samples>original["data"]["sample_count"]):
        raise PermissionError("Original PCM source SHA or available sample interval differs")
    return timeline,original_events,{
        "event_id":p["cue_id"],"event_kind":"sound",
        "subject_id":p["subject_id"],"start_tick":start,"end_tick":end,
        "source_id":p["recorded_sound_id"],
        "source_revision":p["recorded_sound_revision"],
        "payload":{"gain":float(p["gain"]),
                   "source_first_sample":offset,
                   "source_sample_count":samples,
                   "recorded_source_sha256":p["recorded_sound_sha256"],
                   "director_entered_sound_cue":True,
                   "samples_rendered":False},
    }


def publish_sound_cue(index,spec):
    timeline,events,insert=preflight_sound_cue(index,spec)
    return TemporalLedger(index).publish(
        spec["project_id"],spec["decision_id"],
        [{k:v for k,v in entry.items()
          if k!="source_document_sha256"} for entry in events]+[insert],
        duration_tick=timeline["data"]["duration_tick"],
        expected_revision=0)


def verify_sound_cue(index,spec):
    timeline,events,added=preflight_sound_cue(index,spec)
    pid=spec["project_id"]
    ledger=TemporalLedger(index)
    record=index.read_revision(pid,spec["decision_id"],1)
    if (record["kind"]!="temporal" or record["data"].get("duration_tick")!=
            timeline["data"]["duration_tick"] or
            record["data"].get("event_count")!=len(events)+1 or
            record["data"].get("creator_approved") is not False or
            record["data"].get("presentation_frames_rendered") is not False):
        raise RuntimeError("Authored sound event timeline has changed")
    proof=ledger.verify(pid,spec["decision_id"],1)
    if proof["document_sha256"]!=record["document_sha256"]:
        raise RuntimeError("Sound-event copied source provenance differs")
    new=ledger.events_in(
        pid,spec["decision_id"],1,start_tick=0,
        end_tick=timeline["data"]["duration_tick"],
        limit=MAX_SOUND_SOURCE_EVENTS+2)["events"]
    expected=[{k:v for k,v in entry.items()
               if k!="source_document_sha256"} for entry in events]+[added]
    actual=[{k:v for k,v in entry.items()
             if k!="source_document_sha256"} for entry in new]
    def key(value):
        return (value["start_tick"],value["event_id"])
    if sorted(actual,key=key)!=sorted(expected,key=key):
        raise RuntimeError("New sound cue or inherited original events differ")
    return record["document_sha256"]


def preflight_editorial_cut(index,spec):
    pid=spec["project_id"]
    _exact_source(index,pid,spec["source_id"],spec["source_revision"],
                  spec["source_sha256"],"presentation")
    if (spec["duration_tick"] is not None or
            type(spec["payload"]) is not list or
            not 1<=len(spec["payload"])<=64 or
            any(type(x) is not dict or set(x)!=SEGMENT_KEYS
                for x in spec["payload"])):
        raise ValueError("Exact bounded human editorial source segments required")
    assembly=_slate(index)
    draft=assembly.preview(
        pid,spec["source_id"],spec["source_revision"],spec["payload"])
    if (draft["graph_document_sha256"]!=spec["source_sha256"] or
            draft["draft_uncommitted"] is not True or
            draft["render_approved"] is not False or
            draft["selection_changes_active_cut"] is not False):
        raise RuntimeError("Source slate draft is not a nonauthorizing native preview")
    return draft


def publish_editorial_cut(index,spec):
    draft=preflight_editorial_cut(index,spec)
    def trusted(event,scope):
        return (event=="host_verified_exact_editorial_spec" and
                scope["operation"]=="nvp.slate.commit_assembled_edit.v1" and
                scope["project_id"]==spec["project_id"] and
                scope["edit_id"]==spec["decision_id"] and
                scope["expected_revision"]==0 and
                scope["graph_id"]==spec["source_id"] and
                scope["graph_document_sha256"]==spec["source_sha256"] and
                scope["ordered_segment_sha256"]==_digest(draft["segments"]) and
                scope["final_render_approval"] is False)
    slate=DigitalSlateBranches(index,verify_editor_action=lambda *_:False)
    assembly=SlateSequenceAssembly(slate,verify_editor_action=trusted)
    return assembly.commit(
        spec["project_id"],spec["decision_id"],
        graph_id=spec["source_id"],
        graph_revision=spec["source_revision"],
        segments=spec["payload"],
        editor_event="host_verified_exact_editorial_spec",
        expected_revision=0)


def verify_editorial_cut(index,spec):
    draft=preflight_editorial_cut(index,spec)
    cut=_slate(index).open_edit(
        spec["project_id"],spec["decision_id"],1)
    d=cut["data"]
    if (d["graph_id"]!=spec["source_id"] or
            d["graph_revision"]!=spec["source_revision"] or
            d["graph_document_sha256"]!=spec["source_sha256"] or
            d["ordered_segment_sha256"]!=_digest(draft["segments"]) or
            d["duration_tick"]!=draft["duration_tick"] or
            d["source_performance_modified"] is not False or
            d["render_approved"] is not False or
            d["retimed"] is not False):
        raise RuntimeError("Native editorial cut diverged from the human preview")
    return cut["document_sha256"]


def preview_sound_cue(index,pid,source_id,source_rev,source_sha,payload):
    source=index.read_revision(pid,source_id,source_rev)
    draft={
        "project_id":pid,"source_id":source_id,"source_revision":source_rev,
        "source_sha256":source_sha,"duration_tick":str(
            source["data"]["duration_tick"]),"payload":payload,
    }
    original,old,cue=preflight_sound_cue(index,draft)
    return {"format":"nvp.wo6.07d.native_sound_cue_preview.v1",
            "original_timeline_sha256":original["document_sha256"],
            "prior_event_count":len(old),
            "new_sound_cue_id":cue["event_id"],
            "authored_sample_count":cue["payload"]["source_sample_count"],
            "no_audio_rendered":True,"no_worker_authorized":True}


def typed_decision_sha(spec):
    """One SHA of the EXACT human-entered source+new decision+parameters."""
    fields=("project_id","decision_kind","decision_id","source_id",
            "source_revision","source_sha256","payload","duration_tick")
    return sha256(canonical_bytes({k:spec[k] for k in fields})).hexdigest()


def preview_typed_decision(index,spec):
    """Source-verified read-only typed preview; NO creator/tool grant."""
    pid=spec["project_id"]
    _id(spec["decision_id"],"new exact decision object ID")
    if spec["decision_id"]==spec["source_id"]:
        raise ValueError("Cannot reuse original FilmIndex object identity")
    try:
        index.read_revision(pid,spec["decision_id"])
    except KeyError:
        pass
    else:
        raise PermissionError("Decision identity already exists")
    kind=spec["decision_kind"]
    if kind=="sound_cue":
        source,existing,cue=preflight_sound_cue(index,spec)
        detail={"inherited_event_count":len(existing),
                "added_event_id":cue["event_id"],
                "sample_count":cue["payload"]["source_sample_count"],
                "original_duration_tick":source["data"]["duration_tick"]}
    elif kind=="editorial_cut":
        draft=preflight_editorial_cut(index,spec)
        detail={"source_graph_sha256":draft["graph_document_sha256"],
                "draft_sha256":draft["draft_sha256"],
                "ordered_segment_sha256":_digest(draft["segments"]),
                "segment_count":len(draft["segments"]),
                "duration_tick":draft["duration_tick"]}
    else:
        raise ValueError("Only typed sound-cue or slate-edit preview supported")
    return {
        "format":"nvp.wo6.07d.read_only_typed_decision_preview.v1",
        "status":"READ_ONLY_TYPED_DECISION_NO_GRANT",
        "project_id":pid,
        "decision_kind":kind,
        "original_source_sha256":spec["source_sha256"],
        "typed_preview_sha256":typed_decision_sha(spec),
        "original_unchanged":True,
        "native_worker_authorized":False,
        "creative_approval_granted":False,
        "rendered_sound":False,
        "active_edit_committed":False,
        "final_film_approved":False,
        "details":detail,
    }
