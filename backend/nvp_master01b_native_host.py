"""MASTER-01B: creator-bound, OS-contained, journaled technical-film assembly.

Production host only: not a public HTTP endpoint or model tool. Bound to the
existing FilmIndex, ApprovedTaskBindings, TaskLedger, WorkerHostLease, native
launcher and memory watchdog. Output stays unapproved (not picture-locked).

A Linux crash cannot be automatically declared reaped without an actual
post-stop witness; default (non-delegated) Linux execution is a development
mode. Strict Linux cgroup-v2 custody is opt-in and requires real delegation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import threading
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_longform_review import (
    FORMAT, REEL_FORMAT, MIN_FRAMES, MAX_FRAMES, MAX_REEL_FRAMES,
    reopen_review,
)
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import (wait_guarded, NativeCancelRequested)
from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_host_lease import WorkerHostLease

PLAN = "nvp.master01b.sealed_review_plan.v1"
RECEIPT = "nvp.master01b.native_review_receipt.v1"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _tool(name: str, value: str | None) -> Path:
    request = value or name
    if type(request) is not str or Path(request).name.lower() not in (name, name + ".exe"):
        raise PermissionError("Only the approved native " + name + " executable is allowed")
    selected = shutil.which(name)
    if not selected:
        raise RuntimeError("Required native binary missing: " + name)
    path = Path(selected).resolve(strict=True)
    if value is not None:
        requested = shutil.which(request)
        if not requested or Path(requested).resolve(strict=True) != path:
            raise PermissionError("Native tool path must match trusted host PATH inventory")
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Native tool is not a regular file")
    return path


class NativeMasterReviewHost:
    def __init__(self, index: FilmIndex, ledger: TaskLedger, root: Path, *,
                 verify_creator_action, strict_linux_tree: bool = False,
                 publication_mode: str = "worker_publishes"):
        if (not isinstance(index, FilmIndex) or not isinstance(ledger, TaskLedger)
            or not callable(verify_creator_action)):
            raise TypeError("Trusted FilmIndex, TaskLedger and creator verifier required")
        if type(strict_linux_tree) is not bool:
            raise TypeError("Strict Linux OS tree policy must be boolean")
        requested = Path(root)
        if requested.is_symlink():
            raise RuntimeError("Unsafe NVP native film workspace")
        requested.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = requested.resolve()
        self.index, self.ledger = index, ledger
        self.creator = verify_creator_action
        if publication_mode not in ("worker_publishes", "host_staged"):
            raise ValueError("Unsupported native film publication mode")
        self.strict_linux_tree = strict_linux_tree
        self.publication_mode = publication_mode
        self.python = Path(sys.executable).resolve(strict=True)
        self.worker = Path(__file__).resolve().parents[1] / "tools" / "nvp_master01b_native_worker.py"
        self.module = Path(__file__).resolve().with_name("nvp_longform_review.py")
        self.stage_module = Path(__file__).resolve().with_name("nvp_master01c_two_phase.py")
        self.owner = "master01b_" + hashlib.sha256(str(self.root).encode()).hexdigest()[:22]
        self.events: dict[str, str] = {}  # Native, ephemeral: lost approvals fail closed on restart.
        self._cancel: dict[str, threading.Event] = {}
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_master01b_grants(
                job_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL, review_id TEXT NOT NULL,
                spec_sha TEXT NOT NULL, plan_sha TEXT NOT NULL,
                expires_at REAL NOT NULL, event_sha TEXT UNIQUE NOT NULL,
                ram_mb INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                stop_witness INTEGER NOT NULL DEFAULT 0,
                stop_exit_code INTEGER, result_sha TEXT
            )""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS native_master01b_one_target
                ON native_master01b_grants(project_id, review_id)""")
        self.binding = ApprovedTaskBindings(ledger, approval_check=self._check)

    def _grant(self, job: str) -> dict:
        with self.ledger._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM native_master01b_grants WHERE job_id=?", (job,)).fetchone()
        if row is None:
            raise KeyError("Unknown native film review task")
        return dict(row)

    def _plan(self, job: str) -> dict:
        path = self.root / job / "plan.json"
        row = self._grant(job)
        if (path.is_symlink() or not path.is_file() or _sha(path) != row["plan_sha"]):
            raise RuntimeError("Sealed film review plan changed or disappeared")
        raw = path.read_bytes()
        plan = json.loads(raw)
        if (canonical_bytes(plan) != raw or plan.get("job_id") != job
            or plan.get("format") != PLAN
            or plan.get("creator_approved_final_master") is not False):
            raise RuntimeError("Native film review plan is inconsistent")
        return plan

    def _source_binding(self, project_id: str, refs: list[dict]) -> list[dict]:
        if type(refs) is not list or not 2 <= len(refs) <= 12:
            raise ValueError("Exactly 2–12 immutable reel references are required")
        seen, output, frames = set(), [], 0
        for ref in refs:
            if type(ref) is not dict or set(ref) != {"object_id", "revision"}:
                raise ValueError("Reel reference must have only object_id and revision")
            object_id = _id(ref["object_id"], "reel identity")
            revision = ref["revision"]
            if type(revision) is not int or revision < 1 or (object_id, revision) in seen:
                raise ValueError("Bad or duplicate reel source revision")
            seen.add((object_id, revision))
            record = self.index.read_revision(project_id, object_id, revision)
            data = record["data"]
            if (record["kind"] != "presentation" or data.get("format") != REEL_FORMAT
                or data.get("creator_approved_final_master") is not False
                or type(data.get("frames")) is not int
                or not 1 <= data["frames"] <= MAX_REEL_FRAMES):
                raise RuntimeError("Untrusted technical reel or unbounded source")
            self.index.verify_media_file(project_id, data["movie_sha256"], "video/quicktime")
            frames += data["frames"]
            if frames > MAX_FRAMES:
                raise ValueError("Native film review exceeds 60 seconds")
            output.append({"object_id": object_id, "revision": revision,
                           "document_sha256": record["document_sha256"],
                           "movie_sha256": data["movie_sha256"], "frames": data["frames"]})
        if frames < MIN_FRAMES:
            raise ValueError("Native film review must last at least 30 seconds")
        return output

    def _check(self, approval_id: str, digest: str, spec: dict) -> bool:
        try:
            job = spec["task_id"]
            grant = self._grant(job)
            plan = self._plan(job)
            if (grant["approval_id"] != approval_id or grant["spec_sha"] != digest
                or grant["revoked"] or grant["result_sha"] is not None
                or grant["stop_witness"] or time.time() > grant["expires_at"]
                or hashlib.sha256(canonical_bytes(spec)).hexdigest() != digest
                or spec.get("kind") != "compositing" or spec.get("job_id") != job
                or plan["project_id"] != grant["project_id"]
                or plan["review_id"] != grant["review_id"]
                or plan["ram_mb"] != grant["ram_mb"]
                or plan["publication_mode"] != spec["creator_scope"]["publication_mode"]
                or plan["source_binding_sha256"] != spec["source_binding_sha256"]
                or any(_sha(Path(plan[key])) != plan[key + "_sha256"] for key in
                       ("python", "worker", "module", "stage_module", "ffmpeg", "ffprobe"))
                or self.events.get(job) is None):
                return False
            refs = self._source_binding(plan["project_id"], plan["source_refs"])
            actual = hashlib.sha256(canonical_bytes({"sources": refs})).hexdigest()
            if actual != spec["source_binding_sha256"]:
                return False
            return self.creator(self.events[job], spec["creator_scope"]) is True
        except (OSError, KeyError, ValueError, TypeError, RuntimeError, PermissionError):
            return False

    def stage_and_approve(self, project_id: str, review_id: str, refs: list[dict],
                          creator_event: str, *, ram_mb: int = 1024,
                          duration_seconds: int = 3600,
                          ffmpeg: str | None = None, ffprobe: str | None = None) -> dict:
        _id(review_id, "review identity")
        if (type(ram_mb) is not int or not 512 <= ram_mb <= 8192
            or type(duration_seconds) is not int or not 60 <= duration_seconds <= 86400
            or type(creator_event) is not str or not creator_event):
            raise ValueError("Native film approval request invalid")
        try:
            self.index.read_revision(project_id, review_id)
        except KeyError:
            pass
        else:
            raise RuntimeError("Review ID already published")
        sources = self._source_binding(project_id, refs)
        if any(ref["object_id"] == review_id for ref in sources):
            raise ValueError("Cannot reference review as its own source")
        ff, probe = _tool("ffmpeg", ffmpeg), _tool("ffprobe", ffprobe)
        binding = hashlib.sha256(canonical_bytes({"sources": sources})).hexdigest()
        scope = {"operation": "nvp.master01b.unapproved_longform_review",
                 "project_id": project_id, "review_id": review_id,
                 "source_binding_sha256": binding,
                 "source_revisions": sources, "frames": sum(x["frames"] for x in sources),
                 "ram_mb": ram_mb, "task_duration_seconds": duration_seconds,
                 "publication_mode": self.publication_mode,
                 "native_binary_sha256": {"ffmpeg": _sha(ff), "ffprobe": _sha(probe)},
                 "creator_approved_final_master": False}
        if self.creator(creator_event, dict(scope)) is not True:
            raise PermissionError("Creator denied exact technical review operation")
        event_sha = hashlib.sha256(creator_event.encode()).hexdigest()
        with self.ledger._db() as db:
            if db.execute("SELECT 1 FROM native_master01b_grants WHERE event_sha=?",
                          (event_sha,)).fetchone():
                raise PermissionError("Creator approval event already consumed")
            if db.execute("SELECT 1 FROM native_master01b_grants WHERE project_id=? AND review_id=?",
                          (project_id, review_id)).fetchone():
                raise RuntimeError("Technical film review target already reserved")
        job = "reviewjob" + secrets.token_hex(16)
        plan = {"format": PLAN, "job_id": job,
                "studio_db_path": str(self.index.studio.db_path.resolve(strict=True)),
                "project_id": project_id, "review_id": review_id,
                "source_refs": refs, "source_binding_sha256": binding,
                "publication_mode": self.publication_mode,
                "creator_approved_final_master": False, "dcp_delivered": False,
                "ram_mb": ram_mb,
                "python": str(self.python), "worker": str(self.worker),
                "module": str(self.module), "stage_module": str(self.stage_module),
                "ffmpeg": str(ff), "ffprobe": str(probe)}
        for key in ("python", "worker", "module", "stage_module", "ffmpeg", "ffprobe"):
            plan[key + "_sha256"] = _sha(Path(plan[key]))
        job_dir = self.root / job
        job_dir.mkdir(mode=0o700)
        path = job_dir / "plan.json"
        with path.open("xb") as stream:
            stream.write(canonical_bytes(plan))
            stream.flush()
            os.fsync(stream.fileno())
        approval_id = "reviewapproval" + secrets.token_hex(16)
        # The bound task spec is sealed by ApprovedTaskBindings and rechecked
        # against creator scope and input digests before reserving resources.
        spec = {"task_id": job, "job_id": job, "kind": "compositing",
                "source_binding_sha256": binding, "creator_scope": scope}
        digest = hashlib.sha256(canonical_bytes(spec)).hexdigest()
        self.events[job] = creator_event
        try:
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO native_master01b_grants
                    (job_id,approval_id,project_id,review_id,spec_sha,plan_sha,
                     expires_at,event_sha,ram_mb) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (job, approval_id, project_id, review_id, digest, _sha(path),
                     time.time() + duration_seconds,
                     event_sha,ram_mb))
                db.commit()
            self.binding.enqueue(AdmissionRequest(
                job, "compositing", "Source-bound 30-60s technical film review", ram_mb),
                owner_key=self.owner, lane="standard", approval_id=approval_id,
                document=spec)
        except sqlite3.IntegrityError as exc:
            self.events.pop(job, None)
            raise PermissionError("Creator event or review target was already reserved") from exc
        except BaseException:
            self.events.pop(job, None)
            raise
        return {"job_id": job, "review_id": review_id, "state": "QUEUED",
                "native_worker_started": False,
                "creator_approved_final_master": False}

    def revoke(self, job: str) -> dict:
        row = self._grant(job)
        if self.ledger.get_task(job)["state"] != "QUEUED":
            raise RuntimeError("Running work requires controlled host cancellation")
        with self.ledger._db() as db:
            db.execute("UPDATE native_master01b_grants SET revoked=1 WHERE job_id=?", (job,))
        self.events.pop(job, None)
        return self.ledger.cancel_queued(job, owner_key=self.owner)

    def request_cancel(self, job: str) -> None:
        """Same-process trusted host signal; not a model-facing cancellation tool."""
        self._grant(job)
        flag = self._cancel.get(job)
        if flag is None:
            raise RuntimeError("No currently supervised worker for cancellation")
        flag.set()

    def _record_worker_stop(self, job: str, code: int) -> None:
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE native_master01b_grants
                SET stop_witness=1,stop_exit_code=? WHERE job_id=? AND stop_witness=0""",
                (code, job))
            db.commit()

    def _verify(self, job: str) -> dict:
        plan = self._plan(job)
        row = self.index.read_revision(plan["project_id"], plan["review_id"], 1)
        data = row["data"]
        if (row["kind"] != "presentation" or data.get("format") != FORMAT
            or data.get("creator_approved_final_master") is not False
            or data.get("dcp_delivered") is not False):
            raise RuntimeError("Worker attempted to publish non-review output")
        refs = self._source_binding(plan["project_id"], plan["source_refs"])
        if (hashlib.sha256(canonical_bytes({"sources": refs})).hexdigest()
            != plan["source_binding_sha256"] or
            [(x["object_id"], x["revision"]) for x in data["reels"]] !=
            [(x["object_id"], x["revision"]) for x in plan["source_refs"]]):
            raise RuntimeError("Published technical review source inputs are not the approved ones")
        proof = reopen_review(self.index, plan["project_id"], plan["review_id"],
                              ffmpeg=plan["ffmpeg"], ffprobe=plan["ffprobe"])
        return {"proof": proof, "document_sha256": row["document_sha256"]}

    def _receipt(self, job: str, independent: dict) -> None:
        plan = self._plan(job)
        path = self.root / job / "worker_receipt.json"
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Missing durable native film worker receipt")
        raw = path.read_bytes()
        receipt = json.loads(raw)
        proof = independent["proof"]
        if (canonical_bytes(receipt) != raw or receipt.get("format") != RECEIPT
            or receipt.get("job_id") != job or receipt.get("project_id") != plan["project_id"]
            or receipt.get("review_id") != plan["review_id"]
            or receipt.get("source_binding_sha256") != plan["source_binding_sha256"]
            or receipt.get("document_sha256") != independent["document_sha256"]
            or receipt.get("movie_sha256") != proof["movie_sha256"]
            or receipt.get("frames") != proof["frames"]
            or receipt.get("creator_approved_final_master") is not False
            or receipt.get("dcp_delivered") is not False):
            raise RuntimeError("Native film worker result receipt differs from reopened film")

    def _complete_staged_after_stop(self, job: str, plan: dict) -> dict:
        """Native worker prepared only. Host revalidates and commits once."""
        from backend.nvp_master01c_two_phase import verify_prepared, commit_prepared
        # A queued job or a cold-start recovery must not silently execute a
        # different staging verifier, codec binary or native worker than the
        # sealed creator-approved plan specified.
        for key in ("python", "worker", "module", "stage_module", "ffmpeg", "ffprobe"):
            if _sha(Path(plan[key])) != plan[key + "_sha256"]:
                raise RuntimeError("Pinned native film dependency changed before publication")
        prepared = verify_prepared(self.index, self.root / job / "stage",
                                   ffmpeg=plan["ffmpeg"], ffprobe=plan["ffprobe"])
        manifest = prepared["manifest"]
        refs = self._source_binding(plan["project_id"], plan["source_refs"])
        source_digest = hashlib.sha256(canonical_bytes({"sources": refs})).hexdigest()
        if (manifest["project_id"] != plan["project_id"]
            or manifest["review_id"] != plan["review_id"]
            or manifest["source_refs"] != plan["source_refs"]
            or source_digest != plan["source_binding_sha256"]):
            raise RuntimeError("Prepared review is not bound to the approved source plan")
        receipt_path = self.root / job / "worker_receipt.json"
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise RuntimeError("Native preparation receipt missing")
        original = receipt_path.read_bytes()
        receipt = json.loads(original)
        if (canonical_bytes(receipt) != original
            or receipt.get("format") != "nvp.master01c.native_preparation_receipt.v1"
            or receipt.get("job_id") != job
            or receipt.get("project_id") != plan["project_id"]
            or receipt.get("review_id") != plan["review_id"]
            or receipt.get("source_binding_sha256") != source_digest
            or receipt.get("prepared_manifest_sha256") != prepared["manifest_sha256"]
            or receipt.get("movie_sha256") != prepared["movie_sha256"]
            or receipt.get("frames") != prepared["frames"]
            or receipt.get("creator_approved_final_master") is not False
            or receipt.get("dcp_delivered") is not False):
            raise RuntimeError("Native preparation receipt differs from staged film")
        if self._cancel.get(job) is not None and self._cancel[job].is_set():
            raise NativeCancelRequested("Creator cancelled before host FilmIndex publication")
        # Only the host publishes. The staged worker never calls put_media_file
        # or register_revision. A crash after either step is safe to reconcile
        # against the existing precise FilmIndex revision without rerendering.
        committed = commit_prepared(self.index, self.root / job / "stage",
                                    ffmpeg=plan["ffmpeg"], ffprobe=plan["ffprobe"])
        return {"proof": reopen_review(self.index, plan["project_id"], plan["review_id"],
                        ffmpeg=plan["ffmpeg"], ffprobe=plan["ffprobe"]),
                "document_sha256": committed["document_sha256"]}

    def _complete_after_stop(self, job: str) -> dict:
        grant = self._grant(job)
        if grant["stop_witness"] != 1 or grant["stop_exit_code"] != 0:
            raise RuntimeError("Cannot verify film without successful OS worker stop witness")
        plan = self._plan(job)
        if plan.get("publication_mode", "worker_publishes") == "host_staged":
            independent = self._complete_staged_after_stop(job, plan)
        else:
            independent = self._verify(job)
            self._receipt(job, independent)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_master01b_grants SET result_sha=? WHERE job_id=?",
                       (independent["document_sha256"], job))
            db.commit()
        self.ledger.finish(job, "SUCCEEDED", "Native contained AV review independently verified")
        return {"job_id": job, "state": "SUCCEEDED",
                "status": "VERIFIED_TECHNICAL_REVIEW_UNAPPROVED",
                "document_sha256": independent["document_sha256"],
                **independent["proof"]}

    def run_next(self, *, timeout_seconds: int = 900) -> dict | None:
        with WorkerHostLease(self.root):
            admitted = self.binding.claim_next(owner_key=self.owner)
            if admitted is None or not admitted["admitted"]:
                return admitted
            job = admitted["task_id"]
            proc = None
            stopped = False
            code = None
            cancel = threading.Event()
            self._cancel[job] = cancel
            try:
                self.binding.verified_spec(job, owner_key=self.owner)
                plan = self._plan(job)
                self.ledger.update(job, "preparing_scene", "Starting bounded native multi-reel review")
                directory = self.root / job
                with (directory / "stdout.log").open("xb") as out, (directory / "stderr.log").open("xb") as err:
                    proc = launch_contained(
                        [str(self.python), str(self.worker), "--plan", str(directory / "plan.json")],
                        cwd=str(directory), stdout=out, stderr=err,
                        memory_mb=self._grant(job)["ram_mb"],
                        linux_cgroup_tree_required=self.strict_linux_tree)
                    code = wait_guarded(
                        proc, self.ledger, job, timeout_seconds=timeout_seconds,
                        poll_interval=0.2, should_cancel=cancel.is_set)
                    proc.close()
                    stopped = True
                self._record_worker_stop(job, code)
                if code != 0:
                    raise RuntimeError("Native film review worker exited with code " + str(code))
                self.ledger.update(job, "verifying_output", "Reopening source-bound technical review")
                return self._complete_after_stop(job)
            except BaseException as exc:
                if proc is not None and not stopped:
                    try:
                        if proc.poll() is None:
                            proc.terminate_tree()
                        code = proc.wait(timeout=15)
                        proc.close()
                        stopped = True
                    except BaseException:
                        stopped = False
                if proc is None:
                    stopped = True  # No child was ever started.
                if stopped:
                    # Do not claim complete if a fault crossed the worker/DB
                    # publication boundary; preserve review for investigation.
                    if proc is not None and not self._grant(job)["stop_witness"]:
                        self._record_worker_stop(job, int(code if code is not None else 13))
                    row = self.ledger.get_task(job)
                    if row["state"] == "ACTIVE":
                        status = "CANCELLED" if isinstance(exc, NativeCancelRequested) else "FAILED"
                        self.ledger.finish(job, status,
                                           ("Native film review: " + type(exc).__name__)[:240])
                raise
            finally:
                self._cancel.pop(job, None)

    def reconcile_after_restart(self, job: str) -> dict:
        """Never replay. Prove old worker stopped before releasing its reservation.

        A kernel host lease is not a guarantee Linux grandchildren died on
        host crash unless a delegated cgroup or other OS witness is provided.
        Absent an fsynced post-stop record, retain ACTIVE and require an
        independently verified full process-tree reaping witness.
        """
        with WorkerHostLease(self.root):
            grant = self._grant(job)
            state = self.ledger.get_task(job)["state"]
            if state == "SUCCEEDED":
                proof = self._verify(job)
                if proof["document_sha256"] != grant["result_sha"]:
                    raise RuntimeError("Recorded successful film has changed")
                return {"job_id": job, "state": "SUCCEEDED", **proof["proof"]}
            if state != "ACTIVE":
                return {"job_id": job, "state": state}
            if grant["stop_witness"] != 1:
                return {"job_id": job, "state": "STALE_UNVERIFIED",
                        "reservation_retained": True,
                        "detail": "No OS reaping proof; do not rerun or release memory"}
            if grant["stop_exit_code"] == 0:
                try:
                    return self._complete_after_stop(job)
                except (KeyError, RuntimeError, ValueError, OSError):
                    # A stopped worker with missing evidence is interrupted,
                    # not an invitation to rerun a non-idempotent publish.
                    pass
            self.ledger.finish(job, "INTERRUPTED", "Reaped native film worker; output not accepted")
            return {"job_id": job, "state": "INTERRUPTED", "replayed": False}