"""WO6-B: native saved-plan Take execution on existing Windows custody.

The only operation is a new exact-source frozen Take. Its worker independently
evaluates the immutable OpenUSD layers/checkpoints in real AppContainer
custody; only the native host can publish a new FilmIndex identity.
"""
from __future__ import annotations

from backend.nvp_performance_probe import measured, span, observe_windows_job
from hashlib import sha256
from contextlib import ExitStack, contextmanager
import json
import os
import shutil
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_g03_protected_scene_supervisor import _stream_read
from backend.nvp_openusd_take import OpenUSDTakeCapture, canonical, sha
from backend.nvp_wo6_saved_retake_authority import SavedRetakeTaskAuthority, RAM_MB
from backend.nvp_wo6_saved_retake_scope import check_saved_retake_current
from backend.nvp_w1g_encrypted_source import require_efs_stage
from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_host_lease import WorkerHostLease
from backend.nvp_wo6_recovery import RetakeRecovery
from backend.nvp_wo6_retake_control import RetakeControl
from tools.nvp_wo6_take_worker import MAGIC_IN, MAGIC_OUT, MAX_INPUT, MAX_OUTPUT, LAYER_KEYS

RECEIPT="nvp.wo6.protected_take_execution.v1"


def _digest_file(path):
    h=sha256()
    with Path(path).open("rb") as fd:
        for chunk in iter(lambda:fd.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def _code_inventory(root):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():
        raise PermissionError("Native worker code root unavailable")
    result={}
    for item in sorted(root.rglob("*")):
        if item.is_symlink():
            raise PermissionError("Linked native worker code refused")
        relative=item.relative_to(root).as_posix()
        if item.is_dir():
            if relative not in ("backend","tools"):
                raise PermissionError("Unexpected native worker code directory")
            continue
        if not item.is_file() or item.suffix!=".py":
            raise PermissionError("Unexpected native worker code entry")
        result[relative]=_digest_file(item)
    if len(result)>600 or "tools/nvp_wo6_take_worker.py" not in result or "backend/__init__.py" not in result:
        raise PermissionError("Incomplete or unbounded native worker code inventory")
    return result


@contextmanager
def _source_code_scope(repo):
    # FileFinder must enumerate package parents; do not grant the original
    # checkout ACLs or expose creator bytes. Stage a separate code-only root.
    with tempfile.TemporaryDirectory(prefix="nvp-wo6-code-") as tmp:
        root=Path(tmp).resolve(strict=True)
        original={}
        for folder in ("backend","tools"):
            (root/folder).mkdir()
        sources=sorted((repo/"backend").glob("*.py"))+[
            repo/"tools"/"nvp_wo6_take_worker.py",
            repo/"tools"/"nvp_g03_protected_scene_worker.py"]
        if not 2<=len(sources)<=599:
            raise PermissionError("Bounded reviewed Python source required")
        for source in sources:
            if source.is_symlink() or source.parent.is_symlink() or not source.is_file():
                raise PermissionError("Linked or absent native worker source")
            relative=source.relative_to(repo).as_posix()
            original[relative]=_digest_file(source)
            shutil.copyfile(source,root/relative)
        (root/"tools"/"__init__.py").write_bytes(b"")
        original["tools/__init__.py"]=sha256(b"").hexdigest()
        if _code_inventory(root)!=original:
            raise PermissionError("Staged native code did not match exact sources")
        def verify():
            current=_code_inventory(root)
            if current!=original:
                raise PermissionError("Staged native code changed")
            return current
        yield root,verify


@contextmanager
def _command_scope():
    if sys.platform!="win32":
        raise PermissionError("Protected native Take execution requires Windows AppContainer")
    exe=Path(sys.executable).resolve(strict=True)
    if getattr(sys,"frozen",False):
        def frozen():
            return [str(exe),"--wo6-protected-take-worker"],[exe.parent],[],_digest_file(exe)
        yield frozen
        return
    repo=Path(__file__).resolve().parents[1]
    with _source_code_scope(repo) as (root,verify):
        def command():
            pin=sha({"executable":_digest_file(exe),"modules":verify()})
            return [str(exe),"-I","-B",str(root/"tools"/"nvp_wo6_take_worker.py")],[exe.parent,root],[],pin
        yield command


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


@measured("take.worker")
def _execute_pipe(raw, pin, live, *, command_scope, scope_sha, command_sha, task, ledger, recovery, timeout=120):
    command,roots,files,actual=command_scope()
    command=command+[scope_sha]
    if sha(command)!=command_sha:
        raise PermissionError("Sealed exact worker command changed")
    if actual!=pin or not live():
        raise PermissionError("Worker or native scope changed before launch")
    if type(timeout) is not int or not 5<=timeout<=120:
        raise ValueError("Bounded native worker time required")
    # Use exactly the existing audited AppContainer+Job+release slot launcher.
    # The worker's cwd is EFS and empty; all source/output travel only in pipes.
    with tempfile.TemporaryDirectory(prefix="nvp-wo6-take-") as tmp:
        root=Path(tmp)
        require_efs_stage(root)
        with ExitStack() as stack:
            def pipe():
                r,w=os.pipe()
                return (stack.enter_context(os.fdopen(r,"rb",buffering=0)),
                        stack.enter_context(os.fdopen(w,"wb",buffering=0)))
            inp,send=pipe(); receive,out=pipe(); error_in,err=pipe()
            stdout=bytearray(); stderr=bytearray(); errors=[]; threads=[]
            proc=None
            journal=None
            bound=False
            try:
                if not live() or command_scope()[3]!=pin:
                    raise PermissionError("Native authorization changed before launch")
                recovery.launch_intent(task)
                proc=launch_contained(command,cwd=str(root),stdin=inp,stdout=out,
                    stderr=err,memory_mb=RAM_MB,windows_appcontainer_required=True,
                    appcontainer_code_roots=roots,appcontainer_code_files=files)
                from backend.nvp_g03_windows_appcontainer import AppContainerJobProcess
                if type(proc) is not AppContainerJobProcess:
                    raise PermissionError("Native AppContainer custody unavailable")
                # Bind the original existing kernel launch journal to this
                # exact task, without a second competing custody journal.
                journal=proc._worker._original_journal
                from backend.nvp_w1g_release_gate import OriginalWindowsLaunchJournal
                if (type(journal) is not OriginalWindowsLaunchJournal or
                    journal._record["command_sha256"]!=command_sha or
                    journal._record["state"]!="RUNNING"):
                    raise PermissionError("Original protected launch journal not bound")
                recovery.running(task,journal.token)
                bound=True
                ledger.update(task,"building_scene","Native protected job: "+journal.token)
                inp.close();out.close();err.close()
                payload=MAGIC_IN+struct.pack("!Q",len(raw))+raw
                for fn,args in ((_write_all,(send,payload,errors)),
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
                alive=any(th.is_alive() for th in threads)
                workspace_dirty=bool(list(root.rglob("*")))
                still_live=live()
                pin_matches=command_scope()[3]==pin
                if (journal.path.is_symlink() or journal.path.stat().st_size>2048):
                    raise RuntimeError("Original native process journal not readable")
                evidence=json.loads(journal.path.read_text("utf-8"))
                if (evidence!=journal._record or evidence["job_id"]!=journal.token or
                    evidence["command_sha256"]!=command_sha or
                    evidence["state"]!="TREE_REAPED_VERIFIED" or
                    evidence["process_tree_custody_verified"] is not True or
                    evidence["worker_exit_verified"] is not True):
                    raise RuntimeError("Original native Job tree close unproven")
                if not alive and not workspace_dirty:
                    recovery.custody_closed(task,journal.token)
                _require_clean_worker_result(rc,errors,stderr,stdout,alive,
                    workspace_dirty,still_live,pin_matches,
                    startup_diagnostic=_reviewed_cpython_startup_diagnostic(command,
                        platform=sys.platform,implementation=sys.implementation.name,
                        version=sys.version_info[:2],frozen=getattr(sys,"frozen",False)))
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
                return result,journal.token
            finally:
                if proc is not None:
                    try:
                        if proc.poll() is None:proc.terminate_tree()
                        proc.wait(timeout=12)
                    finally:proc.close()
                    # AppContainer close proves Job + profile/ACL cleanup.
                    # Pipe and workspace checks are separate and mandatory.
                    for endpoint in (inp,out,err):
                        endpoint.close()
                    for th in threads:th.join(timeout=6)
                    if (bound and not any(th.is_alive() for th in threads)
                        and not list(root.rglob("*"))):
                        recovery.custody_closed(task,journal.token)


def _reviewed_cpython_startup_diagnostic(command, *, platform, implementation,
                                        version, frozen):
    # CPython 3.13 Modules/getpath.py warns if an existing executable's
    # realpath lookup is denied. Windows lowbox can deny final-path lookup
    # while still permitting the exact host-pinned executable to run.
    # Recognize only the one observed ASCII line for the sealed source-mode
    # command. Do not relax the lowbox, suppress warnings, normalize unknown
    # bytes, accept other paths, or extend this exception to frozen binaries.
    import ntpath
    if (platform!="win32" or implementation!="cpython" or version!=(3,13)
        or frozen or len(command)!=5 or command[1:3]!=["-I","-B"]
        or not ntpath.isabs(command[0])
        or ntpath.basename(command[0]).lower()!="python.exe"
        or ntpath.basename(command[3])!="nvp_wo6_take_worker.py"):
        return b""
    exe=command[0]
    if not exe.isascii() or any(ord(c)<32 or ord(c)==127 for c in exe):
        return b""
    return ("Failed to find real location of "+exe+"\n").encode("ascii")


def _require_clean_worker_result(rc, errors, stderr, stdout, alive,
                                 workspace_dirty, still_live, pin_matches,
                                 *, startup_diagnostic=b""):
    # The only nonempty stderr permitted is the entire exact reviewed
    # startup line, with no additions or repetitions. All other checks,
    # including the following canonical result, journal, checkpoint, source
    # and immutable publication checks, remain mandatory.
    unexpected_stderr=bool(stderr) and bytes(stderr)!=startup_diagnostic
    if (rc!=0 or errors or unexpected_stderr or alive or workspace_dirty or not still_live or not pin_matches):
        raise RuntimeError("Protected native Take failed: "+
            "exit="+str(rc)+" pipe_errors="+str(len(errors))+
            " stderr_bytes="+str(len(stderr))+" stdout_bytes="+str(len(stdout))+
            " pipe_alive="+str(alive)+" workspace_dirty="+str(workspace_dirty)+
            " live="+str(still_live)+" pin_matches="+str(pin_matches))


def _write_all(file, payload, errors):
    try:
        view=memoryview(payload)
        while view:
            n=file.write(view)
            if type(n) is not int or not 0<n<=len(view):
                raise OSError("Incomplete native pipe write")
            view=view[n:]
        file.flush()
    except OSError:
        errors.append("Native worker input pipe failed")
    finally:
        file.close()


def execute_saved_retake(index, ledger, *, project_id, plan_id, plan_sha256,
                        new_take_id, confirm_native, live_gate, control=None):
    """One synchronous native action; no generic executor or caller path."""
    if control is None:
        control=RetakeControl()
    if type(control) is not RetakeControl:
        raise TypeError("Private native cancellation control required")
    # One kernel lease spans reconciliation, admission, native custody and
    # publication. A live host is never mistaken for a cold-start orphan.
    try:
        with WorkerHostLease(ledger.root) as lease:
            recovery=RetakeRecovery(ledger,lease)
            try:
                index.studio.get_project(project_id)
                if any(state=="HELD_UNVERIFIED" for _,state in recovery.reconcile(index,project_id)):
                    raise PermissionError("Previous Take cleanup remains unverified")
                try:
                    with _command_scope() as command_scope:
                        return _execute_saved(index,ledger,project_id=project_id,plan_id=plan_id,
                            plan_sha256=plan_sha256,new_take_id=new_take_id,
                            confirm_native=confirm_native,live_gate=live_gate,command_scope=command_scope,
                            recovery=recovery,host_lease=lease,control=control)
                except Exception:
                    result=recovery.reconcile(index,project_id)
                    task=control.task_id
                    if task is not None and (task,"CANCELLED") in result:
                        return {"status":"CANCELLED","task_id":task,"project_id":project_id,
                                "new_take_created":False,"film_approved":False}
                    raise
            finally:
                # Block concurrent cancellation before releasing the OS lease.
                control.close()
    finally:
        control.close()


def _execute_saved(index, ledger, *, project_id, plan_id, plan_sha256,
                   new_take_id, confirm_native, live_gate, command_scope, recovery, host_lease, control):
    def seal(scope):
        raw=_payload(index,scope)
        command,_,_,pin=command_scope()
        return {"worker_sha256":pin,"input_sha256":sha256(raw).hexdigest(),
                "command_sha256":sha(command+[scope["scope_sha256"]])}
    authority=SavedRetakeTaskAuthority(index,ledger,project_id,
        confirm_native=confirm_native,live_gate=live_gate,seal_execution=seal)
    try:
        queued=authority.queue(plan_id=plan_id,plan_sha256=plan_sha256,new_take_id=new_take_id)
        task=queued["task_id"]
        with authority.admitted(task,host_lease=host_lease) as spec:
            if spec is None:
                ledger.cancel_queued(task,owner_key=authority.owner)
                return {"status":"NOT_ADMITTED","task_id":task,"worker_executed":False}
            recovery.prepare(task,spec)
            control.bind(recovery,task)
            scope=spec["scope"]; execution=spec["execution"]
            spec_sha=sha256(canonical_bytes(spec)).hexdigest()
            raw=_payload(index,scope)
            if sha256(raw).hexdigest()!=execution["input_sha256"]:
                raise PermissionError("Sealed native input changed")
            live=lambda:authority.grant_live(spec) and not recovery.cancelled(task)
            ledger.update(task,"building_scene","Evaluating exact native source in protected worker")
            result,journal_id=_execute_pipe(raw,execution["worker_sha256"],live,
                command_scope=command_scope,
                scope_sha=scope["scope_sha256"],command_sha=execution["command_sha256"],
                task=task,ledger=ledger,recovery=recovery)
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
                "original_process_journal_id":journal_id,
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
            recovery.publication_pending(task,receipt)
            saved=capture.freeze(project_id,new_take_id,scene_id=scope["scene_id"],
                scene_revision=scope["scene_revision"],timeline_id=scope["timeline_id"],
                timeline_revision=scope["timeline_revision"],sample_ticks=scope["sample_ticks"],
                creator_event=task,protected_retake_receipt=receipt,precommit_guard=guard)
            proof=capture.verify_take(project_id,new_take_id)
            row=index.read_revision(project_id,new_take_id,1)
            if (proof["take_document_sha256"]!=saved["document_sha256"] or
                row["data"]["protected_retake_execution"]!=receipt or not live()):
                raise RuntimeError("New immutable Take requires reconciliation")
            recovery.take_verified(task,receipt)
            ledger.finish(task,"SUCCEEDED","Protected native Take and original source independently verified")
            return {"status":"VERIFIED_NEW_TAKE","task_id":task,"project_id":project_id,
                "take_id":new_take_id,"take_document_sha256":saved["document_sha256"],
                "worker_executed":True,"film_approved":False,"rendered_frames":False}
    finally:
        authority.close()
