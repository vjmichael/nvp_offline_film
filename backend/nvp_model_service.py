"""Model discovery for optional, loopback-only OpenAI-compatible writer servers.

NVP never downloads models or claims a GGUF is loaded merely from its filename.
The /v1/models endpoint advertises what the connected local server reports;
only a completed generation proves that a particular model produced text.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.error import URLError, HTTPError

from backend.nvp_idea_pipeline import local_llm_endpoint, LocalModelUnavailable, LocalScriptModel

MAX_MODEL_LIST_BYTES = 256_000
MAX_MODEL_ID_LEN = 256


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def model_family(model_id: str) -> str:
    """Hints for display only: never used for inference routing or capabilities."""
    normalized = model_id.casefold().replace("_", "-")
    if "gemma" in normalized and "4" in normalized and "31b" in normalized:
        return "Gemma 4 31B"
    if "qwen" in normalized and "3.8" in normalized and "27b" in normalized:
        return "Qwen3.8 27B"
    if "qwen" in normalized and "3.6" in normalized and "35b" in normalized:
        return "Qwen3.6 35B-A3B (verify quantization)"
    return "Other local model"


def _models_url(chat_url: str) -> str:
    endpoint = urlsplit(chat_url)
    return f"{endpoint.scheme}://{endpoint.netloc}/v1/models"


def configured_endpoint(port: int | None = None) -> str | None:
    if port is None:
        return local_llm_endpoint()
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("Select a valid local model server port (1024–65535)")
    return f"http://127.0.0.1:{port}/v1/chat/completions"


def discover_models(port: int | None = None) -> dict:
    """Non-throwing status for UI; no proxy, redirect, auth, or remote calls."""
    try:
        url = configured_endpoint(port)
    except ValueError:
        return {"state": "invalid_configuration", "models": [],
                "message": "Invalid NVP_LLM_URL: use a local loopback /v1/chat/completions endpoint"}
    if not url:
        return {"state": "not_configured", "models": [],
                "message": "Set NVP_LLM_URL to the local model server in the NVP launch environment"}
    request = Request(_models_url(url), headers={"Accept": "application/json"})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=3) as response:
            if getattr(response, "status", 200) != 200:
                raise ValueError("Model server did not return HTTP 200")
            raw = response.read(MAX_MODEL_LIST_BYTES + 1)
            if len(raw) > MAX_MODEL_LIST_BYTES:
                raise ValueError("Model list exceeded size limit")
        payload = json.loads(raw.decode("utf-8"))
        entries = payload["data"]
        if not isinstance(entries, list):
            raise ValueError("Model list does not contain a data array")
        seen = set()
        models = []
        for entry in entries[:100]:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            model_id = entry["id"]
            if (not model_id or len(model_id) > MAX_MODEL_ID_LEN
                    or any(ord(c) < 32 for c in model_id) or model_id in seen):
                continue
            seen.add(model_id)
            models.append({"id": model_id, "family_hint": model_family(model_id)})
        return {"state": "available" if models else "empty", "models": models,
                "message": "Models reported by the local server (generation readiness not yet verified)"}
    except (OSError, HTTPError, URLError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        # Avoid leaking system/user environment or uncontrolled server responses.
        return {"state": "unavailable", "models": [],
                "message": "Local model server is unreachable or returned an invalid model list"}


def writer_for(model_id: str, port: int | None = None) -> LocalScriptModel:
    if not isinstance(model_id, str) or not model_id or len(model_id) > MAX_MODEL_ID_LEN:
        raise ValueError("Select a valid model from the local server")
    models = discover_models(port)
    if models["state"] != "available":
        raise LocalModelUnavailable(models["message"])
    if model_id not in {m["id"] for m in models["models"]}:
        raise ValueError("The selected model is not reported by the local server; refresh the model list")
    return LocalScriptModel(endpoint=configured_endpoint(port), model_name=model_id)
