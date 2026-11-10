"""Manual physical Qwen/local GGUF scene-breakdown acceptance.

Connect an already running local llama.cpp server. NVP does not start a new
model or use a remote URL. A completed provider response and token counts are
not proof of the actual model weights; optional source GGUF + binary hashes
are separately recorded and never treated as process binding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from datetime import datetime,timezone

from backend.nvp_studio import Studio
from backend.nvp_scene_library import SceneLibrary
from backend.nvp_model_service import writer_for
from backend.nvp_wo6_verified_local_model import ProvenLocalModelWriter


def digest(path):
    p=Path(path).resolve(strict=True)
    if not p.is_file():
        raise ValueError("Native test path is not a file")
    h=hashlib.sha256()
    with p.open("rb") as f:
        while b:=f.read(4*1024*1024):
            h.update(b)
    return {"path":str(p),"sha256":h.hexdigest(),"bytes":p.stat().st_size}


def run(model_id,port,report,gguf=None,model_server_binary=None):
    if not isinstance(model_id,str) or not model_id.strip():
        raise ValueError("Exact selected local model ID required")
    report=Path(report)
    if not report.is_absolute() or report.is_symlink() or report.exists():
        raise ValueError("Use a new absolute evidence file outside existing projects")
    # Never read or alter the creator's project. The new source is unapproved
    # and deleted after completion, only a summary of metadata survives.
    with tempfile.TemporaryDirectory(prefix="nvp-plan03-genuine-model-") as tmp:
        studio=Studio(Path(tmp)/"nvp_studio.sqlite3")
        p=studio.create_project("Local model breakdown acceptance",
                                "A dog eats food on a kitchen floor")
        text=("INT. KITCHEN - MORNING\n\n"
              "A golden retriever eats food from a ceramic bowl.\n\n"
              "OWNER\nPlease finish your breakfast.")
        p=studio.save_screenplay(p["id"],text,p["revision"])
        service=SceneLibrary(studio)
        snapshot=service.snapshot(p["id"])
        scene=snapshot["scenes"][0]
        writer=ProvenLocalModelWriter(writer_for(model_id,port))
        generated=service.propose_ai_breakdown(
            p["id"],scene["scene_id"],p["revision"],writer=writer)
        receipt=generated["provider_completion_receipt"]
        if (not receipt or not generated["provider_response_observed"] or
                receipt["selected_model_id"]!=model_id or
                receipt["provider_reported_model_id"]!=model_id or
                receipt["provider_reported_completion_tokens"]<=0):
            raise RuntimeError("No independently observed completed local provider response")
        if (generated["creator_approval_granted"] or
                generated["native_tools_invoked"] or
                service.snapshot(p["id"])!=snapshot):
            raise RuntimeError("AI proposal mutated screenplay or granted source permission")
        source_p=studio.get_project(p["id"])
        if source_p["screenplay"]!=text:
            raise RuntimeError("Model-generated proposal altered original creator writing")
        # Only sanitized bounded model strings and proof metadata, not a
        # full user screenplay or private local provider URL, are recorded.
        evidence={
            "format":"nvp.plan03.real_local_scene_breakdown_observation.v1",
            "status":"PROVIDER_COMPLETION_OBSERVED_UNAPPROVED",
            "observed_utc":datetime.now(timezone.utc).isoformat(),
            "source_scene_sha256":scene["source_scene_sha256"],
            "source_screenplay_unchanged":True,
            "local_loopback_only":True,
            "provider":receipt,
            "proposal":generated["suggestions"],
            "model_file_hash_observed":digest(gguf) if gguf else None,
            "server_binary_hash_observed":digest(model_server_binary)
                if model_server_binary else None,
            "actual_process_model_file_binding_independently_verified":False,
            "creator_action_required":True,
            "original_take_published":False,
            "rendering_authorized":False,
        }
        report.parent.mkdir(parents=True,exist_ok=True)
        with report.open("x",encoding="utf8") as f:
            json.dump(evidence,f,indent=2,sort_keys=True)
        return evidence


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--model-id",required=True)
    p.add_argument("--port",type=int,required=True)
    p.add_argument("--evidence",required=True)
    p.add_argument("--gguf")
    p.add_argument("--model-server-binary")
    args=p.parse_args(argv)
    result=run(args.model_id,args.port,args.evidence,args.gguf,args.model_server_binary)
    print(result["status"])
    print("EVIDENCE="+args.evidence)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
