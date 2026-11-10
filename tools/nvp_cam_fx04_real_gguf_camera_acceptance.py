"""Real disposable GGUF -> original ActorID-guided CAM-FX-04 proposal acceptance.

No fake model, forged provider receipt, automatic source edits, or OS approval.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from backend.nvp_idea_pipeline import LocalScriptModel
from backend.nvp_model_service import discover_models
from backend.nvp_wo6_verified_local_model import ProvenLocalModelWriter
from backend.nvp_cam_fx04_model_camera_candidate import (
    generate_camera_candidate, FORMAT as CAMERA_FORMAT)
from tools.nvp_wo6_07b_real_gguf_smoke import checked_path,sha256_file,_port

REPORT_FORMAT="nvp.cam_fx04.real_gguf_approved_original_scene_camera_draft.v1"


def run(model_path,server_path,report_path,consent):
    if consent!="I_APPROVE_DISPOSABLE_LOCAL_GGUF_TEST":
        raise PermissionError("Explicit consent for disposable GGUF acceptance required")
    model=checked_path(model_path,model=True)
    server=checked_path(server_path)
    report=Path(report_path)
    if not report.is_absolute() or report.is_symlink() or report.exists():
        raise PermissionError("Only a new absolute evidence receipt location")
    report.parent.mkdir(parents=True,exist_ok=True)
    original_sha=sha256_file(model)
    binary_sha=sha256_file(server)
    # Authentic actor and district sources from the independently accepted
    # OpenUSD/FilmIndex/PCM fixture, not model-invented actors or proxies.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tests"))
    from test_nvp_cam_fx03_04_native_director import OriginalCAMFX03SourceAndDurableAI
    fixture_class=OriginalCAMFX03SourceAndDurableAI
    fixture_class.setUpClass()
    fixture=fixture_class("test_local_model_source_contract_and_atomic_cancelled_late_response")
    proc=None
    try:
        fixture.setUp()
        source=fixture.guide(fixture.actor_id)
        before=fixture.index.list_objects(fixture.pid,kind="take")
        alias="nvp-camfx-real-"+secrets.token_hex(8)
        port=_port()
        with tempfile.TemporaryDirectory(prefix="nvp-camfx-real-gguf-") as t:
            temp=Path(t)
            log=temp/"model-server.log"
            try:
                with log.open("wb") as stream:
                    proc=subprocess.Popen([
                        str(server),"-m",str(model),"--host","127.0.0.1",
                        "--port",str(port),"-c","8192",
                        "--n-gpu-layers","0","--alias",alias
                    ],cwd=str(temp),stdin=subprocess.DEVNULL,
                       stdout=stream,stderr=subprocess.STDOUT,
                       start_new_session=(os.name!="nt"))
                deadline=time.monotonic()+180
                while time.monotonic()<deadline:
                    if proc.poll() is not None:
                        raise RuntimeError("Real llama-server exited before GGUF readiness")
                    found=discover_models(port)
                    if (found["state"]=="available" and
                            alias in {x["id"] for x in found["models"]}):
                        break
                    time.sleep(.4)
                else:
                    raise TimeoutError("Actual loaded GGUF model readiness not observed")
                writer=ProvenLocalModelWriter(LocalScriptModel(
                    endpoint=f"http://127.0.0.1:{port}/v1/chat/completions",
                    model_name=alias))
                started=time.monotonic()
                result=generate_camera_candidate(
                    fixture.spec,source,
                    direction=("Prepare a cinematic dolly along the actual original "
                               "ActorID while preserving the first/last source Film "
                               "Time ticks exactly and keeping camera near the "
                               "source framing. Never approve or apply."),
                    model_id=alias,writer=writer)
                elapsed=round((time.monotonic()-started)*1000)
                receipt=result["provider_completion_receipt"]
                if (result["format"]!=CAMERA_FORMAT or
                    not result["unapproved_draft_only"] or
                    result["os_authorization_granted"] or
                    result["model_weights_attested"] or
                    result["original_actor_takes_and_pcm_modified"] or
                    receipt["provider_reported_completion_tokens"]<1 or
                    not receipt["provider_self_report_not_attestation"] or
                    fixture.index.list_objects(fixture.pid,kind="take")!=before):
                    raise RuntimeError("Genuine camera GGUF output not source-safe/unapproved")
                if sha256_file(model)!=original_sha or sha256_file(server)!=binary_sha:
                    raise RuntimeError("GGUF or model server changed during actual generation")
                report.write_text(json.dumps({
                    "format":REPORT_FORMAT,
                    "status":"REAL_GGUF_CAMERA_PROPOSAL_GENERATED_UNAPPROVED",
                    "model_id":alias,
                    "gguf_file_sha256":original_sha,
                    "gguf_file_size_bytes":model.stat().st_size,
                    "llama_server_executable_sha256":binary_sha,
                    "actual_model_tokens":receipt["provider_reported_completion_tokens"],
                    "source_guidance_sha256":source["guidance_sha256"],
                    "source_world_take_sha256":result["source_original_take_sha256"],
                    "model_generated_text_sha256":result["model_text_sha256"],
                    "native_camera_rail_candidate_sha256":
                        result["provider_completion_receipt"]["generated_text_sha256"],
                    "director_camera_rail_unapproved":True,
                    "original_actor_pcm_and_takes_unchanged":True,
                    "native_worker_authorized":False,
                    "human_director_approval":False,
                    "production_model_quality_accepted":False,
                    "representative_7b_plus_model_tested":False,
                    "elapsed_model_ms":elapsed
                },sort_keys=True,indent=2),"utf8")
                return result
            finally:
                if proc is not None and proc.poll() is None:
                    if os.name=="nt":
                        proc.terminate()
                    else:
                        os.killpg(proc.pid,signal.SIGTERM)
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        if os.name=="nt":
                            proc.kill()
                        else:
                            os.killpg(proc.pid,signal.SIGKILL)
                        proc.wait(timeout=15)
                if log.is_file() and not log.is_symlink():
                    shutil.copyfile(log,report.parent/"camera_gguf_server_diagnostic.log")
    finally:
        fixture.doCleanups()
        fixture_class.tearDownClass()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model",required=True)
    parser.add_argument("--llama-server",required=True)
    parser.add_argument("--report",required=True)
    parser.add_argument("--consent",required=True)
    a=parser.parse_args(argv)
    result=run(a.model,a.llama_server,a.report,a.consent)
    print("NVP_CAMFX04_REAL_GGUF_UNAPPROVED_SOURCE_CAMERA_PASSED="+
          result["model_text_sha256"],flush=True)


if __name__=="__main__":
    main()
