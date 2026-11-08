"""WO6-05: creator-approved film-time shot sequences and derived color decisions.

Native host only. These are source-bound DATA authorship operations, not
rendering, final mastering, film-review acceptance, or AI self-authorization.
The worker reuses first-party DA-01 and DA-06 implementations.
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
from backend.nvp_exact_time_shots import ExactTimeShotSequence, PATTERNS, MAX_SHOTS, _tick
from backend.nvp_film_index import FilmIndex, _id, _sha
from backend.nvp_native_color_decisions import NativeColorDecisions, validate_parameters
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded, NativeCancelRequested
from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_host_lease import exclusive_worker_host
from backend.nvp_wo6_kernel_attestation import (
    persist_windows_job_identity, immutable_job_name,
    attest_windows_job_stopped)
from backend.nvp_wo6_impact_preview import preview_source_impact, _source_lifecycle_state
from backend.nvp_wo6_native_take_action import digest_file, _exact_source
from backend.nvp_wo6_recovery import WO6DurableRecovery
from backend.nvp_wo6_native_shot_action import _validate_ai_review_context
from backend.nvp_wo6_scene_context import assemble_film_crew_context
from backend.nvp_wo6_sound_editorial_decisions import (
    preflight_sound_cue,preflight_editorial_cut,
    verify_sound_cue,verify_editorial_cut,typed_decision_sha)

FORMAT = "nvp.wo6.creator_authorized_data_decision.v1"
RECEIPT = "nvp.wo6.native_data_decision_receipt.v1"
OPERATION = "nvp.film.author_data_decision.v1"
KINDS = ("color", "camera_sequence", "sound_cue", "editorial_cut")


def _preflight(index, spec):
    pid = spec["project_id"]
    _id(spec["decision_id"], "new decision identity")
    if spec["decision_kind"] not in KINDS:
        raise ValueError("Unsupported native decision type")
    try:
        index.read_revision(pid, spec["decision_id"])
    except KeyError:
        pass
    else:
        raise PermissionError("A decision cannot rewrite any existing FilmIndex object")
    if spec["decision_kind"] == "color":
        take_id, take_sha = spec["source_id"], spec["source_sha256"]
        take = index.read_revision(pid, take_id, 1)
        if (take["kind"] != "take" or take["document_sha256"] != take_sha or
                take["data"].get("frozen") is not True or
                _source_lifecycle_state(index, pid, take_id) in ("RETIRED", "PURGED")):
            raise PermissionError("New color decisions require a non-retired exact frozen Take")
        proof = OpenUSDTakeCapture(
            index, verify_creator_action=lambda *_: False).verify_take(pid, take_id)
        if proof["take_document_sha256"] != take_sha:
            raise PermissionError("Original OpenUSD Take did not reopen")
        if (spec["decision_id"] == take_id or
                validate_parameters(spec["payload"]) != spec["payload"]):
            raise ValueError("Invalid non-destructive color decision parameters")
        change_kind = "revise_color"
    elif spec["decision_kind"]=="sound_cue":
        preflight_sound_cue(index,spec)
        change_kind="revise_sound"
    elif spec["decision_kind"]=="editorial_cut":
        draft=preflight_editorial_cut(index,spec)
        change_kind="revise_edit"
    else:
        scene_id = spec["source_id"]
        _exact_source(index, pid, scene_id, spec["source_revision"],
                      spec["source_sha256"], "scene")
        if spec["decision_id"] == scene_id:
            raise ValueError("Camera timeline cannot reuse the original scene identity")
        shots = spec["payload"]
        if type(shots) is not list or not 1 <= len(shots) <= MAX_SHOTS:
            raise ValueError("Camera timeline requires 1..128 bounded observations")
        sequence = ExactTimeShotSequence(index)
        _, cameras = sequence._scene(pid, scene_id, spec["source_revision"])
        duration = _tick(spec["duration_tick"], "camera timeline duration", minimum=1)
        seen, previous_end = set(), 0
        for shot in shots:
            if type(shot) is not dict or set(shot) != {
                "shot_id", "camera_path", "start_tick", "end_tick", "pattern"
            }:
                raise ValueError("Exact Film Time camera shot fields required")
            _id(shot["shot_id"], "unique camera shot")
            start = _tick(shot["start_tick"], "camera start")
            end = _tick(shot["end_tick"], "camera end", minimum=1)
            if (shot["shot_id"] in seen or
                    shot["camera_path"] not in cameras or
                    shot["pattern"] not in PATTERNS or
                    start < previous_end or end <= start or end > duration):
                raise PermissionError("Camera observations overlap, have bad identity or exceed scene")
            previous_end = end
            seen.add(shot["shot_id"])
        change_kind = "revise_camera"
    if spec["decision_kind"] in ("sound_cue","editorial_cut"):
        if spec.get("typed_preview_sha256")!=typed_decision_sha(spec):
            raise PermissionError("Human typed sound/edit preview changed before native worker admission")
    if "reviewed_ai_consultation" in spec:
        reviewed=_validate_ai_review_context(
            spec["reviewed_ai_consultation"],
            action_kind=spec["decision_kind"],
            take_sha256=spec["reviewed_ai_consultation"]["take_sha256"])
        if (spec.get("creative_scope",{}).get("reviewed_ai_consultation")!=reviewed
                or spec["creative_scope"].get("model_text_is_authority") is not False):
            raise PermissionError("Original sealed human AI consultation differs")
        take_id=spec["reviewed_original_take_id"]
        packet=assemble_film_crew_context(
            index,pid,take_id,1,int(reviewed["film_time_tick"]),
            max_prims=16,max_events=12)
        if (packet["context_sha256"]!=reviewed["verified_source_context_sha256"] or
                packet["historical_take_not_current_scene"] or
                any(not row["is_current_head"] for row in packet["source_heads"])):
            raise PermissionError("Reviewed original scene/timeline changed before native sound/edit")
        if spec["decision_kind"]=="sound_cue":
            take=index.read_revision(pid,take_id,1)
            if (take["document_sha256"]!=reviewed["take_sha256"] or
                    take["data"].get("timeline_id")!=spec["source_id"] or
                    take["data"].get("timeline_revision")!=spec["source_revision"]):
                raise PermissionError("Reviewed original Take has a different source soundtrack timeline")
        if spec["decision_kind"]=="editorial_cut":
            graph=__import__("backend.nvp_digital_slate_branches",
                fromlist=["DigitalSlateBranches"]).DigitalSlateBranches(
                index,verify_editor_action=lambda *_:False).open_graph(
                pid,spec["source_id"],spec["source_revision"])
            if not any(
                    n["take_id"]==take_id and
                    n["take_document_sha256"]==reviewed["take_sha256"]
                    for n in graph["data"]["nodes"]):
                raise PermissionError("Reviewed original Take absent from the actual edit graph")
    preview = preview_source_impact(
        index, pid, spec["source_id"], spec["source_revision"],
        spec["source_sha256"], change_kind,
        scene_id=spec["screenplay_scene_id"],
        screenplay_revision=spec["screenplay_revision"],
        expected_bible_digest=spec["expected_bible_digest"],
        max_nodes=32)
    if (preview["preview_sha256"] != spec["preview_sha256"] or
            preview["status"] != "READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT" or
            preview["indexed_downstream_truncated"]):
        raise PermissionError("Current approved source-impact packet differs")
    return preview


def verify_decision_output(index, spec):
    """Reopen exact FilmIndex bytes; never infer rendering or release consent."""
    pid, kind = spec["project_id"], spec["decision_kind"]
    if kind == "color":
        output = NativeColorDecisions(index).read(pid, spec["decision_id"], 1)
        if (output["parameters"] != spec["payload"] or
                output["take_id"] != spec["source_id"] or
                output["take_sha256"] != spec["source_sha256"] or
                output["source_modified"] is not False or
                output["rendered_frames"] is not False or
                output["flat_master_approved"] is not False):
            raise RuntimeError("Reopened color decision does not match requested source")
    elif kind == "camera_sequence":
        output = ExactTimeShotSequence(index).read(pid, spec["decision_id"], 1)
        if (output["shots"] != [
                {**shot, "gap_before_tick": str(
                    int(shot["start_tick"]) - (
                        int(spec["payload"][i-1]["end_tick"]) if i else 0))}
                for i,shot in enumerate(spec["payload"])] or
                output["scene_id"] != spec["source_id"] or
                output["scene_revision"] != spec["source_revision"] or
                output["scene_document_sha256"] != spec["source_sha256"] or
                output["duration_tick"] != spec["duration_tick"] or
                output["video_frames_created"] is not False):
            raise RuntimeError("Reopened Film Time editorial timeline disagrees")
    elif kind=="sound_cue":
        doc=index.read_revision(pid,spec["decision_id"],1)
        if verify_sound_cue(index,spec)!=doc["document_sha256"]:
            raise RuntimeError("Sound event source changed")
        output={"document_sha256":doc["document_sha256"]}
    elif kind=="editorial_cut":
        doc=index.read_revision(pid,spec["decision_id"],1)
        if verify_editorial_cut(index,spec)!=doc["document_sha256"]:
            raise RuntimeError("Editorial cut source changed")
        output={"document_sha256":doc["document_sha256"]}
    else:
        raise ValueError("Unknown native operation")
    return output


class NativeFilmDecisionHost:
    """Trusted local service; creator+native grants cannot be supplied by AI."""

    def __init__(self, index: FilmIndex, ledger: TaskLedger, root: Path, *,
                 confirm_creator, authorize_native):
        if (not isinstance(index, FilmIndex) or
                not isinstance(ledger, TaskLedger) or
                not callable(confirm_creator) or
                not callable(authorize_native)):
            raise TypeError("Native index, ledger and separate host policies required")
        root = Path(root)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError("Decision worker root must be an absolute non-symlink")
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
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
                        "tools" / "nvp_wo6_data_worker.py").resolve())
        self.owner = "wo6data_" + hashlib.sha256(
            str(self.root).encode()).hexdigest()[:16]
        self.binding = ApprovedTaskBindings(ledger, approval_check=self._check)
        self.recovery = WO6DurableRecovery(ledger)

    def _check(self, approval_id, digest, doc):
        try:
            if (doc["format"] != FORMAT or
                    doc["operation"] != OPERATION or
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

    def queue_decision(self, scope: TrustedReadScope, *, creator_decision_id,
                       decision_kind, decision_id, source_id, source_revision,
                       source_sha256, payload, expected_preview_sha256,
                       duration_tick=None, screenplay_scene_id=None,
                       screenplay_revision=None, expected_bible_digest=None,
                       ram_mb=4096, expires_in_seconds=1800,
                       ai_review_context=None, reviewed_original_take_id=None,
                       expected_typed_preview_sha256=None,
                       director_reason=None):
        if not isinstance(scope, TrustedReadScope):
            raise PermissionError("Native actor/project/turn context required")
        if (type(creator_decision_id) is not str or
                not 1 <= len(creator_decision_id) <= 120 or
                decision_kind not in KINDS or
                type(ram_mb) is not int or not 1024 <= ram_mb <= 8192 or
                type(expires_in_seconds) is not int or
                not 60 <= expires_in_seconds <= 3600 or
                (screenplay_scene_id is None) != (screenplay_revision is None)):
            raise ValueError("Invalid typed native director decision")
        _id(source_id, "source identity")
        _id(decision_id, "new film decision")
        _sha(source_sha256)
        _sha(expected_preview_sha256)
        if type(source_revision) is not int or source_revision < 1:
            raise ValueError("Exact native source revision required")
        if decision_kind == "color":
            if source_revision != 1 or duration_tick is not None:
                raise ValueError("Color plan uses immutable original Take revision 1")
            payload = validate_parameters(payload)
        elif decision_kind=="camera_sequence":
            if (type(duration_tick) is not str or type(payload) is not list or
                    not 1<=len(payload)<=MAX_SHOTS):
                raise ValueError("Camera sequence needs exact Film Time and bounded shots")
        elif decision_kind=="sound_cue":
            if type(duration_tick) is not str or type(payload) is not dict:
                raise ValueError("Sound cue needs original exact Film Time and recorded PCM")
        elif decision_kind=="editorial_cut":
            if duration_tick is not None or type(payload) is not list:
                raise ValueError("Editorial requires exact immutable slate branches")
        if decision_kind in ("sound_cue","editorial_cut"):
            _sha(expected_typed_preview_sha256)
            if (type(director_reason) is not str or
                    not 12<=len(director_reason.strip())<=512):
                raise ValueError("Independent sound/editorial creative reason required")
            director_reason=director_reason.strip()
        elif (expected_typed_preview_sha256 is not None or
              director_reason is not None):
            raise ValueError("Sound/editorial typed preview and reason cannot affect older operations")
        reviewed=None
        if ai_review_context is not None:
            reviewed=_validate_ai_review_context(
                ai_review_context,action_kind=decision_kind,
                take_sha256=ai_review_context.get("take_sha256"))
            _id(reviewed_original_take_id,"reviewed original frozen Take")
        elif reviewed_original_take_id is not None:
            raise PermissionError("Original reviewed Take cannot be supplied without AI consultation")
        spec = {
            "format": FORMAT, "operation": OPERATION, "kind": "compositing",
            "actor_id": scope.actor_id, "project_id": scope.project_id,
            "turn_id": scope.turn_id, "creator_decision_id": creator_decision_id,
            "decision_kind": decision_kind, "decision_id": decision_id,
            "source_id": source_id, "source_revision": source_revision,
            "source_sha256": source_sha256, "payload": payload,
            "duration_tick": duration_tick,
            "screenplay_scene_id": screenplay_scene_id,
            "screenplay_revision": screenplay_revision,
            "expected_bible_digest": expected_bible_digest,
            "preview_sha256": expected_preview_sha256, "ram_mb": ram_mb,
        }
        if decision_kind in ("sound_cue","editorial_cut"):
            spec["typed_preview_sha256"]=expected_typed_preview_sha256
            spec["director_reason"]=director_reason
        if reviewed is not None:
            spec["reviewed_ai_consultation"]=reviewed
            spec["reviewed_original_take_id"]=reviewed_original_take_id
        # A preflight without the creative_scope must not interpret a model
        # suggestion as consent. The identical source check repeats after
        # the sealed creator/native scope is constructed.
        if reviewed is None:
            _preflight(self.index, spec)
        spec["creative_scope"] = {
            "operation": OPERATION, "project_id": scope.project_id,
            "decision_kind": decision_kind, "decision_id": decision_id,
            "original_source_id": source_id, "original_source_sha256": source_sha256,
            "source_impact_sha256": expected_preview_sha256,
            "typed_authoring_payload": payload, "duration_tick": duration_tick,
            "no_original_take_or_scene_mutation": True,
            "no_render_or_release_approval": True,
        }
        if decision_kind in ("sound_cue","editorial_cut"):
            spec["creative_scope"]["director_reason"]=director_reason
            spec["creative_scope"]["typed_preview_sha256"]=expected_typed_preview_sha256
        if reviewed is not None:
            spec["creative_scope"]["reviewed_ai_consultation"]=reviewed
            spec["creative_scope"]["model_text_is_authority"]=False
            spec["creative_scope"]["director_typed_values_independently"]=True
        _preflight(self.index,spec)
        task = "wo6data_" + secrets.token_hex(12)
        approval = "wo6approval_" + secrets.token_hex(12)
        spec.update(
            task_id=task, native_approval_id=approval,
            python_sha256=digest_file(self.python),
            worker_sha256=digest_file(self.worker),
            expires_at=time.time()+expires_in_seconds)
        raw = canonical_bytes(spec)
        sha = hashlib.sha256(raw).hexdigest()
        if not self._check(approval,sha,spec):
            raise PermissionError("Creator or trusted native tool permission was denied")
        folder = self.root / task
        folder.mkdir(mode=0o700,exist_ok=False)
        try:
            with (folder/"task.json").open("xb") as stream:
                stream.write(raw)
                stream.flush()
                __import__("os").fsync(stream.fileno())
            if os.name=="nt":
                persist_windows_job_identity(
                    folder,task_id=task,
                    spec_sha256=hashlib.sha256(canonical_bytes(spec)).hexdigest(),
                    owner=self.owner)
            self.binding.enqueue(
                AdmissionRequest(task, "compositing",
                                 "Approve source-bound native film decision", ram_mb),
                owner_key=self.owner,lane="standard",
                approval_id=approval,document=spec)
        except BaseException:
            shutil.rmtree(folder)
            raise
        return {"task_id":task,"state":"QUEUED","native_worker_started":False,
                "decision_id":decision_id,"film_delivered":False}

    @exclusive_worker_host
    def run_next(self, *, timeout_seconds=900, expected_task_id=None):
        claimed = self.binding.claim_next(
            owner_key=self.owner,expected_task_id=expected_task_id)
        if not claimed or not claimed["admitted"]:
            return claimed
        task = claimed["task_id"]
        proc = None
        cleaned = False
        try:
            spec = self.binding.verified_spec(task,owner_key=self.owner)
            folder = self.root/task
            path = folder/"task.json"
            raw = canonical_bytes(spec)
            if (folder.is_symlink() or path.is_symlink() or
                    path.read_bytes()!=raw or
                    digest_file(self.python)!=spec["python_sha256"] or
                    digest_file(self.worker)!=spec["worker_sha256"]):
                raise PermissionError("Approved native operation binary/spec was modified")
            _preflight(self.index,spec)
            if os.name=="nt" and not attest_windows_job_stopped(
                    folder,task_id=task,
                    spec_sha256=hashlib.sha256(raw).hexdigest(),
                    owner=self.owner):
                raise PermissionError("Native Windows Job Object already owns task")
            with (folder/"stdout.log").open("wb") as out, (
                    folder/"stderr.log").open("wb") as err:
                proc = launch_contained(
                    (([str(self.python), "--nvp-wo6-worker", "data"] if
                      self.frozen_worker else [str(self.python), str(self.worker)])
                     + ["--spec", str(path),
                     "--studio-db",str(self.index.studio.db_path),
                     "--expected-sha",hashlib.sha256(raw).hexdigest(),
                     "--ledger-db",str(self.ledger.db_path),
                     "--owner-key",self.owner]),
                    cwd=str(folder),stdout=out,stderr=err,
                    memory_mb=spec["ram_mb"],
                    windows_job_name=(
                        immutable_job_name(task) if os.name=="nt" else None))
                self.ledger.update(task,"building_scene",
                                   "Contained native Film Time or color decision writer")
                def cancel():
                    if self.recovery.cancel_requested(task):
                        return True
                    try:
                        self.binding.verified_spec(task,owner_key=self.owner)
                        return False
                    except PermissionError:
                        return True
                if wait_guarded(proc,self.ledger,task,
                                timeout_seconds=timeout_seconds,
                                should_cancel=cancel) != 0:
                    raise RuntimeError("Native Film Time/color worker failed")
                proc.close()
                cleaned = True
            path = folder/"receipt.json"
            if path.is_symlink():
                raise PermissionError("Symlinked native decision receipt refused")
            receipt = json.loads(path.read_bytes())
            output = verify_decision_output(self.index,spec)
            if (receipt.get("format")!=RECEIPT or
                    receipt.get("task_id")!=task or
                    receipt.get("decision_sha256")!=output["document_sha256"] or
                    receipt.get("source_impact_sha256")!=spec["preview_sha256"] or
                    receipt.get("reviewed_ai_consultation")!=
                        spec.get("reviewed_ai_consultation") or
                    receipt.get("model_instruction_executed") is not False or
                    receipt.get("model_approval_accepted") is not False or
                    receipt.get("rendered_frames") is not False or
                    receipt.get("film_delivered") is not False):
                raise RuntimeError("Native decision output receipt differs from FilmIndex")
            if spec["decision_kind"] in ("camera_sequence","sound_cue","editorial_cut"):
                _exact_source(self.index,spec["project_id"],spec["source_id"],
                              spec["source_revision"],spec["source_sha256"],
                              {"camera_sequence":"scene","sound_cue":"temporal",
                               "editorial_cut":"presentation"}[spec["decision_kind"]])
            if self.recovery.cancel_requested(task):
                raise NativeCancelRequested("Creator cancelled after decision commit")
            if not self._check(spec["native_approval_id"],
                               hashlib.sha256(raw).hexdigest(),spec):
                raise PermissionError("Human or native grant revoked before completion")
            self.ledger.update(task,"verifying_output",
                               "Verified original revisions and derived decision bytes")
            self.recovery.finish_verified(task,detail=
                "Non-destructive source-bound film decision saved, no film delivered")
            return {"task_id":task,"state":"SUCCEEDED",
                    "decision_id":spec["decision_id"],
                    "decision_sha256":output["document_sha256"],
                    "reviewed_ai_consultation":spec.get("reviewed_ai_consultation"),
                    "model_instruction_executed":False,
                    "film_delivered":False}
        except BaseException as error:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                    cleaned=True
                except BaseException:
                    cleaned=False
            if proc is None or cleaned:
                state=self.ledger.get_task(task)
                if state and state["state"]=="ACTIVE":
                    self.ledger.finish(task,
                        "CANCELLED" if isinstance(error,NativeCancelRequested)
                        else "INTERRUPTED",
                        "Cancelled; immutable decision may require reconciliation"
                        if isinstance(error,NativeCancelRequested) else
                        "Worker stopped; native decision commit needs reconciliation")
            raise
