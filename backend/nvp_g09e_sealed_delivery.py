"""W1-E authenticated encrypted long-film checkpoint and recovery register.

Only G03 LiveFilmStore owns this register; all source IDs, job intents, user
review and reel receipts are persisted in AES-GCM encrypted SQLite revisions.
Derived reel bytes are AES-GCM sealed via put_original()/one-use worker grants,
never in G09-E's ordinary disk render folder. No auto-adoption of orphaned
ciphertext after crashes; a new approved render gets a fresh owned asset name.

The matching AppContainer worker is backend.nvp_g09e_sealed_worker. This
service requires an external NATIVE one-use human approval callback and
independent Windows sandbox attestor; ordinary HTTP confirmation is not one.
"""
from __future__ import annotations

from hashlib import sha256
import json
import secrets
import threading

from backend.nvp_g07_edit import G07Editor
from backend.nvp_g08_native_avi import TICKS_FRAME,FPS
from backend.nvp_g09e_chunk import (
    MAX_FRAMES,MAX_CHUNKS,FRAMES_PER_CHUNK,
    chunk_bounds,source_digests,iter_source_pcm,_canonical)
from backend.nvp_g09e_audio import FilmMeter,plan_gain
from backend.nvp_g09e_sealed_worker import ProtectedSealedReelWorker
from backend.nvp_g09e_delivery import ACTIVE
from backend.nvp_g03_live_store import LiveFilmError

