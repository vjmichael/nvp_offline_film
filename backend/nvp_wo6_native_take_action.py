"""WO6-05: creator-confirmed, host-granted immutable native Take action.

This is intentionally NOT part of NativeAiReadHost. Model proposals and
WO6-04 impact previews are never grants. A trusted desktop host must supply
two independent, current policy checks: human creative confirmation AND
native worker authorization. Jobs reuse NVP's durable ledger, immutable
ApprovedTaskBindings, OS containment and guarded cancellation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import time

from backend.nvp_ai_read_host import TrustedReadScope
from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_take import OpenUSDTakeCapture, MAX_CHECKPOINTS
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded, NativeCancelRequested
from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_host_lease import exclusive_worker_host
from backend.nvp_wo6_recovery import WO6DurableRecovery
from backend.nvp_wo6_impact_preview import preview_source_impact, _source_lifecycle_state

OPERATION = "nvp.film.create_frozen_take.v1"
FORMAT = "nvp.wo6.creator_approved_new_take_task.v1"
RECEIPT_FORMAT = "nvp.wo6.native_new_take_receipt.v1"


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _exact_source(index, pid, oid, revision, digest, kind):
    _id(oid, "approved source ID")
    if type(revision) is not int or revision < 1:
        raise ValueError("Exact positive original source revision required")
    row = index.read_revision(pid, oid, revision)
    if row["kind"] != kind or row["document_sha256"] != digest:
        raise PermissionError("Selected original source kind/SHA mismatch")
    current = index.read_revision(pid, oid)
    if current["revision"] != revision or current["document_sha256"] != digest:
        raise PermissionError("Source revision was superseded before execution")
    if _source_lifecycle_state(index, pid, oid) in ("RETIRED", "PURGED"):
        raise PermissionError("Retired original source cannot produce a new Take")
    return row


def _preflight(index, spec):
    pid = spec["project_id"]
    _require_pid(pid)
    _exact_source(index, pid, spec["scene_id"], spec["scene_revision"],
                  spec["scene_sha256"], "scene")
    _exact_source(index, pid, spec["timeline_id"], spec["timeline_revision"],
                  spec["timeline_sha256"], "temporal")
    # This intentionally refuses an old name even when an old Take was frozen.
    try:
        index.read_revision(pid, spec["take_id"])
    except KeyError:
        pass
    else:
        raise PermissionError("New Take ID already exists; never overwrite")
    capture = OpenUSDTakeCapture(index, verify_creator_action=lambda *_: False)
    source, timeline, _, duration = capture._sources(
        pid, spec["scene_id"], spec["scene_revision"],
        spec["timeline_id"], spec["timeline_revision"])
    if (source["document_sha256"] != spec["scene_sha256"] or
            timeline["document_sha256"] != spec["timeline_sha256"] or
            any(tick >= duration for tick in spec["sample_ticks"])):
        raise PermissionError("Source changed or sample tick outside duration")
    preview = preview_source_impact(
        index, pid, spec["scene_id"], spec["scene_revision"],
        spec["scene_sha256"], "retake",
        scene_id=spec.get("screenplay_scene_id"),
        screenplay_revision=spec.get("screenplay_revision"),
        expected_bible_digest=spec.get("expected_bible_digest"),
        max_nodes=32)
    if (preview["preview_sha256"] != spec["preview_sha256"] or
            preview["status"] != "READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT" or
            preview["indexed_downstream_truncated"]):
        raise PermissionError("Director source impact preview is stale/incomplete")
    return preview


class NativeTakeActionHost:
    """Private first-party host. Never expose stage/run methods as AI tools."""

    def __init__(self, index: FilmIndex, ledger: TaskLedger, job_root: Path, *,
                 confirm_creator, authorize_native):
        if (not isinstance(index, FilmIndex) or
                not isinstance(ledger, TaskLedger) or
                not callable(confirm_creator) or
                not callable(authorize_native)):
            raise TypeError("Native FilmIndex, ledger and two policy callbacks required")
        root = Path(job_root)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError("Host-owned job root must be absolute and not a symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root.resolve()
        self.index, self.ledger = index, ledger
        self.confirm_creator, self.authorize_native = (
            confirm_creator, authorize_native)
        self.python = Path(sys.executable).resolve()
        self.worker = (Path(__file__).resolve().parents[1] /
                       "tools" / "nvp_wo6_take_worker.py").resolve()
        self.owner = "wo6take_" + hashlib.sha256(
            str(self.root).encode("utf-8")).hexdigest()[:16]
        self.binding = ApprovedTaskBindings(ledger, approval_check=self._check)
        self.recovery = WO6DurableRecovery(ledger)

    def _check(self, approval_id, digest, document):
        if (document.get("format") != FORMAT or
                document.get("native_approval_id") != approval_id or
                document.get("operation") != OPERATION or
                document.get("kind") != "compositing" or
                hashlib.sha256(canonical_bytes(document)).hexdigest() != digest or
                time.time() >= document.get("expires_at", 0)):
            return False
        try:
            scope = TrustedReadScope(
                document["actor_id"], document["project_id"],
                document["turn_id"])
            creative = dict(document["creative_scope"])
            return (self.confirm_creator(document["creator_decision_id"],
                                         creative) is True and
                    self.authorize_native(scope, digest, dict(document)) is True)
        except (TypeError, ValueError, KeyError):
            return False

    def queue_new_take(self, scope: TrustedReadScope, *, creator_decision_id,
                       scene_id, scene_revision, scene_sha256,
                       timeline_id, timeline_revision, timeline_sha256,
                       new_take_id, sample_ticks, expected_preview_sha256,
                       screenplay_scene_id=None, screenplay_revision=None,
                       expected_bible_digest=None, ram_mb=4096,
                       expires_in_seconds=1800):
        if not isinstance(scope, TrustedReadScope):
            raise PermissionError("Host-created actor/project/turn scope required")
        _require_pid(scope.project_id)
        for value in (scene_id, timeline_id, new_take_id):
            _id(value, "NVP native source or new Take identity")
        if len({scene_id, timeline_id, new_take_id}) != 3:
            raise ValueError("Original sources and new Take ID must differ")
        if (type(sample_ticks) is not list or
                not 1 <= len(sample_ticks) <= MAX_CHECKPOINTS or
                any(type(t) is not int or t < 0 for t in sample_ticks) or
                sorted(set(sample_ticks)) != sample_ticks):
            raise ValueError("Bounded sorted unique exact Film Time samples required")
        if (type(ram_mb) is not int or not 1024 <= ram_mb <= 8192 or
                type(expires_in_seconds) is not int or
                not 60 <= expires_in_seconds <= 3600):
            raise ValueError("Bounded worker memory and approval expiry required")
        if (type(creator_decision_id) is not str or
                not 1 <= len(creator_decision_id) <= 120 or
                type(expected_preview_sha256) is not str or
                len(expected_preview_sha256) != 64):
            raise ValueError("Exact human decision and impact digest required")
        if (screenplay_scene_id is None) != (screenplay_revision is None):
            raise ValueError("Exact screenplay scene and revision must accompany each other")
        spec = {
            "format": FORMAT, "operation": OPERATION, "kind": "compositing",
            "actor_id": scope.actor_id, "turn_id": scope.turn_id,
            "project_id": scope.project_id,
            "creator_decision_id": creator_decision_id,
            "scene_id": scene_id, "scene_revision": scene_revision,
            "scene_sha256": scene_sha256,
            "timeline_id": timeline_id, "timeline_revision": timeline_revision,
            "timeline_sha256": timeline_sha256,
            "take_id": new_take_id, "sample_ticks": list(sample_ticks),
            "screenplay_scene_id": screenplay_scene_id,
            "screenplay_revision": screenplay_revision,
            "expected_bible_digest": expected_bible_digest,
            "preview_sha256": expected_preview_sha256,
            "ram_mb": ram_mb,
        }
        _preflight(self.index, spec)
        creative = {
            "operation": OPERATION, "project_id": scope.project_id,
            "new_take_id": new_take_id, "original_scene_sha": scene_sha256,
            "original_timeline_sha": timeline_sha256,
            "preview_sha256": expected_preview_sha256,
            "sample_ticks": list(sample_ticks), "old_takes_immutable": True,
            "approved_bible_digest": expected_bible_digest,
            "no_existing_dcp_mutation": True,
        }
        spec["creative_scope"] = creative
        task_id = "wo6take_" + secrets.token_hex(12)
        approval_id = "wo6approval_" + secrets.token_hex(12)
        spec.update(task_id=task_id, native_approval_id=approval_id,
                    python_sha256=digest_file(self.python),
                    worker_sha256=digest_file(self.worker),
                    expires_at=time.time() + expires_in_seconds)
        raw = canonical_bytes(spec)
        digest = hashlib.sha256(raw).hexdigest()
        # Both policy gates run BEFORE writing a job spec or scheduling work.
        if not self._check(approval_id, digest, spec):
            raise PermissionError("Creator confirmation or separate host grant denied")
        folder = self.root / task_id
        folder.mkdir(mode=0o700, exist_ok=False)
        try:
            with (folder / "task.json").open("xb") as out:
                out.write(raw)
                out.flush()
                __import__("os").fsync(out.fileno())
            self.binding.enqueue(
                AdmissionRequest(task_id, "compositing",
                                 "Create approved new immutable OpenUSD Take",
                                 ram_mb),
                owner_key=self.owner, lane="standard",
                approval_id=approval_id, document=spec)
        except BaseException:
            shutil.rmtree(folder)
            raise
        return {
            "task_id": task_id, "state": "QUEUED", "native_worker_started": False,
            "new_take_id": new_take_id, "preview_sha256": expected_preview_sha256,
            "creator_and_host_grants_not_model_issued": True,
        }

    @exclusive_worker_host
    def run_next(self, *, timeout_seconds=900):
        claimed = self.binding.claim_next(owner_key=self.owner)
        if not claimed or not claimed["admitted"]:
            return claimed
        task_id = claimed["task_id"]
        worker = None
        cleaned = False
        try:
            spec = self.binding.verified_spec(task_id, owner_key=self.owner)
            folder = self.root / task_id
            spec_path = folder / "task.json"
            if (folder.is_symlink() or spec_path.is_symlink() or
                    digest_file(self.python) != spec["python_sha256"] or
                    digest_file(self.worker) != spec["worker_sha256"] or
                    hashlib.sha256(spec_path.read_bytes()).hexdigest() !=
                    hashlib.sha256(canonical_bytes(spec)).hexdigest()):
                raise PermissionError("Native worker/source task pin changed")
            _preflight(self.index, spec)
            self.ledger.update(task_id, "preparing_scene",
                               "Creator and host grants verified; checking native source")
            command = [
                str(self.python), str(self.worker), "--spec", str(spec_path),
                "--studio-db", str(self.index.studio.db_path),
                "--expected-sha", hashlib.sha256(canonical_bytes(spec)).hexdigest(),
            ]
            with (folder / "stdout.log").open("wb") as out, (
                    folder / "stderr.log").open("wb") as err:
                worker = launch_contained(
                    command, cwd=str(folder), stdout=out, stderr=err,
                    memory_mb=spec["ram_mb"])
                self.ledger.update(task_id, "building_scene",
                                   "Contained native frozen Take creation")
                def cancelled():
                    if self.recovery.cancel_requested(task_id):
                        return True
                    try:
                        self.binding.verified_spec(task_id, owner_key=self.owner)
                        return False
                    except PermissionError:
                        return True
                status = wait_guarded(
                    worker, self.ledger, task_id,
                    timeout_seconds=timeout_seconds, should_cancel=cancelled)
                if status != 0:
                    raise RuntimeError("Contained native Take worker failed")
                worker.close()
                cleaned = True
            receipt_path = folder / "receipt.json"
            if receipt_path.is_symlink():
                raise PermissionError("Native receipt symlink refused")
            receipt = json.loads(receipt_path.read_text("utf-8"))
            verified = OpenUSDTakeCapture(
                self.index, verify_creator_action=lambda *_: False
            ).verify_take(spec["project_id"], spec["take_id"])
            if (receipt.get("format") != RECEIPT_FORMAT or
                    receipt.get("task_id") != task_id or
                    receipt.get("take_document_sha256") !=
                    verified["take_document_sha256"] or
                    receipt.get("scene_sha256") != spec["scene_sha256"] or
                    receipt.get("timeline_sha256") != spec["timeline_sha256"] or
                    receipt.get("rendered_frames") is not False or
                    receipt.get("existing_dcp_replaced") is not False):
                raise RuntimeError("Native Take output cannot be independently verified")
            # A human or trusted host may revoke during native execution.
            # A completed Take is immutable, but its job must not be called
            # creator-accepted after a revocation or expiry.
            if self.recovery.cancel_requested(task_id):
                raise NativeCancelRequested("Creator cancelled completed source operation")
            if not self._check(spec["native_approval_id"],
                               hashlib.sha256(canonical_bytes(spec)).hexdigest(),
                               spec):
                raise PermissionError("Creator or native grant revoked before acceptance")
            self.ledger.update(task_id, "verifying_output",
                               "Reopened original scene, timed events and frozen Take")
            self.recovery.finish_verified(
                task_id, detail="New immutable source Take verified; film not rendered")
            return {"task_id": task_id, "state": "SUCCEEDED",
                    "new_take_id": spec["take_id"],
                    "take_document_sha256": verified["take_document_sha256"],
                    "native_worker_executed": True, "film_delivered": False}
        except BaseException as error:
            if worker is not None:
                try:
                    if worker.poll() is None:
                        worker.terminate_tree()
                    worker.close()
                    cleaned = True
                except BaseException:
                    cleaned = False
            if cleaned or worker is None:
                state = self.ledger.get_task(task_id)
                if state and state["state"] == "ACTIVE":
                    # A worker can crash after the immutable FilmIndex commit.
                    # NEVER retry automatically or claim a rollback.
                    self.ledger.finish(
                        task_id, "CANCELLED" if isinstance(error, NativeCancelRequested) else "INTERRUPTED",
                        "Cancelled after contained worker cleanup; source commit may still exist" if isinstance(error, NativeCancelRequested) else
                        "Worker stopped; source Take commit may require reconciliation")
            raise
