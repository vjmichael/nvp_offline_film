"""PLAN-02-C: independently witnessed real GGUF/llama-server camera advice.

THIS executable test is separate from mock provider contract tests. It loads
an actual local GGUF with a real llama.cpp server, hashes both files before
and after inference, and inspects completed token/response receipts. It
never persists an approved rail or edits original scene/audio/ActorID data.
This is a disposable native CI/creator acceptance tool, not browser IPC.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time

from backend.nvp_idea_pipeline import LocalScriptModel
from backend.nvp_model_service import discover_models
from backend.nvp_wo6_verified_local_model import ProvenLocalModelWriter
from backend.nvp_plan02c_model_advice import generate_source_camera_advice

REPORT="nvp.plan02c.real_gguf_original_source_camera_advice_evidence.v1"
APPROVAL="I_APPROVE_DISPOSABLE_LOCAL_GGUF_TEST"

# Validation stays fully fail-closed. These are MODEL-ORIGIN candidate
# rejections that can justify a NEW inference attempt; no output is
# normalized, repaired, approved or quietly published.
RETRYABLE_MODEL_ERRORS=frozenset({
    "AI cannot retime frozen source Film Time boundaries",
    "Camera look-at may not coincide with its position",
    "Camera rail would exceed bounded travel velocity",
    "Camera rail would exceed bounded vector acceleration",
    "Cubic overshoot escapes camera world bounds",
    "Rail Film Time must strictly increase",
})

def retryable_model_rejection(error):
    return type(error) is ValueError and str(error) in RETRYABLE_MODEL_ERRORS



def digest(path):
    hashed=sha256()
    with path.open("rb") as stream:
        while block:=stream.read(1024*1024):
            hashed.update(block)
    return hashed.hexdigest()


def checked_path(text):
    file=Path(text)
    if not file.is_absolute() or file.is_symlink() or not file.is_file():
        raise PermissionError("Exact absolute native GGUF/server file required")
    return file.resolve(strict=True)


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1",0))
        return listener.getsockname()[1]


def run(model_path,server_path,report_path,consent):
    if consent!=APPROVAL:
        raise PermissionError("Explicit disposable GGUF execution consent required")
    model=checked_path(model_path)
    server=checked_path(server_path)
    report=Path(report_path)
    if (not report.is_absolute() or report.is_symlink() or report.exists()):
        raise PermissionError("Write a NEW absolute real GGUF evidence report")
    report.parent.mkdir(parents=True,exist_ok=True)
    if model.open("rb").read(4)!=b"GGUF":
        raise ValueError("Selected real local model is not GGUF")
    model_sha=digest(model)
    binary_sha=digest(server)
    # Test uses the exact canonical source Take/camera published in the
    # native CI fixture, NOT a legacy 01M source bank or fake model text.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tests"))
    from test_nvp_plan02c_native_camera_ai import CanonicalDirectorRailTests
    fixture=CanonicalDirectorRailTests(
        "test_contract_only_model_advice_stays_unapproved_without_publishing")
    fixture.setUp()
    process=None
    try:
        source_take=fixture.index.read_revision(
            fixture.pid,fixture.spec["take_id"],1)["document_sha256"]
        sound_before=fixture.sound.read(
            fixture.pid,"mic_signal",1,0,1000)
        before=fixture.index.list_objects(fixture.pid,kind="presentation")
        alias="nvp-plan02c-real-"+secrets.token_hex(6)
        port=free_port()
        with tempfile.TemporaryDirectory(prefix="nvp-plan02c-real-gguf-") as temp:
            logfile=Path(temp)/"llama-server.log"
            with logfile.open("wb") as log:
                process=subprocess.Popen([
                    str(server),"-m",str(model),"--host","127.0.0.1",
                    "--port",str(port),"-c","8192",
                    "--n-gpu-layers","0","--alias",alias],
                    cwd=temp,stdin=subprocess.DEVNULL,stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=os.name!="nt")
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise RuntimeError("Actual llama-server exited before GGUF model loaded")
                found=discover_models(port)
                if found["state"]=="available" and alias in {
                        x["id"] for x in found["models"]}:
                    break
                time.sleep(.4)
            else:
                raise TimeoutError("No real selected loaded GGUF observed")
            writer=ProvenLocalModelWriter(
                LocalScriptModel(
                    endpoint=f"http://127.0.0.1:{port}/v1/chat/completions",
                    model_name=alias))
            rejected=[]
            result=None
            start=fixture.spec["film_start_tick"]
            end=fixture.spec["film_end_tick"]
            for attempt in range(1,4):
                try:
                    result=generate_source_camera_advice(
                        fixture.service,fixture.pid,fixture.spec,
                        direction=(
                            "Propose a TWO-node original source camera dolly. "
                            "Keep each node at the exact original Film Time. "
                            f"First tick integer {start}, final tick integer {end}. "
                            "Copy these integer numbers digit for digit, no rounding. "
                            "Keep two source-bounded finite positions and targets. "
                            "NEVER place a camera at its own target: each position "
                            "must be at least three metres from its target. "
                            "Use both node targets [0, 3, 0] and both camera "
                            "positions [0, 0, 0] or [0.5, 0, 0] as a safe "
                            "source-verified example. Move gradually, not fast. "
                            "Use exactly the allowed typed node fields. "
                            f"Genuine unapproved source advice attempt {attempt}."),
                        model_id=alias,writer=writer)
                    break
                except ValueError as exc:
                    # A retimed/unsafe original camera candidate must never
                    # be silently repaired. Only known model-origin
                    # validation failures may request a FRESH inference
                    # with a separate provider receipt. No approval is
                    # derived from any failed attempt.
                    if not retryable_model_rejection(exc):
                        raise
                    receipt=writer.completion_receipt
                    if (type(receipt) is not dict or
                            type(receipt.get("provider_reported_completion_tokens")) is not int or
                            receipt["provider_reported_completion_tokens"]<1):
                        raise
                    rejected.append({
                        "attempt":attempt,"reason":str(exc),
                        "provider_completion":receipt})
            if result is None:
                raise RuntimeError("All genuine GGUF attempts failed strict source-safe camera validation")
            receipt=result["provider_completion_receipt"]
            if (result["status"]!="UNAPPROVED_SOURCE_CAMERA_ADVICE" or
                result["human_authorization_granted"] is not False or
                result["rail_published"] is not False or
                result["original_pcm_and_take_modified"] is not False or
                receipt["provider_reported_completion_tokens"]<1 or
                not receipt["provider_self_report_not_attestation"] or
                fixture.index.read_revision(
                    fixture.pid,fixture.spec["take_id"],1
                )["document_sha256"]!=source_take or
                fixture.index.list_objects(
                    fixture.pid,kind="presentation")!=before or
                fixture.sound.read(fixture.pid,"mic_signal",1,0,1000)!=sound_before):
                raise RuntimeError("Real GGUF response changed original or forged authority")
            if digest(model)!=model_sha or digest(server)!=binary_sha:
                raise RuntimeError("Real GGUF or llama-server executable changed")
            payload={
                "format":REPORT,
                "status":"REAL_HASHED_GGUF_GENERATED_UNAPPROVED_SOURCE_CAMERA_ADVICE",
                "gguf_file_sha256":model_sha,
                "llama_server_file_sha256":binary_sha,
                "model_file_bytes":model.stat().st_size,
                "model_id":alias,
                "source_take_sha256":source_take,
                "original_model_response_sha256":receipt["response_sha256"],
                "verified_local_model_prompt_tokens":
                    receipt["provider_reported_prompt_tokens"],
                "provider_reported_completion_tokens":
                    receipt["provider_reported_completion_tokens"],
                "source_guidance_sha256":
                    result["original_scene_observation_sha256"],
                "native_original_camera_advice_sha256":
                    result["proposed_spec_sha256"],
                "rejected_retimitings":rejected,
                "source_original_pcm_unchanged":True,
                "human_publication_approval":False,
                "native_renderer_worker_authorized":False,
                "representative_7b_model_tested":False,
                "physical_director_approval_tested":False}
            report.write_text(json.dumps(payload,sort_keys=True,indent=2),"utf8")
            print("NVP_PLAN02C_ACTUAL_GGUF_SOURCE_CAMERA_UNAPPROVED_PASS="+
                  result["proposed_spec_sha256"],flush=True)
            return payload
    finally:
        if process is not None and process.poll() is None:
            if os.name!="nt":
                os.killpg(process.pid,signal.SIGTERM)
            else:process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                if os.name!="nt":os.killpg(process.pid,signal.SIGKILL)
                else:process.kill()
                process.wait(timeout=15)
        fixture.doCleanups()


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model",required=True)
    p.add_argument("--llama-server",required=True)
    p.add_argument("--report",required=True)
    p.add_argument("--consent",required=True)
    args=p.parse_args()
    run(args.model,args.llama_server,args.report,args.consent)
