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
from backend.nvp_temporal_ledger import MAX_TICK,TICKS_PER_SECOND

STATUS_FORMAT="nvp.index_time09.native_av_host.v1"
OPERATION="nvp.native.index_time09.av_review.v1"
TABLE="nvp_native_index_time09_av_grants"
MAX_CHUNK_BYTES=1024*1024
# One native OS consent authorizes bounded, sequential reviewed sections for
# at most four hours. Only current + one ahead are permitted simultaneously.
MAX_PROGRESSIVE_SECONDS=4*3600
MAX_PROGRESSIVE_TICKS=MAX_PROGRESSIVE_SECONDS*TICKS_PER_SECOND
MAX_ACTIVE_TICKETS=2

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
        # One media worker at a time. The next section waits for the
        # verified current proxy, never competing for a second 2 GiB worker.
        self._executor=ThreadPoolExecutor(max_workers=1,
            thread_name_prefix="NVP original A/V review")
        self._tickets={}
        self._current=None
        self._session=None
        self._closed=False
        # A process restart has no surviving creator/session authority.
        # Old queued tasks are revoked, while active OS-worker reservations
        # are left for independently verified process-tree reconciliation.
        self._reconcile_restarted_grants()

    def _reconcile_restarted_grants(self):
        """Fail closed after host crash; never replay stale progress consent."""
        with self.ledger._db() as db:
            stale=[row[0] for row in db.execute(
                "SELECT task_id FROM "+TABLE+" WHERE revoked=0").fetchall()]
            db.execute("UPDATE "+TABLE+" SET revoked=1 WHERE revoked=0")
        for task in stale:
            state=self.ledger.get_task(task)
            if state is not None and state["state"]=="QUEUED":
                try:self.ledger.cancel_queued(task,owner_key=self.owner)
                except (RuntimeError,PermissionError):
                    # An already-claimed worker must be fenced by the
                    # contained-worker supervisor before ledger release.
                    pass

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
            session_id=spec.get("progressive_session")
            if session_id is not None:
                grant=self._session
                if (grant is None or grant["id"]!=session_id or
                    grant["stopped"] or time.monotonic()>grant["expires"] or
                    row["project_id"]!=grant["project_id"] or
                    row["edit_id"]!=grant["edit_id"] or
                    row["edit_revision"]!=grant["edit_revision"] or
                    row["edit_sha"]!=grant["edit_sha"]):
                    return False
            plan=self._plan(row)
            if session_id is not None and (
                plan["actual_start_tick"]<grant["start_tick"]-TICKS_PER_SECOND or
                plan["actual_start_tick"]+plan["review_duration_tick"]>
                grant["end_tick"]):
                return False
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
        if "progressive_session" in data:
            grant=self._session
            if (grant is None or grant["stopped"] or
                data["progressive_session"]!=grant["id"] or
                time.monotonic()>grant["expires"]):
                raise PermissionError("Progressive approval expired or was revoked")
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

    def start(self,request,*,progressive=False,continuation=False):
        with self._lock:
            # Stopped sessions cannot leave review tickets or in-flight
            # workers available to a later creator's consent. Reap only
            # independently completed tasks. Pending process-tree cleanup
            # blocks creation of a new native grant.
            for obsolete,old in list(self._tickets.items()):
                if old["stopped"] and old["future"].done():
                    self._discard(old)
                    self._tickets.pop(obsolete,None)
            if any(i["stopped"] and not i["future"].done()
                   for i in self._tickets.values()):
                raise RuntimeError("Previous native A/V worker needs safe cleanup")
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
            if continuation:
                grant=self._session
                if (not progressive or grant is None or grant["stopped"] or
                    time.monotonic()>grant["expires"] or
                    (pid,edit,rev,sha)!=(grant["project_id"],grant["edit_id"],
                                         grant["edit_revision"],grant["edit_sha"]) or
                    tick!=grant["expected_next_tick"] or
                    grant["next_ticket"] is not None or
                    len(self._tickets)>=MAX_ACTIVE_TICKETS):
                    raise PermissionError("Unapproved progressive continuation")
            elif self._session is not None:
                raise RuntimeError("Stop the active progressive session before a new review")
            if not continuation and self._current is not None:
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
            if continuation:
                # No new consent dialog: the original, explicit creator grant
                # already bounded the entire sequential session (<=4 hours).
                # Every child still receives its own SHA-pinned approval,
                # TaskLedger entry, worker guard and independent AV receipt.
                if tick>=grant["end_tick"]:
                    raise PermissionError("Progressive approval window ended")
                session_id=grant["id"]
            elif progressive:
                head=self.desktop.reader.index.read_revision(pid,edit)
                duration=int(head["data"]["duration_tick"])
                authorized_end=min(duration,tick+MAX_PROGRESSIVE_TICKS)
                if not self.desktop._confirm(
                    "Progressive original picture + sound review?\n"+
                    "Edit: "+edit+" revision "+str(rev)+"\n"+
                    "Begin at exact Film Time: "+str(tick)+"\n"+
                    "NVP may automatically prepare sequential review parts up "+
                    "to FOUR HOURS of this exact saved edit, or its end.\n"+
                    "At most two 20-minute, 160 MiB temporary sections exist "+
                    "at once, using one contained worker at a time.\n"+
                    "No new approval is required for the next section inside "+
                    "this scope. Stop or edit changes revoke the grant.\n"+
                    "Captured picture and sound stay frozen. Preview is "+
                    "NOT an approved master."):
                    return {"format":STATUS_FORMAT,"status":"DENIED",
                            "original_modified":False,"master_approved":False}
                session_id=secrets.token_urlsafe(24)
            else:
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
                session_id=None
            second=create_plan(
                self.desktop.studio,self.desktop.reader,pid,edit,rev,sha,
                tick,ffprobe=self.ffprobe)
            if plan!=second or self._closed:
                raise RuntimeError("Original source/PTS changed during user consent")
            if progressive:
                approved_end=grant["end_tick"] if continuation else authorized_end
                if (plan["actual_start_tick"]<
                    (grant["start_tick"] if continuation else tick)-TICKS_PER_SECOND
                    or plan["actual_start_tick"]+
                       plan["review_duration_tick"]>approved_end):
                    raise RuntimeError("Source snap exceeds progressive grant")
                if continuation:
                    # Actual snapped boundaries may overlap a held VFR frame
                    # by under a second. The UI must skip that overlap.
                    if plan["actual_start_tick"]>tick:
                        raise RuntimeError("Native next section skipped approved Film Time")
                else:
                    self._session={
                        "id":session_id,"project_id":pid,"edit_id":edit,
                        "edit_revision":rev,"edit_sha":sha,
                        "start_tick":tick,"end_tick":authorized_end,
                        "expires":time.monotonic()+MAX_PROGRESSIVE_SECONDS,
                        "stopped":False,"current_ticket":None,
                        "next_ticket":None,"expected_next_tick":None,
                    }
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
                **({"progressive_session":session_id}
                   if session_id is not None else {}),
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
            if progressive:
                item["progressive_session"]=session_id
                grant=self._session
                if continuation:
                    grant["next_ticket"]=ticket
                else:
                    grant["current_ticket"]=ticket
            if not continuation:
                self._current=ticket
            item["future"]=self._executor.submit(self._run,item)
            return {
                "format":STATUS_FORMAT,"status":"QUEUED",
                "ticket_id":ticket,
                **({"progressive_session_id":session_id,
                    "progressive_limit_tick":str(self._session["end_tick"])}
                   if progressive else {}),
                "project_id":pid,"edit_id":edit,
                "edit_revision":rev,"edit_document_sha256":sha,
                "requested_start_tick":str(tick),
                "actual_start_tick":str(plan["actual_start_tick"]),
                "review_duration_tick":str(plan["review_duration_tick"]),
                "original_modified":False,"master_approved":False,
            }

    def begin_progressive(self,request):
        """One explicit native consent for up to four hours of one exact edit."""
        try:
            return self.start(request,progressive=True)
        except BaseException:
            with self._lock:
                # If grant construction failed before a ticket was accepted,
                # do not leave a phantom live session that blocks recovery.
                if (self._session is not None and
                    self._session["current_ticket"] is None):
                    self._session["stopped"]=True
                    self._session=None
            raise

    def prepare_next_progressive(self,session_id,anchor_ticket):
        """Plan only the immediate successor of the current verified section.

        No browser-chosen next tick or path; the host derives it from the
        predecessor's sealed Film Time plan, and the original consent.
        """
        with self._lock:
            grant=self._session
            if (type(session_id) is not str or type(anchor_ticket) is not str or
                grant is None or grant["id"]!=session_id or grant["stopped"] or
                grant["current_ticket"]!=anchor_ticket or
                time.monotonic()>grant["expires"]):
                raise PermissionError("Progressive session not authorized")
            if grant["next_ticket"] is not None:
                return {"format":STATUS_FORMAT,"status":"ALREADY_QUEUED",
                        "ticket_id":grant["next_ticket"],
                        "progressive_session_id":session_id,
                        "original_modified":False,"master_approved":False}
            state=self.poll(anchor_ticket)
            if state["status"]!="READY":
                return {"format":STATUS_FORMAT,"status":"NOT_READY",
                        "original_modified":False,"master_approved":False}
            current=self._tickets[anchor_ticket]
            end=(current["plan"]["actual_start_tick"]+
                 current["plan"]["review_duration_tick"])
            if end>=grant["end_tick"]:
                return {"format":STATUS_FORMAT,"status":"AT_END",
                        "progressive_session_id":session_id,
                        "original_modified":False,"master_approved":False}
            grant["expected_next_tick"]=end
            request={
                "project_id":grant["project_id"],"edit_id":grant["edit_id"],
                "edit_revision":grant["edit_revision"],
                "edit_document_sha256":grant["edit_sha"],
                "start_tick":str(end),
            }
            return self.start(request,progressive=True,continuation=True)

    def advance_progressive(self,session_id,current_ticket,next_ticket):
        """Revoke old media after an independently verified successor exists."""
        with self._lock:
            grant=self._session
            if (type(session_id) is not str or grant is None or
                grant["id"]!=session_id or grant["stopped"] or
                grant["current_ticket"]!=current_ticket or
                grant["next_ticket"]!=next_ticket or
                current_ticket==next_ticket):
                raise PermissionError("Progressive transition is not authorized")
            old=self._tickets[current_ticket]
            upcoming=self._tickets[next_ticket]
            if (old["progressive_session"]!=session_id or
                upcoming["progressive_session"]!=session_id or
                self.poll(next_ticket)["status"]!="READY"):
                raise RuntimeError("Next A/V review has no verified receipt")
            expected=(old["plan"]["actual_start_tick"]+
                      old["plan"]["review_duration_tick"])
            actual=upcoming["plan"]["actual_start_tick"]
            if (actual>expected or expected>=actual+
                upcoming["plan"]["review_duration_tick"]):
                raise RuntimeError("Source Film Time successor has a missing interval")
            old["stopped"]=True
            old["cancel"].set()
            if not old["future"].done():
                raise RuntimeError("Current A/V worker has not exited")
            with self.ledger._db() as db:
                db.execute("UPDATE "+TABLE+" SET revoked=1 WHERE task_id=?",
                           (old["task"],))
            self._discard(old)
            self._tickets.pop(current_ticket,None)
            grant["current_ticket"]=next_ticket
            grant["next_ticket"]=None
            grant["expected_next_tick"]=None
            self._current=next_ticket
            return {
                "format":STATUS_FORMAT,"status":"ADVANCED",
                "progressive_session_id":session_id,
                "ticket_id":next_ticket,"actual_start_tick":str(actual),
                "transition_tick":str(expected),
                "original_modified":False,"master_approved":False,
            }

    def stop_progressive(self,session_id):
        with self._lock:
            grant=self._session
            if (type(session_id) is not str or grant is None or
                grant["id"]!=session_id):
                raise PermissionError("Unknown progressive session")
            self.desktop._window()
            grant["stopped"]=True
            for item in self._tickets.values():
                item["stopped"]=True
                item["cancel"].set()
                state=self.ledger.get_task(item["task"])
                if state is not None and state["state"]=="QUEUED":
                    try:self.ledger.cancel_queued(item["task"],owner_key=self.owner)
                    except (RuntimeError,PermissionError):pass
                with self.ledger._db() as db:
                    db.execute("UPDATE "+TABLE+" SET revoked=1 WHERE task_id=?",
                               (item["task"],))
            # The in-flight worker remains contained until wait_guarded
            # independently confirms the entire process tree exited.
            for token,item in list(self._tickets.items()):
                if item["future"].done():
                    self._discard(item)
                    self._tickets.pop(token,None)
            self._session=None
            self._current=None
            return {"format":STATUS_FORMAT,"status":"CANCELLATION_REQUESTED",
                    "original_modified":False,"master_approved":False}

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
            if item["cancel"].is_set() or self._closed:
                raise RuntimeError("Creator cancelled after decode but before AV publication")
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
            if item["cancel"].is_set() or self._closed:
                raise RuntimeError("Creator stopped proxy before native publication")
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
        finally:
            # The worker must have terminated and its OS process tree
            # been independently reaped before a cancelled derivative is
            # deleted. Never release active resource reservations on an
            # unverified cleanup.
            if item["cancel"].is_set() and cleaned:
                try:self._discard(item)
                except OSError:pass

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

    def stream_info(self,ticket):
        """Expose a verified *relative* media URL, never a file path.

        The only source for this link is the already installed native
        window's random private review ticket. The loopback HTTP route
        separately requires same-origin and invokes read_range on EVERY
        request. No general-purpose filesystem HTTP action is created.
        """
        with self._lock:
            item,row=self._check_ticket(ticket)
            if item["stopped"] or item["verified"] in (None,False):
                raise PermissionError("No verified original A/V review available")
            state=self.ledger.get_task(item["task"])
            if not state or state["state"]!="SUCCEEDED":
                raise PermissionError("Native source review not completed")
            movie=Path(row["destination"])/"source_review.mp4"
            if movie.is_symlink() or not movie.is_file():
                raise RuntimeError("Verified media was removed")
            stat=movie.stat()
            if (stat.st_size!=item["verified"]["size_bytes"] or
                stat.st_size>MAX_BYTES):
                raise RuntimeError("Native proxy size changed")
            identity=(stat.st_dev,stat.st_ino,stat.st_size,
                      stat.st_mtime_ns,stat.st_ctime_ns)
            if "stream_stat" not in item:
                if _sha_file(movie)!=item["verified"]["media_sha256"]:
                    raise RuntimeError("Native AV proxy changed after verification")
                item["stream_stat"]=identity
            if identity!=item["stream_stat"]:
                raise RuntimeError("Native AV proxy file changed after first read")
            for original in item["plan"]["sources"].values():
                if stamp(Path(original["path"]))!=original["stamp"]:
                    raise RuntimeError("Original media changed since proxy approval")
            return {
                "format":STATUS_FORMAT,"status":"VERIFIED_STREAM",
                "url":"/api/native-av-review/"+ticket+"/media",
                "total_size":stat.st_size,
                "media_sha256":item["verified"]["media_sha256"],
                "content_type":"video/mp4",
                "original_modified":False,"master_approved":False,
            }

    def stream_range(self,ticket,begin,finish):
        """Read up to 1 MiB from the trusted verified proxy on disk.

        The HTTP worker never receives/returns an original path. Each
        request rechecks the edited head, source stamps, original ticket,
        file identity and the local native window before reading.
        """
        if (type(begin) is not int or type(finish) is not int or
            begin<0 or finish<begin or finish-begin+1>MAX_CHUNK_BYTES):
            raise ValueError("Unbounded or invalid media byte-range request")
        with self._lock:
            description=self.stream_info(ticket)
            if finish>=description["total_size"]:
                raise ValueError("Review byte range exceeds approved media")
            item,row=self._check_ticket(ticket)
            movie=Path(row["destination"])/"source_review.mp4"
            with movie.open("rb") as source:
                original=os.fstat(source.fileno())
                def ident(a):
                    return (a.st_dev,a.st_ino,a.st_size,
                            a.st_mtime_ns,a.st_ctime_ns)
                if ident(original)!=item["stream_stat"]:
                    raise RuntimeError("Verified proxy file changed before byte-range read")
                source.seek(begin)
                chunk=source.read(finish-begin+1)
                if len(chunk)!=finish-begin+1 or ident(os.fstat(source.fileno()))!=ident(original):
                    raise RuntimeError("Media file changed during approved range transfer")
            return chunk

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
            with self.ledger._db() as db:
                db.execute("UPDATE "+TABLE+" SET revoked=1 WHERE task_id=?",
                           (item["task"],))
            try:self._discard(item)
            except OSError:pass
        self._tickets.clear()
        self._current=None
        self._session=None
