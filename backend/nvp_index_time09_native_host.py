"""INDEX-TIME-09: trusted OS-contained native A/V review proxy host.

A direct pywebview window approval is checked once for an exact immutable
FilmIndex edit, source-stamped project-local originals, start Film Time and
bounded output. The existing ApprovedTaskBindings + TaskLedger + kernel
worker containment + guarded cancellation protect a new typed AV job.
Only independently verified temporary MP4 bytes may be sent to its own
native window via bounded opaque-ticket reads. No HTTP media path endpoint.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import threading
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings,canonical_bytes
from backend.nvp_index_time09_av_proxy import (
    FORMAT,RECEIPT_FORMAT,MAX_BYTES,canonical,plan as create_plan,
    verify as verify_proxy,
)
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained
from backend.nvp_source_window_decode import _sha_file
from backend.nvp_native_frame_index import stamp
from backend.nvp_film_index import _require_pid, _id, _sha
from backend.nvp_temporal_ledger import MAX_TICK

STATUS_FORMAT="nvp.index_time09.native_av_host.v1"
OPERATION="nvp.native.index_time09.av_review.v1"
TABLE="nvp_native_index_time09_av_grants"
MAX_CHUNK_BYTES=1024*1024

class NativeAVProxyHost:
    def __init__(self,desktop):
        self.desktop=desktop
        self.root=desktop.root/"av_proxy"
        if self.root.is_symlink():raise RuntimeError("Untrusted A/V proxy root")
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.ledger=TaskLedger(self.root/"task_ledger")
        self.owner="index09_"+sha256(str(self.root).encode()).hexdigest()[:22]
        self.ffmpeg,self.ffprobe=desktop._requirements()
        self.python=Path(sys.executable).resolve()
        self.packaged=bool(getattr(sys,"frozen",False))
        self.script=(
            Path(getattr(sys,"_MEIPASS",self.python.parent))/"tools"/"nvp_av_proxy_worker.py"
            if self.packaged else
            Path(__file__).resolve().parents[1]/"tools"/"nvp_av_proxy_worker.py")
        for p in (self.python,self.script,self.ffmpeg,self.ffprobe):
            if not p.is_absolute() or p.is_symlink() or not p.is_file():
                raise RuntimeError("Trusted original media proxy tools are unavailable")
        self.tool_hashes={
            "python_sha":_sha_file(self.python),
            "worker_sha":_sha_file(self.script),
            "ffmpeg_sha":_sha_file(self.ffmpeg),
            "ffprobe_sha":_sha_file(self.ffprobe),
        }
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS nvp_native_index_time09_av_grants (
                task_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL, edit_id TEXT NOT NULL,
                edit_revision INTEGER NOT NULL, edit_sha TEXT NOT NULL,
                plan_sha TEXT NOT NULL, spec_sha TEXT NOT NULL,
                destination TEXT NOT NULL, expires_at REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0, result_sha TEXT,
                python_sha TEXT NOT NULL, worker_sha TEXT NOT NULL,
                ffmpeg_sha TEXT NOT NULL, ffprobe_sha TEXT NOT NULL)""")
        self.bindings=ApprovedTaskBindings(
            self.ledger,approval_check=self._verify_creator)
        self._lock=threading.RLock()
        self._executor=ThreadPoolExecutor(max_workers=1,
            thread_name_prefix="NVP original A/V review")
        self._tickets={}
        self._current=None
        self._closed=False

    def _row(self,task):
        with self.ledger._db() as db:
            db.row_factory=sqlite3.Row
            found=db.execute("SELECT * FROM "+TABLE+" WHERE task_id=?",
                             (task,)).fetchone()
        if found is None:raise KeyError("Unknown native A/V review grant")
        return dict(found)

    def _plan(self,row):
        file=self.root/row["task_id"]/"av_plan.json"
        if (file.is_symlink() or not file.is_file() or
            _sha_file(file)!=row["plan_sha"]):
            raise RuntimeError("Source A/V plan is missing or altered")
        raw=file.read_bytes()
        plan=json.loads(raw)
        if (raw!=canonical(plan) or
            plan.get("format")!=FORMAT or
            plan.get("project_id")!=row["project_id"] or
            plan.get("edit_id")!=row["edit_id"] or
            plan.get("edit_revision")!=row["edit_revision"] or
            plan.get("edit_document_sha256")!=row["edit_sha"]):
            raise RuntimeError("Approved A/V plan and source edit mismatch")
        return plan

    def _verify_creator(self,approval_id,digest,spec):
        try:
            with self.ledger._db() as db:
                found=db.execute(
                    "SELECT task_id FROM "+TABLE+" WHERE approval_id=?",
                    (approval_id,)).fetchone()
            if found is None:return False
            row=self._row(found[0])
            if (row["revoked"] or row["result_sha"] is not None or
                time.time()>row["expires_at"] or
                digest!=row["spec_sha"] or
                sha256(canonical_bytes(spec)).hexdigest()!=digest or
                spec.get("task_id")!=row["task_id"] or
                spec.get("kind")!="compositing" or
                spec.get("operation")!=OPERATION or
                spec.get("plan_sha")!=row["plan_sha"] or
                spec.get("destination")!=row["destination"] or
                spec.get("edit_sha")!=row["edit_sha"] or
                Path(row["destination"]).exists() or
                Path(row["destination"]).is_symlink()):
                return False
            plan=self._plan(row)
            head=self.desktop.reader.index.read_revision(
                row["project_id"],row["edit_id"])
            if (head["revision"]!=row["edit_revision"] or
                head["document_sha256"]!=row["edit_sha"]):
                return False
            for key,path in (("python_sha",self.python),
                             ("worker_sha",self.script),
                             ("ffmpeg_sha",self.ffmpeg),
                             ("ffprobe_sha",self.ffprobe)):
                if (_sha_file(path)!=row[key] or
                    row[key]!=spec.get(key)):
                    return False
            for source in plan["sources"].values():
                if stamp(Path(source["path"]))!=source["stamp"]:
                    return False
            return True
        except (OSError,KeyError,ValueError,RuntimeError,TypeError):
            return False

    def _check_ticket(self,ticket):
        if self._closed or type(ticket) is not str or len(ticket)>128:
            raise PermissionError("Native A/V review authority is unavailable")
        self.desktop._window()
        data=self._tickets.get(ticket)
        if data is None or time.monotonic()>data["expires"]:
            raise PermissionError("Native original A/V review expired")
        row=self._row(data["task"])
        head=self.desktop.reader.index.read_revision(
            row["project_id"],row["edit_id"])
        if (head["revision"]!=row["edit_revision"] or
            head["document_sha256"]!=row["edit_sha"]):
            raise RuntimeError("Newer editorial revision invalidated source review")
        return data,row

    @staticmethod
    def _tick(value):
        if (type(value) is not str or not value.isascii()
            or not value.isdecimal() or not 1<=len(value)<=19 or
            int(value)>MAX_TICK):
            raise ValueError("Exact bounded Film Time tick required")
        return int(value)

    def start(self,request):
        with self._lock:
            self.desktop._window()
            if self._closed:raise RuntimeError("A/V native window closed")
            if type(request) is not dict or set(request)!={
                "project_id","edit_id","edit_revision",
                "edit_document_sha256","start_tick"}:
                raise ValueError("Only typed original Film Time review is allowed")
            pid=request["project_id"];_require_pid(pid)
            edit=request["edit_id"];_id(edit,"original edit")
            rev=request["edit_revision"]
            sha=request["edit_document_sha256"];_sha(sha)
            if type(rev) is not int or not 1<=rev<=1000000:
                raise ValueError("Original edit revision missing")
            tick=self._tick(request["start_tick"])
            if self._current is not None:
                prior=self._tickets[self._current]
                if not prior["future"].done():
                    raise RuntimeError("Previous A/V review must finish cancellation")
                self._discard(prior)
                self._tickets.pop(self._current,None)
                self._current=None
            self.desktop.reader._seek_resolver()
            plan=create_plan(
                self.desktop.studio,self.desktop.reader,pid,edit,rev,sha,
                tick,ffprobe=self.ffprobe)
            if not self.desktop._confirm(
                "Prepare temporary synchronized PICTURE + SOUND playback?\n"+
                "Edit: "+edit+" revision "+str(rev)+"\n"+
                "Film Time: "+str(tick)+" exact ticks\n"+
                "Review length: up to 20 minutes, max 160 MiB\n"+
                "Original sources: "+str(len(plan["sources"]))+
                " · original picture/audio remain frozen.\n"+
                "NVP creates one bounded 24fps/48kHz preview MOVIE.\n"+
                "This is neither source editing nor a final mastered film."):
                return {"format":STATUS_FORMAT,"status":"DENIED",
                        "original_modified":False,"master_approved":False}
            second=create_plan(
                self.desktop.studio,self.desktop.reader,pid,edit,rev,sha,
                tick,ffprobe=self.ffprobe)
            if plan!=second or self._closed:
                raise RuntimeError("Original source/PTS changed during user consent")
            ticket=secrets.token_urlsafe(24)
            task="index09_"+secrets.token_hex(16)
            folder=self.root/task
            folder.mkdir(mode=0o700,exist_ok=False)
            with (folder/"av_plan.json").open("xb") as writer:
                writer.write(canonical(plan))
                writer.flush()
                os.fsync(writer.fileno())
            dest=self.root/("output_"+ticket)
            approval="index09approval_"+secrets.token_hex(16)
            spec={
                "task_id":task,"kind":"compositing",
                "operation":OPERATION,
                "project_id":pid,"edit_id":edit,
                "edit_revision":rev,"edit_sha":sha,
                "plan_sha":sha256(canonical(plan)).hexdigest(),
                "destination":str(dest),
                "ram_mb":2048,**self.tool_hashes,
            }
            row={
                "task_id":task,"approval_id":approval,
                "project_id":pid,"edit_id":edit,
                "edit_revision":rev,"edit_sha":sha,
                "plan_sha":spec["plan_sha"],
                "spec_sha":sha256(canonical_bytes(spec)).hexdigest(),
                "destination":str(dest),"expires_at":time.time()+3600,
                "revoked":0,"result_sha":None,**self.tool_hashes,
            }
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO "+TABLE+" ("+",".join(row)+") VALUES ("+
                    ",".join("?" for _ in row)+")",
                    tuple(row.values()))
                db.commit()
            try:
                self.bindings.enqueue(
                    AdmissionRequest(task,"compositing",
                                     "Native unapproved Film Time A/V review",2048),
                    owner_key=self.owner,lane="interactive",
                    approval_id=approval,document=spec)
            except BaseException:
                if self.ledger.get_task(task) is None:
                    with self.ledger._db() as db:
                        db.execute("DELETE FROM "+TABLE+" WHERE task_id=?",(task,))
                    (folder/"av_plan.json").unlink()
                    folder.rmdir()
                raise
            item={
                "task":task,"ticket":ticket,"expires":time.monotonic()+3600,
                "cancel":threading.Event(),"future":None,
                "plan":plan,"verified":None,"stopped":False,
            }
            self._tickets[ticket]=item
            self._current=ticket
            item["future"]=self._executor.submit(self._run,item)
            return {
                "format":STATUS_FORMAT,"status":"QUEUED",
                "ticket_id":ticket,
                "project_id":pid,"edit_id":edit,
                "edit_revision":rev,"edit_document_sha256":sha,
                "requested_start_tick":str(tick),
                "actual_start_tick":str(plan["actual_start_tick"]),
                "review_duration_tick":str(plan["review_duration_tick"]),
                "original_modified":False,"master_approved":False,
            }

    def _run(self,item):
        task=item["task"]
        process=None
        attempted=False
        cleaned=False
        try:
            # Resource pressure is a waiting condition, not a reason to
            # abandon a live approved QUEUED task. Never run FFmpeg outside
            # the admission policy while memory is unavailable.
            deadline=time.monotonic()+180
            while True:
                if item["cancel"].is_set() or self._closed:
                    raise RuntimeError("Creator cancelled source A/V review")
                admitted=self.bindings.claim_next(owner_key=self.owner)
                if admitted and admitted.get("admitted"):
                    if admitted.get("task_id")!=task:
                        raise RuntimeError("Native A/V worker claimed a foreign task")
                    break
                if time.monotonic()>deadline:
                    raise RuntimeError("Native A/V review admission timed out safely")
                time.sleep(.5)
            spec=self.bindings.verified_spec(task,owner_key=self.owner)
            row=self._row(task)
            plan=self._plan(row)
            self.desktop.reader._seek_resolver()
            fresh=create_plan(
                self.desktop.studio,self.desktop.reader,
                row["project_id"],row["edit_id"],row["edit_revision"],
                row["edit_sha"],plan["requested_start_tick"],
                ffprobe=self.ffprobe)
            if plan!=fresh:
                raise RuntimeError("Original Film Time A/V plan became stale")
            self.ledger.update(task,"rendering",
                "Contained FFmpeg synthesizing temporary synced A/V")
            folder=self.root/task
            command=(
                [str(self.python),"--trusted-av-proxy-worker",row["worker_sha"]]
                if self.packaged else [str(self.python),str(self.script)])
            command +=[
                "--plan",str(folder/"av_plan.json"),
                "--destination",row["destination"],
                "--studio-db",str(self.desktop.studio.db_path.resolve()),
                "--ffmpeg",str(self.ffmpeg),"--ffprobe",str(self.ffprobe),
                "--ffmpeg-sha",row["ffmpeg_sha"],
                "--ffprobe-sha",row["ffprobe_sha"],
            ]
            with (folder/"stdout.log").open("wb") as stdout,(
                folder/"stderr.log").open("wb") as stderr:
                attempted=True
                process=launch_contained(command,cwd=str(folder),
                    stdout=stdout,stderr=stderr,memory_mb=2048)
                code=wait_guarded(
                    process,self.ledger,task,timeout_seconds=1600,
                    should_cancel=lambda:item["cancel"].is_set() or self._closed)
                if code:
                    raise RuntimeError("Native A/V review worker exited unsuccessfully")
                process.close()
                cleaned=True
            self.ledger.update(task,"verifying_output",
                               "Verifying 24fps picture and 48k audio synchronization")
            if create_plan(
                self.desktop.studio,self.desktop.reader,
                row["project_id"],row["edit_id"],row["edit_revision"],
                row["edit_sha"],plan["requested_start_tick"],
                ffprobe=self.ffprobe)!=plan:
                raise RuntimeError("Source FilmIndex or PTS changed during render")
            result=verify_proxy(row["destination"],plan,self.ffprobe)
            receipt=self.root/task/"verified_result.json"
            with receipt.open("xb") as handle:
                handle.write(canonical(result))
                handle.flush()
                os.fsync(handle.fileno())
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "UPDATE "+TABLE+" SET result_sha=? "
                    "WHERE task_id=? AND result_sha IS NULL",
                    (_sha_file(receipt),task))
                db.commit()
            self.ledger.finish(task,"SUCCEEDED",
                "Temporary reviewed A/V verified; frozen sources unchanged")
            with self._lock:
                item["verified"]=result
        except BaseException:
            if process is not None:
                try:
                    if process.poll() is None:
                        process.terminate_tree()
                    process.close()
                    cleaned=process.poll() is not None
                except BaseException:cleaned=False
            if not attempted:cleaned=True
            state=self.ledger.get_task(task)
            if cleaned and state is not None:
                if state["state"]=="ACTIVE":
                    self.ledger.finish(
                        task,"FAILED","Native original A/V proxy failed safely")
                elif state["state"]=="QUEUED":
                    try:self.ledger.cancel_queued(task,owner_key=self.owner)
                    except (RuntimeError,PermissionError):pass
            with self._lock:item["verified"]=False

    def poll(self,ticket):
        with self._lock:
            item,row=self._check_ticket(ticket)
            if item["stopped"]:
                return {"format":STATUS_FORMAT,"status":"CANCELLED",
                        "original_modified":False,"master_approved":False}
            state=self.ledger.get_task(item["task"])
            if item["verified"] is False or (
                state and state["state"] in ("FAILED","CANCELLED","INTERRUPTED")):
                return {"format":STATUS_FORMAT,"status":"RECOVERY_REQUIRED",
                        "original_modified":False,"master_approved":False}
            if not state or state["state"]!="SUCCEEDED":
                return {"format":STATUS_FORMAT,"status":"PREPARING",
                        "original_modified":False,"master_approved":False}
            if item["verified"] is None:
                raise RuntimeError("Native A/V receipt was not independently accepted")
            movie=Path(row["destination"])/"source_review.mp4"
            if movie.is_symlink() or movie.stat().st_size!=item["verified"]["size_bytes"]:
                raise RuntimeError("Prepared native review media changed")
            return {
                "format":STATUS_FORMAT,"status":"READY",
                **{k:v for k,v in item["verified"].items()
                   if k not in ("format","status")},
                "ticket_id":ticket,
                "actual_start_tick":str(item["plan"]["actual_start_tick"]),
                "review_duration_tick":str(item["plan"]["review_duration_tick"]),
                "original_modified":False,"master_approved":False,
            }

    def chunk(self,ticket,offset):
        with self._lock:
            item,row=self._check_ticket(ticket)
            if item["stopped"] or type(offset) is not int or offset<0:
                raise PermissionError("Unauthorized native review media read")
            state=self.ledger.get_task(item["task"])
            if (state is None or state["state"]!="SUCCEEDED" or
                item["verified"] is None or item["verified"] is False):
                raise PermissionError("Unverified temporary video is never served")
            if item["verified"]["size_bytes"]>MAX_BYTES:
                raise RuntimeError("Media derivative exceeds bounded preview")
            movie=Path(row["destination"])/"source_review.mp4"
            if movie.is_symlink() or not movie.is_file():
                raise RuntimeError("Verified proxy file was removed")
            if movie.stat().st_size!=item["verified"]["size_bytes"]:
                raise RuntimeError("Verified proxy size changed")
            if offset>item["verified"]["size_bytes"]:
                raise ValueError("Native chunk offset is outside approved media")
            # Completed proxy files are immutable within the private NVP
            # workspace. Audit its full original SHA before first release,
            # then ensure each chunk comes from the same stat identity.
            if "media_stat" not in item:
                if _sha_file(movie)!=item["verified"]["media_sha256"]:
                    raise RuntimeError("Verified temporary proxy changed after rendering")
                stat=movie.stat()
                item["media_stat"]=(
                    stat.st_dev,stat.st_ino,stat.st_size,
                    stat.st_mtime_ns,stat.st_ctime_ns)
            with movie.open("rb") as inp:
                before=os.fstat(inp.fileno())
                if (before.st_dev,before.st_ino,before.st_size,
                    before.st_mtime_ns,before.st_ctime_ns)!=item["media_stat"]:
                    raise RuntimeError("Verified proxy was swapped during chunk transfer")
                inp.seek(offset)
                raw=inp.read(MAX_CHUNK_BYTES)
                after=os.fstat(inp.fileno())
                if (before.st_dev,before.st_ino,before.st_size,
                    before.st_mtime_ns,before.st_ctime_ns)!=(
                    after.st_dev,after.st_ino,after.st_size,
                    after.st_mtime_ns,after.st_ctime_ns):
                    raise RuntimeError("Native source playback bytes changed mid-read")
            return {
                "format":STATUS_FORMAT,"status":"VERIFIED_CHUNK",
                "ticket_id":ticket,"offset":offset,
                "next_offset":offset+len(raw),
                "total_size":item["verified"]["size_bytes"],
                "sha256":sha256(raw).hexdigest(),
                "data_base64":base64.b64encode(raw).decode("ascii"),
                "original_modified":False,"master_approved":False,
            }

    def _discard(self,item):
        row=self._row(item["task"])
        folder=Path(row["destination"])
        if folder.is_symlink() or not folder.is_dir():
            return
        for name in ("source_review.mp4","review_receipt.json"):
            p=folder/name
            if p.is_file() and not p.is_symlink():p.unlink()
        try:folder.rmdir()
        except OSError:pass

    def stop(self,ticket):
        with self._lock:
            item,row=self._check_ticket(ticket)
            item["stopped"]=True
            item["cancel"].set()
            state=self.ledger.get_task(item["task"])
            if state and state["state"]=="QUEUED":
                try:
                    self.ledger.cancel_queued(item["task"],owner_key=self.owner)
                    with self.ledger._db() as db:
                        db.execute("UPDATE "+TABLE+
                                   " SET revoked=1 WHERE task_id=?",
                                   (item["task"],))
                except (RuntimeError,PermissionError):
                    pass
            if item["future"].done():
                self._discard(item)
            return {"format":STATUS_FORMAT,"status":"CANCELLATION_REQUESTED",
                    "original_modified":False,"master_approved":False}

    def close(self):
        with self._lock:
            if self._closed:return
            self._closed=True
            for item in self._tickets.values():
                item["stopped"]=True
                item["cancel"].set()
        self._executor.shutdown(wait=True,cancel_futures=False)
        for item in self._tickets.values():
            try:self._discard(item)
            except OSError:pass
        self._tickets.clear()
