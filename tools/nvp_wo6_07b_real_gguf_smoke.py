"""WO6-07B opt-in REAL GGUF / llama-server / FilmIndex acceptance.

Run in a disposable CI checkout or explicitly from installed NVP.exe.
This launches only the named local llama-server binary and GGUF with
CPU-only settings. It never touches the user's actual production project,
grants director consent, installs models or declares finished-film quality.
"""
from __future__ import annotations

import argparse
import hashlib
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
from urllib.request import Request,ProxyHandler,HTTPRedirectHandler,build_opener

from backend.nvp_model_service import discover_models
from backend.nvp_wo6_verified_local_model import ProvenLocalModelWriter
from backend.nvp_idea_pipeline import LocalScriptModel
from backend.nvp_wo6_director_model_proposal import director_model_suggestion
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND

FORMAT="nvp.wo6_07b.real_gguf_inference_frozen_take_acceptance.v1"
MAX_GGUF_BYTES=128*1024**3


def sha256_file(path):
    h=hashlib.sha256()
    with path.open("rb") as fd:
        for chunk in iter(lambda:fd.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def checked_path(path,*,model=False):
    p=Path(path)
    if (not p.is_absolute() or p.is_symlink() or
            not p.is_file()):
        raise PermissionError("Accepted local model/binary must be an absolute regular file")
    resolved=p.resolve(strict=True)
    length=resolved.stat().st_size
    if model:
        if not 1024*1024<=length<=MAX_GGUF_BYTES:
            raise RuntimeError("GGUF size is outside permitted bounded acceptance range")
        with resolved.open("rb") as fd:
            if fd.read(4)!=b"GGUF":
                raise RuntimeError("Model file has no native GGUF magic")
    elif not 1024<=length<=1_000_000_000:
        raise RuntimeError("Native llama-server executable size is unexpected")
    return resolved


def _port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1",0))
        return s.getsockname()[1]


def _film_source(root):
    studio=Studio(root/"film.sqlite3")
    project=studio.create_project(
        "Disposable GGUF native director integration",
        "THIS IS NOT AN ORIGINAL FINISHED FILM")
    pid=project["id"]
    index=FilmIndex(studio)
    scene=OpenUSDSceneBridge(index).publish(
        pid,"gguf_scene",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,2,-5]},
            {"path":"/World/Light","role":"light","position":[2,3,4]},
        ],curves=[{"path":"/World/Actor","samples":[
            {"tick":0,"position":[0,0,0]},
            {"tick":2*TICKS_PER_SECOND,"position":[2,0,0]},
        ]}],native_schemas=True)
    index.register_revision(pid,"gguf_actor_source","performance",
        {"format":"nvp.wo6_07b.genuine_test_actor.v1"})
    temporal=TemporalLedger(index).publish(
        pid,"gguf_events",[{
            "event_id":"walk","event_kind":"action",
            "subject_id":"Actor","start_tick":0,
            "end_tick":2*TICKS_PER_SECOND,
            "source_id":"gguf_actor_source","source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor",
                       "director_intent":"walk toward camera"},
        }],duration_tick=3*TICKS_PER_SECOND)
    take=OpenUSDTakeCapture(
        index,verify_creator_action=lambda e,_:e=="DISPOSABLE_TEST_ONLY").freeze(
        pid,"gguf_take",scene_id="gguf_scene",scene_revision=1,
        timeline_id="gguf_events",timeline_revision=1,
        sample_ticks=[0,TICKS_PER_SECOND],
        creator_event="DISPOSABLE_TEST_ONLY")
    return index,pid,scene,temporal,take


