"""PLAN-02-C: genuine selected-loopback GGUF camera advice, never authority.

Native OpenUSD original Take and exact Film Time are pinned before and after
completion. The model may suggest 2-4 camera control nodes but cannot choose
a new source, retime actor/audio, start tools, write USD, or approve anything.
Provider token receipts attest a completed RESPONSE only; authentic model
weights require separate hashed llama.cpp + GGUF physical/CI acceptance.
"""
from __future__ import annotations

from hashlib import sha256
import json

from backend.nvp_plan02c_rails import (
    CanonicalSourceRails,TECHNIQUES,normalize_rail,_hash)
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_wo6_verified_local_model import FORMAT as PROVIDER_FORMAT

FORMAT="nvp.plan02c.unapproved_verified_source_gguf_advice.v1"
MAX_DIRECTION=1200
MAX_OUTPUT=5000
MAX_NODES=4
NODE_FIELDS=frozenset((
    "tick","position_m","target_m","roll_deg",
    "focal_length_mm","focus_distance_m"))
SYSTEM=(
    "You are a non-authoritative film director's camera assistant. "
    "Only the human director may approve any camera rail, source edits, "
    "model action, native USD publication or renderer worker. "
    "Reply with one JSON object containing exactly 'technique' and 'nodes'. "
    "Technique is a supplied allowed enum; nodes have exactly six fields "
    "tick, position_m, target_m, roll_deg, focal_length_mm and focus_distance_m. "
    "Use 2 to 4 control points. Film Time ticks are exact integers; preserve "
    "the first and last integer unchanged. Do not invent original actors, "
    "original sound recordings, source revision, timeline or approval. "
    "No commentary, markdown, file paths, shell commands or URLs."
)


def _canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,
                      allow_nan=False,separators=(",",":")).encode("ascii")


def candidate_schema(start,end):
    node={"type":"object","additionalProperties":False,
          "properties":{
              "tick":{"type":"integer","minimum":start,"maximum":end},
              "position_m":{"type":"array","minItems":3,"maxItems":3,
                            "items":{"type":"number"}},
              "target_m":{"type":"array","minItems":3,"maxItems":3,
                          "items":{"type":"number"}},
              "roll_deg":{"type":"number","minimum":-180,"maximum":180},
              "focal_length_mm":{"type":"number","minimum":8,"maximum":300},
              "focus_distance_m":{"type":"number","minimum":0.05,
                                  "maximum":10000}},
          "required":sorted(NODE_FIELDS)}
    return {"type":"object","additionalProperties":False,
            "properties":{
                "technique":{"type":"string","enum":sorted(TECHNIQUES)},
                "nodes":{"type":"array","minItems":2,"maxItems":MAX_NODES,
                         "items":node}},
            "required":["technique","nodes"]}


