"""Read-only, bounded GPU observations; never admission or custody evidence.

Existing native resource sensors report MiB. WDDM PDH reports bytes; the
adapter and process counters are independent observations, not additive.
"""
from __future__ import annotations

import re
import sys
import time

MIB = 1024 * 1024
PERIOD_NS = 2_000_000_000
MAX_ROWS = 64
_ADAPTER = re.compile(r"luid_0x[0-9a-f]{8}_0x[0-9a-f]{8}_phys_[0-9]{1,3}", re.I)
_DEVICE = re.compile(r"(?:dxgi:[0-9]{1,3}|nvidia:[0-9]{1,3}|card[0-9]{1,3})")
_FIELDS = ("dedicated_used_bytes", "shared_used_bytes", "budget_bytes", "capacity_bytes")


def _number(value):
    return value if type(value) is int and 0 <= value < 2**60 else None


def _wddm_rows(pdh, *, pid=None):
    """English PDH provider; absent/localized/unreadable counters are unknown.

    Never log provider instance strings for other processes. Exact PID prefix,
    adapter identity and physical-node suffix only; refuse duplicate names.
    """
    obj = "GPU Adapter Memory" if pid is None else "GPU Process Memory"
    prefix = "" if pid is None else f"pid_{pid}_"
    # PDH caches instance enumeration; refresh before each bounded sample.
    pdh.EnumObjects(None, None, pdh.PERF_DETAIL_WIZARD, 1)
    counters, instances = pdh.EnumObjectItems(None, None, obj, pdh.PERF_DETAIL_WIZARD)
    selected = []
    for instance in instances:
        if not isinstance(instance, str) or not instance.startswith(prefix):
            continue
        device = instance[len(prefix):]
        if _ADAPTER.fullmatch(device):
            selected.append((instance, device.lower()))
    if len(selected) > 16 or len({d for _, d in selected}) != len(selected):
        return []
    if "Dedicated Usage" not in counters or not selected:
        return []
    query = pdh.OpenQuery()
    handles = []
    try:
        for instance, device in selected:
            for metric, field in (("Dedicated Usage", "dedicated_used_bytes"),
                                  ("Shared Usage", "shared_used_bytes")):
                if metric in counters:
                    try:
                        handle = pdh.AddCounter(query, f"\\{obj}({instance})\\{metric}")
                        handles.append((device, field, handle))
                    except Exception:
                        pass
        if not handles:
            return []
        pdh.CollectQueryData(query)
        values = {}
        for device, field, handle in handles:
            try:
                _, value = pdh.GetFormattedCounterValue(handle,
                    pdh.PDH_FMT_LARGE | getattr(pdh, "PDH_FMT_NOSCALE", 0))
                if _number(value) is not None:
                    values.setdefault(device, {})[field] = value
            except Exception:
                pass
        return [{"source": "windows_pdh", "device": key,
                 "scope": "adapter_global" if pid is None else "owned_root_process",
                 **value} for key, value in sorted(values.items())
                if "dedicated_used_bytes" in value]
    finally:
        pdh.CloseQuery(query)


def _native_adapters():
    from backend import nvp_resource_guard as resources
    rows, errors = [], 0
    sources = []
    if sys.platform == "win32":
        sources.append((resources._windows_dxgi_gpus, "windows_dxgi_process_budget"))
        try:
            import win32pdh
            rows.extend(_wddm_rows(win32pdh))
        except Exception:
            errors += 1
    elif sys.platform == "linux":
        sources.append((resources._linux_amd_gpus, "linux_drm_amdgpu_global"))
    if sys.platform in ("linux", "win32"):
        sources.append((resources._nvml_gpus, "nvml_global"))
    for getter, source in sources:
        try:
            for gpu in getter()[:16]:
                if gpu.source != source or not _DEVICE.fullmatch(gpu.device_id):
                    continue
                used, limit = _number(gpu.used_mb), _number(gpu.budget_mb)
                global_scope = source != "windows_dxgi_process_budget"
                if used is None or limit is None or limit <= 0:
                    continue
                if gpu.globally_measured is not global_scope or (global_scope and used > limit):
                    continue
                rows.append({"source": source, "device": gpu.device_id,
                    "scope": "adapter_global" if global_scope else "host_process_local",
                    "dedicated_used_bytes": used*MIB,
                    "capacity_bytes" if global_scope else "budget_bytes": limit*MIB})
        except Exception:
            errors += 1
    return rows, errors


