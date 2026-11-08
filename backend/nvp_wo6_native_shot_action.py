"""WO6-05: director-confirmed native camera, blocking and lighting shot operations.

Native host only: no model-executable capability and no direct filesystem or
render authority. Reuses existing SHOT-01 OpenUSD authoring, ApprovedTaskBindings,
TaskLedger, real resource guards, containment and SHA-verifiable source custody.
"""
from __future__ import annotations

import hashlib
import os
import json
from pathlib import Path
import secrets
import shutil
import sys
import time

from backend.nvp_ai_read_host import TrustedReadScope
from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_shot_overrides import (
    OpenUSDShotOverrides, _normalize, _author_layer, _sha as _shot_sha,
    MAX_OPINIONS, PURPOSES, CONTINUITY,
)
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded, NativeCancelRequested
from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_host_lease import exclusive_worker_host
from backend.nvp_wo6_kernel_attestation import (
    persist_windows_job_identity, immutable_job_name,
    attest_windows_job_stopped)
from backend.nvp_wo6_recovery import WO6DurableRecovery
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_native_take_action import digest_file, _exact_source

FORMAT = "nvp.wo6.native_shot_action_spec.v1"
RECEIPT = "nvp.wo6.native_shot_action_receipt.v1"
ACTION_KINDS = {
    "camera": ("revise_camera", frozenset({
        "translation_offset", "camera_focal_length_mm", "camera_f_stop",
        "camera_focus_distance_m", "camera_sensor_width_mm",
        "camera_sensor_height_mm",
    }), frozenset({"camera"})),
    "blocking": ("revise_actor_performance", frozenset({
        "translation_offset", "visibility", "eyeline_target",
    }), frozenset({"actor", "prop"})),
    "lighting": ("revise_scene", frozenset({
        "translation_offset", "visibility", "light_intensity",
    }), frozenset({"light"})),
}


AI_REVIEW_FIELDS = frozenset({
    "proposal_id","take_sha256","model_text_sha256",
    "verified_source_context_sha256","film_time_tick",
    "director_selected_action_kind",
})
_HEX = frozenset("0123456789abcdef")


def _validate_ai_review_context(review, *, action_kind, take_sha256):
    """Only human-reviewed, host-built *provenance*, never executable model text."""
    if review is None:
        return None
    if type(review) is not dict or set(review) != AI_REVIEW_FIELDS:
        raise ValueError("AI consultation must be exact bounded host provenance")
    if (type(review["proposal_id"]) is not str or
            not review["proposal_id"].startswith("wo6proposal_") or
            len(review["proposal_id"]) != 36 or
            any(c not in _HEX for c in review["proposal_id"][12:])):
        raise ValueError("Invalid native AI suggestion ID")
    for key in ("take_sha256","model_text_sha256",
                "verified_source_context_sha256"):
        val=review[key]
        if (type(val) is not str or len(val)!=64 or
                any(c not in _HEX for c in val)):
            raise ValueError("Unsealed AI source SHA")
    if (review["take_sha256"]!=take_sha256 or
            review["director_selected_action_kind"]!=action_kind or
            type(review["film_time_tick"]) is not str or
            len(review["film_time_tick"])>16 or
            not review["film_time_tick"].isascii() or
            not review["film_time_tick"].isdecimal() or
            str(int(review["film_time_tick"]))!=review["film_time_tick"]):
        raise PermissionError("Reviewed advice does not match director-selected source/action")
    return dict(review)