def source_observation(service:CanonicalSourceRails,pid,spec):
    """Actual bounded native OpenUSD source world, not model-invented actors."""
    checked,plan,take=service.source(pid,spec)
    data=take["data"]
    start,end=checked["film_start_tick"],checked["film_end_tick"]
    ticks=sorted({start,(start+end)//2,end-1})
    world=OpenUSDTimeState(service.index)
    objects=[]
    for tick in ticks:
        frame=world.evaluate(
            pid,data["scene_id"],data["scene_revision"],
            data["timeline_id"],data["timeline_revision"],tick=tick)
        if (frame["scene_document_sha256"]!=data["scene_document_sha256"] or
            frame["timeline_document_sha256"]!=data["timeline_document_sha256"]):
            raise RuntimeError("Original actor/source Film Time observation changed")
        objects.append({
            "film_tick":tick,"scene_sample_sha256":frame["snapshot_sha256"],
            "objects":[{
                "prim_path":o["path"],"semantic_role":o["semantic_role"],
                "world_translation_m":o["world_translation"]}
                for o in frame["objects"][:32]]})
    context={
        "source_take_sha256":take["document_sha256"],
        "source_scene_sha256":data["scene_document_sha256"],
        "camera_timeline_sha256":plan["document_sha256"],
        "source_camera_path":checked["source_camera_path"],
        "source_rail_sha256":_hash(checked),
        "original_actor_and_sound_sources_unchanged":True,
        "source_film_time_observations":objects}
    context["guidance_sha256"]=_hash(context)
    return context


def generate_source_camera_advice(service:CanonicalSourceRails,pid,
                                  raw_spec,*,direction,model_id,writer):
    if (type(direction) is not str or
            not 1<=len(direction.strip())<=MAX_DIRECTION or
            any(ord(c)<32 and c not in "\n\t" for c in direction)):
        raise ValueError("Bounded director intent required")
    if type(model_id) is not str or not 1<=len(model_id)<=256:
        raise ValueError("Select a supported local GGUF provider model")
    if not callable(getattr(writer,"complete_camera_candidate",None)):
        raise PermissionError("Only host-selected verified completion adapter permitted")
    checked,plan,take=service.source(pid,raw_spec)
    guidance=source_observation(service,pid,checked)
    source={
        "current_rail":checked,
        "source_observation":guidance,
        "director_intent":direction.strip(),
        "allowed_techniques":sorted(TECHNIQUES),
        "mandatory_first_film_tick":checked["film_start_tick"],
        "mandatory_last_film_tick":checked["film_end_tick"],
        "model_has_no_publication_or_native_worker_authority":True}
    message=_canonical(source)
    if len(message)>18000:
        raise ValueError("Verified original USD scene advice exceeds context bound")
    answer=writer.complete_camera_candidate(
        SYSTEM,message.decode("ascii"),
        candidate_schema(checked["film_start_tick"],checked["film_end_tick"]))
    if type(answer) is not str or not 1<=len(answer.strip())<=MAX_OUTPUT:
        raise ValueError("Selected model returned no bounded camera advice")
    def reject_constant(_):
        raise ValueError("No nonfinite AI camera coordinates")
    try:obj=json.loads(answer,parse_constant=reject_constant)
    except (ValueError,TypeError) as exc:
        raise ValueError("GGUF output is not strict camera JSON") from exc
    if (type(obj) is not dict or set(obj)!={"technique","nodes"} or
            obj["technique"] not in TECHNIQUES or
            type(obj["nodes"]) is not list or
            not 2<=len(obj["nodes"])<=MAX_NODES or
            any(type(n) is not dict or set(n)!=NODE_FIELDS
                for n in obj["nodes"])):
        raise ValueError("GGUF cannot add unknown shot controls or source paths")
    if (type(obj["nodes"][0]["tick"]) is not int or
            type(obj["nodes"][-1]["tick"]) is not int or
            obj["nodes"][0]["tick"]!=checked["film_start_tick"] or
            obj["nodes"][-1]["tick"]!=checked["film_end_tick"]):
        raise ValueError("AI cannot retime frozen source Film Time boundaries")
    nodes=[]
    for node in obj["nodes"]:
        nodes.append({
            "tick":node["tick"],"position_m":node["position_m"],
            "target_m":node["target_m"],"roll_deg":node["roll_deg"],
            "focal_length_mm":node["focal_length_mm"],
            "focus_distance_m":node["focus_distance_m"],
            "f_stop":checked["nodes"][0]["f_stop"],
            "tangent_in_mps":[0.,0.,0.],
            "tangent_out_mps":[0.,0.,0.],
            "segment_mode":"hermite","easing":"smoothstep"})
    proposed=normalize_rail(
        {**checked,"technique":obj["technique"],"nodes":nodes},
        min(int(take["data"]["duration_tick"]),int(plan["duration_tick"])))
    # No stale-source acceptance; inspect original composition again after
    # the genuine model response, not before only.
    after=source_observation(service,pid,checked)
    if after!=guidance:
        raise RuntimeError("Original 3D source changed during GGUF advice")
    receipt=getattr(writer,"completion_receipt",None)
    if (type(receipt) is not dict or receipt.get("format")!=PROVIDER_FORMAT or
            receipt.get("selected_model_id")!=model_id or
            receipt.get("provider_reported_model_id")!=model_id or
            receipt.get("generated_text_sha256")!=sha256(
                answer.strip().encode("utf8")).hexdigest() or
            receipt.get("provider_self_report_not_attestation") is not True or
            receipt.get("native_worker_authorized") is not False or
            type(receipt.get("provider_reported_completion_tokens")) is not int or
            receipt["provider_reported_completion_tokens"]<1):
        raise PermissionError("Actual completed local-model response receipt missing")
    return {"format":FORMAT,
            "status":"UNAPPROVED_SOURCE_CAMERA_ADVICE",
            "source_take_sha256":take["document_sha256"],
            "camera_timeline_sha256":plan["document_sha256"],
            "original_scene_observation_sha256":guidance["guidance_sha256"],
            "direction_sha256":sha256(direction.strip().encode("utf8")).hexdigest(),
            "proposed_rail_spec":proposed,
            "proposed_spec_sha256":_hash(proposed),
            "provider_completion_receipt":dict(receipt),
            "actual_gguf_weights_verified":False,
            "human_authorization_granted":False,
            "rail_published":False,
            "native_worker_authorized":False,
            "original_pcm_and_take_modified":False}
