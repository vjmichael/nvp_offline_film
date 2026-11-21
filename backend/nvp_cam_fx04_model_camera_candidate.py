"""CAM-FX-04: real source-grounded local-model *advice*, never authority.

A host-selected WO6 GGUF provider can propose a bounded camera path using
only first-party USD ActorID source evidence. All returned values are
untrusted: strict JSON, native 01E/01M source/time constraints, actual USD
camera-layer generation and current SQLite draft version are independently
rechecked before a *draft* changes. Approval is a separate OS action.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_cam_fx01_camera_rails import (
    TECHNIQUES,normalize_rail,_hash)
from backend.nvp_cam_fx03_source_guidance import FORMAT as GUIDANCE_FORMAT
from backend.nvp_wo6_verified_local_model import FORMAT as PROVIDER_FORMAT

FORMAT="nvp.cam_fx04.untrusted_source_bounded_local_model_camera_advice.v1"
MAX_DIRECTION=1200
MAX_REPLY=5000
MAX_NODES=4
NODE_FIELDS=frozenset({
    "tick","position_m","target_m","roll_deg",
    "focal_length_mm","focus_distance_m"})
SYSTEM=(
    "You advise a human film director on one digital 3D camera rail. "
    "You are not an approver and cannot edit original ActorID performances, "
    "invent actor identities, start tools or write USD. Reply with EXACT JSON "
    "object keys technique and nodes. Technique must be from the supplied "
    "allowed list. nodes must have 2-4 items with exact integer original "
    "Film Time ticks, and each node must have ONLY these six keys: tick, "
    "position_m [3 metre numbers], target_m [3 metre numbers], roll_deg, "
    "focal_length_mm and focus_distance_m. Keep the exact first and last "
    "ticks and original source framing/real ActorID bounds. No Markdown, "
    "paths, shell commands, URLs, approvals or commentary."
)

def _canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")

def camera_candidate_schema(start,end):
    node={
        "type":"object","additionalProperties":False,
        "properties":{
            "tick":{"type":"integer","minimum":start,"maximum":end},
            "position_m":{"type":"array","minItems":3,"maxItems":3,
                          "items":{"type":"number"}},
            "target_m":{"type":"array","minItems":3,"maxItems":3,
                        "items":{"type":"number"}},
            "roll_deg":{"type":"number","minimum":-180,"maximum":180},
            "focal_length_mm":{"type":"number","minimum":8,"maximum":300},
            "focus_distance_m":{"type":"number","minimum":.05,"maximum":10000}},
        "required":sorted(NODE_FIELDS)}
    return {"type":"object","additionalProperties":False,
            "properties":{
                "technique":{"type":"string","enum":sorted(TECHNIQUES)},
                "nodes":{"type":"array","minItems":2,"maxItems":MAX_NODES,
                         "items":node}},
            "required":["technique","nodes"]}

def generate_camera_candidate(rail_spec,source_guidance,*,direction,
                              model_id,writer):
    """No side effect. A durable host attempt persists result separately."""
    if (type(direction) is not str or
        not 1<=len(direction.strip())<=MAX_DIRECTION or
        any(ord(c)<32 and c not in "\n\t" for c in direction)):
        raise ValueError("Bounded director explanation/intent required")
    if (type(model_id) is not str or not 1<=len(model_id)<=256 or
        not callable(getattr(writer,"complete",None))):
        raise PermissionError("Only selected host-owned local-model writer")
    if (type(source_guidance) is not dict or
        source_guidance.get("format")!=GUIDANCE_FORMAT or
        not source_guidance.get("native_scene_reviewed") or
        not source_guidance.get("source_actor_takes_and_pcm_unchanged") or
        source_guidance.get("rail_spec_sha256")!=_hash(rail_spec)):
        raise PermissionError("Only independently verified actual original scene context")
    check=dict(source_guidance)
    checksum=check.pop("guidance_sha256",None)
    if checksum!=_hash(check):
        raise RuntimeError("Host USD source framing evidence was altered")
    # A real model sees source-derived metrics but never unrestricted
    # filesystem paths, model endpoints, or native OS authorization handles.
    observations=[]
    for frame in source_guidance["source_guided_frames"][:3]:
        observations.append({
            "film_tick":frame["film_tick"],
            "selected_actor_id":frame["selected_actor_id"],
            "selected_actor_center_world_m":
                frame["selected_actor_center_world_m"],
            "actor_framing":[{
                "actor_id":a["actor_id"],
                "center_world_m":a["center_world_m"],
                "frame_coverage":a["frame"]["coverage"],
                "frame_state":a["frame"]["state"]}
                for a in frame["original_actor_views"][:24]],
            "occlusion":frame["selected_actor_center_ray"]["state"]})
    source={
        "current_rail_spec":rail_spec,
        "source_project_id":source_guidance["project_id"],
        "source_world_take_sha256":source_guidance["world_take_sha256"],
        "source_camera_bank_sha256":
            source_guidance["camera_bank_sha256"],
        "native_source_guidance_sha256":checksum,
        "approved_district_sha256":
            source_guidance["approved_district_sha256"],
        "source_actor_geometry_observations":observations,
        "allowed_techniques":sorted(TECHNIQUES),
        "mandatory_first_film_tick":rail_spec["film_start_tick"],
        "mandatory_last_film_tick":rail_spec["film_end_tick"],
        "director_intent":direction.strip(),
        "model_is_not_authorized_to_publish_or_render":True}
    payload=_canonical(source)
    if len(payload)>18000:
        raise MemoryError("Native source-backed AI prompt exceeds context bound")
    schema=camera_candidate_schema(
        rail_spec["film_start_tick"],rail_spec["film_end_tick"])
    constrained=getattr(writer,"complete_camera_candidate",None)
    output=(constrained(SYSTEM,payload.decode("ascii"),schema)
            if callable(constrained)
            else writer.complete(SYSTEM,payload.decode("ascii")))
    if type(output) is not str or not 1<=len(output)<=MAX_REPLY:
        raise ValueError("Local camera advice is missing or unbounded")
    def reject_constant(_):
        raise ValueError("No nonfinite model numbers are admitted")
    try:
        data=json.loads(output,parse_constant=reject_constant)
    except (ValueError,TypeError) as exc:
        raise ValueError("Model must return one exact JSON camera proposal") from exc
    if (type(data) is not dict or set(data)!={"technique","nodes"} or
        type(data["technique"]) is not str or
        data["technique"] not in TECHNIQUES or
        type(data["nodes"]) is not list or
        not 2<=len(data["nodes"])<=MAX_NODES):
        raise ValueError("Only known source-limited virtual film technique fields")
    original_nodes=rail_spec["nodes"]
    start=rail_spec["film_start_tick"]
    end=rail_spec["film_end_tick"]
    if (type(data["nodes"][0]) is not dict or
        type(data["nodes"][-1]) is not dict or
        data["nodes"][0].get("tick")!=start or
        data["nodes"][-1].get("tick")!=end):
        raise ValueError("AI cannot retime the source performance boundary")
    nodes=[]
    for i,item in enumerate(data["nodes"]):
        if type(item) is not dict or set(item)!=NODE_FIELDS:
            raise ValueError("AI rail node has unexpected keys")
        if type(item["tick"]) is not int:
            raise ValueError("AI source key must be an integer Film Time tick")
        nodes.append({
            "tick":item["tick"],"position_m":item["position_m"],
            "target_m":item["target_m"],"roll_deg":item["roll_deg"],
            "focal_length_mm":item["focal_length_mm"],
            "focus_distance_m":item["focus_distance_m"],
            "f_stop":original_nodes[0]["f_stop"],
            "tangent_in_mps":[0.,0.,0.],
            "tangent_out_mps":[0.,0.,0.],
            "segment_mode":"hermite","easing":"smoothstep"})
    candidate={**rail_spec,"technique":data["technique"],"nodes":nodes}
    # Actual native duration comes from source bank, not from model text.
    clean=normalize_rail(candidate,rail_spec["film_end_tick"])
    receipt=getattr(writer,"completion_receipt",None)
    if (type(receipt) is not dict or
        receipt.get("format")!=PROVIDER_FORMAT or
        receipt.get("selected_model_id")!=model_id or
        receipt.get("provider_reported_model_id")!=model_id or
        receipt.get("generated_text_sha256")!=sha256(
            output.strip().encode("utf8")).hexdigest() or
        receipt.get("native_worker_authorized") is not False or
        receipt.get("provider_self_report_not_attestation") is not True):
        raise RuntimeError("Real local model output lacks matching host completion evidence")
    return {"format":FORMAT,
            "model_id":model_id,
            "source_guidance_sha256":checksum,
            "source_original_take_sha256":
                source_guidance["world_take_sha256"],
            "source_bank_sha256":
                source_guidance["camera_bank_sha256"],
            "director_direction_sha256":
                sha256(direction.strip().encode("utf8")).hexdigest(),
            "model_text_sha256":
                sha256(output.strip().encode("utf8")).hexdigest(),
            "provider_completion_receipt":dict(receipt),
            "proposed_rail_spec":clean,
            "unapproved_draft_only":True,
            "model_weights_attested":False,
            "os_authorization_granted":False,
            "original_actor_takes_and_pcm_modified":False}
