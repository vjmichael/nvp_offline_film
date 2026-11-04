"""STACK-02C3: durable resource reservations and truthful production activity.

All admission decisions are serialized with SQLite BEGIN IMMEDIATE across NVP
host processes. Stale ACTIVE reservations deliberately block rather than being
silently stolen after a crash; an OS-verified recovery must finalize them.
Activity % only exists when an actual provider supplies a measured fraction.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3
import time

from backend.nvp_resource_guard import AdmissionRequest,collect_resources,decide_admission,emergency_pressure

PHASES=frozenset({
    "waiting_for_resources","checking_memory","starting","loading_model",
    "warming_model","processing_prompt","generating","offloading_model",
    "preparing_scene","building_scene","rendering","saving_output",
    "verifying_output","cooling_down","recovering","finished",
    "external_model_wait","failed","cancelled",
})
TERMINAL=frozenset({"SUCCEEDED","FAILED","CANCELLED","INTERRUPTED"})


def default_runtime_dir():
    if os.name=="nt":
        base=os.environ.get("LOCALAPPDATA") or str(Path.home()/"AppData"/"Local")
        return Path(base)/"NVP"/"runtime"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home()/".local"/"state")/"nvp"/"runtime"


class TaskLedger:
    def __init__(self,root=None,*,sampler=collect_resources):
        self.root=Path(root or default_runtime_dir()).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.db_path=self.root/"task_activity.sqlite3"
        self.sampler=sampler
        with self._db() as db:
            # Switch journal mode only during schema initialization. Reissuing
            # PRAGMA journal_mode=WAL on every per-task connection can contend
            # with a second NVP host in the admission BEGIN IMMEDIATE window.
            # Busy timeout is established before this initialization.
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                    state TEXT NOT NULL, phase TEXT NOT NULL, detail TEXT NOT NULL,
                    completed_fraction REAL, ram_mb INTEGER NOT NULL DEFAULT 0,
                    gpu_mb INTEGER NOT NULL DEFAULT 0, device_id TEXT,
                    reserved INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL, at REAL NOT NULL, state TEXT NOT NULL,
                    phase TEXT NOT NULL, detail TEXT NOT NULL,
                    completed_fraction REAL
                );
            """)

    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.db_path,timeout=20,isolation_level=None)
        try:
            # First operation must install busy handler. Never reconfigure WAL
            # while another process is holding admission's write transaction.
            db.execute("PRAGMA busy_timeout=20000")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:db.close()

    def _event(self,db,task_id,state,phase,detail,fraction):
        db.execute("""INSERT INTO task_events(task_id,at,state,phase,detail,completed_fraction)
                     VALUES(?,?,?,?,?,?)""",
                   (task_id,time.time(),state,phase,detail,fraction))

    def admit(self,request:AdmissionRequest):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM tasks WHERE id=?",(request.task_id,)).fetchone():
                db.rollback()
                raise RuntimeError("Task ID already used; durable request must not be repeated")
            snap=self.sampler()
            used=db.execute("""SELECT COALESCE(SUM(ram_mb),0),
                COALESCE(SUM(CASE WHEN device_id=? THEN gpu_mb ELSE 0 END),0)
                FROM tasks WHERE reserved=1""",(request.device_id,)).fetchone()
            allowed,reason,margins=decide_admission(snap,request,int(used[0]),int(used[1]))
            state="ACTIVE" if allowed else "QUEUED"
            phase="starting" if allowed else "waiting_for_resources"
            now=time.time()
            db.execute("""INSERT INTO tasks(id,kind,title,state,phase,detail,completed_fraction,
                ram_mb,gpu_mb,device_id,reserved,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (request.task_id,request.kind,request.title,state,phase,reason,None,
                 request.ram_mb,request.gpu_mb,request.device_id,int(allowed),now,now))
            self._event(db,request.task_id,state,phase,reason,None)
            db.commit()
        return {"admitted":allowed,"state":state,"reason":reason,"margins":margins}

    def retry(self,task_id):
        """Trusted host calls this to promote a queued task, no UI shell access."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT kind,title,state,ram_mb,gpu_mb,device_id
                              FROM tasks WHERE id=?""",(task_id,)).fetchone()
            if not row or row[2]!="QUEUED":
                db.rollback()
                raise RuntimeError("Only queued tasks can be retried")
            req=AdmissionRequest(task_id,row[0],row[1],row[3],row[4],row[5])
            used=db.execute("""SELECT COALESCE(SUM(ram_mb),0),
                COALESCE(SUM(CASE WHEN device_id=? THEN gpu_mb ELSE 0 END),0)
                FROM tasks WHERE reserved=1""",(req.device_id,)).fetchone()
            allowed,reason,margins=decide_admission(self.sampler(),req,int(used[0]),int(used[1]))
            state="ACTIVE" if allowed else "QUEUED"
            phase="starting" if allowed else "waiting_for_resources"
            db.execute("""UPDATE tasks SET state=?,phase=?,detail=?,reserved=?,updated_at=? WHERE id=?""",
                (state,phase,reason,int(allowed),time.time(),task_id))
            self._event(db,task_id,state,phase,reason,None)
            db.commit()
        return {"admitted":allowed,"state":state,"reason":reason,"margins":margins}

    def observe_external(self,task_id,title,phase="external_model_wait",
                         detail="Awaiting separately managed local AI server"):
        """Observation only; never claim NVP loaded/unloaded an external model."""
        if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}",task_id)
            or not isinstance(title,str) or not 1<=len(title)<=120 or phase not in PHASES):
            raise ValueError("Invalid external activity")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            now=time.time()
            db.execute("""INSERT INTO tasks(id,kind,title,state,phase,detail,
                ram_mb,gpu_mb,reserved,created_at,updated_at)
                VALUES(?,?,?,?,?,?,0,0,0,?,?)""",
                (task_id,"external_ai",title,"OBSERVING",phase,detail[:240],now,now))
            self._event(db,task_id,"OBSERVING",phase,detail[:240],None)
            db.commit()

    def update(self,task_id,phase,detail,*,fraction=None):
        if (phase not in PHASES or not isinstance(detail,str) or len(detail)>240 or
            fraction is not None and
            (type(fraction) not in (int,float) or not 0<=fraction<=1)):
            raise ValueError("Progress requires a valid phase and measured 0..1 fraction")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT state FROM tasks WHERE id=?",(task_id,)).fetchone()
            if not row or row[0] not in ("ACTIVE","OBSERVING"):
                db.rollback();raise RuntimeError("Task not currently working")
            db.execute("""UPDATE tasks SET phase=?,detail=?,completed_fraction=?,updated_at=?
                WHERE id=?""",(phase,detail,fraction,time.time(),task_id))
            self._event(db,task_id,row[0],phase,detail,fraction)
            db.commit()

    def finish(self,task_id,state,detail=""):
        if state not in TERMINAL or not isinstance(detail,str) or len(detail)>240:
            raise ValueError("Invalid task terminal state")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT state FROM tasks WHERE id=?",(task_id,)).fetchone()
            if not row or row[0] not in ("ACTIVE","OBSERVING","QUEUED"):
                db.rollback();raise RuntimeError("Task already finished or missing")
            phase="finished" if state=="SUCCEEDED" else "cancelled" if state=="CANCELLED" \
                  else "recovering" if state=="INTERRUPTED" else "failed"
            fraction=1.0 if state=="SUCCEEDED" else None
            db.execute("""UPDATE tasks SET state=?,phase=?,detail=?,completed_fraction=?,
                reserved=0,updated_at=? WHERE id=?""",
                (state,phase,detail,fraction,time.time(),task_id))
            self._event(db,task_id,state,phase,detail,fraction)
            db.commit()

    def get_task(self,task_id):
        with self._db() as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
        return dict(row) if row else None

    def critical_pressure(self,task_id):
        row=self.get_task(task_id)
        if not row or row["state"]!="ACTIVE":return None
        return emergency_pressure(self.sampler(),
            gpu_device=row["device_id"] if row["gpu_mb"] else None)

    def heartbeat(self,task_id):
        # Actual Blender supervisor emits this while its contained child
        # remains alive. A heartbeat is NOT fabricated render percentage.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT state FROM tasks WHERE id=?",(task_id,)).fetchone()
            if not row or row[0]!="ACTIVE":
                db.rollback()
                raise RuntimeError("Cannot heartbeat a nonrunning NVP task")
            db.execute("UPDATE tasks SET updated_at=? WHERE id=?",
                       (time.time(),task_id))
            db.commit()

    def snapshot(self,limit=12):
        if type(limit) is not int or not 1<=limit<=100:raise ValueError("Invalid task limit")
        sample=self.sampler()
        with self._db() as db:
            db.row_factory=sqlite3.Row
            rows=[dict(x) for x in db.execute("""SELECT id,kind,title,state,phase,detail,
                completed_fraction,ram_mb,gpu_mb,device_id,created_at,updated_at
                FROM tasks ORDER BY CASE WHEN state IN ('ACTIVE','QUEUED','OBSERVING')
                THEN 0 ELSE 1 END,updated_at DESC LIMIT ?""",(limit,))]
            reserved=db.execute("""SELECT COALESCE(SUM(ram_mb),0),
                COALESCE(SUM(gpu_mb),0) FROM tasks WHERE reserved=1""").fetchone()
        # Never show an abandoned ACTIVE row as definitely still rendering.
        # Presentation changes to STALE_UNVERIFIED only; reservations remain
        # held until verified OS worker cleanup and journal reconciliation.
        now=time.time()
        for row in rows:
            if row["state"]=="ACTIVE" and now-row["updated_at"]>15:
                row["state"]="STALE_UNVERIFIED"
                row["phase"]="recovering"
                row["completed_fraction"]=None
                row["detail"]="Worker stopped reporting; cleanup and output verification required. Safety reservation retained."
        return {"format":"nvp.system.resource_activity.v1","sample":sample.public(),
            "tasks":rows,"reservations":{"ram_mb":int(reserved[0]),"gpu_mb":int(reserved[1])},
            "safety":{"ram_headroom_fraction":.20,"ram_min_headroom_mb":2048,
                "vram_headroom_fraction":.20,"vram_min_headroom_mb":1024,
                "unknown_vram_behavior":"queue_gpu_work",
                "progress_policy":"measured_or_indeterminate",
                "external_model_management":"not_owned_by_nvp"}}

    def events(self,task_id,limit=30):
        if type(limit) is not int or not 1<=limit<=100:raise ValueError("Invalid limit")
        with self._db() as db:
            db.row_factory=sqlite3.Row
            return [dict(x) for x in db.execute("""SELECT sequence,at,state,phase,detail,
                completed_fraction FROM task_events WHERE task_id=?
                ORDER BY sequence DESC LIMIT ?""",(task_id,limit))]
