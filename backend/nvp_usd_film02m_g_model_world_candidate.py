"""USD-FILM-02M-G — source-bounded *actual local model* world candidate.

Pure candidate production: no FilmIndex write, native approval, worker grant,
shell/file/model-selected URL or direct draft mutation. A separate native
director operation must validate, persist and preview the candidate.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_wo6_verified_local_model import FORMAT as PROVIDER_FORMAT

FORMAT = "nvp.usd_film02m_g.local_model_world_candidate.v1"
MAX_DIRECTION = 1200
MAX_PROMPT = 18000
MAX_REPLY = 5000
PARAMS = frozenset({
    "seed", "source_buildings", "grid_cols", "grid_rows",
    "lot_spacing_m", "world_origin_m", "source_triangle_budget",
    "source_instance_budget",
})
SYSTEM = (
    "You advise a film director on procedural ORIGINAL 3D building districts. "
    "You are not a tool, operator or approver. Return a single JSON object "
    "with exactly one key: params. params must have exactly eight keys: "
    "seed, source_buildings, grid_cols, grid_rows, lot_spacing_m, "
    "world_origin_m, source_triangle_budget, source_instance_budget. "
    "Use ONLY source building ID and integer revision pairs supplied by the "
    "verified catalog. Return no Markdown, commands, paths, URLs, new asset "
    "names, director operations, approval statements or extra fields."
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _typed_params(candidate, catalog):
    if type(candidate) is not dict or set(candidate) != {"params"}:
        raise ValueError("Model output must be only a typed params object")
    params = candidate["params"]
    if type(params) is not dict or set(params) != PARAMS:
        raise ValueError("Model did not supply exact original district parameters")
    integer_keys = ("seed", "grid_cols", "grid_rows",
                    "source_triangle_budget", "source_instance_budget")
    if any(type(params[k]) is not int for k in integer_keys):
        raise ValueError("Original world integer inputs must be integers, not bool or strings")
    if (not 0 <= params["seed"] <= 2147483647 or
        not 1 <= params["grid_cols"] <= 16 or
        not 1 <= params["grid_rows"] <= 16 or
        not 1 <= params["source_instance_budget"] <= 256 or
        not 100 <= params["source_triangle_budget"] <= 2000000):
        raise ValueError("Model exceeded bounded original source world limits")
    spacing=params["lot_spacing_m"]
    if type(spacing) not in (int, float) or not math.isfinite(spacing) or not 4 <= spacing <= 10000:
        raise ValueError("Invalid finite lot spacing")
    origin=params["world_origin_m"]
    if (type(origin) is not list or len(origin)!=3 or
        any(type(n) not in (int,float) or not math.isfinite(n) or
            abs(n)>100000000 for n in origin)):
        raise ValueError("Invalid finite bounded world origin")
    buildings=params["source_buildings"]
    if type(buildings) is not list or not 1 <= len(buildings) <= 8:
        raise ValueError("Select one through eight source-approved buildings")
    approved={
        (b["building_id"],b["revision"])
        for b in catalog["source_buildings"]
        if type(b) is dict and type(b.get("building_id")) is str
        and type(b.get("revision")) is int
    }
    seen=set()
    for b in buildings:
        if (type(b) is not dict or set(b)!={"building_id","revision"} or
            type(b["building_id"]) is not str or
            type(b["revision"]) is not int or
            (b["building_id"],b["revision"]) not in approved or
            b["building_id"] in seen):
            raise PermissionError("AI proposed an unapproved or duplicate source building")
        seen.add(b["building_id"])
    if params["grid_cols"]*params["grid_rows"] > params["source_instance_budget"]:
        raise ValueError("Grid violates proposed source instance budget")
    return params


def _host_world_json_schema(catalog):
    """Source-limited grammar: constraints are STILL rechecked by NVP.

    The JSON-schema hint helps small real GGUF models finish exact JSON,
    but is not a source authorization or evidence of instruction following.
    """
    names=sorted({b["building_id"] for b in catalog["source_buildings"]
                  if type(b) is dict and type(b.get("building_id")) is str
                  and type(b.get("revision")) is int})
    names=names[:24]
    if not names:
        raise ValueError("No original 3D source building may be proposed")
    entry={
        "type":"object","additionalProperties":False,
        "properties":{
            "building_id":{"type":"string","enum":names},
            "revision":{"type":"integer","minimum":1}},
        "required":["building_id","revision"],
    }
    params={
        "type":"object","additionalProperties":False,
        "properties":{
            "seed":{"type":"integer","minimum":0,"maximum":2147483647},
            "source_buildings":{"type":"array","minItems":1,
                                "maxItems":8,"items":entry},
            "grid_cols":{"type":"integer","minimum":1,"maximum":16},
            "grid_rows":{"type":"integer","minimum":1,"maximum":16},
            "lot_spacing_m":{"type":"number","minimum":4},
            "world_origin_m":{"type":"array","minItems":3,
                "maxItems":3,"items":{"type":"number"}},
            "source_triangle_budget":{"type":"integer","minimum":100,
                "maximum":2000000},
            "source_instance_budget":{"type":"integer","minimum":1,
                "maximum":256},
        },
        "required":sorted(PARAMS),
    }
    return {"type":"object","additionalProperties":False,
            "properties":{"params":params},"required":["params"]}


def generate_model_world_candidate(
        catalog, *, project_id, district_id, expected_revision,
        direction, model_id, model):
    """Generate one source-locked proposal from an already host-selected model.

    Model provider self-reports are evidence of completion, not binary or
    weights attestation. Source planner must independently reverify geometry.
    """
    if (type(catalog) is not dict or
        catalog.get("format")!="nvp.usd_film02m_f.native_source_catalog.v1" or
        catalog.get("project_id")!=project_id or
        type(catalog.get("source_buildings")) is not list or
        type(catalog.get("approved_districts")) is not list or
        type(project_id) is not str or type(district_id) is not str or
        type(expected_revision) is not int or expected_revision<0):
        raise PermissionError("Exact native source catalog and district required")
    if (type(direction) is not str or
        not 1 <= len(direction.strip()) <= MAX_DIRECTION or
        any(ord(c)<32 and c not in "\n\t" for c in direction)):
        raise ValueError("Bounded plain text director intent required")
    if (type(model_id) is not str or not 1<=len(model_id)<=256 or
        not callable(getattr(model,"complete",None))):
        raise PermissionError("Only host-selected loaded model is usable")
    district=next((d for d in catalog["approved_districts"]
        if d.get("district_id")==district_id),None)
    if (district["revision"] if district else 0)!=expected_revision:
        raise RuntimeError("Native approved district head changed")
    facts={
        "project_id":project_id, "district_id":district_id,
        "expected_revision":expected_revision,
        "approved_source_buildings":[{
            "building_id":b["building_id"], "revision":b["revision"],
            "document_sha256":b["document_sha256"]}
            for b in catalog["source_buildings"][:24]],
        "approved_district_source_sha256":
            district["document_sha256"] if district else None,
        "director_intent":direction.strip(),
        "maximum_source_buildings":8,
        "no_source_write_or_approval":True,
    }
    prompt=_canonical(facts)
    if len(prompt)>MAX_PROMPT:
        raise ValueError("Native catalog prompt exceeds bounded model context")
    constrained=getattr(model,"complete_world_candidate",None)
    # The host-selected real GGUF writer can ask llama.cpp for strict JSON.
    # The returned text is STILL untrusted and passes identical _typed_params
    # and native OpenUSD geometry/source admission to all other providers.
    response=(constrained(SYSTEM,prompt.decode("ascii"),
                          _host_world_json_schema(catalog))
              if callable(constrained)
              else model.complete(SYSTEM,prompt.decode("ascii")))
    if (type(response) is not str or not 1<=len(response)<=MAX_REPLY):
        raise ValueError("No complete bounded model candidate")
    # Strict JSON only: no untrusted code fences, executable tool calls or
    # permissive substring extraction of a JSON object from other text.
    candidate=json.loads(response)
    params=_typed_params(candidate,catalog)
    receipt=getattr(model,"completion_receipt",None)
    digest=sha256(response.strip().encode("utf8")).hexdigest()
    if (type(receipt) is not dict or receipt.get("format")!=PROVIDER_FORMAT or
        receipt.get("selected_model_id")!=model_id or
        receipt.get("provider_reported_model_id")!=model_id or
        receipt.get("generated_text_sha256")!=digest or
        type(receipt.get("provider_reported_completion_tokens")) is not int or
        receipt["provider_reported_completion_tokens"]<1 or
        receipt.get("native_worker_authorized") is not False or
        receipt.get("provider_self_report_not_attestation") is not True):
        raise PermissionError("No verified host-observed completed provider response")
    return {
        "format":FORMAT,"status":"GENERATED_UNAPPROVED",
        "project_id":project_id,"district_id":district_id,
        "expected_revision":expected_revision,"params":params,
        "model_id":model_id,"model_completion_receipt":dict(receipt),
        "model_text_sha256":digest,
        "context_sha256":sha256(prompt).hexdigest(),
        "source_catalog_sha256":sha256(_canonical(facts["approved_source_buildings"])).hexdigest(),
        "host_source_validation_pending":True,
        "proposal_durable":False,
        "actor_takes_modified":False,"creative_approval_granted":False,
        "worker_authorization_granted":False,
    }