FORMAT="nvp.w1e.sealed_long_film.v1"
MANIFEST="nvp.w1e.sealed_long_film_playlist.v1"
MAX_OUTPUT_BYTES=32*1024**3


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS w1e_sealed_film_jobs(
        id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
        edit_revision INTEGER NOT NULL,
        source_json TEXT NOT NULL,source_sha256 TEXT NOT NULL,
        total_frames INTEGER NOT NULL,total_chunks INTEGER NOT NULL,
        status TEXT NOT NULL,completed_chunks INTEGER NOT NULL DEFAULT 0,
        completed_bytes INTEGER NOT NULL DEFAULT 0,
        sound_plan_json TEXT,sound_plan_sha256 TEXT,
        manifest_name TEXT,manifest_sha256 TEXT,
        issue TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        CHECK(status IN ('queued','analyzing','rendering','finalizing',
                         'completed','interrupted','cancelled','failed')))""")
    db.execute("""CREATE TABLE IF NOT EXISTS w1e_sealed_film_reels(
        job_id TEXT NOT NULL,project_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,start_frame INTEGER NOT NULL,
        end_frame INTEGER NOT NULL,worker_id TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,output_name TEXT NOT NULL,
        reel_sha256 TEXT NOT NULL,size_bytes INTEGER NOT NULL,
        native_receipt_json TEXT NOT NULL,completed_at TEXT NOT NULL,
        PRIMARY KEY(job_id,chunk_index),UNIQUE(project_id,output_name))""")


def _now():
    from datetime import datetime,timezone
    return datetime.now(timezone.utc).isoformat()


class SealedFilmDelivery:
    def __init__(self,studio,live,*,access,review_authority,
                 os_isolation_attestor):
        if not callable(review_authority) or not callable(os_isolation_attestor):
            raise ValueError("Protected film export needs native human review and OS attestation")
        self.studio=studio;self.live=live;self.access=access
        self.review_authority=review_authority
        self.native=ProtectedSealedReelWorker(live,
            review_authority=self._review_child_ticket,
            os_isolation_attestor=os_isolation_attestor)
        self.guard=threading.RLock()
        self.active={}
        self.tickets={}

    def _auth(self,pid,token):
        if not self.live.exists(pid):
            raise PermissionError("This is not an encrypted film project")
        if not self.access().permitted(pid,token,renew=False):
            raise PermissionError("Reopen your film to continue protected export")
        self.live._session(pid,token)

    def _change(self,pid,token,fn):
        self._auth(pid,token)
        def inner(db,key,folder):
            _schema(db)
            return fn(db)
        return self.live._change(pid,token,inner)

    def _read(self,pid,token,fn):
        self._auth(pid,token)
        with self.live._guard:
            key=self.live._session(pid,token)
            db,_=self.live._read_db(self.live._folder(pid),pid,key)
            try:
                _schema(db)
                return fn(db)
            finally:db.close()

    def _job(self,pid,token,job):
        def read(db):
            row=db.execute("""SELECT * FROM w1e_sealed_film_jobs
                WHERE project_id=? AND id=?""",(pid,job)).fetchone()
            if row is None:raise KeyError("Protected film work order was not found")
            return dict(row)
        return self._read(pid,token,read)

    def _reels(self,pid,token,job):
        return self._read(pid,token,lambda db:[dict(r) for r in db.execute(
            """SELECT * FROM w1e_sealed_film_reels WHERE project_id=? AND
            job_id=? ORDER BY chunk_index""",(pid,job))])

    def reconcile(self,pid,token):
        """Cold start never proves process exit or adopts orphaned output."""
        active=set(self.active)
        def reconcile(db):
            rows=list(db.execute("""SELECT id FROM w1e_sealed_film_jobs
                WHERE project_id=? AND status IN ('queued','analyzing',
                         'rendering','finalizing')""",(pid,)))
            changed=[]
            for row in rows:
                if row["id"] in active:continue
                db.execute("""UPDATE w1e_sealed_film_jobs SET
                    status='interrupted',updated_at=?,issue=?
                    WHERE project_id=? AND id=?""",
                    (_now(),"Earlier protected worker custody cannot be presumed after restart",
                     pid,row["id"]))
                changed.append(row["id"])
            return changed
        with self.guard:
            return self._change(pid,token,reconcile)

    def preview(self,pid,token,expected_revision):
        """Host-authenticated source scope for a real native OS review.

        Computes from actual frozen film and decisions, not browser-supplied
        model claims. Does NOT create a render or mint an execution ticket.
        """
        self._auth(pid,token)
        if type(expected_revision) is not int or expected_revision<1:
            raise ValueError("Review and save the current film edit")
        editor=G07Editor(self.studio,self.live,token)
        current=editor.view(pid)
        if current["revision"]!=expected_revision or current["missing_sources"]:
            raise RuntimeError("Review the actual saved original before private rendering")
        first=editor.native_assembly(pid,expected_revision,
            window=(0,min(240,round(current["duration_seconds"]*FPS))*TICKS_FRAME))
        frames=first["duration_tick"]//TICKS_FRAME
        if not 720<frames<=MAX_FRAMES or first["duration_tick"]!=frames*TICKS_FRAME:
            raise ValueError("Private working film requires exact whole frames")
        return {"project_id":pid,"edit_revision":expected_revision,
            "source_sha256":sha256(_canonical(source_digests(first))).hexdigest(),
            "total_frames":frames,
            "native_human_approval_required":True,
            "no_implicit_worker_authorization":True}

    def start(self,pid,token,expected_revision,approval_id):
        """External native human review must consume one exact-film ticket."""
        self._auth(pid,token)
        self.reconcile(pid,token)
        if type(expected_revision) is not int or expected_revision<1:
            raise ValueError("A reviewed saved edit revision is required")
        editor=G07Editor(self.studio,self.live,token)
        current=editor.view(pid)
        if current["revision"]!=expected_revision or current["missing_sources"]:
            raise RuntimeError("Saved film source changed after director review")
        first=editor.native_assembly(pid,expected_revision,
            window=(0,min(240,round(current["duration_seconds"]*FPS))*TICKS_FRAME))
        frames=first["duration_tick"]//TICKS_FRAME
        if not 720<frames<=MAX_FRAMES or first["duration_tick"]!=frames*TICKS_FRAME:
            raise ValueError("Protected film must be 30 seconds to 3 hours, whole-frame aligned")
        source=source_digests(first)
        digest=sha256(_canonical(source)).hexdigest()
        if not isinstance(approval_id,str) or len(approval_id)<24:
            raise PermissionError("Native one-use director approval is required")
        if not self.review_authority(pid,expected_revision,digest,frames,
                                     approval_id):
            raise PermissionError("Native director did not approve this exact film")
        job=secrets.token_hex(16)
        now=_now()
        def create(db):
            if db.execute("""SELECT 1 FROM w1e_sealed_film_jobs WHERE
                project_id=? AND status IN ('queued','analyzing',
                'rendering','finalizing')""",(pid,)).fetchone():
                raise RuntimeError("Another protected render is still active")
            db.execute("""INSERT INTO w1e_sealed_film_jobs(
                id,project_id,edit_revision,source_json,source_sha256,
                total_frames,total_chunks,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,'queued',?,?)""",
                (job,pid,expected_revision,_canonical(source).decode("utf8"),
                 digest,frames,(frames+FRAMES_PER_CHUNK-1)//FRAMES_PER_CHUNK,
                 now,now))
        self._change(pid,token,create)
        self._launch(pid,token,job)
        return self.status(pid,token,job)

    def _launch(self,pid,token,job):
        with self.guard:
            if job in self.active:
                raise RuntimeError("The private film job is already running")
            stop=threading.Event()
            thread=threading.Thread(target=self._perform,
                args=(pid,token,job,stop),daemon=True,
                name="nvp-w1e-sealed-film-"+job[:8])
            self.active[job]=(thread,stop)
            thread.start()

    def _set(self,pid,token,job,status,*,issue=None,plan=None,manifest=None):
        def update(db):
            current=db.execute("""SELECT status FROM w1e_sealed_film_jobs
                WHERE project_id=? AND id=?""",(pid,job)).fetchone()
            if current is None:raise KeyError("Protected film job missing")
            if current["status"] in ("completed","cancelled","failed","interrupted"):
                raise RuntimeError("Protected film job is terminal")
            values={"status":status,"updated_at":_now(),"issue":issue}
            if plan is not None:
                values["sound_plan_json"]=_canonical(plan).decode("utf8")
                values["sound_plan_sha256"]=sha256(
                    values["sound_plan_json"].encode("utf8")).hexdigest()
            if manifest is not None:
                values["manifest_name"]=manifest["name"]
                values["manifest_sha256"]=manifest["sha256"]
            setters=",".join(f"{key}=?" for key in values)
            db.execute(f"UPDATE w1e_sealed_film_jobs SET {setters} WHERE project_id=? AND id=?",
                (*values.values(),pid,job))
        return self._change(pid,token,update)

    def _review_child_ticket(self,pid,job,index,binding,approval_id):
        with self.guard:
            record=self.tickets.pop(approval_id,None)
        return record==(pid,job,index,binding)

    def _one_reel_ticket(self,pid,job,index,binding):
        ticket=secrets.token_urlsafe(32)
        with self.guard:self.tickets[ticket]=(pid,job,index,binding)
        return ticket

    def _window(self,pid,token,job,record,index):
        start,end=chunk_bounds(record["total_frames"],index)
        assembly=G07Editor(self.studio,self.live,token).native_assembly(
            pid,record["edit_revision"],window=(start*TICKS_FRAME,end*TICKS_FRAME))
        source=source_digests(assembly)
        if sha256(_canonical(source)).hexdigest()!=record["source_sha256"]:
            raise RuntimeError("Frozen original Take or creative review changed")
        return assembly,start,end

    def _analyze(self,pid,token,job,record,stop):
        report=record["sound_plan_json"]
        if report:
            if sha256(report.encode("utf8")).hexdigest()!=record["sound_plan_sha256"]:
                raise RuntimeError("The sealed sound plan changed after approval")
            return json.loads(report)
        self._set(pid,token,job,"analyzing")
        meter=FilmMeter(duration_samples=record["total_frames"]*2000)
        for index in range(record["total_chunks"]):
            if stop.is_set():raise InterruptedError("Director stopped film analysis")
            assembly,start,end=self._window(pid,token,job,record,index)
            for sample,raw in iter_source_pcm(assembly,start,end):
                meter.feed(raw)
        measured=meter.finish()
        first,_,_=self._window(pid,token,job,record,0)
        plan=plan_gain(measured,first.get("approved_finishing"))
        self._set(pid,token,job,"rendering",plan=plan)
        return plan

    def _append(self,pid,token,job,record,index,receipt):
        start,end=chunk_bounds(record["total_frames"],index)
        if (receipt["index"]!=index or receipt["job_id"]!=job or
            receipt["start_frame"]!=start or receipt["end_frame"]!=end or
            receipt["size_bytes"]<=0 or
            not receipt["encrypted_output"] or
            not receipt["os_process_tree_closed"] or
            not receipt["independent_audio_picture_verified"]):
            raise RuntimeError("Protected native worker custody is incomplete")
        # The native supervisor has already sealed and independently read
        # back this exact output. Never ingest a file selected by the WebView.
        def commit(db):
            existing=db.execute("""SELECT 1 FROM w1e_sealed_film_reels
                WHERE job_id=? AND chunk_index=?""",(job,index)).fetchone()
            if existing:raise RuntimeError("An earlier protected reel occupies this frame range")
            prior=db.execute("""SELECT status,source_sha256,completed_chunks,
                completed_bytes FROM w1e_sealed_film_jobs
                WHERE project_id=? AND id=?""",(pid,job)).fetchone()
            if (prior is None or prior["status"]!="rendering" or
                prior["completed_chunks"]!=index or
                prior["source_sha256"]!=record["source_sha256"] or
                receipt["source_sha256"]!=record["source_sha256"] or
                prior["completed_bytes"]+receipt["size_bytes"]>MAX_OUTPUT_BYTES):
                raise RuntimeError("Protected reel job changed during worker execution")
            db.execute("""INSERT INTO w1e_sealed_film_reels(
                job_id,project_id,chunk_index,start_frame,end_frame,
                worker_id,source_sha256,output_name,reel_sha256,
                size_bytes,native_receipt_json,completed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job,pid,index,receipt["start_frame"],receipt["end_frame"],
                 receipt["worker_id"],receipt["source_sha256"],receipt["output_name"],
                 receipt["sha256"],receipt["size_bytes"],
                 _canonical(receipt).decode("utf8"),_now()))
            db.execute("""UPDATE w1e_sealed_film_jobs SET
                completed_chunks=?,completed_bytes=?,updated_at=?
                WHERE project_id=? AND id=?""",
                (index+1,prior["completed_bytes"]+receipt["size_bytes"],
                 _now(),pid,job))
        self._change(pid,token,commit)

    def _complete(self,pid,token,job,record):
        rows=self._reels(pid,token,job)
        if len(rows)!=record["total_chunks"]:
            raise RuntimeError("A protected film is missing verified reels")
        source=record["source_sha256"]
        cursor=0;total=0
        entries=[]
        for i,row in enumerate(rows):
            if (row["chunk_index"]!=i or row["start_frame"]!=cursor or
                row["source_sha256"]!=source or
                not row["end_frame"]>cursor):
                raise RuntimeError("Protected reel time continuity is broken")
            cursor=row["end_frame"];total+=row["size_bytes"]
            entries.append({"chunk_index":i,"start_frame":row["start_frame"],
                "end_frame":row["end_frame"],"sha256":row["reel_sha256"],
                "bytes":row["size_bytes"],"asset_name":row["output_name"]})
        if cursor!=record["total_frames"] or total>MAX_OUTPUT_BYTES:
            raise RuntimeError("Protected film lost complete frame coverage")
        manifest={"format":MANIFEST,"job_id":job,"source_sha256":source,
            "total_frames":cursor,"fps":24,"audio_hz":48000,
            "reels":entries,"reel_count":len(entries),
            "encrypted_originals":True,
            "no_plaintext_working_film_files":True,
            "not_a_gapless_professional_or_DCP_file":True}
        raw=_canonical(manifest)
        if len(raw)>2*1024*1024:
            raise RuntimeError("Protected film playlist is too large")
        name=f"render/{job}/verified-playlist.json"
        indexed=self._read(pid,token,lambda db:db.execute(
            "SELECT sha256,size_bytes FROM source_assets WHERE name=?",
            (name,)).fetchone())
        if indexed:
            # Crash after durable encrypted asset publication but before
            # the completed state: authenticate and compare EXACT bytes.
            # Never adopt an unknown filesystem orphan or changed playlist.
            prior=self.live.get_original(pid,token,name)
            if prior!=raw or indexed["sha256"]!=sha256(raw).hexdigest():
                raise RuntimeError("Protected playlist changed after interrupted publication")
            digest=indexed["sha256"]
        else:
            witness=self.live.put_original(pid,token,name,raw,"application/json")
            digest=witness["sha256"]
        self._set(pid,token,job,"completed",manifest={
            "name":name,"sha256":digest})
        return manifest

    def _perform(self,pid,token,job,stop):
        try:
            record=self._job(pid,token,job)
            self._auth(pid,token)
            plan=self._analyze(pid,token,job,record,stop)
            record=self._job(pid,token,job)
            if record["status"]=="queued":
                self._set(pid,token,job,"rendering")
            parts={r["chunk_index"]:r for r in self._reels(pid,token,job)}
            if any(i!=k for i,k in enumerate(sorted(parts))):
                raise RuntimeError("A protected reel checkpoint is discontinuous")
            for index in range(record["total_chunks"]):
                if stop.is_set():raise InterruptedError("Director stopped protected film")
                self._auth(pid,token)
                if index in parts:
                    # Every previously accepted checkpoint must independently
                    # authenticate from sealed storage before being reused.
                    part=parts[index]
                    raw=self.live.get_original(pid,token,part["output_name"])
                    if sha256(raw).hexdigest()!=part["reel_sha256"]:
                        raise RuntimeError("Prior sealed reel changed after restart")
                    continue
                assembly,start,end=self._window(pid,token,job,record,index)
                digests=source_digests(assembly)
                binding=sha256(_canonical(digests)).hexdigest()
                ticket=self._one_reel_ticket(pid,job,index,binding)
                try:
                    receipt=self.native.render(pid,token,job,index,
                        record["total_frames"],assembly,plan,ticket,cancel=stop)
                finally:
                    with self.guard:self.tickets.pop(ticket,None)
                self._append(pid,token,job,record,index,receipt)
            self._set(pid,token,job,"finalizing")
            self._complete(pid,token,job,record)
        except BaseException as error:
            state="cancelled" if stop.is_set() else (
                "interrupted" if isinstance(error,(InterruptedError,PermissionError,
                    LiveFilmError)) else "failed")
            try:self._set(pid,token,job,state,
                issue="Protected film requires human review before continuing")
            except Exception:pass
        finally:
            with self.guard:
                self.active.pop(job,None)
                for ticket,value in list(self.tickets.items()):
                    if value[1]==job:self.tickets.pop(ticket,None)

    def resume(self,pid,token,job,approval_id):
        self._auth(pid,token)
        self.reconcile(pid,token)
        record=self._job(pid,token,job)
        if record["status"] not in ("interrupted","failed","cancelled"):
            raise RuntimeError("Protected film is not available for reviewed restart")
        if not self.review_authority(
                pid,record["edit_revision"],record["source_sha256"],
                record["total_frames"],approval_id):
            raise PermissionError("Protected film restart requires new native human review")
        first,_,_=self._window(pid,token,job,record,0)
        def reopen(db):
            db.execute("""UPDATE w1e_sealed_film_jobs SET
                status='queued',issue=NULL,updated_at=?
                WHERE project_id=? AND id=? AND status IN
                ('interrupted','failed','cancelled')""",
                (_now(),pid,job))
        self._change(pid,token,reopen)
        self._launch(pid,token,job)
        return self.status(pid,token,job)

    def cancel(self,pid,token,job):
        self._auth(pid,token)
        with self.guard:
            active=self.active.get(job)
            if active:active[1].set()
        return self.status(pid,token,job)

    def list(self,pid,token):
        self._auth(pid,token)
        self.reconcile(pid,token)
        rows=self._read(pid,token,lambda db:[
            row["id"] for row in db.execute("""SELECT id FROM
            w1e_sealed_film_jobs WHERE project_id=?
            ORDER BY created_at DESC LIMIT 25""",(pid,))])
        return [self.status(pid,token,job) for job in rows]

    def manifest(self,pid,token,job):
        record=self._job(pid,token,job)
        if record["status"]!="completed" or not record["manifest_name"]:
            raise RuntimeError("Protected film playlist has not been verified")
        original=self.live.get_original(pid,token,record["manifest_name"])
        if sha256(original).hexdigest()!=record["manifest_sha256"]:
            raise RuntimeError("Sealed film manifest changed after completion")
        data=json.loads(original)
        if (data.get("format")!=MANIFEST or
            data.get("source_sha256")!=record["source_sha256"] or
            data.get("total_frames")!=record["total_frames"] or
            data.get("reel_count")!=record["total_chunks"]):
            raise RuntimeError("Protected film playback source identity changed")
        return data

    def reel(self,pid,token,job,index):
        import hashlib
        from backend.nvp_g08_native_avi import verify_movie
        from backend.nvp_g09e_chunk import MAX_CHUNK_BYTES
        index=int(index)
        record=self._job(pid,token,job)
        if record["status"]!="completed" or not 0<=index<record["total_chunks"]:
            raise RuntimeError("The protected original film reel is unavailable")
        manifest=self.manifest(pid,token,job)
        part=manifest["reels"][index]
        if part["chunk_index"]!=index:
            raise RuntimeError("A protected film playlist index changed")
        original=self.live.get_original(pid,token,part["asset_name"])
        if (not 0<len(original)<=MAX_CHUNK_BYTES or
            len(original)!=part["bytes"] or
            hashlib.sha256(original).hexdigest()!=part["sha256"]):
            raise RuntimeError("Sealed film reel authentication failed")
        checked=verify_movie(original,part["end_frame"]-part["start_frame"],
                             expected_sha=part["sha256"])
        if not checked["verified"]:
            raise RuntimeError("Protected reel lost its original Film Time")
        return original

    def status(self,pid,token,job):
        row=self._job(pid,token,job)
        return {"format":FORMAT,"id":job,"job_id":job,"status":row["status"],
            "completed_chunks":row["completed_chunks"],
            "total_chunks":row["total_chunks"],
            "reels_total":row["total_chunks"],
            "reels_verified":row["completed_chunks"],
            "progress_percent":round(100*row["completed_chunks"]/
                max(1,row["total_chunks"]),2),
            "total_frames":row["total_frames"],
            "duration_seconds":row["total_frames"]/24,
            "resumable":row["status"] in ("interrupted","cancelled","failed"),
            "completed":row["status"]=="completed",
            "working_film_encrypted":True,
            "source_sha256":row["source_sha256"],
            "issue":row["issue"],
            "complete":row["status"]=="completed",
            "requires_new_human_approval":row["status"] in (
                "interrupted","cancelled","failed")}
