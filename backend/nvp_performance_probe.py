"""PERF-02A reconstruction: opt-in, process-local observational measurements.

Never consult telemetry for approval, scheduling, publication or custody. No
project identifiers, paths, arguments, data or exception messages are retained.
Counters are process-wide (not exclusive per span); nested spans may overlap.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import os
import time

STAGES = frozenset(("usd.import", "usd.compose", "usd.open", "usd.publish",
    "take.sample", "take.freeze", "take.verify", "blender.operation",
    "blender.launch", "blender.cleanup", "take.worker", "reel.plan",
    "reel.analysis", "reel.render", "reel.frame", "reel.export", "reel.verify",
    "reel.publish", "worker.job", "cache.lookup", "cache.accept", "cache.evict",
    "cycles.chunk", "cycles.plan", "cycles.verify", "cycles.gather"))
_ACTIVE = ContextVar("nvp_perf_active", default=None)
HOST_FIELDS = ("rss_bytes", "peak_rss_bytes", "commit_bytes", "peak_commit_bytes",
               "read_bytes", "write_bytes")


def _counter(value):
    return value if type(value) is int and value >= 0 else None


def _snapshot():
    result = dict.fromkeys(HOST_FIELDS)
    try:
        if os.name == "nt":
            import win32api
            import win32process
            h = win32api.GetCurrentProcess()
            m = win32process.GetProcessMemoryInfo(h)
            for key, native in (("rss_bytes", "WorkingSetSize"),
                ("peak_rss_bytes", "PeakWorkingSetSize"), ("commit_bytes", "PagefileUsage"),
                ("peak_commit_bytes", "PeakPagefileUsage")):
                result[key] = _counter(m.get(native))
            try:
                io = win32process.GetProcessIoCounters(h)
                result["read_bytes"] = _counter(io.get("ReadTransferCount"))
                result["write_bytes"] = _counter(io.get("WriteTransferCount"))
            except Exception:
                pass
        elif os.path.isdir("/proc/self"):
            with open("/proc/self/status", encoding="ascii") as stream:
                for line in stream:
                    name, _, value = line.partition(":")
                    key = {"VmRSS": "rss_bytes", "VmHWM": "peak_rss_bytes"}.get(name)
                    if key is not None:
                        result[key] = int(value.split()[0]) * 1024
            with open("/proc/self/io", encoding="ascii") as stream:
                for line in stream:
                    name, _, value = line.partition(":")
                    key = {"read_bytes": "read_bytes", "write_bytes": "write_bytes"}.get(name)
                    if key is not None:
                        result[key] = _counter(int(value))
    except Exception:
        pass
    return result


class PerfSession:
    def __init__(self, *, gpu=False):
        self.gpu = None
        if gpu:
            from backend.nvp_gpu_observation import GPUObserver
            self.gpu = GPUObserver()
        self.rows = {}
        self.job = {"samples": 0, "cpu_samples": 0, "commit_samples": 0,
                    "cpu_100ns": None, "peak_commit_bytes": None}
        self.cache = {"hits": 0, "misses": 0}
        self.observation_errors = 0

    def report(self):
        return {"format": "nvp.perf.observations.v1", "platform": os.name,
                "scope": "current process; overlapping spans; native Job samples at close",
                "stages": {k: dict(v) for k, v in sorted(self.rows.items())},
                "windows_job": dict(self.job), "cache": dict(self.cache),
                "io_semantics": "Windows transfer bytes; Linux storage bytes",
                "memory_semantics": "process lifetime peak; not per-span allocation",
                "observation_errors": self.observation_errors,
                "gpu_memory_bytes": None, "gpu_budget_bytes": None,
                "gpu_unavailable_reason": "see per-sensor GPU evidence; no single comparable scalar",
                "gpu": self.gpu.report() if self.gpu is not None else {"enabled": False,
                    "status": "disabled", "sensors": []}}

    def _record(self, name, wall, cpu, before, after, raised):
        row = self.rows.setdefault(name, {"calls": 0, "raised": 0, "wall_ns": 0,
            "max_wall_ns": 0, "cpu_ns": 0, "peak_rss_bytes": None,
            "peak_commit_bytes": None, "read_bytes": None, "write_bytes": None,
            "io_sample_pairs": 0})
        row["calls"] += 1
        row["raised"] += int(raised)
        row["wall_ns"] += wall
        row["max_wall_ns"] = max(row["max_wall_ns"], wall)
        row["cpu_ns"] += cpu
        for key in ("peak_rss_bytes", "peak_commit_bytes"):
            values = [x for x in (row[key], before.get(key), after.get(key)) if x is not None]
            row[key] = max(values) if values else None
        if all(before.get(k) is not None and after.get(k) is not None and after[k] >= before[k]
               for k in ("read_bytes", "write_bytes")):
            row["io_sample_pairs"] += 1
            for key in ("read_bytes", "write_bytes"):
                row[key] = (row[key] or 0) + after[key] - before[key]


@contextmanager
def observe(*, gpu=False):
    session = PerfSession(gpu=gpu)
    token = _ACTIVE.set(session)
    try:
        if session.gpu is not None:
            session.gpu.sample(force=True)
        yield session
    finally:
        try:
            if session.gpu is not None:
                session.gpu.sample(force=True)
        finally:
            _ACTIVE.reset(token)


@contextmanager
def span(name):
    session = _ACTIVE.get()
    if session is None or name not in STAGES:
        yield
        return
    try:
        if session.gpu is not None:
            session.gpu.sample()
        before = _snapshot()
        wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    except Exception:
        session.observation_errors += 1
        yield
        return
    raised = True
    try:
        yield
        raised = False
    finally:
        try:
            elapsed = time.perf_counter_ns() - wall
            used = time.process_time_ns() - cpu
            session._record(name, elapsed, used, before, _snapshot(), raised)
        except Exception:
            session.observation_errors += 1


def measured(name):
    if name not in STAGES:
        raise ValueError("Unknown static performance stage")
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            session = _ACTIVE.get()
            if session is None:
                return fn(*args, **kwargs)
            with span(name):
                result = fn(*args, **kwargs)
                if name == "cache.lookup":
                    session.cache["misses" if result is None else "hits"] += 1
                return result
        return wrapped
    return decorate


def observe_windows_job(handle):
    """Use only an already-owned Job handle, before its original close."""
    session = _ACTIVE.get()
    if session is None:
        return
    try:
        import win32job
        a = win32job.QueryInformationJobObject(handle, win32job.JobObjectBasicAccountingInformation)
        e = win32job.QueryInformationJobObject(handle, win32job.JobObjectExtendedLimitInformation)
        if a.get("ActiveProcesses") != 0:
            return
        user, kernel = _counter(a.get("TotalUserTime")), _counter(a.get("TotalKernelTime"))
        peak = _counter(e.get("PeakJobMemoryUsed"))
        row = session.job
        row["samples"] += 1
        if user is not None and kernel is not None:
            row["cpu_samples"] += 1
            row["cpu_100ns"] = (row["cpu_100ns"] or 0) + user + kernel
        if peak is not None:
            row["commit_samples"] += 1
            row["peak_commit_bytes"] = max(row["peak_commit_bytes"] or 0, peak)
    except Exception:
        session.observation_errors += 1


def observe_live_windows_gpu(handle, pid):
    session = _ACTIVE.get()
    if session is not None and session.gpu is not None:
        try:
            session.gpu.worker(handle, pid)
        except Exception:
            session.observation_errors += 1
