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
    "take_id","take_document_sha256","camera_timeline_id",
    "camera_timeline_revision","camera_timeline_sha256",
    "source_camera_path","camera_id","film_start_tick","film_end_tick",
    "technique","rail_origin_m","filmback_mm","nodes"})
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
    """CANONICAL source-bound CAM-FX rail; no world-bank implicit authority."""
    from backend.nvp_film_index import _sha
    if type(spec) is not dict or set(spec)!=RAIL_FIELDS:
        raise ValueError("Exact frozen source, camera and control fields required")
    for key in ("take_id","camera_timeline_id"):
        _id(spec[key],key)
    for key in ("take_document_sha256","camera_timeline_sha256"):
        _sha(spec[key])
    if type(spec["camera_timeline_revision"]) is not int or spec[
            "camera_timeline_revision"]<1:
        raise ValueError("Exact camera timeline revision required")
    src=spec["source_camera_path"]
    if (type(src) is not str or not src.startswith("/World/") or
            len(src)>240 or any(ch in src for ch in ("\\","..","//"))):
        raise ValueError("Original source camera path must be bounded authored USD")
    name=spec["camera_id"]
    if (type(name) is not str or not 1<=len(name)<=50 or
            not name[0].isalpha() or not name.replace("_","").isalnum()):
        raise ValueError("Director rail camera identity must be an OpenUSD token")
    start,end=spec["film_start_tick"],spec["film_end_tick"]
    if (type(start) is not int or type(end) is not int or
            not 0<=start<end<=source_duration or
            end-start>MAX_DURATION_TICKS or end>MAX_INTERVAL_TICKS):
        raise ValueError("Virtual rail must stay in verified original Film Time")
    technique=spec["technique"]
    if type(technique) is not str or technique not in TECHNIQUES:
        raise ValueError("Only known typed shot technique allowed")
    origin=_vec(spec["rail_origin_m"],MAX_COORD_M,"origin rebase")
    filmback=spec["filmback_mm"]
    if type(filmback) is not list or len(filmback)!=2:
        raise ValueError("Finite native camera filmback required")
    filmback=[_number(x,8,70,"filmback mm") for x in filmback]
    nodes=_validate_nodes(spec["nodes"],start,end,origin)
    return {**{key:spec[key] for key in (
        "take_id","take_document_sha256","camera_timeline_id",
        "camera_timeline_revision","camera_timeline_sha256",
        "source_camera_path","camera_id")},
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


from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_scene import OpenUSDSceneBridge

CANONICAL_FORMAT="nvp.plan02c.canonical_frozen_take_camera_rail.v1"
CANONICAL_PREVIEW="nvp.plan02c.camera_rail_preview.v1"

class CanonicalSourceRails:
    """Source-bounded rail revisions; real native consent is host-controlled."""

    def __init__(self,index:FilmIndex,*,approve):
        if not isinstance(index,FilmIndex) or not callable(approve):
            raise TypeError("Real FilmIndex and creator authorization required")
        self.index=index
        self.approve=approve

    def source(self,pid,spec):
        _require_pid(pid)
        _id(spec["take_id"],"frozen Take")
        _id(spec["camera_timeline_id"],"original camera timeline")
        take=self.index.read_revision(pid,spec["take_id"],1)
        if (take["kind"]!="take" or
            take["document_sha256"]!=spec["take_document_sha256"]):
            raise PermissionError("Stale or foreign original frozen Take")
        # Verifies original OpenUSD composition, checkpoints and any
        # incomplete multi-object publication before granting a preview.
        OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda *_:False).verify_take(
                pid,spec["take_id"])
        camera=ExactTimeShotSequence(self.index).read(
            pid,spec["camera_timeline_id"],spec["camera_timeline_revision"])
        if (camera["document_sha256"]!=spec["camera_timeline_sha256"] or
            camera["scene_id"]!=take["data"]["scene_id"] or
            camera["scene_revision"]!=take["data"]["scene_revision"] or
            camera["scene_document_sha256"]!=take["data"]["scene_document_sha256"]):
            raise PermissionError("Original camera and actor/sound Take source differs")
        source=OpenUSDSceneBridge(self.index).open(
            pid,camera["scene_id"],camera["scene_revision"])[0]
        if source["data"]["prim_roles"].get(spec["source_camera_path"])!="camera":
            raise PermissionError("Rail targets no original authored camera")
        spec=normalize_rail(spec,min(
            int(take["data"]["duration_tick"]),int(camera["duration_tick"])))
        if not any(
                s["camera_path"]==spec["source_camera_path"] and
                int(s["start_tick"])<=spec["film_start_tick"] and
                int(s["end_tick"])>=spec["film_end_tick"]
                for s in camera["shots"]):
            raise PermissionError("Rail crosses an unapproved camera cut or source gap")
        return spec,camera,take

    def _candidate(self,pid,rail_id,raw,expected_revision):
        _id(rail_id,"new director rail identity")
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Exact rail revision required")
        spec,camera,take=self.source(pid,raw)
        old_sha=None
        if expected_revision:
            previous=self.verify(pid,rail_id,expected_revision)
            if any(previous["rail_spec"][key]!=spec[key] for key in (
                    "take_id","take_document_sha256",
                    "camera_timeline_id","camera_timeline_revision",
                    "camera_timeline_sha256","source_camera_path","camera_id")):
                raise PermissionError("Rail revision cannot switch original source")
            old_sha=self.index.read_revision(
                pid,rail_id,expected_revision)["document_sha256"]
        else:
            try:self.index.read_revision(pid,rail_id,1)
            except KeyError:pass
            else:raise PermissionError("Rail already exists; revision required")
        from backend.nvp_plan02c_usd_rail import generate_source_rail_layer
        layer=generate_source_rail_layer(rail_id,spec)
        doc={
            "format":CANONICAL_FORMAT,"rail_spec":spec,
            "take_document_sha256":take["document_sha256"],
            "camera_timeline_sha256":camera["document_sha256"],
            "rail_layer_sha256":sha256(layer).hexdigest(),
            "rail_layer_bytes":len(layer),
            "previous_revision_sha256":old_sha,
            "source_take_modified":False,"sound_source_modified":False,
            "camera_source_modified":False,"rendered_film_frames":0,
            "director_artistic_picture_approved":False}
        return doc,layer

    def preview(self,pid,rail_id,raw,expected_revision=0):
        doc,layer=self._candidate(pid,rail_id,raw,expected_revision)
        spec=doc["rail_spec"]
        keys={spec["film_start_tick"],spec["film_end_tick"],
              (spec["film_start_tick"]+spec["film_end_tick"])//2}
        keys.update(n["tick"] for n in spec["nodes"])
        return {
            "format":CANONICAL_PREVIEW,"rail_id":rail_id,
            "expected_revision":expected_revision,
            "proposal_sha256":_hash(doc),
            "take_document_sha256":doc["take_document_sha256"],
            "camera_timeline_sha256":doc["camera_timeline_sha256"],
            "layer_sha256":doc["rail_layer_sha256"],
            "source_film_time_samples":[evaluate_rail(spec,t) for t in sorted(keys)],
            "source_scene_modified":False,"director_approved":False,
            "native_worker_authorized":False,
            "frame_grid_authority":False}

    def publish(self,pid,rail_id,raw,expected_revision,proposal_sha256):
        doc,layer=self._candidate(pid,rail_id,raw,expected_revision)
        if type(proposal_sha256) is not str or proposal_sha256!=_hash(doc):
            raise PermissionError("Camera rail preview is stale or forged")
        scope={
            "operation":"nvp.plan02c.publish_source_rail.v1",
            "project_id":pid,"rail_id":rail_id,
            "expected_revision":expected_revision,
            "source_take_sha256":doc["take_document_sha256"],
            "camera_timeline_sha256":doc["camera_timeline_sha256"],
            "source_camera_path":doc["rail_spec"]["source_camera_path"],
            "film_start_tick":doc["rail_spec"]["film_start_tick"],
            "film_end_tick":doc["rail_spec"]["film_end_tick"],
            "proposal_sha256":proposal_sha256,
            "layer_sha256":doc["rail_layer_sha256"]}
        if self.approve(dict(scope)) is not True:
            raise PermissionError("Fresh native director approval was refused")
        # Recheck every source hash and optional predecessor AFTER dialog.
        confirm,again=self._candidate(pid,rail_id,raw,expected_revision)
        if confirm!=doc or again!=layer:
            raise PermissionError("Source or rail changed during OS confirmation")
        stored=self.index.put_blob(pid,layer,media_type="text/vnd.usda")
        if stored!=doc["rail_layer_sha256"]:
            raise RuntimeError("Original source rail layer digest changed")
        receipt=self.index.register_revision(
            pid,rail_id,"presentation",doc,
            expected_revision=expected_revision,
            dependencies=[
                {"object_id":raw["take_id"],"revision":1,"role":"source_take"},
                {"object_id":raw["camera_timeline_id"],
                 "revision":raw["camera_timeline_revision"],
                 "role":"timeline"}])
        return {"format":"nvp.plan02c.director_approved_rail_receipt.v1",
                "rail_id":rail_id,"revision":receipt["revision"],
                "rail_document_sha256":receipt["document_sha256"],
                "source_take_sha256":doc["take_document_sha256"],
                "layer_sha256":stored,
                "original_modified":False,"film_master_approved":False,
                "renderer_worker_authorized":False}

    def verify(self,pid,rail_id,revision):
        _require_pid(pid)
        _id(rail_id,"original camera rail")
        if type(revision) is not int or revision<1:
            raise ValueError("Exact approved rail revision required")
        record=self.index.read_revision(pid,rail_id,revision)
        doc=record["data"]
        if record["kind"]!="presentation" or doc.get("format")!=CANONICAL_FORMAT:
            raise PermissionError("Not an approved original Take camera rail")
        spec,camera,take=self.source(pid,doc["rail_spec"])
        from backend.nvp_plan02c_usd_rail import generate_source_rail_layer
        layer=generate_source_rail_layer(rail_id,spec)
        prev=None
        if revision>1:
            previous=self.index.read_revision(pid,rail_id,revision-1)
            if previous["data"].get("format")!=CANONICAL_FORMAT:
                raise RuntimeError("Prior camera rail was replaced")
            prev=previous["document_sha256"]
        expected={
            "format":CANONICAL_FORMAT,"rail_spec":spec,
            "take_document_sha256":take["document_sha256"],
            "camera_timeline_sha256":camera["document_sha256"],
            "rail_layer_sha256":sha256(layer).hexdigest(),
            "rail_layer_bytes":len(layer),
            "previous_revision_sha256":prev,
            "source_take_modified":False,"sound_source_modified":False,
            "camera_source_modified":False,"rendered_film_frames":0,
            "director_artistic_picture_approved":False}
        if expected!=doc or self.index.get_blob(pid,expected["rail_layer_sha256"])!=layer:
            raise RuntimeError("Strong camera layer or frozen Take was altered")
        return doc