def _check_shot_source(index, spec):
    pid = spec["project_id"]
    _require_pid(pid)
    _id(spec["shot_id"], "new director shot identity")
    if spec["shot_id"] in {spec["take_id"], spec["scene_id"]}:
        raise ValueError("New shot needs independent immutable identity")
    _exact_source(index, pid, spec["scene_id"], spec["scene_revision"],
                  spec["scene_sha256"], "scene")
    if type(spec["expected_revision"]) is not int or spec["expected_revision"] != 0:
        raise ValueError("First native shot bridge accepts new immutable shot IDs only")
    try:
        index.read_revision(pid, spec["shot_id"])
    except KeyError:
        pass
    else:
        raise PermissionError("Existing director shot cannot be overwritten")
    source_take = index.read_revision(pid, spec["take_id"], 1)
    if (source_take["kind"] != "take" or
            source_take["document_sha256"] != spec["take_sha256"] or
            source_take["data"].get("scene_id") != spec["scene_id"] or
            source_take["data"].get("scene_revision") != spec["scene_revision"] or
            source_take["data"].get("scene_document_sha256") != spec["scene_sha256"]):
        raise PermissionError("Native shot is not bound to the selected frozen Take")
    proof = OpenUSDTakeCapture(
        index, verify_creator_action=lambda *_: False).verify_take(
            pid, spec["take_id"])
    if proof["take_document_sha256"] != spec["take_sha256"]:
        raise PermissionError("Frozen original Take could not be reopened")
    shot = OpenUSDShotOverrides(index, verify_director_action=lambda *_: False)
    _, scene, stage = shot._take(pid, spec["take_id"])
    kind = spec["action_kind"]
    if kind not in ACTION_KINDS:
        raise ValueError("Only host-supported shot action types are allowed")
    change_kind, permitted, roles = ACTION_KINDS[kind]
    if (type(spec["changes"]) is not list or
            not 1 <= len(spec["changes"]) <= MAX_OPINIONS or
            any(type(x) is not dict or
                x.get("property") not in permitted or
                scene["data"]["prim_roles"].get(x.get("path")) not in roles
                for x in spec["changes"])):
        raise PermissionError("Property or actor role exceeds approved shot scope")
    if "reviewed_ai_consultation" in spec:
        reviewed=_validate_ai_review_context(
            spec["reviewed_ai_consultation"],
            action_kind=kind,take_sha256=spec["take_sha256"])
        if (spec.get("creative_scope",{}).get(
                "reviewed_ai_consultation")!=reviewed or
                spec["creative_scope"].get("model_text_is_authority") is not False):
            raise PermissionError("Reviewed AI provenance differs from OS creative approval")
    normalized = _normalize(spec["changes"], scene, stage)
    if normalized != spec["changes"]:
        raise PermissionError("Shot opinions are not canonical")
    if _shot_sha(_author_layer(normalized)) != spec["shot_layer_sha256"]:
        raise PermissionError("Native USD opinion layer digest changed")
    preview = preview_source_impact(
        index, pid, spec["scene_id"], spec["scene_revision"],
        spec["scene_sha256"], change_kind,
        scene_id=spec.get("screenplay_scene_id"),
        screenplay_revision=spec.get("screenplay_revision"),
        expected_bible_digest=spec.get("expected_bible_digest"),
        max_nodes=32)
    if (preview["preview_sha256"] != spec["preview_sha256"] or
            preview["status"] != "READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT" or
            preview["indexed_downstream_truncated"]):
        raise PermissionError("Director's source-impact preview requires refresh")
    return source_take, scene, preview