def run_real_gguf_acceptance(*,model_path,server_path,report_path=None,
                             consent="",max_startup_seconds=180):
    if consent!="I_APPROVE_DISPOSABLE_LOCAL_GGUF_TEST":
        raise PermissionError("Explicit local GGUF acceptance consent required")
    model=checked_path(model_path,model=True)
    binary=checked_path(server_path)
    if report_path is not None:
        report=Path(report_path)
        if (not report.is_absolute() or report.is_symlink() or
                report.exists() or not report.parent.is_dir()):
            raise PermissionError("New absolute report path required")
    else:
        report=None
    model_sha=sha256_file(model)
    binary_sha=sha256_file(binary)
    with tempfile.TemporaryDirectory(prefix="nvp-wo6-07b-real-gguf-") as temp:
        root=Path(temp)
        log=root/"server.log"
        port=_port()
        alias="nvp-07b-"+secrets.token_hex(8)
        args=[str(binary),"-m",str(model),"--host","127.0.0.1",
              "--port",str(port),"-c","8192",
              "--n-gpu-layers","0","--alias",alias]
        flags=(subprocess.CREATE_NEW_PROCESS_GROUP
               if os.name=="nt" else 0)
        with log.open("wb") as logfile:
            proc=subprocess.Popen(
                args,cwd=str(root),stdin=subprocess.DEVNULL,
                stdout=logfile,stderr=subprocess.STDOUT,
                creationflags=flags,start_new_session=os.name!="nt")
            try:
                until=time.monotonic()+max_startup_seconds
                models=None
                while time.monotonic()<until:
                    if proc.poll() is not None:
                        raise RuntimeError("Native llama-server exited before model readiness")
                    models=discover_models(port)
                    if models["state"]=="available" and alias in {
                            x["id"] for x in models["models"]}:
                        break
                    time.sleep(.4)
                else:
                    raise RuntimeError("Actual GGUF model was not reported ready before timeout")
                index,pid,scene,temporal,take=_film_source(root)
                provider=ProvenLocalModelWriter(
                    LocalScriptModel(
                        endpoint=f"http://127.0.0.1:{port}/v1/chat/completions",
                        model_name=alias))
                original_hash=take["document_sha256"]
                started=time.monotonic()
                proposal=director_model_suggestion(
                    index,pid,"gguf_take",original_hash,
                    "0","Suggest one practical camera or actor direction grounded "
                        "only in the supplied original scene.",alias,provider)
                elapsed=max(0,round((time.monotonic()-started)*1000))
                receipt=proposal["provider_completion_receipt"]
                if (not proposal["provider_completion_observed"] or
                        receipt["provider_reported_completion_tokens"]<1 or
                        not proposal["model_text_is_untrusted"] or
                        proposal["native_worker_authorized"] or
                        proposal["creative_approval_granted"] or
                        proposal["film_delivered"] or
                        index.read_revision(pid,"gguf_take",1)[
                            "document_sha256"]!=original_hash or
                        proc.poll() is not None):
                    raise RuntimeError("Real GGUF output/source/permission proof failed")
                if sha256_file(model)!=model_sha or sha256_file(binary)!=binary_sha:
                    raise RuntimeError("Native GGUF/binary changed during acceptance")
                outcome={
                    "format":FORMAT,"status":"LOCAL_GGUF_COMPLETION_OBSERVED",
                    "real_native_gguf_server_launched":True,
                    "model_file_size_bytes":model.stat().st_size,
                    "model_file_sha256":model_sha,
                    "llama_server_executable_sha256":binary_sha,
                    "ephemeral_loopback_port":port,
                    "native_server_process_id_observed":proc.pid,
                    "model_alias":alias,
                    "native_source_scene_sha256":scene["document_sha256"],
                    "native_source_take_sha256":original_hash,
                    "completed_provider_receipt":receipt,
                    "director_suggestion_sha256":proposal["model_text_sha256"],
                    "director_suggestion_char_count":len(proposal["suggestion_text"]),
                    "source_modified":False,
                    "native_worker_authorized":False,
                    "human_director_reviewed":False,
                    "visible_webview2_checked":False,
                    "installed_windows_app_verified":bool(getattr(sys,"frozen",False)),
                    "physical_display_or_audio_verified":False,
                    "original_30minute_film_accepted":False,
                    "theatrical_master_accepted":False,
                    "elapsed_model_ms":elapsed,
                    "provider_self_report_not_independent_model_attestation":True,
                }
                if report is not None:
                    with report.open("x",encoding="utf-8") as fd:
                        fd.write(json.dumps(outcome,sort_keys=True,indent=2)+"\n")
                        fd.flush()
                        os.fsync(fd.fileno())
                return outcome
            finally:
                # Acceptance-only server is not the creator's existing model.
                # Never unload arbitrary instances or send a kill-all command.
                if proc.poll() is None:
                    if os.name=="nt":
                        subprocess.run(
                            ["taskkill","/PID",str(proc.pid),"/T","/F"],
                            capture_output=True,timeout=15,check=False)
                    else:
                        try:
                            os.killpg(proc.pid,signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        if os.name!="nt":
                            try:os.killpg(proc.pid,signal.SIGKILL)
                            except ProcessLookupError:pass
                        else:
                            proc.kill()
                        proc.wait(timeout=10)


def main(argv=None):
    parser=argparse.ArgumentParser(
        description="Explicit, disposable real GGUF-to-verified-USD Take smoke")
    parser.add_argument("--model",required=True)
    parser.add_argument("--llama-server",required=True)
    parser.add_argument("--report")
    parser.add_argument("--consent",required=True)
    args=parser.parse_args(argv)
    result=run_real_gguf_acceptance(
        model_path=args.model,server_path=args.llama_server,
        report_path=args.report,consent=args.consent)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
