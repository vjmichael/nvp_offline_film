"""WO6-B finite, pathless native OpenUSD checkpoint evaluator.

Only immutable self-contained scene layers and exact authored event IDs travel
over inherited binary pipes. No live FilmIndex, keys, writable database or
external assets are mounted. The host alone can publish a verified Take.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import sys

if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.nvp_g03_protected_scene_worker import _binary_stdio, read_exact
from backend.nvp_openusd_take import canonical, sha, MAX_CHECKPOINTS
from backend.nvp_openusd_scene import (
    _usd, _layer_from_text, _compose, _evaluate, MAX_PRIMS, MAX_USD_LAYER_BYTES)
from backend.nvp_openusd_channels import evaluate_parameter_channels

MAGIC_IN=b"NVPWO6IN1"
MAGIC_OUT=b"NVPWO6OUT1"
MAX_INPUT=24*1024*1024
MAX_OUTPUT=4096
LAYER_KEYS={"layout":"layout_layer_sha256","motion":"motion_layer_sha256",
            "parameters":"parameter_layer_sha256","skeletons":"skeleton_layer_sha256"}


def evaluate_input(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_INPUT:
        raise ValueError("Bounded native Take source required")
    doc=json.loads(raw)
    if canonical(doc)!=raw or set(doc)!={"format","scope_sha256","scene","layers","events","ticks"} or doc["format"]!="nvp.wo6.take_worker_input.v1":
        raise ValueError("Exact native Take input required")
    scene=doc["scene"]; ticks=doc["ticks"]; events=doc["events"]
    if (any(scene.get(k) for k in ("asset_bindings","actor_bindings","imported_characters")) or
        scene.get("contains_external_references") is not False):
        raise PermissionError("External assets or cast require a protected source resolver")
    order=scene["layer_order"]
    if order not in (["motion","layout"],["parameters","motion","layout"],
        ["skeletons","motion","layout"],["skeletons","parameters","motion","layout"]):
        raise ValueError("Unsupported immutable layer graph")
    if (set(doc["layers"])!=set(order) or type(ticks) is not list or
        not 1<=len(ticks)<=MAX_CHECKPOINTS or
        any(type(t) is not int or t<0 for t in ticks) or ticks!=sorted(set(ticks)) or
        type(events) is not list or len(events)!=len(ticks)):
        raise ValueError("Invalid native layer or Film Time budget")
    _,Sdf,Usd,UsdGeom=_usd()
    layers={}
    for key,text in doc["layers"].items():
        payload=text.encode("utf-8")
        if (not 0<len(payload)<=MAX_USD_LAYER_BYTES or
            sha256(payload).hexdigest()!=scene[LAYER_KEYS[key]] or
            not text.lstrip().startswith("#usda 1.0") or "@" in text or
            re.search(r"\b(?:references|payload|subLayers|clips|assetInfo)\b",text)):
            raise PermissionError("Unverified or external USD layer refused")
        layers[key]=_layer_from_text(text,"wo6_"+key+".usda",Sdf)
    stage=_compose(layers["layout"],layers["motion"],Sdf,Usd,
                   layers.get("parameters"),layers.get("skeletons"))
    roles=scene["prim_roles"]
    if type(roles) is not dict or not 1<=len(roles)<=MAX_PRIMS:
        raise ValueError("Bounded exact semantic roles required")
    checkpoints=[]
    for tick,active in zip(ticks,events):
        if type(active) is not list or len(active)>500 or any(type(x) is not str for x in active):
            raise ValueError("Invalid authored event IDs")
        prims=sorted(roles)
        checkpoint={"tick":tick,"poses":[_evaluate(stage,p,tick,Sdf,Usd,UsdGeom)
                    for p in prims],"active_event_ids":active}
        if scene.get("performance_channels"):
            checkpoint["performance_channels"]=evaluate_parameter_channels(
                stage,scene["performance_channels"],roles,tick)
        if scene.get("native_schema_version"):
            from backend.nvp_openusd_native_schemas import evaluate_native_schema
            values=evaluate_parameter_channels(stage,scene.get("performance_channels",[]),roles,tick)
            checkpoint["native_scene_schemas"]=[value for p in prims if
                (value:=evaluate_native_schema(stage,p,roles[p],tick,values)) is not None]
        if scene.get("skeleton_rigs"):
            from backend.nvp_openusd_skeleton import evaluate_skeletons
            checkpoint["skeletal_pose"]=evaluate_skeletons(stage,scene["skeleton_rigs"],tick)
        checkpoints.append(checkpoint)
    return {"format":"nvp.wo6.take_worker_result.v1","scope_sha256":doc["scope_sha256"],
            "input_sha256":sha256(raw).hexdigest(),"sample_digest_sha256":sha(checkpoints),
            "checkpoint_count":len(checkpoints)}


def worker_entry():
    try:
        inp,out,_err=_binary_stdio()
        header=read_exact(inp,len(MAGIC_IN)+8)
        if header[:len(MAGIC_IN)]!=MAGIC_IN:
            raise ValueError("Wrong native worker protocol")
        size=struct.unpack("!Q",header[len(MAGIC_IN):])[0]
        if not 0<size<=MAX_INPUT:
            raise ValueError("Native source budget exceeded")
        raw=read_exact(inp,size)
        if inp.read(1):
            raise ValueError("Trailing native input")
        result=canonical(evaluate_input(raw))
        if len(result)>MAX_OUTPUT:
            raise ValueError("Native output budget exceeded")
        out.write(MAGIC_OUT+struct.pack("!Q",len(result))+result)
        out.flush()
        return 0
    except Exception:
        # Never echo original creator source, paths or diagnostic contents.
        return 3


if __name__=="__main__":
    raise SystemExit(worker_entry())
