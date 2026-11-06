"""SCALE-03B: authorized, resource-admitted native source-window review host.

This integrates existing ApprovedTaskBindings, TaskLedger, native OS worker
containment and measured memory watchdog. It never grants itself approval.
Results are UNAPPROVED source review PNGs, not a finished film master.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained
from backend.nvp_source_window_preflight import SourceWindowPreflight
from backend.nvp_source_window_decode import verify_review_window
from backend.nvp_film_index import _id


def _sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _sha_doc(doc):
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


class NativeSourceWindowHost:
    def __init__(self, preflight: SourceWindowPreflight, ledger: TaskLedger,
                 root: Path, *, verify_creator_action,
                 decoder_backend="ffmpeg", index_cache_root=None, ffprobe_path=None):
        if (not isinstance(preflight, SourceWindowPreflight) or
            not isinstance(ledger, TaskLedger) or
            not callable(verify_creator_action)):
            raise TypeError("Trusted native source host requires creator-policy verifier")
        self.preflight, self.ledger = preflight, ledger
        root = Path(root)
        if root.is_symlink():
            raise RuntimeError("Native job root must not be a symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root.resolve()
        if decoder_backend not in ("ffmpeg", "nvp_index"):
            raise ValueError("Unknown source-window backend")
        self.decoder_backend = decoder_backend
        self.ffprobe = None
        self.ffprobe_sha = None
        self.index_cache_root = None
        if decoder_backend == "nvp_index":
            ffprobe = Path(ffprobe_path or shutil.which("ffprobe") or "")
            if (not ffprobe.is_absolute() or not ffprobe.is_file() or
                ffprobe.is_symlink()):
                raise RuntimeError("Native FFprobe must be an approved absolute executable")
            self.ffprobe = ffprobe.resolve()
            self.ffprobe_sha = _sha_file(self.ffprobe)
            cache = Path(index_cache_root) if index_cache_root else self.root / "native_frame_indexes"
            if not cache.is_absolute() or cache.is_symlink():
                raise RuntimeError("NVP source index cache needs trusted absolute root")
            cache.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.index_cache_root = str(cache.resolve())
        self.python = Path(sys.executable).resolve()
        self.script = Path(__file__).resolve().parents[1] / "tools" / "nvp_source_window_worker.py"
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError("Native FFmpeg executable unavailable")
        self.ffmpeg = Path(exe).resolve()
        self.owner = "srcwindow_" + hashlib.sha256(str(self.root).encode()).hexdigest()[:20]
        self._creator = verify_creator_action
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_source_window_grants (
                task_id TEXT PRIMARY KEY,
                approval_id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL,
                edit_id TEXT NOT NULL,
                edit_revision INTEGER NOT NULL,
                edit_sha TEXT NOT NULL,
                first_frame INTEGER NOT NULL,
                frame_count INTEGER NOT NULL,
                destination TEXT NOT NULL,
                source_db TEXT NOT NULL,
                plan_sha TEXT NOT NULL,
                spec_sha TEXT NOT NULL,
                python_sha TEXT NOT NULL,
                script_sha TEXT NOT NULL,
                ffmpeg_sha TEXT NOT NULL,
                ffmpeg_path TEXT NOT NULL,
                ram_mb INTEGER NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL,
                result_sha TEXT)""")
            columns = {entry[1] for entry in db.execute(
                "PRAGMA table_info(native_source_window_grants)")}
            for name, datatype in (
                ("decoder_backend", "TEXT NOT NULL DEFAULT 'ffmpeg'"),
                ("ffprobe_path", "TEXT"),
                ("ffprobe_sha", "TEXT"),
                ("index_cache_root", "TEXT"),
            ):
                if name not in columns:
                    db.execute("ALTER TABLE native_source_window_grants ADD COLUMN "
                               + name + " " + datatype)
        self.binding = ApprovedTaskBindings(ledger, approval_check=self._check)

    def _row(self, task):
        with self.ledger._db() as db:
            db.row_factory = __import__("sqlite3").Row
            row = db.execute(
                "SELECT * FROM native_source_window_grants WHERE task_id=?", (task,)
            ).fetchone()
        if row is None:
            raise KeyError("No approved source-window task")
        return dict(row)

    def _check(self, approval, digest, doc):
        try:
            with self.ledger._db() as db:
                idrow = db.execute(
                    "SELECT task_id FROM native_source_window_grants WHERE approval_id=?",
                    (approval,)).fetchone()
            if idrow is None:
                return False
            row = self._row(idrow[0])
            if (row["revoked_at"] is not None or time.time() > row["expires_at"] or
                digest != row["spec_sha"] or _sha_doc(doc) != digest or
                doc.get("task_id") != row["task_id"] or
                doc.get("kind") != "compositing" or
                doc.get("edit_sha") != row["edit_sha"] or
                doc.get("destination") != row["destination"] or
                doc.get("ram_mb") != row["ram_mb"] or
                doc.get("decoder_backend", "ffmpeg") != row["decoder_backend"] or
                doc.get("ffprobe_sha") != row["ffprobe_sha"] or
                doc.get("index_cache_root") != row["index_cache_root"] or
                (row["decoder_backend"] == "nvp_index" and (
                    not row["ffprobe_path"] or not row["index_cache_root"] or
                    _sha_file(row["ffprobe_path"]) != row["ffprobe_sha"])) or
                Path(row["destination"]).exists() or
                Path(row["destination"]).is_symlink() or
                _sha_file(self.python) != row["python_sha"] or
                _sha_file(self.script) != row["script_sha"] or
                _sha_file(self.ffmpeg) != row["ffmpeg_sha"] or
                str(self.ffmpeg) != row["ffmpeg_path"]):
                return False
            folder = self.root / row["task_id"]
            plan_path = folder / "window_plan.json"
            if _sha_file(plan_path) != row["plan_sha"]:
                return False
            plan = json.loads(plan_path.read_bytes())
            if (plan["project_id"] != row["project_id"] or
                plan["edit_id"] != row["edit_id"] or
                plan["edit_revision"] != row["edit_revision"] or
                plan["edit_document_sha256"] != row["edit_sha"] or
                plan["first_frame"] != row["first_frame"] or
                plan["frame_count"] != row["frame_count"]):
                return False
            return True
        except (OSError, KeyError, ValueError, TypeError, RuntimeError):
            return False

    def stage_and_approve(self, project_id, edit_id, revision, *,
                          first_frame, frame_count, destination, creator_event,
                          ram_mb=1024, duration_s=1800):
        if (type(ram_mb) is not int or not 1024 <= ram_mb <= 8192 or
            type(duration_s) is not int or not 60 <= duration_s <= 3600):
            raise ValueError("Invalid approved window resource limits")
        policy = "preview" if self.decoder_backend == "nvp_index" else "full"
        plan = self.preflight.prepare(
            project_id, edit_id, revision, first_frame=first_frame,
            frame_count=frame_count, integrity_policy=policy)
        dest = Path(destination)
        if (dest.exists() or dest.is_symlink() or
            not dest.parent.is_dir() or dest.parent.is_symlink()):
            raise RuntimeError("Native output must be a new directory under safe parent")
        dest = str(dest.absolute())
        scope = {"operation": "nvp.native.source_window.review",
                 "project_id": project_id, "edit_id": edit_id,
                 "revision": revision, "edit_sha": plan["edit_document_sha256"],
                 "first_frame": first_frame, "frame_count": frame_count,
                 "destination": dest, "ram_mb": ram_mb,
                 "decoder_backend": self.decoder_backend,
                 "source_integrity": plan["source_preflight"],
                 "final_master": False}
        if self._creator(creator_event, dict(scope)) is not True:
            raise PermissionError("Creator refused exact source-window review")
        if self.preflight.prepare(project_id, edit_id, revision,
                                  first_frame=first_frame, frame_count=frame_count,
                                  integrity_policy=policy) != plan:
            raise RuntimeError("Source window changed during creator authorization")
        if Path(dest).exists():
            raise RuntimeError("Native output destination changed")
        task = "srcwindow_" + secrets.token_hex(16)
        folder = self.root / task
        folder.mkdir(mode=0o700, exist_ok=False)
        raw = canonical_bytes(plan)
        with (folder / "window_plan.json").open("xb") as stream:
            stream.write(raw)
            stream.flush()
            __import__("os").fsync(stream.fileno())
        spec = {"task_id": task, "kind": "compositing",
                "project_id": project_id, "edit_sha": plan["edit_document_sha256"],
                "first_frame": first_frame, "frame_count": frame_count,
                "destination": dest, "ram_mb": ram_mb,
                "ffmpeg_sha": _sha_file(self.ffmpeg),
                "decoder_backend": self.decoder_backend,
                "ffprobe_sha": self.ffprobe_sha,
                "index_cache_root": self.index_cache_root}
        approval = "srcapproval_" + secrets.token_hex(16)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_source_window_grants
                (task_id,approval_id,project_id,edit_id,edit_revision,edit_sha,
                 first_frame,frame_count,destination,source_db,plan_sha,spec_sha,
                 python_sha,script_sha,ffmpeg_sha,ffmpeg_path,ram_mb,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task,approval,project_id,edit_id,revision,
                 plan["edit_document_sha256"],first_frame,frame_count,dest,
                 str(self.preflight.publisher.index.studio.db_path),
                 hashlib.sha256(raw).hexdigest(),_sha_doc(spec),
                 _sha_file(self.python),_sha_file(self.script),
                 _sha_file(self.ffmpeg),str(self.ffmpeg),ram_mb,
                 time.time()+duration_s))
            db.execute("""UPDATE native_source_window_grants
                SET decoder_backend=?,ffprobe_path=?,ffprobe_sha=?,index_cache_root=?
                WHERE task_id=?""",
                (self.decoder_backend, str(self.ffprobe) if self.ffprobe else None,
                 self.ffprobe_sha, self.index_cache_root, task))
            db.commit()
        self.binding.enqueue(
            AdmissionRequest(task, "compositing", "Extract exact source review window",
                             ram_mb),
            owner_key=self.owner, lane="standard",
            approval_id=approval, document=spec)
        return {"task_id": task, "state": "QUEUED", "frames": frame_count,
                "native_worker_started": False}

    def run_next(self, *, timeout_seconds=900):
        admission = self.binding.claim_next(owner_key=self.owner)
        if not admission or not admission["admitted"]:
            return admission
        task = admission["task_id"]
        proc = None
        cleaned = False
        attempted = False
        try:
            self.binding.verified_spec(task, owner_key=self.owner)
            row = self._row(task)
            plan = json.loads((self.root / task / "window_plan.json").read_bytes())
            policy = "preview" if row["decoder_backend"] == "nvp_index" else "full"
            if self.preflight.prepare(
                row["project_id"], row["edit_id"], row["edit_revision"],
                first_frame=row["first_frame"], frame_count=row["frame_count"],
                integrity_policy=policy) != plan:
                raise RuntimeError("Native source was altered before worker admission")
            self.ledger.update(task, "rendering", "Extracting bounded original video window")
            folder = self.root / task
            cmd = [str(self.python), str(self.script),
                   "--plan", str(folder / "window_plan.json"),
                   "--destination", row["destination"],
                   "--studio-db", row["source_db"],
                   "--ffmpeg", row["ffmpeg_path"],
                   "--ffmpeg-sha", row["ffmpeg_sha"],
                   "--decoder-backend", row["decoder_backend"]]
            if row["decoder_backend"] == "nvp_index":
                cmd.extend(["--ffprobe", row["ffprobe_path"],
                            "--ffprobe-sha", row["ffprobe_sha"],
                            "--index-root", row["index_cache_root"]])
            with (folder / "stdout.log").open("wb") as out, (
                folder / "stderr.log").open("wb") as err:
                attempted = True
                proc = launch_contained(
                    cmd, cwd=str(folder), stdout=out, stderr=err,
                    memory_mb=row["ram_mb"])
                result = wait_guarded(
                    proc, self.ledger, task, timeout_seconds=timeout_seconds)
                if result != 0:
                    raise RuntimeError("Contained source review worker failed")
                proc.close()
                cleaned = True
            self.ledger.update(task, "verifying_output",
                               "Independently verifying native window review media")
            if self.preflight.prepare(
                row["project_id"], row["edit_id"], row["edit_revision"],
                first_frame=row["first_frame"], frame_count=row["frame_count"],
                integrity_policy=policy) != plan:
                raise RuntimeError("Source changed during contained native operation")
            result = verify_review_window(row["destination"], plan)
            receipt_path = Path(row["destination"]) / "review_receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            if (row["decoder_backend"] == "nvp_index" and
                (receipt.get("decoder_backend") != "nvp_sqlite_index_v1" or
                 receipt.get("source_sha_rehashed") is not False or
                 receipt.get("source_integrity") != "UNVERIFIED_FAST_PREVIEW")):
                raise RuntimeError("Indexed preview receipt has false integrity claims")
            receipt_sha = _sha_file(receipt_path)
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE native_source_window_grants SET result_sha=?
                    WHERE task_id=? AND result_sha IS NULL""", (receipt_sha, task))
                db.commit()
            self.ledger.finish(task, "SUCCEEDED",
                               "Verified bounded unapproved source review window")
            return {**result, "task_id": task, "state": "SUCCEEDED"}
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                    cleaned = proc.poll() is not None
                except BaseException:
                    cleaned = False
            if not attempted:
                cleaned = True
            if cleaned and self.ledger.get_task(task)["state"] == "ACTIVE":
                self.ledger.finish(task, "FAILED",
                                   "Native source-window extraction failed")
            raise

    def verify_completed(self, task):
        row = self._row(task)
        if (self.ledger.get_task(task)["state"] != "SUCCEEDED" or
            not row["result_sha"]):
            raise RuntimeError("No completed verified source-window receipt")
        plan_path = self.root / task / "window_plan.json"
        if (plan_path.is_symlink() or _sha_file(plan_path) != row["plan_sha"]):
            raise RuntimeError("Sealed native source-window plan changed after publication")
        plan = json.loads(plan_path.read_bytes())
        if (plan.get("edit_document_sha256") != row["edit_sha"] or
            plan.get("project_id") != row["project_id"] or
            plan.get("edit_id") != row["edit_id"] or
            plan.get("edit_revision") != row["edit_revision"] or
            plan.get("first_frame") != row["first_frame"] or
            plan.get("frame_count") != row["frame_count"]):
            raise RuntimeError("Native source-window plan differs from approved operation")
        result = verify_review_window(row["destination"], plan)
        if row["decoder_backend"] == "nvp_index" and (
            result.get("decoder_backend") != "nvp_sqlite_index_v1" or
            result.get("source_integrity") != "UNVERIFIED_FAST_PREVIEW"):
            raise RuntimeError("Completed review changed decoder or integrity status")
        if (_sha_file(Path(row["destination"]) / "review_receipt.json")
                != row["result_sha"]):
            raise RuntimeError("Native review publication changed")
        return result
