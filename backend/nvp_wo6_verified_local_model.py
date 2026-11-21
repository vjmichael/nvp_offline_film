"""WO6-07B: bounded loopback local-model completion with provider evidence.

Provider-reported model ID and token accounting are evidence of a real
completed provider RESPONSE, NOT cryptographic proof of neural inference
or the backing GGUF. The separate native acceptance tool hashes the actual
model file and llama-server executable to bind an observed GGUF test.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import time
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener
from urllib.parse import urlsplit

from backend.nvp_idea_pipeline import LocalModelUnavailable
from backend.nvp_model_service import writer_for

FORMAT="nvp.wo6.local_model_provider_completion.v1"
MAX_RESPONSE_BYTES=128000
MAX_PROMPT_BYTES=36000
MAX_GENERATED_CHARS=5000
MAX_MODEL_TOKENS=600


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None


class ProvenLocalModelWriter:
    """Host-created wrapper; its URL must come from existing writer_for()."""

    def __init__(self,provider):
        endpoint=getattr(provider,"endpoint",None)
        model_name=getattr(provider,"model_name",None)
        # Never accept a direct browser-selected URL or client-supplied
        # constructor string: only an existing model_service-selected writer.
        from backend.nvp_idea_pipeline import LocalScriptModel
        if not isinstance(provider,LocalScriptModel):
            raise TypeError("Trusted selected local script writer required")
        if not isinstance(endpoint,str):
            raise PermissionError("Only an already-authorized loopback writer may run")
        try:
            url=urlsplit(endpoint)
            if (url.scheme!="http" or url.hostname not in
                    ("127.0.0.1","localhost","::1") or
                    type(url.port) is not int or not 1<=url.port<=65535 or
                    url.username is not None or url.password is not None or
                    url.query or url.fragment or
                    url.path!="/v1/chat/completions"):
                raise ValueError("Untrusted model HTTP destination")
        except ValueError as exc:
            raise PermissionError("Only strict local model chat endpoints are allowed") from exc
        if (not isinstance(model_name,str) or not 1<=len(model_name)<=256):
            raise ValueError("Exact selected model required")
        self.endpoint=endpoint
        self.model_name=model_name
        self.completion_receipt=None

    def complete(self,system,user):
        return self._complete_bounded(system,user)

    def complete_world_candidate(self,system,user,schema):
        """Opt-in reviewed JSON-schema constraint for native original worlds.

        This restricts model *output format*, not world approval, source
        identity, runtime permission or downstream USD geometry validation.
        """
        if (type(schema) is not dict or len(json.dumps(
                schema,sort_keys=True,separators=(",",":"),
                allow_nan=False))>15000):
            raise ValueError("Only bounded host-owned original-world schema")
        return self._complete_bounded(system,user,schema)

    def complete_camera_candidate(self,system,user,schema):
        """Host-reviewed camera JSON grammar, not source/model authorization."""
        if (type(schema) is not dict or len(json.dumps(
                schema,sort_keys=True,separators=(",",":"),
                allow_nan=False))>12000):
            raise ValueError("Only bounded native source camera output schema")
        return self._complete_bounded(system,user,schema,
                                      schema_name="nvp_original_camera_rail")

    def _complete_bounded(self,system,user,schema=None,*,schema_name="nvp_original_world_candidate"):
        if (type(system) is not str or type(user) is not str or
                not 1<=len(system)<=4000 or
                not 1<=len(user.encode("utf-8"))<=MAX_PROMPT_BYTES):
            raise ValueError("Only bounded system and verified source prompt accepted")
        self.completion_receipt=None
        body_request={
            "model":self.model_name,
            "messages":[
                {"role":"system","content":system},
                {"role":"user","content":user}
            ],
            "temperature":0.2,
            "max_tokens":MAX_MODEL_TOKENS,
            "stream":False
        }
        if schema is not None:
            body_request["response_format"]={
                "type":"json_schema",
                "json_schema":{
                    "name":schema_name,
                    "strict":True,
                    "schema":schema,
                },
            }
        request_bytes=json.dumps(
            body_request,ensure_ascii=True,allow_nan=False).encode("ascii")
        request=Request(self.endpoint,request_bytes,{
            "Content-Type":"application/json",
            "Accept":"application/json"},method="POST")
        started=time.monotonic()
        try:
            with build_opener(ProxyHandler({}),_NoRedirect()).open(
                    request,timeout=90) as response:
                if getattr(response,"status",200)!=200:
                    raise ValueError("Local model returned unexpected HTTP status")
                raw=response.read(MAX_RESPONSE_BYTES+1)
                if len(raw)>MAX_RESPONSE_BYTES:
                    raise ValueError("Local model response exceeded bounded limit")
            body=json.loads(raw)
            if (not isinstance(body,dict) or
                    body.get("model")!=self.model_name or
                    not isinstance(body.get("choices"),list) or
                    len(body["choices"])!=1):
                raise ValueError("Completed model identity or choice cardinality differs")
            choice=body["choices"][0]
            if (not isinstance(choice,dict) or
                    choice.get("finish_reason")!="stop" or
                    not isinstance(choice.get("message"),dict)):
                raise ValueError("Local model did not finish normally")
            generated=choice["message"].get("content")
            if (type(generated) is not str or not generated.strip() or
                    len(generated)>MAX_GENERATED_CHARS or
                    any(ord(c)<32 and c not in "\t\n" for c in generated)):
                raise ValueError("Local model reply is empty or unsafe")
            usage=body.get("usage")
            if not isinstance(usage,dict):
                raise ValueError("Local model supplied no completion token usage")
            prompt_tokens=usage.get("prompt_tokens")
            completion_tokens=usage.get("completion_tokens")
            if (type(prompt_tokens) is not int or
                    not 1<=prompt_tokens<=250000 or
                    type(completion_tokens) is not int or
                    not 1<=completion_tokens<=MAX_MODEL_TOKENS):
                raise ValueError("Local model did not report genuine positive token usage")
            # Provider-reported counts can be forged. The receipt labels this.
            trimmed=generated.strip()
            result={
                "format":FORMAT,"selected_model_id":self.model_name,
                "provider_reported_model_id":body["model"],
                "provider_completion_finish_reason":"stop",
                "provider_reported_prompt_tokens":prompt_tokens,
                "provider_reported_completion_tokens":completion_tokens,
                "request_sha256":sha256(request_bytes).hexdigest(),
                "response_sha256":sha256(raw).hexdigest(),
                "generated_text_sha256":sha256(trimmed.encode("utf8")).hexdigest(),
                "elapsed_wall_ms":max(0,round((time.monotonic()-started)*1000)),
                "model_weights_sha256_verified":False,
                "model_binary_sha256_verified":False,
                "provider_self_report_not_attestation":True,
                "native_worker_authorized":False,
                "film_delivered":False,
            }
            self.completion_receipt=result
            return trimmed
        except (OSError,ValueError,TypeError,KeyError,IndexError,
                UnicodeError) as exc:
            # This is a host-internal exception; the desktop bridge
            # already hides it and exposes a bounded error category.
            raise LocalModelUnavailable(
                "Loopback provider did not return a valid completed generation") from exc


def verified_writer_for(model_id):
    """Reuse NVP's existing explicit model discovery/loopback enforcement."""
    return ProvenLocalModelWriter(writer_for(model_id))
