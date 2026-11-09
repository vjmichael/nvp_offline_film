"""CAM-FX-01: exact-Film-Time director-editable virtual camera rails.

A rail is bounded, original-source-linked data, NOT scene geometry, a camera
collision body, a performance rewrite, a full camera-roll render, or an AI
approval. Position is rail-local metres plus an exact world-space origin.
The frozen 01E ActorID/PCM Take and 01M director source bank are immutable.
CAM-FX-02 authors only a distinct stronger first-party OpenUSD camera layer.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank

FORMAT="nvp.cam_fx01.original_film_time_director_camera_rail.v1"
PREVIEW="nvp.cam_fx01.verified_director_rail_proposal.v1"
MAX_NODES=48
MAX_DURATION_TICKS=90*T
MAX_SPEED_MPS=250.0
MAX_ACCEL_MPS2=1400.0
MAX_COORD_M=100000.0
MAX_INTERVAL_TICKS=2**53-1
TECHNIQUES=frozenset({
    "static","custom","dolly","truck","pedestal","crane","arc","orbit",
    "track","pan_tilt","dutch","rack_focus","dolly_zoom","reveal",
    "follow","push_pull","insert","pov","over_shoulder","reaction",
    "two_shot","establishing","compound"})
MODES=frozenset({"hold","linear","hermite"})
EASING=frozenset({"linear","smoothstep"})
RAIL_FIELDS=frozenset({
    "camera_bank_id","camera_bank_revision","camera_id",
    "film_start_tick","film_end_tick","technique","rail_origin_m",
    "filmback_mm","nodes"})
NODE_FIELDS=frozenset({
    "tick","position_m","target_m","tangent_in_mps","tangent_out_mps",
    "roll_deg","focal_length_mm","focus_distance_m","f_stop",
    "segment_mode","easing"})


def _canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,
                      allow_nan=False,separators=(",",":")).encode("ascii")


def _hash(value):
    return sha256(_canonical(value)).hexdigest()


def _number(value,low,high,what):
    if (type(value) not in (float,int) or not math.isfinite(value)
        or not low<=value<=high):
        raise ValueError("Finite bounded "+what+" required")
    return float(value)


def _vec(value,limit,what):
    if type(value) is not list or len(value)!=3:
        raise ValueError("Expected three coordinates for "+what)
    return [_number(x,-limit,limit,what) for x in value]


def _norm(v):
    return math.sqrt(sum(x*x for x in v))


def _sub(a,b):
    return [x-y for x,y in zip(a,b)]


def _lerp(a,b,u):
    return a+(b-a)*u


def _interpolate(left,right,u,duration_s):
    if left["segment_mode"]=="hold":
        return list(left["position_m"])
    if left["easing"]=="smoothstep":
        u=u*u*(3-2*u)
    if left["segment_mode"]=="linear":
        return [_lerp(a,b,u) for a,b in zip(
            left["position_m"],right["position_m"])]
    a=left["position_m"]
    b=right["position_m"]
    m0=left["tangent_out_mps"]
    m1=right["tangent_in_mps"]
    return [
        (2*u**3-3*u*u+1)*a[i]+
        (u**3-2*u*u+u)*m0[i]*duration_s+
        (-2*u**3+3*u*u)*b[i]+
        (u**3-u*u)*m1[i]*duration_s
        for i in range(3)]


def _validate_nodes(nodes,start,end,origin):
    if type(nodes) is not list or not 2<=len(nodes)<=MAX_NODES:
        raise ValueError("Rail needs 2-48 precisely timed control points")
    seen=[]
    previous=-1
    for item in nodes:
        if type(item) is not dict or set(item)!=NODE_FIELDS:
            raise ValueError("Rail point has unexpected or missing typed control")
        tick=item["tick"]
        if type(tick) is not int or not start<=tick<=end or tick<=previous:
            raise ValueError("Rail Film Time must strictly increase")
        previous=tick
        pos=_vec(item["position_m"],MAX_COORD_M,"rail-local position")
        target=_vec(item["target_m"],MAX_COORD_M,"rail-local look-at target")
        if _norm(_sub(target,pos))<0.02:
            raise ValueError("Camera look-at may not coincide with its position")
        incoming=_vec(item["tangent_in_mps"],MAX_SPEED_MPS,
                      "incoming tangent metres per second")
        outgoing=_vec(item["tangent_out_mps"],MAX_SPEED_MPS,
                      "outgoing tangent metres per second")
        node={
            "tick":tick,"position_m":pos,"target_m":target,
            "tangent_in_mps":incoming,"tangent_out_mps":outgoing,
            "roll_deg":_number(item["roll_deg"],-180,180,"camera roll"),
            "focal_length_mm":_number(
                item["focal_length_mm"],8,300,"native camera focal length"),
            "focus_distance_m":_number(
                item["focus_distance_m"],.05,10000,"focus distance"),
            "f_stop":_number(item["f_stop"],.7,32,"physical camera aperture"),
            "segment_mode":item["segment_mode"],
            "easing":item["easing"],
        }
        if (node["segment_mode"] not in MODES or
            node["easing"] not in EASING):
            raise ValueError("Only bounded, explicitly reviewed rail interpolation")
        if any(abs(a+b)>MAX_COORD_M for a,b in zip(origin,pos)):
            raise ValueError("Rebased camera position outside approved world range")
        seen.append(node)
    if seen[0]["tick"]!=start or seen[-1]["tick"]!=end:
        raise ValueError("Rail must contain exact first and last Film Time ticks")
    # Validate each independently cubic/linear/eased segment by physical
    # velocity and acceleration, not merely by bounded control handles.
    for a,b in zip(seen,seen[1:]):
        dt=(b["tick"]-a["tick"])/T
        if not 1/T<=dt<=90:
            raise ValueError("Rail segment duration outside exact Film Time limits")
        if (a["segment_mode"]=="hold" and
            _norm(_sub(a["position_m"],b["position_m"]))>1e-6):
            raise ValueError("Held camera cannot teleport at the next Film Time key")
        positions=[_interpolate(a,b,i/16,dt) for i in range(17)]
        velocity=[[v*16/dt for v in _sub(x,y)]
                  for x,y in zip(positions[1:],positions)]
        if any(_norm(v)>MAX_SPEED_MPS+1e-5 for v in velocity):
            raise ValueError("Camera rail would exceed bounded travel velocity")
        if any(abs(value)>MAX_COORD_M for pt in positions for value in pt):
            raise ValueError("Cubic overshoot escapes camera world bounds")
        accel=[_norm(_sub(v1,v0))*16/dt
               for v0,v1 in zip(velocity,velocity[1:])]
        if accel and max(accel)>MAX_ACCEL_MPS2+1e-5:
            raise ValueError("Camera rail would exceed bounded vector acceleration")
    return seen


def normalize_rail(spec,source_duration):
    if type(spec) is not dict or set(spec)!=RAIL_FIELDS:
        raise ValueError("Exact source-linked director camera rail fields required")
    _id(spec["camera_bank_id"],"director source bank")
    name=spec["camera_id"]
    if (type(name) is not str or not name or
        not name[0].isalpha() or not name.replace("_","").isalnum()
        or len(name)>50):
        raise ValueError("Rail camera must use a valid native USD token")
    revision=spec["camera_bank_revision"]
    if type(revision) is not int or revision<1:
        raise ValueError("Exact reviewed bank revision required")
    start,end=spec["film_start_tick"],spec["film_end_tick"]
    if (type(start) is not int or type(end) is not int or
        not 0<=start<end<=source_duration or
        end-start>MAX_DURATION_TICKS or end>MAX_INTERVAL_TICKS):
        raise ValueError("Rail must fit a bounded unchanged 01E performance interval")
    technique=spec["technique"]
    if type(technique) is not str or technique not in TECHNIQUES:
        raise ValueError("Unknown typed camera/shot technique")
    origin=_vec(spec["rail_origin_m"],MAX_COORD_M,"origin rebase")
    filmback=spec["filmback_mm"]
    if type(filmback) is not list or len(filmback)!=2:
        raise ValueError("Native camera filmback must be width and height")
    filmback=[_number(x,8,70,"filmback mm") for x in filmback]
    nodes=_validate_nodes(spec["nodes"],start,end,origin)
    return {
        "camera_bank_id":spec["camera_bank_id"],
        "camera_bank_revision":revision,
        "camera_id":name,
        "film_start_tick":start,"film_end_tick":end,
        "technique":technique,"rail_origin_m":origin,
        "filmback_mm":filmback,"nodes":nodes}


def evaluate_rail(spec,tick):
    """Pure deterministic evaluation at any integer original Film Time tick."""
    if type(tick) is not int or not spec["film_start_tick"]<=tick<=spec[
            "film_end_tick"]:
        raise ValueError("Requested exact film tick is not on this rail")
    origin=spec["rail_origin_m"]
    nodes=spec["nodes"]
    if tick==nodes[-1]["tick"]:
        a=b=nodes[-1]
        u=0.0
    else:
        i=next(i for i in range(len(nodes)-1)
               if nodes[i]["tick"]<=tick<nodes[i+1]["tick"])
        a,b=nodes[i],nodes[i+1]
        u=(tick-a["tick"])/(b["tick"]-a["tick"])
    if a is b:
        local=list(a["position_m"])
        mix=0.0
    else:
        local=_interpolate(a,b,u,(b["tick"]-a["tick"])/T)
        mix=(u*u*(3-2*u) if a["easing"]=="smoothstep" else u)
        if a["segment_mode"]=="hold":mix=0.0
    def blend(key):
        return _lerp(a[key],b[key],mix)
    target=[_lerp(a["target_m"][i],b["target_m"][i],mix)
            for i in range(3)]
    if _norm(_sub(target,local))<0.02:
        raise RuntimeError("Animated camera target collides with camera")
    return {
        "film_tick":tick,
        "position_m":[local[i]+origin[i] for i in range(3)],
        "target_m":[target[i]+origin[i] for i in range(3)],
        "rail_local_position_m":local,
        "roll_deg":blend("roll_deg"),
        "focal_length_mm":blend("focal_length_mm"),
        "focus_distance_m":blend("focus_distance_m"),
        "f_stop":blend("f_stop"),
        "filmback_mm":list(spec["filmback_mm"]),
        "technique":spec["technique"],
        "source_performance_edited":False,
        "camera_has_physical_collider":False}


class OriginalCameraRails:
    """Immutable FilmIndex rail revisions with independently authored USD."""

    def __init__(self,index:FilmIndex,*,verify_director_action):
        if not isinstance(index,FilmIndex) or not callable(verify_director_action):
            raise TypeError("Native FilmIndex and genuine director authority required")
        self.index=index
        self.confirm=verify_director_action

    def _prepare(self,pid,rail_id,rail_spec,expected_revision):
        _require_pid(pid)
        _id(rail_id,"director virtual camera rail")
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Exact previous rail revision required")
        if (type(rail_spec) is not dict or
            type(rail_spec.get("camera_bank_id")) is not str or
            type(rail_spec.get("camera_bank_revision")) is not int):
            raise ValueError("Source-locked camera rail required")
        bank_id=rail_spec["camera_bank_id"]
        bank_rev=rail_spec["camera_bank_revision"]
        bank=DirectorCameraBank(self.index,verify_director_action=lambda *_:False
                                ).verify(pid,bank_id,bank_rev)
        source=self.index.read_revision(pid,bank_id,bank_rev)
        spec=normalize_rail(rail_spec,bank["source_duration_ticks"])
        if not any(c["camera_id"]==spec["camera_id"] for c in bank["cameras"]):
            raise PermissionError("Rail cannot introduce an unapproved source camera")
        take=self.index.read_revision(pid,bank["world_take_id"],1)
        if take["document_sha256"]!=bank["world_take_sha256"]:
            raise RuntimeError("Frozen original actor/world Take changed")
        predecessor=None
        if expected_revision:
            prior=self.verify(pid,rail_id,expected_revision)
            if (prior["camera_bank_id"]!=bank_id or
                prior["world_take_id"]!=bank["world_take_id"] or
                prior["rail_spec"]["camera_id"]!=spec["camera_id"]):
                raise PermissionError("A rail revision may not switch actor or camera sources")
            predecessor=self.index.read_revision(
                pid,rail_id,expected_revision)["document_sha256"]
        from backend.nvp_cam_fx02_usd_camera_layer import (
            generate_camera_director_layer)
        layer=generate_camera_director_layer(rail_id,spec)
        layer_sha=sha256(layer).hexdigest()
        doc={
            "format":FORMAT,
            "rail_spec":spec,
            "camera_bank_id":bank_id,"camera_bank_revision":bank_rev,
            "camera_bank_sha256":source["document_sha256"],
            "world_take_id":bank["world_take_id"],
            "world_take_sha256":bank["world_take_sha256"],
            "source_performance_sha256":bank["source_performance_sha256"],
            "source_duration_ticks":bank["source_duration_ticks"],
            "rail_layer_sha256":layer_sha,
            "rail_layer_bytes":len(layer),
            "previous_rail_revision_sha256":predecessor,
            "original_actor_takes_and_pcm_unchanged":True,
            "original_camera_bank_unchanged":True,
            "native_cycles_frames_rendered":0,
            "human_picture_quality_approved":False}
        return doc,layer

    def preview(self,pid,rail_id,rail_spec,*,expected_revision=0):
        doc,layer=self._prepare(pid,rail_id,rail_spec,expected_revision)
        samples=[evaluate_rail(doc["rail_spec"],t) for t in sorted({
            doc["rail_spec"]["film_start_tick"],
            (doc["rail_spec"]["film_start_tick"]+
             doc["rail_spec"]["film_end_tick"])//2,
            doc["rail_spec"]["film_end_tick"]})]
        return {"format":PREVIEW,"rail_id":rail_id,
                "expected_revision":expected_revision,
                "proposal_sha256":_hash(doc),
                "camera_bank_sha256":doc["camera_bank_sha256"],
                "world_take_sha256":doc["world_take_sha256"],
                "rail_layer_sha256":doc["rail_layer_sha256"],
                "rail_layer_bytes":len(layer),
                "film_time_samples":samples,
                "director_creative_approval_granted":False,
                "native_blender_workers_started":0,
                "original_actor_takes_and_pcm_unchanged":True}

    def publish(self,pid,rail_id,rail_spec,*,expected_revision,
                preview_sha256,director_event):
        doc,layer=self._prepare(pid,rail_id,rail_spec,expected_revision)
        if type(preview_sha256) is not str or preview_sha256!=_hash(doc):
            raise PermissionError("A stale or absent director rail preview cannot publish")
        scope={
            "operation":"nvp.cam_fx02.publish_exact_director_camera_rail.v1",
            "project_id":pid,"rail_id":rail_id,
            "expected_revision":expected_revision,
            "world_take_sha256":doc["world_take_sha256"],
            "source_performance_sha256":doc["source_performance_sha256"],
            "camera_bank_sha256":doc["camera_bank_sha256"],
            "source_camera_id":doc["rail_spec"]["camera_id"],
            "film_start_tick":doc["rail_spec"]["film_start_tick"],
            "film_end_tick":doc["rail_spec"]["film_end_tick"],
            "shot_technique":doc["rail_spec"]["technique"],
            "proposed_rail_sha256":preview_sha256,
            "stronger_usd_layer_sha256":doc["rail_layer_sha256"],
        }
        if self.confirm(director_event,scope) is not True:
            raise PermissionError("Only fresh exact director rail approval may publish")
        # FilmIndex blobs are content addressed, but never a grant. Failed
        # optimistic revisions leave at most a harmless unlinked blob.
        stored=self.index.put_blob(pid,layer,media_type="text/vnd.usda")
        if stored!=doc["rail_layer_sha256"]:
            raise RuntimeError("Native OpenUSD rail bytes changed before commit")
        record=self.index.register_revision(
            pid,rail_id,"presentation",doc,
            expected_revision=expected_revision,
            dependencies=[
                {"object_id":doc["camera_bank_id"],
                 "revision":doc["camera_bank_revision"],"role":"camera"},
                {"object_id":doc["world_take_id"],
                 "revision":1,"role":"source_take"}])
        return {**record,"source_usd_layer_sha256":stored,
                "original_actor_takes_and_pcm_unchanged":True,
                "director_picture_approved":False}

    def verify(self,pid,rail_id,revision):
        _require_pid(pid)
        _id(rail_id,"exact original camera rail")
        if type(revision) is not int or revision<1:
            raise ValueError("Revisioned camera source required")
        record=self.index.read_revision(pid,rail_id,revision)
        if (record["kind"]!="presentation" or
            record["data"].get("format")!=FORMAT):
            raise PermissionError("Not an approved director camera rail")
        expected,_=self._prepare_verified_record(
            pid,rail_id,record,revision)
        if expected!=record["data"]:
            raise RuntimeError("Native rail revision or original source changed")
        return record["data"]

    def _prepare_verified_record(self,pid,rail_id,record,revision):
        # Do not recurse _prepare() when verifying an existing revision.
        doc=record["data"]
        bank=DirectorCameraBank(self.index,
            verify_director_action=lambda *_:False).verify(
                pid,doc["camera_bank_id"],doc["camera_bank_revision"])
        source=self.index.read_revision(
            pid,doc["camera_bank_id"],doc["camera_bank_revision"])
        spec=normalize_rail(doc["rail_spec"],bank["source_duration_ticks"])
        if (spec["camera_bank_id"]!=doc["camera_bank_id"] or
            spec["camera_bank_revision"]!=doc["camera_bank_revision"] or
            not any(x["camera_id"]==spec["camera_id"]
                    for x in bank["cameras"])):
            raise RuntimeError("Frozen director camera source is no longer valid")
        take=self.index.read_revision(pid,bank["world_take_id"],1)
        if take["document_sha256"]!=bank["world_take_sha256"]:
            raise RuntimeError("Frozen original ActorID world Take was modified")
        from backend.nvp_cam_fx02_usd_camera_layer import (
            generate_camera_director_layer)
        layer=generate_camera_director_layer(rail_id,spec)
        previous=None
        if revision>1:
            prior=self.index.read_revision(pid,rail_id,revision-1)
            if prior["data"].get("format")!=FORMAT:
                raise RuntimeError("Old native camera rail revision changed type")
            if (prior["data"]["camera_bank_id"]!=doc["camera_bank_id"] or
                prior["data"]["world_take_id"]!=bank["world_take_id"] or
                prior["data"]["rail_spec"]["camera_id"]!=spec["camera_id"]):
                raise RuntimeError("Rail source identity switched across revisions")
            previous=prior["document_sha256"]
        expected={
            "format":FORMAT,"rail_spec":spec,
            "camera_bank_id":doc["camera_bank_id"],
            "camera_bank_revision":doc["camera_bank_revision"],
            "camera_bank_sha256":source["document_sha256"],
            "world_take_id":bank["world_take_id"],
            "world_take_sha256":bank["world_take_sha256"],
            "source_performance_sha256":bank["source_performance_sha256"],
            "source_duration_ticks":bank["source_duration_ticks"],
            "rail_layer_sha256":sha256(layer).hexdigest(),
            "rail_layer_bytes":len(layer),
            "previous_rail_revision_sha256":previous,
            "original_actor_takes_and_pcm_unchanged":True,
            "original_camera_bank_unchanged":True,
            "native_cycles_frames_rendered":0,
            "human_picture_quality_approved":False}
        if self.index.get_blob(pid,expected["rail_layer_sha256"])!=layer:
            raise RuntimeError("Stored native rail layer was replaced")
        edges={(e["role"],e["object_id"],e["revision"])
               for e in record["dependencies"]}
        required={
            ("camera",doc["camera_bank_id"],doc["camera_bank_revision"]),
            ("source_take",bank["world_take_id"],1)}
        if edges!=required:
            raise RuntimeError("Immutable rail source dependency edges changed")
        return expected,layer
