"""P1-A — audit actual durable microphone PCM through the compiled native worker.

This bridge DOES NOT capture a hardware microphone. The trusted native
miniaudio/PortAudio recorder still owns device I/O, exact source clocks and
its original durable recovery spool. BEFORE any immutable FilmIndex source
or Take publication, this bridge passes bounded exact PCM windows to the
reviewed first-party original_capture executable through ProtectedNativeWorker.
Each window requires the original worker's separate creator consent, actual
OS process-tree custody, protected Windows EFS source staging, and independent
result verification. A false/failed audit cannot publish a Digital Take.

No arbitrary executable, filesystem path, authorization or device selector is
taken from the browser/model. Actual device process-tree custody and installed
physical EFS acceptance are separate open production gates.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import struct

from backend.nvp_film_index import _id,_require_pid
from backend.nvp_w1g_protected_native_worker import ProtectedNativeWorker
from backend.nvp_w1g_encrypted_source import verify_efs_inputs

FORMAT="nvp.w1g.original_microphone_worker_audit.v1"
PCM_WINDOW_BYTES=4*1024*1024
SHA=re.compile(r"^[0-9a-f]{64}$")


class OriginalMicrophoneNativeWorkerAudit:
    """Trusted host-only compiled worker bridge; never a UI or policy token."""

    def __init__(self, worker: ProtectedNativeWorker, *,
                 recovery_root: Path):
        if type(worker) is not ProtectedNativeWorker:
            raise TypeError("Actual protected first-party worker authority required")
        root=Path(recovery_root)
        if (not root.is_absolute() or not root.is_dir() or root.is_symlink()):
            raise PermissionError("Trusted original microphone recovery root required")
        self.worker=worker
        self.recovery_root=root.resolve(strict=True)

    def verify_original_spool(self, *, project_id, take_id, source_id,
                              scene_id, scene_document_sha256,
                              camera_timeline_document_sha256,
                              subject_id, emitter_path,
                              source_path: Path, recorded_samples: int,
                              original_pcm_sha256: str,
                              start_tick: int, end_tick: int):
        _require_pid(project_id)
        for name in (take_id,source_id,scene_id,subject_id):
            _id(name,"native original filming identity")
        if (any(type(value) is not str or not SHA.fullmatch(value) for value in (
                scene_document_sha256,camera_timeline_document_sha256,
                original_pcm_sha256)) or
            type(recorded_samples) is not int or recorded_samples<=0 or
            type(start_tick) is not int or type(end_tick) is not int or
            start_tick<0 or end_tick<=start_tick or
            type(emitter_path) is not str or not emitter_path.startswith("/") or
            len(emitter_path)>512):
            raise PermissionError("Original microphone Film Time or SHA identity missing")
        source=Path(source_path)
        if (not source.is_absolute() or source.is_symlink() or
            not source.is_file() or source.parent.is_symlink() or
            not source.parent.name.startswith("nvp-live-original-") or
            source.parent.resolve(strict=True).parent!=self.recovery_root or
            source.name not in ("recording.pcm","independent_0.pcm",
                                "independent_1.pcm")):
            raise PermissionError("Original PCM must reside in the current trusted native device spool")
        if os.name=="nt":
            verify_efs_inputs(source.parent,(source.name,))
        before=source.stat()
        if (not before.st_size or before.st_size!=recorded_samples*2 or
            before.st_size>600*48000*2):
            raise PermissionError("Original native device PCM count/size is inconsistent")
        digest=sha256()
        window_receipts=[]
        total_samples=0
        # Never allocate a whole long-form recording or silently omit a tail.
        with source.open("rb") as fp:
            while window:=fp.read(PCM_WINDOW_BYTES):
                if len(window)%2:
                    raise RuntimeError("Original PCM16LE window is not sample-aligned")
                window_sha=sha256(window).hexdigest()
                window_samples=len(window)//2
                window_peak=max(abs(v[0]) for v in struct.iter_unpack("<h",window))
                plan={
                    "role":"original_capture","project_id":project_id,
                    "take_id":take_id,"source_id":source_id,
                    "scene_id":scene_id,
                    "scene_document_sha256":scene_document_sha256,
                    "camera_timeline_document_sha256":
                        camera_timeline_document_sha256,
                    "subject_id":subject_id,"emitter_path":emitter_path,
                    "first_sample":total_samples,
                    "sample_count":window_samples,
                    "start_tick":start_tick,"end_tick":end_tick,
                    "source_pcm_sha256":original_pcm_sha256,
                }
                # This is the actual installed C++ role worker, not a new
                # Python replacement or a synthetic acceptance callback.
                verified=self.worker.run(
                    "original_capture",project_id,plan,
                    sealed_inputs={"source.pcm":window},
                    memory_mb=512,timeout_s=120)
                if (type(verified) is not dict or
                    verified.get("state")!="SUCCEEDED_VERIFIED" or
                    verified.get("output_independently_verified") is not True or
                    verified.get("process_tree_custody_verified") is not True or
                    verified.get("input_sha256")!={"source.pcm":window_sha}):
                    raise PermissionError("Original native capture worker lacked final OS/result evidence")
                worker_sha=verified.get("worker_sha256")
                plan_sha=verified.get("plan_sha256")
                kernel=verified.get("os_custody_receipt")
                if (type(worker_sha) is not str or not SHA.fullmatch(worker_sha) or
                    type(plan_sha) is not str or not SHA.fullmatch(plan_sha) or
                    type(kernel) is not dict or
                    kernel.get("process_tree_custody_verified") is not True):
                    raise PermissionError("Original native capture requires exact worker, plan and kernel receipt identities")
                from backend.nvp_p1a_take_provenance import audit_sha256
                kernel_sha=audit_sha256(kernel)
                job=verified.get("job_id")
                if type(job) is not str or not re.fullmatch(r"w1g_[0-9a-f]{24}",job):
                    raise PermissionError("Original native capture receipt lacks authentic job identity")
                directory=self.worker.runtime/job
                manifest=directory/"capture.manifest"
                receipt=directory/"result.json"
                if (manifest.is_symlink() or not manifest.is_file() or
                    receipt.is_symlink() or not receipt.is_file()):
                    raise PermissionError("Original native capture audit output missing")
                expected=(
                    f"format=nvp.w1g.pcm_intake.v1\n"
                    f"samples={window_samples}\npeak={window_peak}\n"
                    f"source_sha256={window_sha}\n").encode("ascii")
                if (manifest.read_bytes()!=expected or
                    sha256(receipt.read_bytes()).hexdigest()!=verified.get("result_sha256")):
                    raise PermissionError("Native original PCM evidence changed after worker execution")
                digest.update(window)
                window_receipts.append({
                    "job_id":job,"first_sample":total_samples,
                    "sample_count":window_samples,
                    "window_pcm_sha256":window_sha,
                    "worker_result_sha256":verified["result_sha256"],
                    "native_worker_binary_sha256":worker_sha,
                    "native_worker_plan_sha256":plan_sha,
                    "os_custody_receipt_sha256":kernel_sha,
                    "original_native_kernel_custody_verified":True,
                })
                total_samples+=window_samples
        # The original descriptor was opened before native worker execution.
        # An external writer can change the same-length source while a buffered
        # read continues to produce the old PCM bytes. Windows timestamps may
        # also have insufficient resolution to prove no such modification.
        # Independently reopen the ORIGINAL on-disk source and hash every
        # exact byte after all native audit windows have completed.
        if source.is_symlink() or source.parent.is_symlink():
            raise RuntimeError("Original microphone spool changed or truncated during native audit")
        fresh_digest=sha256()
        with source.open("rb") as reread:
            while fresh_window:=reread.read(PCM_WINDOW_BYTES):
                fresh_digest.update(fresh_window)
        after=source.stat()
        if (before.st_size!=after.st_size or
            before.st_mtime_ns!=after.st_mtime_ns or
            total_samples!=recorded_samples or
            digest.hexdigest()!=original_pcm_sha256 or
            fresh_digest.hexdigest()!=original_pcm_sha256):
            raise RuntimeError("Original microphone spool changed or truncated during native audit")
        return {
            "format":FORMAT,"project_id":project_id,
            "take_id":take_id,"source_id":source_id,
            "scene_id":scene_id,
            "scene_document_sha256":scene_document_sha256,
            "camera_timeline_document_sha256":camera_timeline_document_sha256,
            "subject_id":subject_id,"emitter_path":emitter_path,
            "start_tick":str(start_tick),"end_tick":str(end_tick),
            "original_pcm_sha256":original_pcm_sha256,
            "sample_count":total_samples,
            "window_count":len(window_receipts),
            "native_worker_receipts":window_receipts,
            "all_window_results_and_os_custody_verified":True,
            "device_capture_implemented_by_compiled_worker":False,
            "immutable_take_published":False,
            "physical_microphone_hardware_accepted":False,
        }