def _native_owned_worker(handle, pid):
    """Only an existing native owned root-process handle, never open by PID.

    Verify liveness before and after querying OS counters. Missing or stale
    instances are unknown. This does NOT measure the full Job's GPU memory.
    """
    if sys.platform != "win32" or handle is None or type(pid) is not int or pid <= 0:
        return []
    import win32event
    import win32pdh
    import win32process
    if win32process.GetProcessId(handle) != pid:
        return []
    def alive():
        return win32event.WaitForSingleObject(handle, 0) == win32event.WAIT_TIMEOUT
    if not alive():
        return []
    rows = _wddm_rows(win32pdh, pid=pid)
    return rows if alive() else []


class GPUObserver:
    def __init__(self):
        self.rows = {}
        self.last_adapter = self.last_worker = None
        self.adapter_attempts = self.worker_attempts = 0
        self.errors = self.dropped_rows = self.collection_wall_ns = 0

    def _merge(self, rows):
        for r in rows:
            key = (r["source"], r["scope"], r["device"])
            if key not in self.rows and len(self.rows) >= MAX_ROWS:
                self.dropped_rows += 1
                continue
            values = {k: _number(r.get(k)) for k in _FIELDS}
            if all(v is None for v in values.values()):
                continue
            row = self.rows.setdefault(key, {"source": key[0], "scope": key[1],
                "device": key[2], "samples": 0, **{f"{prefix}_{k}": None
                    for k in _FIELDS for prefix in ("first", "last", "peak")},
                "minimum_budget_bytes": None})
            row["samples"] += 1
            for k, value in values.items():
                if value is not None:
                    if row[f"first_{k}"] is None:
                        row[f"first_{k}"] = value
                    row[f"last_{k}"] = value
                    previous = row[f"peak_{k}"]
                    row[f"peak_{k}"] = value if previous is None else max(value, previous)
            b = values["budget_bytes"]
            if b is not None:
                previous = row["minimum_budget_bytes"]
                row["minimum_budget_bytes"] = b if previous is None else min(b, previous)

    def sample(self, *, force=False):
        now = time.perf_counter_ns()
        if not force and self.last_adapter is not None and now-self.last_adapter < PERIOD_NS:
            return
        self.last_adapter = now
        self.adapter_attempts += 1
        try:
            rows, errors = _native_adapters()
            self.errors += errors
            self._merge(rows)
        except Exception:
            self.errors += 1
        finally:
            self.collection_wall_ns += time.perf_counter_ns()-now

    def worker(self, handle, pid):
        self.sample()
        now = time.perf_counter_ns()
        if self.last_worker is not None and now-self.last_worker < PERIOD_NS:
            return
        self.last_worker = now
        self.worker_attempts += 1
        try:
            self._merge(_native_owned_worker(handle, pid))
        except Exception:
            self.errors += 1
        finally:
            self.collection_wall_ns += time.perf_counter_ns()-now

    def report(self):
        return {"enabled": True, "status": "observed" if self.rows else "unavailable",
                "interval_ns": PERIOD_NS, "adapter_attempts": self.adapter_attempts,
                "worker_attempts": self.worker_attempts, "errors": self.errors,
                "dropped_rows": self.dropped_rows, "collection_wall_ns": self.collection_wall_ns,
                "sensors": [dict(value) for _, value in sorted(self.rows.items())],
                "limitations": "sampled peaks; PDH may lag; no cross-sensor summation; "
                    "DXGI host process only; PDH owned root only, not Job tree; "
                    "global usage includes unrelated workloads; English PDH provider only; "
                    "resource sensors rounded down to MiB"}