class NativeShotActionHost:
    """Native-only operation bridge: camera, blocking, lighting; never an AI tool."""

    def __init__(self, index: FilmIndex, ledger: TaskLedger, root: Path, *,
                 confirm_creator, authorize_native):
        if (not isinstance(index, FilmIndex) or
                not isinstance(ledger, TaskLedger) or
                not callable(confirm_creator) or
                not callable(authorize_native)):
            raise TypeError("Verified FilmIndex, task ledger and two policies needed")
        root = Path(root)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError("Host job root must be absolute and non-symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root.resolve()
        self.index, self.ledger = index, ledger
        self.creator, self.authorize = confirm_creator, authorize_native
        self.python = Path(sys.executable).resolve()
        self.frozen_worker = bool(getattr(sys, "frozen", False))
        # The installer bundles NVP.exe, not an independent python.exe or
        # loose .py tool. Its private --nvp-wo6-worker entrypoint performs
        # the same durable admission checks in a separate contained process.
        self.worker = (self.python if self.frozen_worker else
                       (Path(__file__).resolve().parents[1] /
                        "tools" / "nvp_wo6_shot_worker.py").resolve())
        self.owner = "wo6shot_" + hashlib.sha256(
            str(self.root).encode()).hexdigest()[:16]
        self.binding = ApprovedTaskBindings(ledger, approval_check=self._check)
        self.recovery = WO6DurableRecovery(ledger)

    def _check(self, approval_id, digest, doc):
        try:
            if (doc["format"] != FORMAT or
                    doc["operation"] != "nvp.film.author_director_shot.v1" or
                    doc["kind"] != "compositing" or
                    doc["native_approval_id"] != approval_id or
                    hashlib.sha256(canonical_bytes(doc)).hexdigest() != digest or
                    time.time() >= doc["expires_at"]):
                return False
            scope = TrustedReadScope(
                doc["actor_id"], doc["project_id"], doc["turn_id"])
            return (self.creator(doc["creator_decision_id"],
                                 dict(doc["creative_scope"])) is True and
                    self.authorize(scope, digest, dict(doc)) is True)
        except (KeyError, TypeError, ValueError):
            return False

    def queue_shot(self, scope: TrustedReadScope, *, creator_decision_id,
                   action_kind, shot_id, take_id, take_sha256,
                   scene_id, scene_revision, scene_sha256,
                   start_tick, end_tick, changes, purpose,
                   continuity_policy, reason, expected_preview_sha256,
                   screenplay_scene_id=None, screenplay_revision=None,
                   expected_bible_digest=None, ram_mb=4096, expires_in_seconds=1800,
                   ai_review_context=None):
        if not isinstance(scope, TrustedReadScope):
            raise PermissionError("Authenticated host-owned scope required")
        if (type(action_kind) is not str or action_kind not in ACTION_KIN or
                type(start_tick) is not int or type(end_tick) is not int or
                start_tick < 0 or end_tick <= start_tick or
                type(changes) is not list or not 1 <= len(changes) <= MAX_OPINIONS or
                purpose not in PURPOSES or continuity_policy not in CONTINUITY or
                type(reason) is not str or not 1 <= len(reason.strip()) <= 512 or
                type(creator_decision_id) is not str or not creator_decision_id or
                len(creator_decision_id) > 120 or
                type(ram_mb) is not int or not 1024 <= ram_mb <= 8192 or
                type(expires_in_seconds) is not int or
                not 60 <= expires_in_seconds <= 3600):
            raise ValueError("Typed bounded director shot metadata required")
        if (screenplay_scene_id is None) != (screenplay_revision is None):
            raise ValueError("Screenplay scene and exact revision must agree")
        for value in (shot_id, take_id, scene_id):
            _id(value, "shot identity or original source")
        if type(expected_preview_sha256) is not str or len(expected_preview_sha256) != 64:
            raise ValueError("Original approved source impact SHA is required")
        reviewed_ai=_validate_ai_review_context(
            ai_review_context,action_kind=action_kind,take_sha256=take_sha256)
        spec = {
            "format": FORMAT, "operation": "nvp.film.author_director_shot.v1",
            "kind": "compositing", "actor_id": scope.actor_id,
            "project_id": scope.project_id, "turn_id": scope.turn_id,
            "creator_decision_id": creator_decision_id,
            "action_kind": action_kind, "shot_id": shot_id,
            "take_id": take_id, "take_sha256": take_sha256,
            "scene_id": scene_id, "scene_revision": scene_revision,
            "scene_sha256": scene_sha256,
            "start_tick": start_tick, "end_tick": end_tick,
            "changes": changes, "purpose": purpose,
            "continuity_policy": continuity_policy, "reason": reason.strip(),
            "expected_revision": 0, "preview_sha256": expected_preview_sha256,
            "screenplay_scene_id": screenplay_scene_id,
            "screenplay_revision": screenplay_revision,
            "expected_bible_digest": expected_bible_digest, "ram_mb": ram_mb,
        }
        if reviewed_ai is not None:
            # The native first-party creator dialog and durable sealed
            # receipt include consultation evidence; its plain-text model
            # output never enters OpenUSD opinions or worker arguments.
            spec["reviewed_ai_consultation"]=reviewed_ai
        # Normalize before creator sees exact committed proposed values;
        # the native stage validates prim existence, camera/light schema.
        shot = OpenUSDShotOverrides(
            self.index, verify_director_action=lambda *_: False)
        _, scene, stage = shot._take(scope.project_id, take_id)
        spec["changes"] = _normalize(changes, scene, stage)
        spec["shot_layer_sha256"] = _shot_sha(_author_layer(spec["changes"]))
        _check_shot_source(self.index, spec)
        creative = {
            "operation": spec["operation"], "action_kind": action_kind,
            "project_id": scope.project_id, "shot_id": shot_id,
            "take_id": take_id, "take_sha256": take_sha256,
            "scene_sha256": scene_sha256,
            "director_shot_opinion_sha256": spec["shot_layer_sha256"],
            "start_tick": start_tick, "end_tick": end_tick,
            "typed_changes": spec["changes"], "purpose": purpose,
            "continuity_policy": continuity_policy, "reason": reason.strip(),
            "preview_sha256": expected_preview_sha256,
            "no_original_take_mutation": True, "renders_finished": False,
        }
        if reviewed_ai is not None:
            creative["reviewed_ai_consultation"]=reviewed_ai
            creative["model_text_is_authority"]=False
            creative["director_typed_shot_parameters_independently"]=True
        spec["creative_scope"] = creative
        task_id = "wo6shot_" + secrets.token_hex(12)
        approval = "wo6approval_" + secrets.token_hex(12)
        spec.update(task_id=task_id, native_approval_id=approval,
                    python_sha256=digest_file(self.python),
                    worker_sha256=digest_file(self.worker),
                    expires_at=time.time() + expires_in_seconds)
        spec_digest = hashlib.sha256(canonical_bytes(spec)).hexdigest()
        if not self._check(approval, spec_digest, spec):
            raise PermissionError("Director or native host approval denied")
        folder = self.root / task_id
        folder.mkdir(mode=0o700, exist_ok=False)
        try:
            raw = canonical_bytes(spec)
            with (folder / "task.json").open("xb") as stream:
                stream.write(raw)
                stream.flush()
                __import__("os").fsync(stream.fileno())
            if os.name=="nt":
                persist_windows_job_identity(
                    folder,task_id=task_id,
                    spec_sha256=hashlib.sha256(canonical_bytes(spec)).hexdigest(),
                    owner=self.owner)
            self.binding.enqueue(
                AdmissionRequest(task_id, "compositing",
                                 "New approved OpenUSD director shot", ram_mb),
                owner_key=self.owner, lane="standard",
                approval_id=approval, document=spec)
        except BaseException:
            shutil.rmtree(folder)
            raise
        return {"task_id": task_id, "state": "QUEUED",
                "new_shot_id": shot_id, "native_worker_started": False,
                "human_and_host_permission_required": True}

    @exclusive_worker_host
    def run_next(self, *, timeout_seconds=900, expected_task_id=None):
        claim = self.binding.claim_next(
            owner_key=self.owner,expected_task_id=expected_task_id)
        if not claim or not claim["admitted"]:
            return claim
        task_id = claim["task_id"]
        worker = None
        cleaned = False
        try:
            spec = self.binding.verified_spec(task_id, owner_key=self.owner)
            folder = self.root / task_id
            spec_path = folder / "task.json"
            raw = canonical_bytes(spec)
            if (folder.is_symlink() or spec_path.is_symlink() or
                    spec_path.read_bytes() != raw or
                    digest_file(self.python) != spec["python_sha256"] or
                    digest_file(self.worker) != spec["worker_sha256"]):
                raise PermissionError("Native approved shot bytes/tool pin changed")
            _check_shot_source(self.index, spec)
            if os.name=="nt" and not attest_windows_job_stopped(
                    folder,task_id=task_id,
                    spec_sha256=hashlib.sha256(raw).hexdigest(),
                    owner=self.owner):
                raise PermissionError("Native Windows Job Object already owns task")
            with (folder / "stdout.log").open("wb") as out, (
                    folder / "stderr.log").open("wb") as err:
                worker = launch_contained(
                    (([str(self.python), "--nvp-wo6-worker", "shot"] if
                      self.frozen_worker else [str(self.python), str(self.worker)])
                     + ["--spec", str(spec_path),
                     "--studio-db", str(self.index.studio.db_path),
                     "--expected-sha", hashlib.sha256(raw).hexdigest(),
                     "--ledger-db", str(self.ledger.db_path),
                     "--owner-key", self.owner]),
                    cwd=str(folder), stdout=out, stderr=err,
                    memory_mb=spec["ram_mb"],
                    windows_job_name=(
                        immutable_job_name(task_id) if os.name=="nt" else None))
                self.ledger.update(task_id, "building_scene",
                                   "Authoring contained director shot-local OpenUSD layer")
                def cancelled():
                    if self.recovery.cancel_requested(task_id):
                        return True
                    try:
                        self.binding.verified_spec(task_id, owner_key=self.owner)
                        return False
                    except PermissionError:
                        return True
                if wait_guarded(worker, self.ledger, task_id,
                                timeout_seconds=timeout_seconds,
                                should_cancel=cancelled) != 0:
                    raise RuntimeError("Native shot worker returned failure")
                worker.close()
                cleaned = True
            receipt_path = folder / "receipt.json"
            if receipt_path.is_symlink():
                raise RuntimeError("Native shot receipt is a symlink")
            receipt = json.loads(receipt_path.read_text("utf-8"))
            record = self.index.read_revision(
                spec["project_id"], spec["shot_id"], 1)
            shooter = OpenUSDShotOverrides(
                self.index, verify_director_action=lambda *_: False)
            evaluation = shooter.evaluate(
                spec["project_id"], spec["shot_id"], 1,
                tick=spec["start_tick"])
            if (receipt.get("format") != RECEIPT or
                    receipt.get("task_id") != task_id or
                    receipt.get("shot_sha256") != record["document_sha256"] or
                    receipt.get("take_sha256") != spec["take_sha256"] or
                    receipt.get("reviewed_ai_consultation") !=
                        spec.get("reviewed_ai_consultation") or
                    receipt.get("model_instruction_executed") is not False or
                    receipt.get("model_approval_accepted") is not False or
                    evaluation["shot_document_sha256"] != record["document_sha256"] or
                    record["data"]["usd_layer_sha256"] != spec["shot_layer_sha256"] or
                    record["data"]["original_scene_modified"] is not False or
                    record["data"]["original_performance_modified"] is not False or
                    record["data"]["frames_rendered"] is not False):
                raise RuntimeError("Director shot native receipt does not match actual layer")
            if self.recovery.cancel_requested(task_id):
                raise NativeCancelRequested("Creator cancelled completed shot operation")
            _exact_source(
                self.index, spec["project_id"], spec["scene_id"],
                spec["scene_revision"], spec["scene_sha256"], "scene")
            if not self._check(spec["native_approval_id"],
                               hashlib.sha256(raw).hexdigest(), spec):
                raise PermissionError("Director or host approval revoked after shot worker")
            self.ledger.update(task_id, "verifying_output",
                               "Reopened exact immutable shot and original Take")
            self.recovery.finish_verified(
                task_id, detail="New shot override verified; film remains unrendered")
            return {"task_id": task_id, "state": "SUCCEEDED",
                    "shot_id": spec["shot_id"],
                    "shot_document_sha256": record["document_sha256"],
                    "reviewed_ai_consultation":
                        spec.get("reviewed_ai_consultation"),
                    "model_instruction_executed":False,
                    "new_take_created": False, "film_delivered": False}
        except BaseException as error:
            if worker is not None:
                try:
                    if worker.poll() is None:
                        worker.terminate_tree()
                    worker.close()
                    cleaned = True
                except BaseException:
                    cleaned = False
            if worker is None or cleaned:
                state = self.ledger.get_task(task_id)
                if state and state["state"] == "ACTIVE":
                    self.ledger.finish(
                        task_id, "CANCELLED" if isinstance(error, NativeCancelRequested) else "INTERRUPTED",
                        "Cancelled after worker cleanup; shot revision may still exist" if isinstance(error, NativeCancelRequested) else
                        "Native shot interrupted; immutable commit needs reconciliation")
            raise
