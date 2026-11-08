"""WO6-07A: source-grounded *untrusted* local director suggestion.

A real local model may suggest changes to a frozen FilmIndex Take. The
model can neither invoke tools nor grant execution/creative permissions.
The host alone reopens the actual USD Take and verifies SHA, Film Time
and accepted canon. The returned text is a draft, not a specification.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_wo6_scene_context import assemble_film_crew_context

FORMAT="nvp.wo6.untrusted_model_director_suggestion.v1"
MAX_CREATIVE_CHARS=1200
MAX_CONTEXT_BYTES=32000
MAX_MODEL_REPLY_CHARS=5000
_ALLOWED_TICK=re.compile(r"(?:0|[1-9][0-9]{0,14})\Z")

SYSTEM=(
    "You are a FILM DIRECTOR'S NON-AUTHORITATIVE ADVISER, not an operator. "
    "Use only supplied verified FilmIndex, OpenUSD and Film Time evidence. "
    "A character name does not prove a USD actor identity. "
    "Clearly distinguish observed fact, omission, assumption and suggestion. "
    "Offer one specific visual/sound/performance change for the director to "
    "consider. Never claim to render, save, approve, execute, change original "
    "source, read unseen material, approve a final film or certify a DCP. "
    "Your output is plain descriptive text ONLY. No JSON tool calls, "
    "terminal commands, authorization tokens, URLs or approval instructions."
)


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def director_model_suggestion(index:FilmIndex, project_id, take_id,
        take_sha256, film_tick, direction, model_id, model):
    """Run one actual host-provided model completion against verified context.

    The model argument is a trusted host-adapter object, NEVER a native
    browser/model-selected URL, executable or imported Python module.
    """
    if not isinstance(index,FilmIndex):
        raise TypeError("Only the existing original FilmIndex is supported")
    _require_pid(project_id)
    _id(take_id,"immutable Digital Take")
    _sha(take_sha256)
    if (type(film_tick) is not str or not _ALLOWED_TICK.fullmatch(film_tick)):
        raise ValueError("Exact safe Film Time tick text required")
    if (type(direction) is not str or not 1<=len(direction.strip())<=MAX_CREATIVE_CHARS
            or any(ord(c)<32 and c not in "\n\t" for c in direction)):
        raise ValueError("A bounded plain-language direction is required")
    if (type(model_id) is not str or not 1<=len(model_id)<=256 or
            any(ord(c)<32 for c in model_id)):
        raise ValueError("Invalid chosen local model ID")
    if not callable(getattr(model,"complete",None)):
        raise TypeError("Host-owned local model completion adapter required")
    take=index.read_revision(project_id,take_id,1)
    if (take["kind"]!="take" or take["document_sha256"]!=take_sha256 or
            take["data"].get("frozen") is not True):
        raise PermissionError("Local proposal requires the exact verified frozen Take")
    context=assemble_film_crew_context(
        index,project_id,take_id,1,int(film_tick),
        max_prims=16,max_events=12)
    if (context["source_take"]["document_sha256"]!=take_sha256 or
            context["film_time_tick"]!=int(film_tick) or
            context.get("authorization_provided") is not False or
            context.get("side_effects_performed") is not False):
        raise PermissionError("Native source context is not an unprivileged verified read")
    facts={
        "take":context["source_take"],
        "film_time_tick":context["film_time_tick"],
        "original_scene_id":context["scene_id"],
        "scene_document_sha256":context["scene_document_sha256"],
        "source_heads":context["source_heads"],
        "historical_take_not_current_scene":
            context["historical_take_not_current_scene"],
        "visible_scene_prims":context["visible_scene_prims"],
        "scene_prim_count_omitted":context["scene_prim_count_omitted"],
        "active_events":context["active_events"],
        "active_events_truncated":context["active_events_truncated"],
        "sound_events":context["sound_events"],
        "sound_events_omitted":context["sound_events_omitted"],
        "approved_story_facts":context["approved_story_facts"],
        "approved_story_facts_omitted_at_least":
            context["approved_story_facts_omitted_at_least"],
        "actor_binding_verified":
            context["screenplay_to_usd_actor_identity_verified"],
        "verified_source_context_sha256":context["context_sha256"],
        "director_request":direction.strip(),
    }
    prompt=_canonical(facts)
    if len(prompt)>MAX_CONTEXT_BYTES:
        raise RuntimeError("Verified source packet too large; no silent fact truncation")
    # The original hashes are rechecked before and after the model returns.
    source_prompt_sha=sha256(prompt).hexdigest()
    candidate=model.complete(SYSTEM,prompt.decode("ascii"))
    if (type(candidate) is not str or not candidate.strip() or
            len(candidate)>MAX_MODEL_REPLY_CHARS or
            any(ord(c)<32 and c not in "\n\t" for c in candidate)):
        raise ValueError("Model response is not a bounded plain-text suggestion")
    if index.read_revision(project_id,take_id,1)["document_sha256"]!=take_sha256:
        raise PermissionError("Source Take changed while model proposed a change")
    provider_receipt=getattr(model,"completion_receipt",None)
    if provider_receipt is not None:
        from backend.nvp_wo6_verified_local_model import FORMAT as PROVIDER_FORMAT
        if (type(provider_receipt) is not dict or
                provider_receipt.get("format")!=PROVIDER_FORMAT or
                provider_receipt.get("selected_model_id")!=model_id or
                provider_receipt.get("provider_reported_model_id")!=model_id or
                provider_receipt.get("generated_text_sha256")!=
                    sha256(candidate.strip().encode("utf8")).hexdigest() or
                provider_receipt.get("provider_reported_completion_tokens",0)<1 or
                provider_receipt.get("native_worker_authorized") is not False):
            raise PermissionError("Local generation evidence does not match source proposal")
    result={
        "format":FORMAT,
        "status":"LOCAL_MODEL_TEXT_PROPOSED_NOT_APPROVED",
        "project_id":project_id,
        "take_id":take_id,"take_sha256":take_sha256,
        "film_time_tick":film_tick,
        "model_id_reported_by_local_host":model_id,
        "provider_completion_receipt":provider_receipt,
        "provider_completion_observed":provider_receipt is not None,
        "provider_report_self_reported_not_verified_weights":True,
        "verified_source_context_sha256":context["context_sha256"],
        "context_packet_sha256":source_prompt_sha,
        "model_text_sha256":sha256(candidate.encode("utf8")).hexdigest(),
        "suggestion_text":candidate.strip(),
        "model_text_is_untrusted":True,
        "source_context_verified":True,
        "historical_take_not_current_scene":
            context["historical_take_not_current_scene"],
        "creative_approval_granted":False,
        "native_worker_authorized":False,
        "tool_executed":False,
        "source_modified":False,
        "new_take_created":False,
        "film_delivered":False,
        "human_review_required":True,
    }
    return result
