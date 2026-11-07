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
from backend.nvp_production_cinema import CinemaJournal, TASK_KIND as CINEMA_TASK
from backend.nvp_wo4_delivery_journal import CinemaDeliveryJournal
from backend.nvp_wo4_feature_journal import FeatureJournal
from backend.nvp_wo4_multireel import publish_multireel_dcp
from backend.nvp_wo4_supervised_sound import wrap_supervised_sound
from backend.nvp_wo4_file_dcp import publish_file_backed_dcp
from backend.nvp_supervised_codec_process import WorkerCancelled
from backend.nvp_wo4_picture_spool import (
    encode_disk_xyz12,wrap_disk_j2k_picture,verify_frame_file)
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_wo3_atomic_publish import _fsync_directory
from pathlib import Path

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

    def _picture_check(self,job_id,position=None):
        last=[time.monotonic()]
        def check():
            if position is not None and time.monotonic()-last[0]>=1.0:
                self.journal.heartbeat(self.owner,job_id,position)
                last[0]=time.monotonic()
            return self.journal.status(job_id)["cancel_requested"]
        return check

    def _run_cinema_frame(self,segment):
        if not isinstance(self.journal,CinemaJournal):
            raise PermissionError("Cinema workers need the one native cinema journal")
        uid=segment["job_id"]
        pos=segment["position"]
        try:
            reel=self.journal.reel(uid)
            root=self.journal.spool(uid)
            root.mkdir(mode=0o700,exist_ok=True)
            frame_dir=root/"frames"
            work_parent=root/"frame-work"
            if (root.is_symlink() or frame_dir.is_symlink()
                    or work_parent.is_symlink()):
                raise PermissionError("Native spool directory was redirected")
            frame_dir.mkdir(mode=0o700,exist_ok=True)
            work_parent.mkdir(mode=0o700,exist_ok=True)
            work=work_parent/f"{pos:06d}"
            # Never reopen or overwrite an interrupted worker stage.
            work.mkdir(mode=0o700,exist_ok=False)
            out=frame_dir/f"{pos:06d}.j2c"
            codec=ApprovedCodecBinary(
                reel["codec_path"],sha256=reel["codec_sha256"],
                product="OpenJPEG-opj_compress")
            check=self._picture_check(uid,pos)
            receipt=encode_disk_xyz12(
                codec,profile=reel["profile"],
                source_path=segment["source_path"],
                source_sha256=segment["expected_sha256"],
                private_work=work,check_cancel=check)
            if digest_file(segment["source_path"])!=segment["expected_sha256"]:
                raise PermissionError("Approved source frame changed during worker")
            if check():
                raise WorkerCancelled("Creator cancelled before frame checkpoint")
            os.link(work/"frame.j2c",out)
            _fsync_directory(frame_dir)
            committed=self.journal.finish_frame(self.owner,segment,receipt)
            return {"status":"PICTURE_FRAME_CHECKPOINTED",
                    "job_id":uid,"position":pos,
                    "sha256":committed["codestream_sha256"],
                    "production_dcp_accepted":False}
        except InterruptedError:
            if self.journal.status(uid)["cancel_requested"]:
                self.journal.finalize_cancel(uid)
                return {"status":"CANCELLED","job_id":uid}
            self.journal.mark_review(self.owner,uid,pos,"SupervisorInterrupted")
            return {"status":"REVIEW_REQUIRED","job_id":uid,
                    "reason":"SupervisorInterrupted"}
        except (OSError,ValueError,RuntimeError,PermissionError) as exc:
            if self.journal.status(uid)["cancel_requested"]:
                self.journal.finalize_cancel(uid)
                return {"status":"CANCELLED","job_id":uid}
            self.journal.mark_review(self.owner,uid,pos,type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":uid,
                    "reason":type(exc).__name__,
                    "production_dcp_accepted":False}

    def _wrap_cinema_track(self,reel):
        uid=reel["job_id"]
        try:
            root=self.journal.spool(uid)
            frames=root/"frames"
            # The journal holds one hash per frame and enforces ordered,
            # gap-free source-to-picture mapping. Don't trust directory names.
            with self.journal._read() as db:
                rows=[dict(x) for x in db.execute("""
                    SELECT f.position,f.file_sha256,f.file_bytes
                    FROM production_cinema_frames f
                    WHERE f.job_id=? ORDER BY f.position""",(uid,))]
            if len(rows)!=reel["frame_count"]:
                raise PermissionError("Picture reel frames not all committed")
            for index,item in enumerate(rows):
                if item["position"]!=index:
                    raise PermissionError("Unordered picture SHA checkpoint")
                size=verify_frame_file(
                    frames/f"{index:06d}.j2c",item["file_sha256"],
                    reel["profile"])
                if size!=item["file_bytes"]:
                    raise PermissionError("Picture frame changed since commit")
            stage=root/"mxf-stage"
            if root.is_symlink() or frames.is_symlink() or stage.is_symlink():
                raise PermissionError("Native MXF spool was redirected")
            stage.mkdir(mode=0o700,exist_ok=False)
            wrap=ApprovedCodecBinary(reel["wrapper_path"],
                                    sha256=reel["wrapper_sha256"],
                                    product="ASDCP-asdcp_wrap")
            info=ApprovedCodecBinary(reel["info_path"],
                                    sha256=reel["info_sha256"],
                                    product="ASDCP-asdcp_info")
            check=self._picture_check(uid)
            receipt=wrap_disk_j2k_picture(
                wrap,info,frames_dir=frames,stage_dir=stage,
                frame_count=reel["frame_count"],profile=reel["profile"],
                asset_uuid=reel["picture_uuid"],check_cancel=check)
            # The codec sees only derived J2K files, but those checkpoints
            # may not be rewritten by the external wrapper either.
            for index,item in enumerate(rows):
                if verify_frame_file(
                        frames/f"{index:06d}.j2c",item["file_sha256"],
                        reel["profile"])!=item["file_bytes"]:
                    raise PermissionError("CineCert modified an approved J2K checkpoint")
            if check():
                raise WorkerCancelled("Explicit cancellation before MXF checkpoint")
            target=root/"picture.mxf"
            os.link(stage/"picture.mxf",target)
            _fsync_directory(root)
            return self.journal.commit_track(self.owner,uid,receipt)
        except InterruptedError:
            if self.journal.status(uid)["cancel_requested"]:
                self.journal.finalize_cancel(uid)
                return {"status":"CANCELLED","job_id":uid}
            self.journal.track_review(self.owner,uid,"SupervisorInterrupted")
            return {"status":"REVIEW_REQUIRED","job_id":uid,
                    "reason":"SupervisorInterrupted"}
        except (OSError,ValueError,RuntimeError,PermissionError) as exc:
            if self.journal.status(uid)["cancel_requested"]:
                self.journal.finalize_cancel(uid)
                return {"status":"CANCELLED","job_id":uid}
            self.journal.track_review(self.owner,uid,type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":uid,
                    "reason":type(exc).__name__,
                    "production_dcp_accepted":False}

    def _delivery_check(self,uid):
        last=[time.monotonic()]
        def check():
            if time.monotonic()-last[0]>=1:
                self.journal.delivery_heartbeat(self.owner,uid)
                last[0]=time.monotonic()
            return self.journal.status(uid)["cancel_requested"]
        return check

    def _run_delivery(self,step):
        uid=step["job_id"]
        check=self._delivery_check(uid)
        try:
            root=self.journal.spool(uid)
            if root.is_symlink():
                raise PermissionError("Native production spool was redirected")
            if step["stage"]=="SOUND_RUNNING":
                work=root/"sound-stage"
                if work.is_symlink() or work.exists():
                    raise FileExistsError("Existing native sound stage requires review")
                work.mkdir(mode=0o700)
                reel=self.journal.reel(uid)
                wrap=ApprovedCodecBinary(
                    reel["wrapper_path"],sha256=reel["wrapper_sha256"],
                    product="ASDCP-asdcp_wrap")
                info=ApprovedCodecBinary(
                    reel["info_path"],sha256=reel["info_sha256"],
                    product="ASDCP-asdcp_info")
                receipt=wrap_supervised_sound(
                    wrap,info,candidate=self.journal.approved_sound_candidate(uid),
                    source_take_sha=reel["take_sha256"],
                    frames=reel["frame_count"],
                    sound_uuid=step["sound_uuid"],stage_dir=work,
                    check_cancel=check)
                if check():
                    raise WorkerCancelled("Creator cancelled before sound checkpoint")
                os.link(work/"sound.mxf",root/"sound.mxf")
                _fsync_directory(root)
                return self.journal.commit_sound(self.owner,uid,receipt)
            if step["stage"]=="PACKAGE_RUNNING":
                reel=self.journal.reel(uid)
                sound=root/"sound.mxf"
                pic=root/"picture.mxf"
                if (pic.is_symlink() or not pic.is_file() or
                        digest_file(pic)!=reel["track_sha256"] or
                        sound.is_symlink() or not sound.is_file() or
                        digest_file(sound)!=step["sound_sha256"]):
                    raise PermissionError("Verified picture/sound MXF source changed")
                origin=reel["take_sha256"]
                picture={
                    "kind":"picture","asset_uuid":reel["picture_uuid"],
                    "source_take_sha256":origin,
                    "file_path":str(pic),"file_sha256":reel["track_sha256"],
                    "file_bytes":reel["track_bytes"],
                    "profile":reel["profile"],
                    "frame_count":reel["frame_count"],"edit_rate":[24,1],
                    "source_modified":False,"production_dcp_accepted":False}
                snd={
                    "kind":"sound","asset_uuid":step["sound_uuid"],
                    "source_take_sha256":origin,
                    "file_path":str(sound),
                    "file_sha256":step["sound_sha256"],
                    "file_bytes":step["sound_bytes"],
                    "frame_count":reel["frame_count"],"edit_rate":[24,1],
                    "source_modified":False,"production_dcp_accepted":False}
                ids={
                    "picture":reel["picture_uuid"],
                    "sound":step["sound_uuid"],"cpl":step["cpl_uuid"],
                    "pkl":step["pkl_uuid"],"assetmap":step["assetmap_uuid"],
                    "reel":step["reel_uuid"]}
                receipt=publish_file_backed_dcp(
                    job_id=uid,picture=picture,sound=snd,
                    title=step["title"],profile=reel["profile"],
                    frames=reel["frame_count"],output_root=step["output_root"],
                    ids=ids,check_cancel=check)
                return self.journal.commit_package(self.owner,uid,receipt)
            raise PermissionError("Unsupported native cinema delivery phase")
        except InterruptedError:
            if self.journal.status(uid)["cancel_requested"]:
                self.journal.finalize_cancel(uid)
                return {"status":"CANCELLED","job_id":uid}
            self.journal.delivery_review(self.owner,uid,"SupervisorInterrupted")
            return {"status":"REVIEW_REQUIRED","job_id":uid,
                    "reason":"SupervisorInterrupted"}
        except (OSError,RuntimeError,PermissionError,ValueError) as exc:
            if self.journal.status(uid)["cancel_requested"]:
                self.journal.finalize_cancel(uid)
                return {"status":"CANCELLED","job_id":uid}
            self.journal.delivery_review(self.owner,uid,type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":uid,
                    "reason":type(exc).__name__,
                    "production_dcp_accepted":False}

    def _run_index_commit(self,uid):
        try:
            return self.journal.commit_filmindex(uid)
        except (OSError,RuntimeError,PermissionError,ValueError,KeyError) as exc:
            self.journal._mark_delivery_restart_review(uid,type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":uid,
                    "reason":type(exc).__name__,
                    "production_dcp_accepted":False}

    def _run_multireel_feature(self,task):
        fid=task["feature_id"]
        manifest=task["manifest"]
        try:
            result=publish_multireel_dcp(
                reels=manifest["reels"],ids=manifest["ids"],
                title=manifest["title"],profile=manifest["profile"],
                output_root=manifest["output_root"],
                check_cancel=lambda:self.journal.feature_cancel_requested(
                    fid,self.owner))
            if self.journal.feature_cancel_requested(fid,self.owner):
                raise WorkerCancelled("Authorized cancellation before feature checkpoint")
            receipt=self.journal.commit_feature(self.owner,fid,result)
            return {"status":"FEATURE_PUBLISHED_PENDING_INDEX",
                    "feature_id":fid,"destination":receipt["destination"],
                    "production_dcp_accepted":False}
        except InterruptedError:
            if self.journal.feature_cancel_requested(fid,self.owner):
                self.journal.finalize_feature_cancel(fid,self.owner)
                return {"status":"CANCELLED","feature_id":fid}
            self.journal.feature_review(self.owner,fid,"SupervisorInterrupted")
            return {"status":"REVIEW_REQUIRED","feature_id":fid}
        except (OSError,ValueError,PermissionError,RuntimeError) as exc:
            self.journal.feature_review(self.owner,fid,type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","feature_id":fid,
                    "reason":type(exc).__name__,"production_dcp_accepted":False}

    def _run_feature_index(self,fid):
        try:
            return self.journal.commit_feature_index(fid)
        except (OSError,ValueError,PermissionError,RuntimeError) as exc:
            self.journal._mark_feature_restart_review(fid)
            return {"status":"REVIEW_REQUIRED","feature_id":fid,
                    "reason":type(exc).__name__,"production_dcp_accepted":False}

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
            if isinstance(self.journal,CinemaJournal):
                track=self.journal.next_track(self.owner,self.pid)
                if track is not None:
                    return self._wrap_cinema_track(track)
            if isinstance(self.journal,CinemaDeliveryJournal):
                pending=self.journal.next_pending_index()
                if pending is not None:
                    return self._run_index_commit(pending)
                delivery=self.journal.next_delivery(self.owner,self.pid)
                if delivery is not None:
                    return self._run_delivery(delivery)
            if isinstance(self.journal,FeatureJournal):
                feature_index=self.journal.next_feature_index()
                if feature_index is not None:
                    return self._run_feature_index(feature_index)
                feature=self.journal.next_feature(self.owner)
                if feature is not None:
                    return self._run_multireel_feature(feature)
            return {"status":"IDLE","worker_kind":TASK_KIND}
        if after_claim is not None:
            after_claim(dict(segment))
        if segment["task_kind"]==CINEMA_TASK:
            return self._run_cinema_frame(segment)
        if segment["task_kind"]!=TASK_KIND:
            raise PermissionError("Unknown native worker task kind")
        job_id = segment["job_id"]
        try:
            last_heartbeat=time.monotonic()
            def check_cancel():
                nonlocal last_heartbeat
                if time.monotonic()-last_heartbeat>=1.0:
                    self.journal.heartbeat(
                        self.owner,job_id,segment["position"])
                    last_heartbeat=time.monotonic()
                return self.journal.status(job_id)["cancel_requested"]
            digest, size = verify_approved_file(
                segment,check_cancel=check_cancel)
            if check_cancel():
                raise InterruptedError("Explicit cancellation before verification commit")
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
            if self.journal.status(job_id)["cancel_requested"]:
                self.journal.finalize_cancel(job_id)
                return {"status":"CANCELLED","job_id":job_id}
            self.journal.mark_review(
                self.owner,job_id,segment["position"],type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":job_id,
                    "reason":type(exc).__name__,
                    "production_dcp_accepted":False}


def serve(state_root, *, once=False, poll_seconds=0.25):
    if type(poll_seconds) not in (float,int) or not 0.05<=poll_seconds<=30:
        raise ValueError("Bounded native supervisor polling interval required")
    journal = FeatureJournal(state_root)
    stop = False

    def stop_requested(*_):
        nonlocal stop
        stop = True

    with SingletonSupervisor(journal.root):
        journal.reconcile_after_restart()
        journal.cinema_reconcile()
        journal.delivery_reconcile()
        journal.reconcile_features()
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
