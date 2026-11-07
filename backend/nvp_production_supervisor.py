"""WO4-LF01 standalone native Production Supervisor (first trusted worker).

Run independently of the editor/webview:
    python -m backend.nvp_production_supervisor serve --state-root ABSOLUTE_PATH
No HTTP listener, network, FFmpeg, arbitrary command execution or GUI coupling.
The only current worker hashes approved on-disk media in bounded blocks.
Real cinema render/J2K/MXF worker registration and OS containment are LF02.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import signal
import sys
import time

from backend.nvp_production_journal import ProductionJournal, TASK_KIND

BLOCK_BYTES = 1024 * 1024


class AnotherSupervisorRunning(RuntimeError):
    pass


class SingletonSupervisor:
    """Cross-platform OS-held advisory mutex, freed on process death.

    This is process ownership, not an OS service installer or worker-tree
    containment. Place the lock and journal on a trusted local filesystem.
    """
    def __init__(self, root):
        self.path = Path(root) / "production-supervisor.lock"
        self.fd = None

    def __enter__(self):
        if self.path.is_symlink():
            raise PermissionError("Native supervisor lock was replaced by a symlink")
        self.fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt
                if os.fstat(self.fd).st_size == 0:
                    os.write(self.fd, b"0")
                os.lseek(self.fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise AnotherSupervisorRunning("Production supervisor already owns this journal") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise AnotherSupervisorRunning("Production supervisor already owns this journal") from exc
            return self
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def __exit__(self, *_):
        if self.fd is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    os.lseek(self.fd, 0, os.SEEK_SET)
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None


def verify_approved_file(segment, *, check_cancel=lambda:False):
    """Read-only bounded streaming verification; never opens for writing."""
    file = Path(segment["source_path"])
    if file.is_symlink() or not file.is_file():
        raise PermissionError("Approved source file missing or symlinked")
    before = file.stat()
    digest = hashlib.sha256()
    size = 0
    with file.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size != before.st_size:
            raise PermissionError("Approved source file changed before verification")
        while block := stream.read(BLOCK_BYTES):
            if check_cancel():
                raise InterruptedError("Explicit native production cancellation")
            digest.update(block)
            size += len(block)
            if size > segment["expected_bytes"]:
                raise RuntimeError("Approved media grew beyond source manifest")
        after = os.fstat(stream.fileno())
    if (after.st_size != before.st_size or
            after.st_mtime_ns != before.st_mtime_ns or
            size != segment["expected_bytes"] or
            digest.hexdigest() != segment["expected_sha256"]):
        raise RuntimeError("Approved media SHA/size or source metadata changed")
    return digest.hexdigest(), size


class ProductionSupervisor:
    """Single owner: independent process must hold SingletonSupervisor."""

    def __init__(self, journal):
        if not isinstance(journal, ProductionJournal):
            raise TypeError("Trusted local production journal required")
        self.journal = journal
        self.owner = "Supervisor" + os.urandom(8).hex()
        self.pid = os.getpid()

    def run_one(self, *, after_claim=None):
        # Only the supervisor's process may claim. The singleton lock is
        # held by serve() or the parent native host; no browser entrypoint.
        for item in self.journal.list_jobs():
            status = self.journal.status(item["job_id"])
            if status["cancel_requested"] and status["state"]!="CANCELLED":
                if status["state"]!="VERIFY_COMPLETE":
                    self.journal.finalize_cancel(item["job_id"])
        segment = self.journal.claim_next(self.owner, self.pid)
        if segment is None:
            return {"status":"IDLE","worker_kind":TASK_KIND}
        if after_claim is not None:
            after_claim(dict(segment))
        job_id = segment["job_id"]
        try:
            digest, size = verify_approved_file(
                segment,
                check_cancel=lambda:self.journal.status(job_id)["cancel_requested"])
            result = self.journal.finish_verified(
                self.owner,job_id,segment["position"],digest,size)
            return {"status":"SEGMENT_VERIFIED",
                    "job_id":job_id,"segment":segment["position"],
                    "job_state":result["state"],
                    "production_dcp_accepted":False}
        except InterruptedError:
            self.journal.finalize_cancel(job_id)
            return {"status":"CANCELLED","job_id":job_id}
        except (OSError, RuntimeError, PermissionError, ValueError) as exc:
            self.journal.mark_review(
                self.owner,job_id,segment["position"],type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":job_id,
                    "reason":type(exc).__name__,
                    "production_dcp_accepted":False}


def serve(state_root, *, once=False, poll_seconds=0.25):
    if type(poll_seconds) not in (float,int) or not 0.05<=poll_seconds<=30:
        raise ValueError("Bounded native supervisor polling interval required")
    journal = ProductionJournal(state_root)
    stop = False

    def stop_requested(*_):
        nonlocal stop
        stop = True

    with SingletonSupervisor(journal.root):
        journal.reconcile_after_restart()
        runner = ProductionSupervisor(journal)
        if not once:
            # Shutdown the supervisor, NOT an approved production job.
            # The next process reopens the same durable journal.
            signal.signal(signal.SIGTERM, stop_requested)
            signal.signal(signal.SIGINT, stop_requested)
        completed=[]
        while not stop:
            record=runner.run_one()
            if record["status"]!="IDLE":
                completed.append(record)
            if once or record["status"]=="IDLE" and once:
                break
            if record["status"]=="IDLE":
                time.sleep(poll_seconds)
        return {
            "format":"nvp.wo4.independent_supervisor.v1",
            "status":"STOPPED_WITH_DURABLE_JOURNAL",
            "processed":completed,
            "production_dcp_accepted":False,
            "ffmpeg_used":False,
        }


def main(argv=None):
    parser=argparse.ArgumentParser(description="NVP native production supervisor")
    parser.add_argument("command", choices=("serve","once","status"))
    parser.add_argument("--state-root",required=True,
                        help="Absolute trusted NVP production state directory")
    parser.add_argument("--job-id",
                        help="For read-only job status inspection")
    parsed=parser.parse_args(argv)
    journal=ProductionJournal(parsed.state_root)
    if parsed.command=="status":
        if parsed.job_id:
            print(journal.status(parsed.job_id))
        else:
            print(journal.list_jobs())
        return 0
    if parsed.command=="once":
        print(serve(journal.root,once=True),flush=True)
        return 0
    print("NVP independent production supervisor active",flush=True)
    serve(journal.root)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
