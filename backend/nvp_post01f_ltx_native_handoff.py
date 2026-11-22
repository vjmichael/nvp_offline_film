"""POST-01F R3: fail-closed NVP host -> reviewed LTX worker handoff.

Source-only adapter: not a standalone LTX runtime. The installed executable
must implement --nvp-ltx-job; host-supplied trusted callbacks must authenticate
creator consent, real Windows kernel custody and independent decoded pictures.
A returned quarantine receipt is NOT film publication or creator approval.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading

WIRE = "nvp.post01f.ltx_layout_request.v1"
RESULT = "nvp.post01f.ltx_picture_result.v1"
JOURNAL = "nvp.post01f.ltx_host_journal.v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
PROJECT = re.compile(r"[0-9a-f]{32}\Z")
MAX_PLAN = 16 * 1024
MAX_LAYOUT = 256 * 1024 * 1024
MAX_LOOK = 16 * 1024 * 1024
MAX_CONDITIONING = 16 * 1024
MAX_PICTURE = 512 * 1024 * 1024
FILES_BEFORE = frozenset(("journal.json", "plan.json", "layout.mp4", "look.png", "conditioning.json", "stdout.log", "stderr.log"))
FILES_AFTER = FILES_BEFORE | {"picture.mp4", "result.json"}


def digest_file(path: Path, limit: int) -> str:
    if path.is_symlink() or not path.is_file():
        raise PermissionError("Missing or linked LTX worker file")
    h = sha256()
    total = 0
    with path.open("rb") as f:
        while data := f.read(1024 * 1024):
            total += len(data)
            if total > limit:
                raise PermissionError("Unbounded LTX worker file")
            h.update(data)
    if total == 0:
        raise ValueError("Empty LTX worker file")
    return h.hexdigest()


def _sha(value):
    if type(value) is not str or not SHA.fullmatch(value):
        raise ValueError("SHA-256 digest required")
    return value


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def validate_intent(intent: dict) -> dict:
    """No filenames, commands, or authorization tokens may come from model/UI."""
    if type(intent) is not dict or set(intent) != {
        "project_id", "take_sha256", "layout_sha256", "look_sha256",
        "conditioning_sha256", "model_stack_sha256", "display_frames",
        "model_frames", "fps", "width", "height", "seed", "camera_id",
    }:
        raise ValueError("LTX host intent must be exact and versioned")
    if type(intent["project_id"]) is not str or not PROJECT.fullmatch(intent["project_id"]):
        raise ValueError("Canonical NVP project ID required")
    for key in ("take_sha256", "layout_sha256", "look_sha256", "conditioning_sha256", "model_stack_sha256"):
        _sha(intent[key])
    if (any(type(intent[k]) is not int for k in ("fps", "width", "height", "display_frames", "model_frames", "seed"))
        or intent["fps"] != 24
        or not (64 <= intent["width"] <= 2048 and intent["width"] % 64 == 0)
        or not (64 <= intent["height"] <= 2048 and intent["height"] % 64 == 0)
        or not (8 <= intent["display_frames"] <= 240 and intent["display_frames"] % 8 == 0)
        or intent["model_frames"] != intent["display_frames"] + 1
        or not (0 <= intent["seed"] < 2**63)
        or type(intent["camera_id"]) is not str
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", intent["camera_id"])):
        raise ValueError("Invalid 24-fps LTX 8k+1 grid/camera")
    return dict(intent)


def _write_new(path: Path, data: bytes):
    with path.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _journal(path: Path, obj: dict):
    # Distinct temp file, no PID replay; crash can only leave uncertain status.
    tmp = path.with_name("journal.pending")
    if tmp.exists() or tmp.is_symlink():
        raise RuntimeError("Unreconciled LTX journal pending")
    _write_new(tmp, _canonical(obj))
    os.replace(tmp, path)


def _check_exact_files(root: Path, permitted: frozenset):
    if any(p.is_symlink() or p.name not in permitted or not p.is_file()
           for p in root.iterdir()):
        raise PermissionError("Worker wrote unreviewed file, symlink or audio")


def admit_picture(root: Path, *, job_id: str, project_id: str, plan_sha256: str,
                  model_stack_sha256: str, picture_verifier, os_witness: dict,
                  model_witness: dict) -> dict:
    """Bounded quarantine admission. These witnesses are host-generated, never worker JSON."""
    if not callable(picture_verifier):
        raise TypeError("Independent decoder is mandatory")
    if (type(os_witness) is not dict or
        os_witness.get("scm_authenticated_receipt_verified") is not True or
        os_witness.get("job_id") != job_id or
        os_witness.get("plan_sha256") != plan_sha256 or
        os_witness.get("process_tree_custody_verified") is not True or
        os_witness.get("appcontainer_zero_network_caps_verified") is not True or
        os_witness.get("wfp_no_egress_verified") is not True or
        os_witness.get("efs_verified") is not True or
        type(os_witness.get("scm_receipt_sha256")) is not str or
        not SHA.fullmatch(os_witness["scm_receipt_sha256"])):
        raise PermissionError("Real independent native security witness absent")
    if (type(model_witness) is not dict or
        model_witness.get("model_loaded") is not True or
        model_witness.get("inference_executed") is not True or
        model_witness.get("gpu_execution_verified") is not True or
        model_witness.get("model_stack_sha256") != model_stack_sha256):
        raise PermissionError("Host cannot verify genuine native LTX execution")
    _check_exact_files(root, FILES_AFTER)
    receipt = root / "result.json"
    if receipt.stat().st_size > MAX_PLAN or receipt.stat().st_size < 2:
        raise ValueError("Invalid worker result length")
    data = json.loads(receipt.read_text("utf-8"))
    if type(data) is not dict or set(data) != {
        "format", "job_id", "project_id", "plan_sha256", "model_stack_sha256",
        "picture_sha256", "picture_frames", "fps", "width", "height", "audio_generated"
    } or data["format"] != RESULT or data["job_id"] != job_id or data["project_id"] != project_id or data["plan_sha256"] != plan_sha256 or data["model_stack_sha256"] != model_stack_sha256 or data["audio_generated"] is not False:
        raise PermissionError("Foreign, stale or unapproved worker picture receipt")
    expected = json.loads((root / "plan.json").read_text("utf-8"))
    if (expected.get("job_id") != job_id or
        type(data["picture_frames"]) is not int or data["picture_frames"] != expected["display_frames"] or
        type(data["fps"]) is not int or data["fps"] != 24 or
        type(data["width"]) is not int or data["width"] != expected["width"] or
        type(data["height"]) is not int or data["height"] != expected["height"]):
        raise PermissionError("Picture timing or geometry differs from authorized source")
    pic_sha = digest_file(root / "picture.mp4", MAX_PICTURE)
    if os_witness.get("picture_sha256") != pic_sha:
        raise PermissionError("SCM authenticated picture digest disagrees with filesystem")
    if pic_sha != _sha(data["picture_sha256"]):
        raise PermissionError("Picture bytes changed after worker output")
    decoded = picture_verifier(root / "picture.mp4", dict(expected), pic_sha)
    if (type(decoded) is not dict or decoded.get("independently_decoded") is not True or
        decoded.get("picture_sha256") != pic_sha or
        decoded.get("presented_frames") != expected["display_frames"] or
        decoded.get("fps") != 24 or decoded.get("pts_verified") is not True or
        decoded.get("audio_streams") != 0):
        raise PermissionError("Independent picture decode/timestamps not authenticated")
    if digest_file(root / "picture.mp4", MAX_PICTURE) != pic_sha:
        raise PermissionError("Picture mutated during native decoder verification")
    return {"state": "PICTURE_VERIFIED_UNAPPROVED", "job_id": job_id,
            "project_id": project_id, "picture_sha256": pic_sha,
            "source_take_sha256": expected["take_sha256"],
            "model_stack_sha256": model_stack_sha256,
            "plan_sha256": plan_sha256,
            "scm_receipt_sha256": os_witness["scm_receipt_sha256"],
            "picture_location": str((root / "picture.mp4").resolve()),
            "creator_approved": False, "publishable": False}


class ProtectedLtxHandoff:
    """Host-side R1 wire + R2 native custody; never exposed as a model tool."""

    def __init__(self, *, runtime_root: Path, installed_bootstrap: Path,
                 bootstrap_sha256: str, model_stack_sha256: str,
                 approved_code_roots: tuple[Path, ...], creator_approve,
                 take_verify, os_verify, model_verify, picture_verify):
        for callback in (creator_approve, take_verify, os_verify, model_verify, picture_verify):
            if not callable(callback):
                raise TypeError("Trusted creator/OS/model/picture authority required")
        self.runtime_root = Path(runtime_root)
        self.bootstrap = Path(installed_bootstrap)
        self.bootstrap_sha256 = _sha(bootstrap_sha256)
        self.model_stack_sha256 = _sha(model_stack_sha256)
        self.code_roots = tuple(Path(p) for p in approved_code_roots)
        self.approve, self.take_verify, self.os_verify, self.model_verify, self.picture_verify = (
            creator_approve, take_verify, os_verify, model_verify, picture_verify)
        if (not self.runtime_root.is_absolute() or not self.runtime_root.is_dir()
            or self.runtime_root.is_symlink() or not self.bootstrap.is_absolute()
            or self.bootstrap.is_symlink() or not self.bootstrap.is_file()
            or not self.code_roots or any(not p.is_absolute() or p.is_symlink() or not p.is_dir() for p in self.code_roots)
            or any(self.runtime_root.resolve().is_relative_to(p.resolve()) or p.resolve().is_relative_to(self.runtime_root.resolve()) for p in self.code_roots)
            or not any(self.bootstrap.resolve().is_relative_to(p.resolve()) for p in self.code_roots)):
            raise PermissionError("Reviewed code, bootstrap and private runtime must be separate")
        self._lock = threading.RLock()
        self._active = {}
        self._scm_active = {}  # Installed SCM stop controller; never a Python worker.
        self._cancelled = set()

    def cancel(self, job_id: str) -> bool:
        if type(job_id) is not str or not re.fullmatch(r"ltx_[0-9a-f]{24}", job_id):
            raise ValueError("Invalid job identity")
        with self._lock:
            proc = self._active.get(job_id)
            scm_cancel = self._scm_active.get(job_id)
            if proc is None and scm_cancel is None:
                return False
            self._cancelled.add(job_id)
        if scm_cancel is not None:
            # The installed native owner sends authorized SERVICE_CONTROL_STOP.
            # It must never report GPU quiescence on a mere STOP acknowledgment.
            return scm_cancel(job_id) is True
        proc.terminate_tree()
        return True

    def reconcile(self) -> list[str]:
        """Never infer successful results from a stale job journal or PID."""
        unresolved = []
        for root in sorted(self.runtime_root.glob("ltx_*")):
            if not root.is_dir() or root.is_symlink() or not re.fullmatch(r"ltx_[0-9a-f]{24}", root.name):
                continue
            jf = root / "journal.json"
            if jf.is_symlink() or not jf.is_file():
                continue
            state = json.loads(jf.read_text("utf-8"))
            if state.get("state") not in ("PICTURE_VERIFIED_UNAPPROVED", "FAILED_UNVERIFIED", "INTERRUPTED_UNVERIFIED"):
                state["state"] = "INTERRUPTED_UNVERIFIED"
                state["publishable"] = False
                _journal(jf, state)
                unresolved.append(root.name)
        return unresolved

    def run(self, *, intent: dict, layout: bytes, look: bytes,
            conditioning: bytes, max_memory_mb: int = 24576,
            timeout_s: int = 3600,
            preallocated_job_id: str | None = None,
            verify_installed_reservation=None,
            scm_owned_launch=None, scm_owned_cancel=None) -> dict:
        # Only a provisioned physical Windows host may perform protected LTX.
        if os.name != "nt":
            raise PermissionError("Native LTX requires the installed Windows AppContainer/EFS host")
        scm_mode = preallocated_job_id is not None
        if scm_mode:
            from backend.nvp_lu_scm_ltx_execution import require_installed_scm_stage
            require_installed_scm_stage(self.runtime_root,
                max_memory_mb=max_memory_mb, timeout_s=timeout_s,
                scm_owned_launch=scm_owned_launch, scm_owned_cancel=scm_owned_cancel)
        elif scm_owned_launch is not None or scm_owned_cancel is not None:
            raise PermissionError("Standalone LTX cannot borrow an SCM execution identity")
        plan = validate_intent(intent)
        if plan["model_stack_sha256"] != self.model_stack_sha256:
            raise PermissionError("Requested model stack differs from installed license-checked lock")
        if (any(type(x) is not bytes for x in (layout, look, conditioning)) or
            not (12 <= len(layout) <= MAX_LAYOUT and 32 <= len(look) <= MAX_LOOK and 2 <= len(conditioning) <= MAX_CONDITIONING)):
            raise ValueError("Derived LTX conditioning must be bounded immutable bytes")
        if not (layout[4:8] == b"ftyp" and look[:8] == b"\x89PNG\r\n\x1a\n"):
            raise PermissionError("Unrecognized derived layout/look container header")
        inputs = {"layout.mp4": layout, "look.png": look, "conditioning.json": conditioning}
        for name, value in inputs.items():
            if sha256(value).hexdigest() != plan[{"layout.mp4":"layout_sha256", "look.png":"look_sha256", "conditioning.json":"conditioning_sha256"}[name]]:
                raise PermissionError("Conditioning digest not tied to current immutable Take")
        if (type(max_memory_mb) is not int or not 4096 <= max_memory_mb <= 65536 or
            type(timeout_s) is not int or not 10 <= timeout_s <= 7200):
            raise ValueError("Finite protected LTX resource budget required")
        if digest_file(self.bootstrap, 64*1024*1024) != self.bootstrap_sha256:
            raise PermissionError("Installed LTX bootstrap executable changed")
        from backend.nvp_post01f_ltx_broker import LOCK_NAME, MAX_LOCK
        if digest_file(self.bootstrap.parent / LOCK_NAME, MAX_LOCK) != self.model_stack_sha256:
            raise PermissionError("Installed LTX model/runtime lock changed")
        source_scope = {"project_id":plan["project_id"], "take_sha256":plan["take_sha256"],
                        "camera_id":plan["camera_id"]}
        if self.take_verify(dict(source_scope)) is not True:
            raise PermissionError("Authoritative immutable Take did not verify before generation")
        # In Lu-connected GPU-lease mode the installed original NVP SCM
        # supervisor MUST reserve this exact original job BEFORE Lu unload.
        # A new random ID at LTX launch would defeat Core's signed worker-stop
        # binding. Standalone mode keeps its independent random job IDs.
        from backend.nvp_lu_ltx_preallocation import select_original_ltx_job
        job_id = select_original_ltx_job(preallocated_job_id=preallocated_job_id,
            verify_installed_reservation=verify_installed_reservation,
            project_id=plan["project_id"], take_sha256=plan["take_sha256"],
            camera_id=plan["camera_id"])
        plan = {"format": WIRE, **plan, "job_id": job_id}
        packed = _canonical(plan)
        if len(packed) > MAX_PLAN:
            raise ValueError("LTX job exceeds versioned IPC limit")
        plan_sha = sha256(packed).hexdigest()
        scope = {"job_id": job_id, "project_id":plan["project_id"],
                 "plan_sha256":plan_sha, "bootstrap_sha256":self.bootstrap_sha256,
                 "model_stack_sha256":self.model_stack_sha256,
                 "input_sha256":{k:sha256(v).hexdigest() for k,v in sorted(inputs.items())},
                 "memory_mb":max_memory_mb, "timeout_seconds":timeout_s}
        if self.approve(dict(scope)) is not True:
            raise PermissionError("Creator did not authorize exact protected generation")
        if digest_file(self.bootstrap, 64*1024*1024) != self.bootstrap_sha256:
            raise PermissionError("Installed LTX executable changed during creator approval")
        root = self.runtime_root / job_id
        root.mkdir(mode=0o700)
        proc = None
        state = {"format":JOURNAL, "job_id":job_id, "state":"PREPARING", "publishable":False}
        try:
            from backend.nvp_w1g_encrypted_source import require_efs_stage, verify_efs_inputs
            require_efs_stage(root)
            _journal(root / "journal.json", state)
            for name, blob in inputs.items():
                _write_new(root / name, blob)
            _write_new(root / "plan.json", packed)
            verify_efs_inputs(root, (*sorted(inputs), "plan.json", "journal.json"))
            state["state"] = "STAGED"
            _journal(root / "journal.json", state)
            if scm_mode:
                # The original SCM service is the ONLY process creator for
                # Lu-borrowed VRAM. No Python launch_contained/second Job exists.
                _write_new(root / "stdout.log", b"")
                _write_new(root / "stderr.log", b"")
                state["state"] = "RUNNING"
                _journal(root / "journal.json", state)
                native_scope = {
                    "job_id":job_id, "project_id":plan["project_id"],
                    "plan_sha256":plan_sha,
                    "bootstrap_sha256":self.bootstrap_sha256,
                    "model_stack_sha256":self.model_stack_sha256,
                    "layout_sha256":scope["input_sha256"]["layout.mp4"],
                    "look_sha256":scope["input_sha256"]["look.png"],
                    "conditioning_sha256":scope["input_sha256"]["conditioning.json"],
                    "take_sha256":plan["take_sha256"],
                    "camera_id":plan["camera_id"],
                }
                with self._lock:
                    self._scm_active[job_id] = scm_owned_cancel
                kernel = scm_owned_launch(dict(native_scope))
                from backend.nvp_lu_scm_ltx_execution import verify_original_scm_kernel_result
                kernel = verify_original_scm_kernel_result(kernel, job_id=job_id,
                    project_id=plan["project_id"], plan_sha256=plan_sha)
                with self._lock:
                    if job_id in self._cancelled:
                        raise InterruptedError("Creator cancelled original SCM LTX job")
            else:
                from backend.nvp_worker_containment import launch_contained
                with (root / "stdout.log").open("xb") as stdout, (root / "stderr.log").open("xb") as stderr, open(os.devnull,"rb") as stdin:
                    proc = launch_contained([str(self.bootstrap.resolve()), "--nvp-ltx-job", str((root / "plan.json").resolve())],
                        cwd=str(root), stdin=stdin, stdout=stdout, stderr=stderr,
                        memory_mb=max_memory_mb, windows_appcontainer_required=True,
                        appcontainer_code_roots=self.code_roots)
                    if getattr(proc, "sandbox_identity", None) != "windows-appcontainer-with-zero-network-capabilities":
                        raise PermissionError("Launcher did not produce genuine protected AppContainer")
                    with self._lock:
                        self._active[job_id] = proc
                    state["state"] = "RUNNING"
                    _journal(root / "journal.json", state)
                    try:
                        rc = proc.wait(timeout=timeout_s)
                    except subprocess.TimeoutExpired:
                        with self._lock:
                            self._cancelled.add(job_id)
                            proc.terminate_tree()
                        raise TimeoutError("LTX native worker exceeded approved deadline")
                    with self._lock:
                        if job_id in self._cancelled:
                            raise InterruptedError("Creator cancelled LTX after launch")
                        if rc != 0:
                            raise RuntimeError("Protected LTX worker failed")
                        # Verify the real AppContainer wrapper/Job/release-fence,
                        # not W1-G's generic WindowsJobProcess-only verifier.
                        from backend.nvp_post01f_native_custody import verified_ltx_appcontainer_exit
                        kernel = verified_ltx_appcontainer_exit(proc)
            model_witness = self.model_verify({**scope, "worker_pid":kernel["worker_pid"]}, root)
            if digest_file(self.bootstrap.parent / LOCK_NAME, MAX_LOCK) != self.model_stack_sha256:
                raise PermissionError("Reviewed model/runtime lock drifted during execution")
            if digest_file(self.bootstrap, 64*1024*1024) != self.bootstrap_sha256:
                raise PermissionError("Installed LTX broker mutated during execution")
            verify_efs_inputs(root, (*sorted(inputs), "plan.json", "journal.json", "picture.mp4", "result.json"))
            if any(digest_file(root/name, MAX_LAYOUT if name=="layout.mp4" else MAX_LOOK if name=="look.png" else MAX_CONDITIONING) != scope["input_sha256"][name] for name in inputs):
                raise PermissionError("Worker mutated source conditioning")
            if digest_file(root / "plan.json", MAX_PLAN) != plan_sha:
                raise PermissionError("Worker changed authorized IPC plan")
            if self.take_verify(dict(source_scope)) is not True:
                raise PermissionError("Original immutable Take changed during protected generation")
            pic_digest = digest_file(root / "picture.mp4", MAX_PICTURE)
            # os_verify must verify the exact independently signed SCM
            # envelope, including this actual picture hash and kernel PID.
            os_witness = self.os_verify({**scope, "picture_sha256":pic_digest}, dict(kernel))
            out = admit_picture(root, job_id=job_id, project_id=plan["project_id"],
                 plan_sha256=plan_sha, model_stack_sha256=self.model_stack_sha256,
                 picture_verifier=self.picture_verify, os_witness=os_witness, model_witness=model_witness)
            state["state"] = out["state"]
            state["picture_sha256"] = out["picture_sha256"]
            _journal(root / "journal.json", state)
            return out
        except BaseException:
            state["state"] = "FAILED_UNVERIFIED"
            if (root / "journal.json").is_file():
                _journal(root / "journal.json", state)
            raise
        finally:
            with self._lock:
                self._active.pop(job_id, None)
                self._scm_active.pop(job_id, None)
                self._cancelled.discard(job_id)
            if proc is not None and getattr(proc, "_worker", None) is not None:
                if proc.poll() is None:
                    proc.terminate_tree()
                proc.close()
