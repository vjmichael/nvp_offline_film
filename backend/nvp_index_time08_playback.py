"""INDEX-TIME-08: bounded playback of immutable original-video assemblies.

Each desktop-only review session is authorized by ONE real OS confirmation
for an exact FilmIndex edit/revision/SHA, start tick, max frame count, and
source sub-window manifest. Existing original-PTS FilmTimeWindowPreflight and
NativeFilmTimeWindowHost schedule and contain real FFmpeg decoding. Every
output remains an unapproved PNG derivative. No original media is written,
no arbitrary paths or worker IDs are ever returned to JS, and no HTTP write
or render endpoint is introduced.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import secrets
import struct
import threading
import time

from backend.nvp_film_index import _id, _require_pid, _sha
from backend.nvp_temporal_ledger import MAX_TICK
from backend.nvp_index_time06_native_desktop import MAX_PNG_BYTES, PNG_MAGIC

FORMAT = "nvp.index_time08.original_assembly_review.v1"
MAX_REVIEW_FRAMES = 96
MAX_SEGMENTS = 12
FRAMES_PER_SEGMENT = 12
MAX_EDIT_CLIPS = 256
SESSION_SECONDS = 1200


def _tick(value):
    if (type(value) is not str or not value.isascii()
        or not value.isdecimal() or not 1<=len(value)<=19):
        raise ValueError("Exact nonnegative 64-bit Film Time tick required")
    tick=int(value)
    if tick>MAX_TICK:
        raise ValueError("Film Time exceeds the native authored tick range")
    return tick


class NativeAssemblyReview:
    def __init__(self, desktop):
        # Constructed solely by the trusted per-window desktop bridge.
        self.desktop=desktop
        self._lock=threading.RLock()
        self._sessions={}
        self._executor=ThreadPoolExecutor(
            max_workers=1,thread_name_prefix="NVP source playback")
        self._closed=False
        self._current=None

    def _check_window(self):
        if self._closed:
            raise PermissionError("Native film review was closed")
        self.desktop._window()

    def _head(self,session):
        index=self.desktop.reader.index
        latest=index.read_revision(session["pid"],session["edit_id"])
        if (latest["revision"]!=session["revision"] or
            latest["document_sha256"]!=session["sha"]):
            raise RuntimeError("Film assembly changed; abandon unapproved preview")

    def _get(self,ticket):
        self._check_window()
        if type(ticket) is not str or not 1<=len(ticket)<=128:
            raise ValueError("Invalid playback ticket")
        session=self._sessions.get(ticket)
        if session is None or time.monotonic()>session["expires"]:
            raise PermissionError("Native playback authority expired")
        self._head(session)
        return session

    def _edit_clips(self,pid,edit_id,revision,sha):
        reader=self.desktop.reader
        original=reader._revision(pid,edit_id,revision)
        current=reader.index.read_revision(pid,edit_id)
        if (original["document_sha256"]!=sha or
            current["revision"]!=revision or
            current["document_sha256"]!=sha):
            raise RuntimeError("FilmIndex source assembly changed")
        count=original["data"]["clip_count"]
        if not 1<=count<=MAX_EDIT_CLIPS:
            raise ValueError("Bounded preview supports up to 256 source clips")
        clips=[]
        after=-1
        while len(clips)<count:
            page=reader.clips(pid,edit_id,revision,
                expected_edit_sha256=sha,after_ordinal=after,limit=100)
            rows=page["clips"]
            if (page["edit_document_sha256"]!=sha or
                not rows or
                any(row["ordinal"]!=after+i+1 for i,row in enumerate(rows))):
                raise RuntimeError("Source assembly page was stale or reordered")
            clips.extend(rows)
            after=clips[-1]["ordinal"]
        if len(clips)!=count:
            raise RuntimeError("Incomplete source assembly page")
        return clips

    def _plan(self,pid,edit_id,revision,sha,start_tick):
        # The first clip/frame is selected with the canonical O(log N)
        # original-PTS index; never guess from nominal frame rate.
        self.desktop.reader._seek_resolver()
        host=self.desktop._get_host()
        clips=self._edit_clips(pid,edit_id,revision,sha)
        selected=self.desktop.reader.seek(
            pid,edit_id,revision,expected_edit_sha256=sha,tick=start_tick)
        if selected["status"]=="INDEXED_SOURCE_FRAME_SELECTED":
            starting_clip=selected["clip_ordinal"]
            starting_frame=int(selected["source_frame_zero"])
        elif selected["status"]=="EMPTY_IMPORTED_VIDEO_GAP":
            next_clip=next(
                (c for c in clips if int(c["film_start_tick"])>=start_tick),None)
            if next_clip is None:
                raise ValueError("No original footage occurs after the selected Film Time")
            starting_clip=next_clip["ordinal"]
            starting_frame=int(next_clip["source_in_frame_zero"])
        else:
            raise RuntimeError("Film Time could not resolve a real source clip")

        windows=[]
        frames=[]
        for clip in clips[starting_clip:]:
            source_start=int(clip["source_in_frame_zero"])
            source_out=int(clip["source_out_frame_zero"])
            first=max(source_start,starting_frame) if clip["ordinal"]==starting_clip else source_start
            if first>=source_out:
                continue
            while (first<source_out and
                   len(frames)<MAX_REVIEW_FRAMES and
                   len(windows)<MAX_SEGMENTS):
                count=min(FRAMES_PER_SEGMENT,source_out-first,
                          MAX_REVIEW_FRAMES-len(frames))
                plan=host.preflight.prepare(
                    pid,edit_id,revision,clip_ordinal=clip["ordinal"],
                    first_zero=first,count=count,mode="preview")
                if (plan["edit_document_sha256"]!=sha or
                    plan["source_id"]!=clip["source_id"] or
                    plan["source_revision"]!=clip["source_revision"] or
                    len(plan["frames"])!=count):
                    raise RuntimeError("Preflight source binding differs from indexed edit")
                start=len(frames)
                for frame in plan["frames"]:
                    frames.append({
                        "index":len(frames),
                        "clip_ordinal":clip["ordinal"],
                        "source_id":clip["source_id"],
                        "source_revision":clip["source_revision"],
                        "source_frame_zero":str(frame["source_frame_zero"]),
                        "source_pts":str(frame["source_pts"]),
                        "film_time_tick":str(frame["film_time_tick"]),
                        "clip_end_tick":str(clip["film_end_tick"]),
                        "review_frame":frame["review_frame"],
                        "segment":len(windows),
                    })
                windows.append({
                    "plan":plan,"start":start,"count":count,
                    "clip_ordinal":clip["ordinal"],
                    "first_zero":first,"task":None,"verified":False,
                })
                first+=count
            if len(frames)>=MAX_REVIEW_FRAMES or len(windows)>=MAX_SEGMENTS:
                break
        if not frames:
            raise ValueError("There is no playable source frame in the bounded window")

        # A held source frame expires at the next measured original PTS,
        # not at one guessed output frame. For the last reviewed frame
        # before a clip ends, look up the next original source PTS boundary.
        # Empty film-time gaps are represented by explicit [end,next start)
        # intervals, so the player displays no frame across a gap.
        for i,frame in enumerate(frames):
            clip=clips[frame["clip_ordinal"]]
            frame_ordinal=int(frame["source_frame_zero"])
            nxt=frames[i+1] if i+1<len(frames) else None
            if (nxt and nxt["clip_ordinal"]==frame["clip_ordinal"]
                and int(nxt["source_frame_zero"])==frame_ordinal+1):
                frame_end=int(nxt["film_time_tick"])
            elif frame_ordinal+1<int(clip["source_out_frame_zero"]):
                observation=host.preflight.publisher.map_clip_window(
                    pid,edit_id,revision,clip_ordinal=frame["clip_ordinal"],
                    first_zero=frame_ordinal+1,count=1)
                frame_end=observation["frames"][0]["time_tick"]
            else:
                frame_end=int(clip["film_end_tick"])
            if frame_end<=int(frame["film_time_tick"]):
                raise RuntimeError("Non-increasing original PTS review interval")
            frame["film_end_tick"]=str(frame_end)
        for a,b in zip(frames,frames[1:]):
            if int(a["film_end_tick"])>int(b["film_time_tick"]):
                raise RuntimeError("Native review source intervals overlap")
        return windows,frames

    def start(self,request):
        self._check_window()
        if type(request) is not dict or set(request)!={
            "project_id","edit_id","edit_revision",
            "edit_document_sha256","start_tick"}:
            raise ValueError("Native exact editorial review identity is required")
        pid=request["project_id"];_require_pid(pid)
        edit=request["edit_id"];_id(edit,"indexed edit")
        revision=request["edit_revision"]
        if type(revision) is not int or not 1<=revision<=1_000_000:
            raise ValueError("Invalid editorial revision")
        sha=request["edit_document_sha256"];_sha(sha)
        tick=_tick(request["start_tick"])
        self.desktop._requirements()
        with self._lock:
            if self._current is not None:
                active=self._sessions[self._current]
                if not active["future"].done():
                    raise RuntimeError("A source preview is still decoding or cancelling")
            windows,frames=self._plan(pid,edit,revision,sha,tick)
            seen_clips=sorted({frame["clip_ordinal"] for frame in frames})
            if not self.desktop._confirm(
                "Review up to "+str(len(frames))+
                " ORIGINAL video frames, across "+str(len(seen_clips))+
                " source placement(s)?\nFilm: "+edit+
                " · revision "+str(revision)+"\n"+
                "Starting Film Time: "+str(tick)+" exact ticks\n"+
                "Exact edit SHA: "+sha+"\n"+
                "NVP will decode at most "+str(len(windows))+
                " bounded chunks using its OS-contained native worker.\n"+
                "Your original footage and earlier assemblies stay unchanged.\n"+
                "These are temporary review pictures, NOT a film export."):
                return {"format":FORMAT,"status":"DENIED",
                        "original_modified":False,"master_approved":False}
            self._check_window()
            checked_windows,checked_frames=self._plan(pid,edit,revision,sha,tick)
            if ([w["plan"] for w in windows]!=
                [w["plan"] for w in checked_windows] or
                frames!=checked_frames):
                raise RuntimeError("Film source/PTS changed during playback approval")
            ticket=secrets.token_urlsafe(24)
            destroot=self.desktop.root/"review_stream"
            destroot.mkdir(parents=True,exist_ok=True,mode=0o700)
            host=self.desktop._get_host()
            queued=[]
            try:
                for i,window in enumerate(windows):
                    plan=window["plan"]
                    dest=destroot/("scene_"+ticket+"_"+str(i))
                    scope={
                        "operation":"nvp.native.film_time.review.v1",
                        "project_id":pid,
                        "edit_id":edit,"edit_revision":revision,
                        "edit_document_sha256":sha,
                        "clip_ordinal":window["clip_ordinal"],
                        "first_zero":window["first_zero"],
                        "frame_count":window["count"],
                        "film_first_tick":plan["frames"][0]["film_time_tick"],
                        "film_last_tick":plan["frames"][-1]["film_time_tick"],
                        "mode":"preview","destination":str(dest),
                        "ram_mb":1024,
                        "source_integrity":plan["source_integrity"],
                        "final_master":False,
                    }
                    grant=self.desktop._grant(scope)
                    try:
                        task=host.stage_and_approve(
                            pid,edit,revision,clip_ordinal=window["clip_ordinal"],
                            first_zero=window["first_zero"],
                            count=window["count"],mode="preview",
                            destination=dest,creator_event=grant,
                            ram_mb=1024,duration_s=SESSION_SECONDS)
                    finally:
                        self.desktop._approvals.pop(grant.token,None)
                    if (task["state"]!="QUEUED" or
                        task["edit_document_sha256"]!=sha):
                        raise RuntimeError("Native source review was not securely queued")
                    window["task"]=task["task_id"]
                    queued.append(task["task_id"])
            except BaseException:
                for task in queued:
                    try:host.revoke_queued(task)
                    except (RuntimeError,KeyError):pass
                raise
            session={
                "pid":pid,"edit_id":edit,"revision":revision,
                "sha":sha,"tick":str(tick),"windows":windows,
                "frames":frames,"ready":0,"finished":False,
                "error":False,"cancelled":False,
                "stop":threading.Event(),"expires":time.monotonic()+SESSION_SECONDS,
                "future":None,
            }
            self._sessions[ticket]=session
            self._current=ticket
            session["future"]=self._executor.submit(self._run,session)
            return {
                "format":FORMAT,"status":"QUEUED","ticket_id":ticket,
                "project_id":pid,"edit_id":edit,
                "edit_revision":revision,"edit_document_sha256":sha,
                "requested_film_tick":str(tick),
                "planned_frames":len(frames),"ready_frames":0,
                "original_modified":False,"master_approved":False,
            }

    def _run(self,session):
        host=self.desktop._get_host()
        try:
            for index,window in enumerate(session["windows"]):
                if session["stop"].is_set() or self._closed:
                    break
                completed=host.run_next(
                    timeout_seconds=180,
                    should_cancel=lambda:session["stop"].is_set() or self._closed)
                if (not isinstance(completed,dict) or
                    completed.get("task_id")!=window["task"] or
                    completed.get("state")!="SUCCEEDED"):
                    raise RuntimeError("Native source review task was not verified")
                proof=host.verify_completed(window["task"])
                if (proof.get("status")!="VERIFIED_UNAPPROVED_FILM_TIME_REVIEW"
                    or proof.get("edit_document_sha256")!=session["sha"] or
                    proof.get("approved_final") is not False or
                    proof.get("review_frames")!=window["count"]):
                    raise RuntimeError("Native frame window receipt failed")
                with self._lock:
                    if session["stop"].is_set():break
                    window["verified"]=True
                    session["ready"]+=window["count"]
            with self._lock:
                session["finished"]=True
        except BaseException:
            with self._lock:
                session["error"]=True
                session["finished"]=True
                session["ready"]=0
        finally:
            if session["stop"].is_set() or session["error"]:
                for window in session["windows"]:
                    try:
                        if host.ledger.get_task(window["task"])["state"]=="QUEUED":
                            host.revoke_queued(window["task"])
                    except (KeyError,RuntimeError,TypeError):
                        pass

    def poll(self,ticket):
        with self._lock:
            session=self._get(ticket)
            if session["cancelled"]:
                return {"format":FORMAT,"status":"CANCELLED",
                        "master_approved":False}
            if session["error"]:
                return {"format":FORMAT,"status":"RECOVERY_REQUIRED",
                        "master_approved":False}
            # Only VERIFIED chunks are published to the renderer. A decoded
            # but unaudited frame is invisible to the browser.
            count=session["ready"]
            frames=[{k:v for k,v in f.items() if k not in ("segment","review_frame","clip_end_tick")}
                    for f in session["frames"][:count]]
            return {
                "format":FORMAT,
                "status":"COMPLETE" if session["finished"] else (
                    "READY" if count else "BUFFERING"),
                "project_id":session["pid"],"edit_id":session["edit_id"],
                "edit_revision":session["revision"],
                "edit_document_sha256":session["sha"],
                "requested_film_tick":session["tick"],
                "planned_frames":len(session["frames"]),
                "ready_frames":count,
                "frames":frames,"finished":session["finished"],
                "source_integrity":"SOURCE_STAMP_UNVERIFIED_PREVIEW",
                "original_modified":False,"master_approved":False,
            }

    def frame(self,ticket,index):
        with self._lock:
            session=self._get(ticket)
            if (session["cancelled"] or session["error"] or
                type(index) is not int or index<0 or index>=session["ready"]):
                raise PermissionError("Playback frame has no verified authority")
            entry=session["frames"][index]
            window=session["windows"][entry["segment"]]
            if not window["verified"]:
                raise RuntimeError("Unverified native source frame")
            host=self.desktop._get_host()
            proof=host.verify_completed(window["task"])
            if (proof.get("status")!="VERIFIED_UNAPPROVED_FILM_TIME_REVIEW" or
                proof.get("edit_document_sha256")!=session["sha"]):
                raise RuntimeError("Native original-review batch was changed")
            row=host._row(window["task"])
            plan=host._plan(window["task"],row)
            frame=plan["frames"][entry["review_frame"]-1]
            if (frame["film_time_tick"]!=int(entry["film_time_tick"]) or
                frame["source_frame_zero"]!=int(entry["source_frame_zero"]) or
                frame["source_pts"]!=int(entry["source_pts"])):
                raise RuntimeError("Native source timing or PTS receipt changed")
            path=Path(row["destination"])/(
                "review_"+str(entry["review_frame"]).zfill(9)+".png")
            if (path.is_symlink() or not path.is_file() or
                not 33<=path.stat().st_size<=MAX_PNG_BYTES):
                raise RuntimeError("Native review PNG is missing or oversized")
            payload=path.read_bytes()
            if (not payload.startswith(PNG_MAGIC) or
                len(payload)>MAX_PNG_BYTES):
                raise RuntimeError("Native review PNG signature mismatch")
            width,height=struct.unpack(">II",payload[16:24])
            if not (0<width<=8192 and 0<height<=8192):
                raise RuntimeError("Unbounded PNG preview dimensions")
            receipt=json.loads((Path(row["destination"])/"review_receipt.json").read_bytes())
            sha=sha256(payload).hexdigest()
            if sha!=receipt["frames"][entry["review_frame"]-1]["sha256"]:
                raise RuntimeError("Untrusted PNG changed after receipt verification")
            return {
                "format":FORMAT,"status":"VERIFIED_FRAME",
                "project_id":session["pid"],"edit_id":session["edit_id"],
                "edit_revision":session["revision"],
                "edit_document_sha256":session["sha"],
                "index":index,
                **{k:v for k,v in entry.items()
                   if k not in ("segment","review_frame","clip_end_tick")},
                "image_data_url":"data:image/png;base64,"+
                    base64.b64encode(payload).decode("ascii"),
                "png_sha256":sha,
                "original_modified":False,"master_approved":False,
            }

    def cancel(self,ticket):
        with self._lock:
            session=self._get(ticket)
            session["cancelled"]=True
            session["stop"].set()
            host=self.desktop._get_host()
            for window in session["windows"]:
                task=window["task"]
                try:
                    if host.ledger.get_task(task)["state"]=="QUEUED":
                        host.revoke_queued(task)
                except (RuntimeError,KeyError,TypeError):
                    pass
            return {
                "format":FORMAT,"status":"CANCELLATION_REQUESTED",
                "original_modified":False,"master_approved":False,
            }

    def close(self):
        with self._lock:
            if self._closed:return
            self._closed=True
            for session in self._sessions.values():
                session["cancelled"]=True
                session["stop"].set()
        self._executor.shutdown(wait=True,cancel_futures=False)
