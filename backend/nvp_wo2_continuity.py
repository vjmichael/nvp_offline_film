"""WO2 bounded continuity/latency/memory acceptance for immutable 3D scenes.

This measures actual supplied source evaluators (USD pose/raster/texture
callbacks), never pretends that fast dummy callbacks are production proof.
Wall-clock performance depends on machine, target resolution and GPU; a
receipt is evidence, not a claim of calibrated visual quality.
"""
from __future__ import annotations

from hashlib import sha256
import math
import statistics
import time
import tracemalloc


def measure_source_continuity(*,sample,source_sha256,duration_seconds=60,
                              sample_hz=10,approved_cancel=None,
                              max_peak_bytes=512*1024*1024):
    """Generate and measure 600 native Film Time samples over 60 seconds.

    sample(film_time_seconds) returns a verified original-source receipt
    mapping with source_sha256, original_modified=False and a stable
    native_preview_sha256 for that exact tick. Results report *measured*
    real wall time and peak allocations, not simulated frame duration.
    """
    if (not callable(sample) or type(source_sha256) is not str or
        len(source_sha256)!=64 or
        any(ch not in "0123456789abcdef" for ch in source_sha256) or
        type(duration_seconds) is not int or
        not 1<=duration_seconds<=3600 or
        type(sample_hz) is not int or not 1<=sample_hz<=60 or
        duration_seconds*sample_hz>3600 or
        type(max_peak_bytes) is not int or
        not 1<=max_peak_bytes<=2*1024**3 or
        (approved_cancel is not None and not callable(approved_cancel))):
        raise ValueError("Invalid bounded original-source continuity request")
    frame_total=duration_seconds*sample_hz
    latencies=[]
    receipts_digest=sha256()
    status="COMPLETE"
    processed=0
    tracemalloc.start()
    start=time.perf_counter()
    try:
        for i in range(frame_total):
            if approved_cancel is not None and approved_cancel():
                status="CANCELLED"
                break
            tick=i/sample_hz
            t0=time.perf_counter()
            output=sample(tick)
            latencies.append(time.perf_counter()-t0)
            if (type(output) is not dict or
                output.get("source_sha256")!=source_sha256 or
                output.get("original_modified") is not False or
                type(output.get("native_preview_sha256")) is not str or
                len(output["native_preview_sha256"])!=64 or
                any(c not in "0123456789abcdef"
                    for c in output["native_preview_sha256"])):
                raise RuntimeError("Continuity sample lost original source authority")
            receipts_digest.update(
                (str(i)+":"+output["native_preview_sha256"]+";").encode("ascii"))
            processed+=1
        _,peak=tracemalloc.get_traced_memory()
    finally:
        total_wall=time.perf_counter()-start
        tracemalloc.stop()
    latency_ms=[v*1000 for v in latencies]
    p95=(sorted(latency_ms)[math.ceil(.95*len(latency_ms))-1]
         if latency_ms else None)
    return {
        "format":"nvp.wo2.source_continuity_measurement.v1",
        "status":status,
        "original_source_sha256":source_sha256,
        "requested_film_seconds":duration_seconds,
        "sample_hz":sample_hz,
        "requested_frames":frame_total,
        "processed_frames":processed,
        "actual_wall_seconds":round(total_wall,6),
        "latency_p95_ms":round(p95,3) if p95 is not None else None,
        "latency_max_ms":round(max(latency_ms),3) if latency_ms else None,
        "peak_python_allocated_bytes":peak,
        "memory_budget_bytes":max_peak_bytes,
        "within_memory_budget":peak<=max_peak_bytes,
        "sample_receipts_sha256":receipts_digest.hexdigest(),
        "original_modified":False,
        "gpu_hardware_verified":False,
        "real_source_rendering_proven":False,
        "physical_color_calibrated":False,
    }


def measure_native_frozen_take(index,project_id,take_id,take_sha256,
                               camera_path,*,duration_seconds=60,
                               sample_hz=2,approved_cancel=None):
    """Run actual source-authoritative OpenUSD + native CPU renders at Film Time.

    Unlike the generic measurement helper, every sampled frame is an actual
    SHA-verified native scene-linear raster, not synthetic preview data.
    This remains *CPU native* evidence: GPU/Hydra, calibrated display and
    actual 60-second installed-device performance require separate tests.
    """
    from backend.nvp_data_av_scene import FrozenSceneAV
    from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
    from backend.nvp_temporal_ledger import TICKS_PER_SECOND
    from backend.nvp_film_index import FilmIndex,_require_pid,_id,_sha
    if not isinstance(index,FilmIndex):
        raise TypeError("FilmIndex required for native 3D continuity acceptance")
    _require_pid(project_id)
    _id(take_id,"frozen USD original Take")
    _sha(take_sha256)
    if (type(camera_path) is not str or
        not camera_path.startswith("/World/")):
        raise PermissionError("Only an authored original USD camera may be used")
    source=FrozenSceneAV(
        index,project_id,take_id,
        expected_take_sha256=take_sha256,listener_path=camera_path)
    try:
        if source.roles.get(camera_path)!="camera":
            raise PermissionError("Native continuity requires a real source camera")
        if (type(duration_seconds) is not int or
            duration_seconds*TICKS_PER_SECOND>source.duration):
            raise RuntimeError("Frozen original Take does not cover continuity interval")
        native=NativeSceneLinearRaster(index)
        def sample(seconds):
            tick=round(seconds*TICKS_PER_SECOND)
            snapshot=source.snapshot(tick)
            _,receipt=native.render(
                project_id,take_id,take_sha256,tick=tick,
                camera_path=camera_path,source_session=source,
                source_snapshot=snapshot)
            if (receipt.get("source_modified") is not False or
                receipt.get("ffmpeg_used") is not False or
                not receipt.get("scene_linear_rgba_sha256")):
                raise RuntimeError("Native source raster lost freeze provenance")
            return {"source_sha256":take_sha256,
                    "original_modified":False,
                    "native_preview_sha256":
                        receipt["scene_linear_rgba_sha256"]}
        measurement=measure_source_continuity(
            sample=sample,source_sha256=take_sha256,
            duration_seconds=duration_seconds,sample_hz=sample_hz,
            approved_cancel=approved_cancel)
        return {**measurement,
            "real_source_rendering_proven":measurement["status"]=="COMPLETE",
            "native_cpu_renderer":"nvp.source_linear.GGX_preview.v1",
            "source_immutable_take_reopened":True,
            "physical_display_calibrated":False,
            "gpu_hardware_verified":False}
    finally:
        source.close()
