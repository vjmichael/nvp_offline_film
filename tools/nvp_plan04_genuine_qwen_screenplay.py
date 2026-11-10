"""Genuine Qwen GGUF against an ORIGINAL ephemeral screenplay, no fake completion.

A separately launched native llama-server (CI or creator's local Windows PC)
must already run a PINNED GGUF on loopback. This calls the real NVP
ProvenLocalModelWriter for EACH authored scene, checks exact source identity,
receives provider response/token receipts, and never approves assets/film.
The runner (not the provider) must independently verify and record GGUF and
llama-server SHA256 and the exact process invocation before claiming binding.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from backend.nvp_model_service import writer_for
from backend.nvp_scene_library import SceneLibrary
from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_wo6_verified_local_model import ProvenLocalModelWriter

SCREENPLAY=(
    "INT. KITCHEN - MORNING\n\n"
    "MARA places a brass key next to a blue lantern.\n\n"
    "MARA\nThe door is locked.\n\n"
    "EXT. GARDEN - NIGHT\n\n"
    "MARA carries the blue lantern past a stone gate.\n\n"
    "MARA\nI can see the path.\n"
)


def sha_file(name):
    if not name:return None
    p=Path(name).resolve(strict=True)
    if not p.is_file():raise ValueError("Verified model/binary must be a real file")
    h=hashlib.sha256()
    with p.open("rb") as f:
        while part:=f.read(4*1024*1024):
            h.update(part)
    return {"sha256":h.hexdigest(),"size":p.stat().st_size,
            "file_name":p.name}


def run(model_id,port,report,*,gguf=None,server_binary=None):
    path=Path(report)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("Fresh absolute report file required")
    model=sha_file(gguf)
    binary=sha_file(server_binary)
    with tempfile.TemporaryDirectory(prefix="nvp-plan04-real-qwen-") as tmp:
        studio=Studio(Path(tmp)/"film.sqlite3")
        project=studio.create_project("The Lantern Key","Mara must open a locked door")
        project=studio.save_screenplay(project["id"],SCREENPLAY,project["revision"])
        service=SceneLibrary(studio)
        before=service.snapshot(project["id"])
        writer=ProvenLocalModelWriter(writer_for(model_id,port))
        result=service.propose_movie_breakdown(
            project["id"],before["project_revision"],writer=writer)
        after=service.snapshot(project["id"])
        if after!=before or result["scene_count"]!=2:
            raise RuntimeError("Qwen output mutated or lost the source screenplay")
        if any(result.get(k) for k in (
                "creator_approval_granted","original_source_modified",
                "native_render_authorized","final_film_published")):
            raise RuntimeError("AI must not approve film or native execution")
        got=result["scenes"]
        if [p["scene_id"] for p in got]!=[p["scene_id"] for p in before["scenes"]]:
            raise RuntimeError("Qwen proposed unverified new scene identities")
        if any(not p["suggestions"]["actors"] or not p["suggestions"]["props"]
               or not p["suggestions"]["locations"] for p in got):
            raise RuntimeError("Actual Qwen did not propose all three categories for every scene")
        if any(p["provider_completion_receipt"] is None or
               p["provider_completion_receipt"][
                   "provider_reported_completion_tokens"]<=0 or
               p["provider_completion_receipt"]["selected_model_id"]!=model_id
               for p in got):
            raise RuntimeError("Genuine Qwen completion evidence missing or wrong model")
        if StoryBible(studio).list_entities(project["id"]):
            raise RuntimeError("AI proposal created an unapproved casting or prop")
        observed={
            "format":"nvp.plan04.genuine_qwen_frozen_screenplay.v1",
            "status":"ACTUAL_QWEN_SCREENPLAY_BREAKDOWN_OBSERVED",
            "observed_utc":datetime.now(timezone.utc).isoformat(),
            "selected_provider_model":model_id,
            "model_gguf_file_sha256":model,
            "llama_server_binary_sha256":binary,
            "process_to_model_binding_verified_by_this_script":False,
            "runner_must_attest_exact_process_launch":True,
            "screenplay_sha256":before["screenplay_sha256"],
            "scene_count":2,
            "scenes":[{
                "heading":p["screenplay_heading"],
                "id":p["scene_id"],
                "scene_sha256":p["source_scene_sha256"],
                "actor_suggestions":p["suggestions"]["actors"],
                "location_suggestions":p["suggestions"]["locations"],
                "prop_suggestions":p["suggestions"]["props"],
                "provider_receipt":p["provider_completion_receipt"],
            } for p in got],
            "screenplay_unchanged_after_model_generation":True,
            "approved_scene_assets_created":False,
            "native_render_started":False,
            "creator_human_approval_witnessed":False,
        }
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(observed,sort_keys=True,indent=2),encoding="utf8")
        print("NVP_PLAN04_GENUINE_QWEN_SCREENPLAY_PROPOSALS_PASS",flush=True)
        return observed


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--model-id",required=True)
    p.add_argument("--port",type=int,required=True)
    p.add_argument("--report",required=True)
    p.add_argument("--gguf")
    p.add_argument("--server-binary")
    a=p.parse_args(argv)
    return run(a.model_id,a.port,a.report,
               gguf=a.gguf,server_binary=a.server_binary)


if __name__=="__main__":
    main()
