"""USD-FILM-01S: resource-adaptive virtual camera / shot batch queue.

The director chooses an EDIT and (optionally) shots per batch. NVP uses
existing RAM/VRAM admission plus CPU count to choose safe *simultaneous*
workers, independently of number of queued shots. A group of 12 shots may
execute one at a time on a small PC. Full GPU renderer support is never
assumed from a VRAM sensor: reviewed backend/device capability is required.

Queue state is SQLite durable, all transitions are compare-and-swap, and
uncompleted claimed shots become INTERRUPTED after a host restart. Replaying
a claim requires a fresh authorization and independent OS custody evidence.
The actual Blender worker remains the existing protected broker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import contextmanager
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

from backend.nvp_resource_guard import (
    AdmissionRequest, ResourceSnapshot, decide_admission)

PLAN_FORMAT="nvp.film01s.adaptive_shot_queue.v1"
JOB_ID=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
SHA=re.compile(r"^[a-f0-9]{64}$")
PREVIEW="lofi"
FINAL="hifi"
STAGES=(PREVIEW,FINAL)


def _canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False)


def _sha(data):
    return sha256(_canonical(data).encode("ascii")).hexdigest()


def _valid_id(value):
    return isinstance(value,str) and JOB_ID.fullmatch(value) is not None


@dataclass(frozen=True)
class Shot:
    shot_id: str
    camera_id: str
    source_in_frame: int
    source_out_frame: int

    def __post_init__(self):
        if (not _valid_id(self.shot_id) or not _valid_id(self.camera_id)
            or type(self.source_in_frame) is not int or
            type(self.source_out_frame) is not int or
            not 0<=self.source_in_frame<self.source_out_frame<=720):
            raise ValueError("One bounded source-locked original 30s camera shot required")


@dataclass(frozen=True)
class BatchPreferences:
    shots_per_batch: int | None = None
    parallel_worker_limit: int | None = None
    renderer: str = "cpu"
    gpu_device_id: str | None = None
    preview_worker_ram_mb: int = 768
    final_worker_ram_mb: int = 3072
    gpu_worker_vram_mb: int = 3072

    def __post_init__(self):
        if (self.shots_per_batch is not None and
            (type(self.shots_per_batch) is not int or
             not 1<=self.shots_per_batch<=64)):
            raise ValueError("Director shots per batch must be 1–64 or Auto")
        if (self.parallel_worker_limit is not None and
            (type(self.parallel_worker_limit) is not int or
             not 1<=self.parallel_worker_limit<=32)):
            raise ValueError("Concurrent worker ceiling must be 1–32 or Auto")
        if self.renderer not in ("cpu","gpu"):
            raise ValueError("Renderer must be reviewed CPU or GPU mode")
        if (self.renderer=="gpu" and
            (not isinstance(self.gpu_device_id,str) or
             not re.fullmatch(r"[A-Za-z0-9:_.-]{1,64}",self.gpu_device_id))):
            raise ValueError("GPU mode requires a measured device ID")
        if self.renderer=="cpu" and self.gpu_device_id is not None:
            raise ValueError("CPU plan cannot carry a hidden GPU reservation")
        if any(type(x) is not int or not 256<=x<=65536 for x in (
            self.preview_worker_ram_mb,self.final_worker_ram_mb,
            self.gpu_worker_vram_mb)):
            raise ValueError("Worker RAM/VRAM budget must be conservative and bounded")


def safe_parallelism(snapshot:ResourceSnapshot,preferences:BatchPreferences,
                     *,quality,verified_cycles_gpu_ids=(),
                     reserved_ram_mb=0,reserved_gpu_mb=0,
                     cpu_threads=None):
    """Predicted safe concurrency; each actual worker still re-admitted."""
    if not isinstance(snapshot,ResourceSnapshot) or not isinstance(
            preferences,BatchPreferences) or quality not in STAGES:
        raise TypeError("Measured NVP resources and typed shot policy required")
    if (type(reserved_ram_mb) is not int or not 0<=reserved_ram_mb<=65536
        or type(reserved_gpu_mb) is not int or
        not 0<=reserved_gpu_mb<=65536):
        raise ValueError("Reserved resources must be bounded")
    threads=os.cpu_count() if cpu_threads is None else cpu_threads
    if type(threads) is not int or not 1<=threads<=4096:
        return {"safe_workers":0,"reason":"CPU capacity unmeasured",
                "memory_margin_mb":None,"gpu_budget_scope":None}
    per_ram=(preferences.preview_worker_ram_mb if quality==PREVIEW else
             preferences.final_worker_ram_mb)
    gpu_mb=(preferences.gpu_worker_vram_mb
            if preferences.renderer=="gpu" else 0)
    if preferences.renderer=="gpu" and preferences.gpu_device_id not in set(
            verified_cycles_gpu_ids):
        return {"safe_workers":0,
                "reason":"Selected GPU not independently verified for Blender/Cycles",
                "memory_margin_mb":None,"gpu_budget_scope":None}
    request=AdmissionRequest(
        "film01s_probe","blender","Source-authentic shot admission",
        per_ram,gpu_mb,preferences.gpu_device_id)
    admitted,reason,margins=decide_admission(
        snapshot,request,
        reserved_ram_mb=reserved_ram_mb,
        reserved_gpu_mb=reserved_gpu_mb)
    if not admitted:
        return {"safe_workers":0,"reason":reason,
                "memory_margin_mb":margins["ram_margin_mb"],
                "gpu_budget_scope":None}
    margin=margins["ram_margin_mb"]
    free_for_workers=max(
        0,snapshot.ram_available_mb-reserved_ram_mb-margin)
    ram_slots=free_for_workers//per_ram
    # CPU render and preview have different measured planning costs.
    # This is an initial conservative cap, not a CPU throughput benchmark.
    cpu_slots=max(1,threads//(2 if quality==PREVIEW else 4))
    cap=min(32,cpu_slots,ram_slots)
    gpu_scope=None
    if preferences.renderer=="gpu":
        gpu=next((x for x in snapshot.gpus
                  if x.device_id==preferences.gpu_device_id),None)
        if gpu is None:
            return {"safe_workers":0,"reason":"GPU telemetry unavailable",
                    "memory_margin_mb":margin,"gpu_budget_scope":None}
        gpu_margin=margins["gpu_margin_mb"]
        slots=max(0,(gpu.free_mb-reserved_gpu_mb-gpu_margin)//gpu_mb)
        # DXGI is a PROCESS budget, not verified globally free VRAM.
        if not gpu.globally_measured:
            slots=min(slots,1)
        cap=min(cap,slots)
        gpu_scope=("global_observed" if gpu.globally_measured
                   else "limited_process_budget_only")
    if preferences.parallel_worker_limit is not None:
        cap=min(cap,preferences.parallel_worker_limit)
    return {"safe_workers":cap,
        "reason":"Safe conservative estimate; recheck before each dispatch"
                 if cap else "No remaining measured worker capacity",
        "memory_margin_mb":margin,"gpu_budget_scope":gpu_scope}


def plan_batches(plan_id,source_performance_sha256,shots,preferences,
                 snapshot,*,final_shot_ids=None,
                 verified_cycles_gpu_ids=(),cpu_threads=None,
                 reserved_ram_mb=0,reserved_gpu_mb=0):
    if not _valid_id(plan_id) or not isinstance(
            source_performance_sha256,str) or not SHA.fullmatch(
                source_performance_sha256):
        raise ValueError("Stable shot plan identity and one original source SHA required")
    if (type(shots) not in (list,tuple) or not 1<=len(shots)<=96 or
        any(not isinstance(x,Shot) for x in shots) or
        len({x.shot_id for x in shots})!=len(shots)):
        raise ValueError("Up to 96 unique director-selected shot IDs required")
    chosen={x.shot_id for x in shots}
    if final_shot_ids is None:
        final_ids=chosen
    else:
        if (type(final_shot_ids) not in (list,tuple,set) or
            any(not _valid_id(x) for x in final_shot_ids) or
            len(set(final_shot_ids))!=len(final_shot_ids) or
            not set(final_shot_ids).issubset(chosen)):
            raise ValueError("Hi-fi shots must be a unique subset of selected low-fi viewpoints")
        final_ids=set(final_shot_ids)
    capacity={
        stage:safe_parallelism(
            snapshot,preferences,quality=stage,
            verified_cycles_gpu_ids=verified_cycles_gpu_ids,
            cpu_threads=cpu_threads,
            reserved_ram_mb=reserved_ram_mb,
            reserved_gpu_mb=reserved_gpu_mb)
        for stage in STAGES
    }
    if preferences.shots_per_batch is None:
        # Auto scales camera batch *grouping* according to preview capacity;
        # a zero-capacity PC can still safely queue one shot for later.
        size=max(1,min(16,capacity[PREVIEW]["safe_workers"]*2))
        batch_mode="AUTO"
    else:
        size=preferences.shots_per_batch
        batch_mode="DIRECTOR"
    groups=[]
    for quality in STAGES:
        included=([shot for shot in shots if shot.shot_id in final_ids]
                  if quality==FINAL else shots)
        for start in range(0,len(included),size):
            number=start//size
            entries=[]
            for shot in included[start:start+size]:
                entries.append({**asdict(shot),"quality":quality,
                    "source_performance_sha256":source_performance_sha256})
            groups.append({
                "quality":quality,
                "batch_index":number,
                "shots":entries,
                "planned_shot_count":len(entries),
                "safe_parallel_workers_at_plan_time":
                    capacity[quality]["safe_workers"]})
    body={
        "format":PLAN_FORMAT,"plan_id":plan_id,
        "original_performance_sha256":source_performance_sha256,
        "batch_mode":batch_mode,
        "shots_per_batch":size,
        "director_requested_shots_per_batch":preferences.shots_per_batch,
        "preferences":asdict(preferences),
        "source_shots":[asdict(shot) for shot in shots],
        "selected_final_shot_ids":[x.shot_id for x in shots
                                   if x.shot_id in final_ids],
        "batches":groups,
        "capacity_at_plan_time":capacity,
        "zero_capacity_jobs_remain_queued":True,
        "shot_group_size_is_not_simultaneous_process_count":True,
        "lowfi_queued_before_hifi":True,
    }
    return {"plan":body,"plan_sha256":_sha(body)}


def preview_batch_layout(viewpoint_count,selected_final_count,preferences,
                         snapshot,*,verified_cycles_gpu_ids=(),
                         cpu_threads=None,
                         reserved_ram_mb=0,reserved_gpu_mb=0):
    """Safe UI estimation only; no fabricated FilmIndex source or worker job."""
    if (type(viewpoint_count) is not int or not 1<=viewpoint_count<=96
        or type(selected_final_count) is not int
        or not 0<=selected_final_count<=viewpoint_count
        or not isinstance(preferences,BatchPreferences)):
        raise ValueError("Count original viewpoints and director-selected final shots")
    capacities={
        stage:safe_parallelism(
            snapshot,preferences,quality=stage,
            verified_cycles_gpu_ids=verified_cycles_gpu_ids,
            cpu_threads=cpu_threads,
            reserved_ram_mb=reserved_ram_mb,
            reserved_gpu_mb=reserved_gpu_mb)
        for stage in STAGES}
    size=(preferences.shots_per_batch
          if preferences.shots_per_batch is not None else
          max(1,min(16,capacities[PREVIEW]["safe_workers"]*2)))
    def groups(count):
        return [{"batch":i+1,
                 "first_shot_number":i*size+1,
                 "shot_count":min(size,count-i*size)}
                for i in range((count+size-1)//size)]
    return {
        "format":"nvp.film01s.read_only_batch_capacity_preview.v1",
        "available_source_viewpoints":viewpoint_count,
        "selected_final_shots":selected_final_count,
        "batch_size_mode":"AUTO" if preferences.shots_per_batch is None
                          else "DIRECTOR",
        "shots_per_batch":size,
        "lowfi_preview_batches":groups(viewpoint_count),
        "hifi_selected_shot_batches":groups(selected_final_count),
        "safe_parallel_workers":capacities,
        "render_jobs_started":0,
        "source_film_index_take_verified":False,
        "browser_has_no_native_render_authority":True,
        "real_dispatch_requires_original_source_and_native_broker":True,
    }


class DurableShotBatchQueue:
    """No render process is started here; NVP's broker remains authoritative."""

    def __init__(self,workspace):
        root=Path(workspace).resolve()
        root.mkdir(parents=True,exist_ok=True)
        if root.is_symlink():
            raise ValueError("Batch scheduler workspace cannot be a symlink")
        self.root=root
        self.db=root/"nvp_shot_batches.sqlite3"
        self._lock=threading.RLock()
        with self._open() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY, plan_sha256 TEXT NOT NULL,
                    json TEXT NOT NULL, created_unix REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS tickets (
                    plan_id TEXT NOT NULL,
                    quality TEXT NOT NULL, batch_index INTEGER NOT NULL,
                    shot_id TEXT NOT NULL, ticket_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL, attempt INTEGER NOT NULL,
                    updated_unix REAL NOT NULL, receipt_sha256 TEXT,
                    PRIMARY KEY(plan_id,quality,shot_id));
                """)

    @contextmanager
    def _open(self):
        # Closing explicitly matters for Windows reinstall and job recovery.
        db=sqlite3.connect(self.db,timeout=15,isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    def enqueue(self,wrapped_plan,*,director_event,authorize):
        if not callable(authorize):
            raise TypeError("Host must explicitly authorize exact shot plan")
        if (type(wrapped_plan) is not dict or
            set(wrapped_plan)!={"plan","plan_sha256"} or
            _sha(wrapped_plan["plan"])!=wrapped_plan["plan_sha256"]):
            raise PermissionError("Original shot plan source SHA changed")
        plan=wrapped_plan["plan"]
        if plan.get("format")!=PLAN_FORMAT:
            raise PermissionError("Unrecognized virtual shot batch plan format")
        scope={
            "operation":"nvp.film01s.enqueue_virtual_shot_batches.v1",
            "plan_id":plan["plan_id"],
            "plan_sha256":wrapped_plan["plan_sha256"],
            "source_performance_sha256":plan["original_performance_sha256"],
            "shots_per_batch":plan["shots_per_batch"],
            "shots":[x["shot_id"] for x in plan["source_shots"]]}
        if authorize(director_event,scope) is not True:
            raise PermissionError("Exact director shot batching consent required")
        jobs=[]
        for group in plan["batches"]:
            for shot in group["shots"]:
                jobs.append({
                    "plan_id":plan["plan_id"],
                    "quality":group["quality"],
                    "batch_index":group["batch_index"],
                    "shot_id":shot["shot_id"],
                    "ticket_sha256":_sha(shot)})
        with self._lock,self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM plans WHERE plan_id=?",
                          (plan["plan_id"],)).fetchone():
                raise RuntimeError("Original shot plan already queued; never overwrite")
            db.execute("INSERT INTO plans VALUES (?,?,?,?)",
                (plan["plan_id"],wrapped_plan["plan_sha256"],
                 _canonical(plan),time.time()))
            for job in jobs:
                db.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?)",
                    (job["plan_id"],job["quality"],job["batch_index"],
                     job["shot_id"],job["ticket_sha256"],"QUEUED",0,
                     time.time(),None))
            db.commit()
        return self.status(plan["plan_id"])

    def _load(self,plan_id):
        if not _valid_id(plan_id):
            raise ValueError("Invalid source shot queue identity")
        with self._open() as db:
            stored=db.execute("SELECT plan_sha256,json FROM plans WHERE plan_id=?",
                              (plan_id,)).fetchone()
        if stored is None:
            raise KeyError("Unknown original shot queue")
        manifest=json.loads(stored[1])
        if _sha(manifest)!=stored[0] or manifest["plan_id"]!=plan_id:
            raise RuntimeError("Original director shot queue manifest corrupted")
        return manifest

    def status(self,plan_id):
        plan=self._load(plan_id)
        with self._open() as db:
            rows=db.execute("""
                SELECT quality,batch_index,shot_id,state,attempt,
                       ticket_sha256,receipt_sha256
                FROM tickets WHERE plan_id=?
                ORDER BY CASE quality WHEN 'lofi' THEN 0 ELSE 1 END,
                         batch_index,shot_id""",(plan_id,)).fetchall()
        tickets=[{
            "quality":q,"batch_index":b,"shot_id":s,"state":state,
            "attempt":a,"ticket_sha256":sha,"receipt_sha256":receipt}
            for q,b,s,state,a,sha,receipt in rows]
        expected=len(plan["source_shots"])+len(plan["selected_final_shot_ids"])
        originals={(batch["quality"],shot["shot_id"]):_sha(shot)
            for batch in plan["batches"] for shot in batch["shots"]}
        if (len(tickets)!=expected or len(originals)!=expected or
            {(ticket["quality"],ticket["shot_id"]):ticket["ticket_sha256"]
             for ticket in tickets}!=originals):
            raise RuntimeError("Durable shot queue source ticket inventory changed")
        counts={s:sum(t["state"]==s for t in tickets)
                for s in ("QUEUED","RUNNING","SUCCEEDED","FAILED","INTERRUPTED")}
        return {"plan_id":plan_id,
                "original_performance_sha256":plan[
                    "original_performance_sha256"],
                "shots_per_batch":plan["shots_per_batch"],
                "planned_batch_count":len(plan["batches"]),
                "shot_tickets":tickets,"states":counts,
                "progress_completed":counts["SUCCEEDED"],
                "progress_required":expected,
                "all_shots_finished":counts["SUCCEEDED"]==expected}

    def recover_interrupted(self,plan_id):
        """No silent resumption: all unclosed claims are INTERRUPTED."""
        self._load(plan_id)
        with self._lock,self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("""UPDATE tickets SET state='INTERRUPTED',
                updated_unix=? WHERE plan_id=? AND state='RUNNING'""",
                (time.time(),plan_id)).rowcount
            db.commit()
        return changed

    def claim(self,plan_id,*,quality,shot_id,attempt,authorizer,
              director_event,prove_prior_worker_stopped,
              snapshot,verified_cycles_gpu_ids=(),cpu_threads=None,
              reserved_ram_mb=0,reserved_gpu_mb=0):
        """One reviewed job admission; never treat a batch as a tool permission."""
        if (quality not in STAGES or not _valid_id(shot_id) or
            type(attempt) is not int or not 1<=attempt<=99 or
            not callable(authorizer) or not callable(prove_prior_worker_stopped)):
            raise ValueError("Fresh bounded camera job authority required")
        plan=self._load(plan_id)
        preferences=BatchPreferences(**plan["preferences"])
        capacity=safe_parallelism(snapshot,preferences,quality=quality,
            verified_cycles_gpu_ids=verified_cycles_gpu_ids,
            cpu_threads=cpu_threads,
            reserved_ram_mb=reserved_ram_mb,
            reserved_gpu_mb=reserved_gpu_mb)
        if capacity["safe_workers"]==0:
            return {"admitted":False,"reason":capacity["reason"],
                    "state":"QUEUED_FOR_RESOURCES"}
        with self._lock,self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            # NVP render concurrency is shared by ALL batches/plans, not
            # separately allocated to every director project or Lu request.
            active=db.execute("""SELECT count(*) FROM tickets
                WHERE state='RUNNING'""").fetchone()[0]
            if active>=capacity["safe_workers"]:
                db.rollback()
                return {"admitted":False,
                        "reason":"Other NVP render workers occupy safe capacity",
                        "state":"QUEUED_FOR_RESOURCES"}
            row=db.execute("""SELECT state,attempt,ticket_sha256 FROM tickets
                WHERE plan_id=? AND quality=? AND shot_id=?""",
                (plan_id,quality,shot_id)).fetchone()
            if row is None:
                raise KeyError("Shot is absent from director's original plan")
            state,old_attempt,ticket_sha=row
            if state=="SUCCEEDED":
                raise PermissionError("Source shot already independently verified")
            if state=="RUNNING":
                raise PermissionError("Existing camera worker claim still active")
            if state in ("FAILED","INTERRUPTED"):
                if attempt<=old_attempt or prove_prior_worker_stopped(
                    plan_id,quality,shot_id,old_attempt) is not True:
                    raise PermissionError(
                        "Fresh attempt needs increased ID and proven native worker custody")
            elif attempt!=1:
                raise PermissionError("First original camera job must use attempt 1")
            if quality==FINAL:
                previous=db.execute("""SELECT state FROM tickets
                    WHERE plan_id=? AND quality='lofi' AND shot_id=?""",
                    (plan_id,shot_id)).fetchone()
                if previous is None or previous[0]!="SUCCEEDED":
                    db.rollback()
                    return {"admitted":False,
                            "reason":"Low-fi original source review must complete before hi-fi",
                            "state":"QUEUED_FOR_PREVIEW"}
            scope={
                "operation":"nvp.film01s.claim_one_source_shot.v1",
                "plan_id":plan_id,"plan_sha256":_sha(plan),
                "original_performance_sha256":plan["original_performance_sha256"],
                "quality":quality,"shot_id":shot_id,
                "shot_sha256":ticket_sha,"attempt":attempt,
                "concurrent_worker_capacity":capacity["safe_workers"]}
            if authorizer(director_event,scope) is not True:
                raise PermissionError("No fresh host authorization for this exact camera shot")
            db.execute("""UPDATE tickets SET state='RUNNING',attempt=?,
                updated_unix=? WHERE plan_id=? AND quality=? AND shot_id=?
                AND state=?""",(attempt,time.time(),plan_id,quality,shot_id,state))
            db.commit()
        return {"admitted":True,"state":"RUNNING",
                "plan_id":plan_id,"quality":quality,"shot_id":shot_id,
                "attempt":attempt,"ticket_sha256":ticket_sha,
                "safe_parallel_workers":capacity["safe_workers"],
                "resource_admission_is_not_renderer_execution":True}

    def finish(self,plan_id,*,quality,shot_id,attempt,verified_receipt_sha256,
               verify_native_renderer_result):
        """Only trusted independent broker verification may mark SUCCESS."""
        if (quality not in STAGES or not _valid_id(shot_id) or
            type(attempt) is not int or not 1<=attempt<=99 or
            not callable(verify_native_renderer_result)):
            raise ValueError("Native renderer verification callback required")
        if (not isinstance(verified_receipt_sha256,str) or not
            SHA.fullmatch(verified_receipt_sha256)):
            raise ValueError("A native receipt SHA is required")
        plan=self._load(plan_id)
        with self._lock,self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT state,attempt,ticket_sha256 FROM tickets
                WHERE plan_id=? AND quality=? AND shot_id=?""",
                (plan_id,quality,shot_id)).fetchone()
            if row is None or row[0]!="RUNNING" or row[1]!=attempt:
                raise RuntimeError("No active original source job to accept")
            scope={
                "plan_id":plan_id,"source_performance_sha256":plan[
                    "original_performance_sha256"],
                "quality":quality,"shot_id":shot_id,
                "ticket_sha256":row[2],"attempt":attempt,
                "native_receipt_sha256":verified_receipt_sha256}
            if verify_native_renderer_result(scope) is not True:
                raise PermissionError("Native worker receipt not independently verified")
            db.execute("""UPDATE tickets SET state='SUCCEEDED',
                updated_unix=?,receipt_sha256=?
                WHERE plan_id=? AND quality=? AND shot_id=?""",
                (time.time(),verified_receipt_sha256,
                 plan_id,quality,shot_id))
            db.commit()
        return True

    def fail(self,plan_id,*,quality,shot_id,attempt):
        self._load(plan_id)
        with self._lock,self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("""UPDATE tickets SET state='FAILED',
                updated_unix=? WHERE plan_id=? AND quality=?
                AND shot_id=? AND attempt=? AND state='RUNNING'""",
                (time.time(),plan_id,quality,shot_id,attempt)).rowcount
            if changed!=1:
                raise RuntimeError("No running original shot to report as failed")
            db.commit()
        return True

    def reconcile_verified_completed(self,plan_id,*,quality,shot_id,attempt,
                                     verified_receipt_sha256,
                                     prove_native_worker_stopped,
                                     verify_original_source_outcome):
        """Adopt a genuinely completed outcome after host/process crash.

        Never restart or replay a worker. Compare the exact original
        attempt and immutable source ticket and independently revalidate
        the native receipt while holding the FULL-sync SQLite transaction.
        A mere output path/SQLite state cannot establish completion.
        """
        if (quality not in STAGES or not _valid_id(shot_id) or
            type(attempt) is not int or not 1<=attempt<=99 or
            type(verified_receipt_sha256) is not str or
            SHA.fullmatch(verified_receipt_sha256) is None or
            not callable(prove_native_worker_stopped) or
            not callable(verify_original_source_outcome)):
            raise ValueError("Independent native custody and exact source receipt needed")
        plan=self._load(plan_id)
        with self._lock,self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT state,attempt,ticket_sha256 FROM tickets
                WHERE plan_id=? AND quality=? AND shot_id=?""",
                (plan_id,quality,shot_id)).fetchone()
            if row is None or row[0] not in ("RUNNING","INTERRUPTED","FAILED"):
                raise RuntimeError("No crashed original claim to reconcile")
            if row[1]!=attempt:
                raise PermissionError("Cannot reconcile another renderer attempt")
            context={
                "plan_id":plan_id,
                "plan_sha256":_sha(plan),
                "source_performance_sha256":plan["original_performance_sha256"],
                "quality":quality,"shot_id":shot_id,
                "ticket_sha256":row[2],"attempt":attempt,
                "native_receipt_sha256":verified_receipt_sha256}
            if prove_native_worker_stopped(context) is not True:
                raise PermissionError("Original worker descendant custody not proven")
            if verify_original_source_outcome(context) is not True:
                raise PermissionError("Original native outcome did not reverify")
            changed=db.execute("""UPDATE tickets SET state='SUCCEEDED',
                updated_unix=?,receipt_sha256=?
                WHERE plan_id=? AND quality=? AND shot_id=?
                AND state=? AND attempt=?""",
                (time.time(),verified_receipt_sha256,plan_id,quality,
                 shot_id,row[0],attempt)).rowcount
            if changed!=1:
                raise RuntimeError("Recovered worker result changed concurrently")
            db.commit()
        return True
