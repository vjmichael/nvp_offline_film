"""NVP-RES-01: measured NVP-owned process resources, safe for Lu to read.

Existing nvp_resource_guard owns SYSTEM RAM/VRAM sampling and heavy-job
admission. This module adds PROCESS-SCOPED evidence for the NVP host and only
children actually launched by NVP's trusted supervisor. It never attaches to
arbitrary foreign PIDs or grants Lu launch/cancel authority.

psutil's descendant enumeration is telemetry only, NOT kernel custody proof.
Lost/detached descendants can evade a process-tree walk; the existing Job
Object/cgroup supervisor remains the execution/termination authority.
Per-process GPU memory is UNKNOWN unless a separately reviewed sensor proves it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
import re
import threading
import time

from backend.nvp_resource_guard import collect_resources

try:
    import psutil
except ImportError:  # A missing wheel must never be represented as zero usage.
    psutil = None

JOB_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
FORMAT = "nvp.resources.owned_process_report.v1"


def _mib(byte_count):
    return round(byte_count / (1024 * 1024), 3)


@dataclass
class _ObservedChild:
    job_id: str
    pid: int
    create_time: float
    peak_rss_mb: float = 0.0
    last_rss_mb: float | None = None
    last_cpu_seconds: float | None = None
    last_read_bytes: int | None = None
    last_write_bytes: int | None = None
    sampled_at: float | None = None
    stopped: bool = False
    last_error: str | None = None
    _last_cpu_seconds: float | None = field(default=None, repr=False)
    _last_monotonic: float | None = field(default=None, repr=False)


def _is_current_child(proc, owner_pid):
    """Accept only a direct/descendant of THIS NVP host at registration."""
    try:
        node=proc
        for _ in range(64):
            parent=node.parent()
            if parent is None:
                return False
            if parent.pid==owner_pid:
                return True
            node=parent
    except (psutil.Error, OSError, ValueError):
        return False
    return False


class NVPProcessResourceMonitor:
    def __init__(self, *, resource_collector=collect_resources, clock=time.time):
        if not callable(resource_collector) or not callable(clock):
            raise TypeError("Native resource collector and clock required")
        self._collect=resource_collector
        self._clock=clock
        self._owner_pid=os.getpid()
        self._lock=threading.RLock()
        self._jobs={}
        self._host_peak_rss_mb=0.0

    def register_owned_child(self,job_id,pid):
        """Only trusted post-launch supervisor calls this, not a model/IPC client."""
        if not isinstance(job_id,str) or not JOB_ID.fullmatch(job_id):
            raise ValueError("Exact bounded NVP-owned job ID required")
        if type(pid) is not int or pid<=0:
            raise ValueError("Invalid NVP owned OS worker pid")
        if psutil is None:
            raise RuntimeError("psutil unavailable: owned worker telemetry cannot be verified")
        try:
            process=psutil.Process(pid)
            if not _is_current_child(process,self._owner_pid):
                raise PermissionError("Cannot attribute a non-NVP process to this host")
            born=process.create_time()
        except psutil.Error as error:
            raise RuntimeError("NVP worker exited before registration") from error
        with self._lock:
            if job_id in self._jobs:
                raise RuntimeError("NVP resource job identity already registered")
            self._jobs[job_id]=_ObservedChild(job_id,pid,born)
        return True

    def _sample_child(self,observed,now):
        """Source process identity must match: stale PID reuse is not a worker."""
        try:
            process=psutil.Process(observed.pid)
            if abs(process.create_time()-observed.create_time)>0.0001:
                observed.last_error="Original worker PID was reused"
                observed.stopped=True
                return []
            # Process-tree telemetry is best effort; descendant escape
            # must be handled by the existing OS custody mechanism, not here.
            descendants=[process]+process.children(recursive=True)
            owned=[]
            seen=set()
            for child in descendants:
                try:
                    identity=(child.pid,child.create_time())
                    if identity in seen:
                        continue
                    seen.add(identity)
                    with child.oneshot():
                        info=child.memory_info()
                        cpu=child.cpu_times()
                        io=child.io_counters() if hasattr(child,"io_counters") else None
                    owned.append((identity,info.rss,
                                  float(cpu.user+cpu.system),
                                  int(io.read_bytes) if io else None,
                                  int(io.write_bytes) if io else None))
                except (psutil.Error, OSError):
                    continue
            if not owned:
                observed.last_error="Worker process disappeared before telemetry read"
                return []
            observed.last_rss_mb=round(_mib(sum(x[1] for x in owned)),3)
            observed.peak_rss_mb=max(observed.peak_rss_mb,observed.last_rss_mb)
            cpu_total=sum(x[2] for x in owned)
            observed.last_cpu_seconds=round(cpu_total,4)
            observed.last_read_bytes=sum(x[3] for x in owned if x[3] is not None) if all(
                x[3] is not None for x in owned) else None
            observed.last_write_bytes=sum(x[4] for x in owned if x[4] is not None) if all(
                x[4] is not None for x in owned) else None
            observed.sampled_at=now
            observed.last_error=None
            return owned
        except (psutil.Error, OSError, ValueError):
            observed.last_error="Worker process telemetry unavailable (exited or inaccessible)"
            return []

    def finish_owned_child(self,job_id):
        """Preserve last observed/peak evidence after the process exits."""
        with self._lock:
            row=self._jobs.get(job_id)
            if row is None:
                return False
            if not row.stopped and psutil is not None:
                self._sample_child(row,self._clock())
            row.stopped=True
            return True

    def read_only_report_for_lu(self):
        """No executable paths, arbitrary processes, control tokens or permissions."""
        snapshot=self._collect()
        host_rss=None
        host_cpu=None
        if psutil is not None:
            try:
                owner=psutil.Process(self._owner_pid)
                if owner.pid!=os.getpid():
                    raise RuntimeError("NVP host process identity changed")
                with owner.oneshot():
                    host_rss=_mib(owner.memory_info().rss)
                    times=owner.cpu_times()
                    host_cpu=round(float(times.user+times.system),4)
            except (psutil.Error,OSError,RuntimeError):
                pass
        with self._lock:
            now=self._clock()
            if host_rss is not None:
                self._host_peak_rss_mb=max(self._host_peak_rss_mb,host_rss)
            reports=[]
            running_rss=0.0
            unknown=0
            for job_id in sorted(self._jobs):
                row=self._jobs[job_id]
                if not row.stopped and psutil is not None:
                    self._sample_child(row,now)
                if not row.stopped:
                    if row.last_error or row.last_rss_mb is None:
                        unknown+=1
                    else:
                        running_rss+=row.last_rss_mb
                reports.append({
                    "job_id":row.job_id,
                    "state":"STOPPED" if row.stopped else "OBSERVING",
                    "worker_pid":row.pid,
                    "observed_rss_mb":row.last_rss_mb,
                    "peak_observed_rss_mb":round(row.peak_rss_mb,3),
                    "observed_cpu_time_seconds":row.last_cpu_seconds,
                    "observed_io_read_bytes":row.last_read_bytes,
                    "observed_io_write_bytes":row.last_write_bytes,
                    "sampled_at":row.sampled_at,
                    "observed_process_tree_only":True,
                    "per_process_gpu_memory_mb":None,
                    "gpu_memory_attribution_supported":False,
                    "warning":row.last_error,
                })
            total=None if host_rss is None or unknown else round(
                host_rss+running_rss,3)
        cpu_count=os.cpu_count()
        return {
            "format":FORMAT,
            "source":"NVP",
            "measured_at_unix":now,
            "report_read_only":True,
            "host_authority_remains_nvp":True,
            "process_ownership_scope":"host_plus_trusted_registered_live_workers",
            "host_process_rss_mb":host_rss,
            "host_peak_observed_rss_mb":round(self._host_peak_rss_mb,3),
            "host_cpu_time_seconds":host_cpu,
            "running_workers_observed_rss_mb":round(running_rss,3),
            "nvp_host_plus_visible_workers_rss_mb":total,
            "unmeasured_running_worker_count":unknown,
            "logical_cpu_count":cpu_count if type(cpu_count) is int and cpu_count>0 else None,
            "system_resource_snapshot":snapshot.public(),
            "owned_workers":reports,
            "process_tree_telemetry_not_kernel_custody_proof":True,
            "no_foreign_process_usage_included":True,
            "unknown_metrics_not_reported_as_zero":True,
            "warnings":[
                *snapshot.warnings,
                *(["psutil missing; cannot attribute NVP process usage"]
                  if psutil is None else []),
                *(["Live process usage incomplete; at least one worker is unmeasured"]
                  if unknown else []),
            ],
        }
