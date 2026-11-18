"""WO6-B: native saved-plan Take execution on existing Windows custody.

The only operation is a new exact-source frozen Take. Its worker independently
evaluates the immutable OpenUSD layers/checkpoints in real AppContainer
custody; only the native host can publish a new FilmIndex identity.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_g03_protected_scene_supervisor import _stream_read, _stream_write
from backend.nvp_openusd_take import OpenUSDTakeCapture, canonical, sha
from backend.nvp_wo6_saved_retake_authority import SavedRetakeTaskAuthority, RAM_MB
from backend.nvp_wo6_saved_retake_scope import check_saved_retake_current
from backend.nvp_w1g_encrypted_source import require_efs_stage
from backend.nvp_worker_containment import launch_contained
from tools.nvp_wo6_take_worker import MAGIC_IN, MAGIC_OUT, MAX_INPUT, MAX_OUTPUT, LAYER_KEYS

RECEIPT="nvp.wo6.protected_take_execution.v1"


def _digest_file(path):
    with Path(path).open("rb") as fd:
        return sha256(fd.read()).hexdigest()


def _command():
    if sys.platform!="win32":
        raise PermissionError("Protected native Take execution requires Windows AppContainer")
    exe=Path(sys.executable).resolve(strict=True)
    if getattr(sys,"frozen",False):
        return [str(exe),"--wo6-protected-take-worker"],[exe.parent],[],_digest_file(exe)
    repo=Path(__file__).resolve().parents[1]
    worker=repo/"tools"/"nvp_wo6_take_worker.py"
    pipe=repo/"tools"/"nvp_g03_protected_scene_worker.py"
    paths=[worker,pipe]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        raise PermissionError("Reviewed fixed native Take worker source unavailable")
    # No original film root or browser-selected code is ever granted.
    code=[exe,worker,pipe]+[repo/"backend"/name for name in (
        "nvp_openusd_scene.py","nvp_openusd_take.py","nvp_openusd_channels.py",
        "nvp_openusd_native_schemas.py","nvp_openusd_skeleton.py")]
    pin=sha([_digest_file(p) for p in code])
    return [str(exe),"-B",str(worker)],[exe.parent,repo/"backend"],paths,pin


def _payload(index, scope):
    pid=scope["project_id"]
    scene, timeline, _stage, _duration=OpenUSDTakeCapture(
        index,verify_creator_action=lambda *_:False)._sources(pid,scope["scene_id"],
        scope["scene_revision"],scope["timeline_id"],scope["timeline_revision"])
    if (scene["document_sha256"]!=scope["scene_sha256"] or
        timeline["document_sha256"]!=scope["timeline_sha256"]):
        raise PermissionError("Exact native source changed")
    source=scene["data"]
    if (any(source.get(k) for k in ("asset_bindings","actor_bindings","imported_characters")) or
        source.get("contains_external_references") is not False):
        raise PermissionError("This Take requires a protected asset or cast resolver")
    from backend.nvp_temporal_ledger import TemporalLedger
    temporal=TemporalLedger(index)
    raw=canonical({"format":"nvp.wo6.take_worker_input.v1",
        "scope_sha256":scope["scope_sha256"],"scene":source,
        "layers":{k:index.get_blob(pid,source[LAYER_KEYS[k]]).decode("utf-8")
                  for k in source["layer_order"]},
        "ticks":scope["sample_ticks"],
        "events":[[r["event_id"] for r in temporal.events_at(pid,scope["timeline_id"],
            scope["timeline_revision"],tick=t,limit=500)] for t in scope["sample_ticks"]]})
    if not 0<len(raw)<=MAX_INPUT:
        raise PermissionError("Self-contained native Take exceeds worker input budget")
    return raw


def _execute_pipe(raw, pin, live, *, timeout=120):
    command,roots,files,actual=_command()
    if actual!=pin or not live():
        raise PermissionError("Worker or native scope changed before launch")
    if type(timeout) is not int or not 5<=timeout<=120:
        raise ValueError("Bounded native worker time required")
    # Use exactly the existing audited AppContainer+Job+release slot launcher.
    # The worker's cwd is EFS and empty; all source/output travel only in pipes.
    with tempfile.TemporaryDirectory(prefix="nvp-wo6-take-") as tmp:
        root=Path(tmp)
        require_efs_stage(root)
        with __import__("contextlib").ExitStack() as stack:
            def pipe():
                r,w=os.pipe()
                return (stack.enter_context(os.fdopen(r,"rb",buffering=0)),
                        stack.enter_context(os.fdopen(w,"wb",buffering=0)))
            inp,send=pipe(); receive,out=pipe(); error_in,err=pipe()
            stdout=bytearray(); stderr=bytearray(); errors=[]; threads=[]
            proc=None
            try:
                if not live() or _command()[3]!=pin:
                    raise PermissionError("Native authorization changed before launch")
                proc=launch_contained(command,cwd=str(root),stdin=inp,stdout=out,
                    stderr=err,memory_mb=RAM_MB,windows_appcontainer_required=True,
                    appcontainer_code_roots=roots,appcontainer_code_files=files)
                from backend.nvp_g03_windows_appcontainer import AppContainerJobProcess
                if type(proc) is not AppContainerJobProcess:
                    raise PermissionError("Native AppContainer custody unavailable")
                inp.close();out.close();err.close()
                payload=MAGIC_IN+struct.pack("!Q",len(raw))+raw
                for fn,args in ((_stream_write,(send,payload,errors)),
                    (_stream_read,(receive,len(MAGIC_OUT)+8+MAX_OUTPUT,stdout,errors)),
                    (_stream_read,(error_in,4096,stderr,errors))):
                    th=threading.Thread(target=fn,args=args,daemon=True)
                    th.start();threads.append(th)
                deadline=time.monotonic()+timeout
                while proc.poll() is None:
                    if errors or time.monotonic()>=deadline or not live():
                        raise PermissionError("Protected Take cancelled, revoked or timed out")
                    time.sleep(.03)
                rc=proc.wait(timeout=12)
                # close independently verifies zero Job processes and profile/ACL
                # recovery, including the original durable launch journal.
                owned=proc
                proc=None
                owned.close()
                for th in threads:th.join(timeout=6)
                if (rc!=0 or errors or any(th.is_alive() for th in threads) or
                    list(root.rglob("*")) or not live() or _command()[3]!=pin):
                    raise RuntimeError("Protected native Take result or custody unverified")
                header=len(MAGIC_OUT)+8
                if not stdout.startswith(MAGIC_OUT) or len(stdout)<header:
                    raise RuntimeError("Native Take output protocol invalid")
                size=struct.unpack("!Q",stdout[len(MAGIC_OUT):header])[0]
                data=bytes(stdout[header:])
                if not 0<size<=MAX_OUTPUT or size!=len(data):
                    raise RuntimeError("Native Take output length invalid")
                result=json.loads(data)
                if canonical(result)!=data:
                    raise RuntimeError("Native Take output not canonical")
                return result
            finally:
                if proc is not None:
                    try:
                        if proc.poll() is None:proc.terminate_tree()
                        proc.wait(timeout=12)
                    finally:proc.close()


def execute_saved_retake(index, ledger, *, project_id, plan_id, plan_sha256,
                        new_take_id, confirm_native, live_gate):
    """One synchronous native action; no generic executor or caller path."""
    _command()
    def seal(scope):
        raw=_payload(index,scope)
        return {"worker_sha256":_command()[3],"input_sha256":sha256(raw).hexdigest()}
    authority=SavedRetakeTaskAuthority(index,ledger,project_id,
        confirm_native=confirm_native,live_gate=live_gate,seal_execution=seal)
    try:
        queued=authority.queue(plan_id=plan_id,plan_sha256=plan_sha256,new_take_id=new_take_id)
        task=queued["task_id"]
        with authority.admitted(task) as spec:
            if spec is None:
                ledger.cancel_queued(task,owner_key=authority.owner)
                return {"status":"NOT_ADMITTED","task_id":task,"worker_executed":False}
            scope=spec["scope"]; execution=spec["execution"]
            spec_sha=sha256(canonical_bytes(spec)).hexdigest()
            raw=_payload(index,scope)
            if sha256(raw).hexdigest()!=execution["input_sha256"]:
                raise PermissionError("Sealed native input changed")
            live=lambda:authority.grant_live(spec)
            ledger.update(task,"building_scene","Evaluating exact native source in protected worker")
            result=_execute_pipe(raw,execution["worker_sha256"],live)
            # Successful return requires the actual AppContainer closed and
            # independently audited, NOT merely a worker-generated boolean.
            original=index.read_revision(project_id,scope["original_take_id"],1)
            if (result!={"format":"nvp.wo6.take_worker_result.v1",
                "scope_sha256":scope["scope_sha256"],"input_sha256":execution["input_sha256"],
                "sample_digest_sha256":original["data"]["sample_digest_sha256"],
                "checkpoint_count":len(scope["sample_ticks"])} or
                original["document_sha256"]!=scope["original_take_sha256"]):
                raise RuntimeError("Native worker differs from verified original Take")
            authority.bindings.verified_spec(task,owner_key=authority.owner)
            receipt={"format":RECEIPT,"project_id":project_id,"task_id":task,
                "scope_sha256":scope["scope_sha256"],"spec_sha256":spec_sha,
                **execution,"sample_digest_sha256":result["sample_digest_sha256"],
                "plan_id":plan_id,"plan_document_sha256":plan_sha256,
                "original_take_id":scope["original_take_id"],
                "original_take_sha256":scope["original_take_sha256"],
                "new_take_id":new_take_id,"scene_sha256":scope["scene_sha256"],
                "timeline_sha256":scope["timeline_sha256"],
                "process_tree_custody_verified":True}
            def guard(_db):
                if not live():
                    raise PermissionError("Native grant revoked before publication")
                check_saved_retake_current(index,scope)
            def approve(event, exact):
                return (event==task and live() and
                    exact.get("project_id")==project_id and exact.get("take_id")==new_take_id and
                    exact.get("scene_document_sha256")==scope["scene_sha256"] and
                    exact.get("timeline_document_sha256")==scope["timeline_sha256"] and
                    exact.get("checkpoint_ticks")==scope["sample_ticks"] and
                    exact.get("checkpoint_sha256")==receipt["sample_digest_sha256"] and
                    exact.get("protected_retake_receipt_sha256")==sha(receipt))
            capture=OpenUSDTakeCapture(index,verify_creator_action=approve)
            ledger.update(task,"verifying_output","Verifying protected native result and immutable source")
            saved=capture.freeze(project_id,new_take_id,scene_id=scope["scene_id"],
                scene_revision=scope["scene_revision"],timeline_id=scope["timeline_id"],
                timeline_revision=scope["timeline_revision"],sample_ticks=scope["sample_ticks"],
                creator_event=task,protected_retake_receipt=receipt,precommit_guard=guard)
            proof=capture.verify_take(project_id,new_take_id)
            row=index.read_revision(project_id,new_take_id,1)
            if (proof["take_document_sha256"]!=saved["document_sha256"] or
                row["data"]["protected_retake_execution"]!=receipt or not live()):
                raise RuntimeError("New immutable Take requires reconciliation")
            ledger.finish(task,"SUCCEEDED","Protected native Take and original source independently verified")
            return {"status":"VERIFIED_NEW_TAKE","task_id":task,"project_id":project_id,
                "take_id":new_take_id,"take_document_sha256":saved["document_sha256"],
                "worker_executed":True,"film_approved":False,"rendered_frames":False}
    finally:
        authority.close()
