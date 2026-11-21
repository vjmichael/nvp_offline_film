"""Bounded local observation overhead and synthetic duration arithmetic, no rendering."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import statistics
import time
import tracemalloc

from backend.nvp_performance_probe import measured, observe
from backend.nvp_p1f_sustained_delivery import FPS, MAX_CHUNK_FRAMES
from backend.nvp_p2_longform_source_plan import MAX_TOTAL_FRAMES, MAX_CHUNKS, MAX_PAGE

MINUTES = (30, 60, 180, 360, 480, 720)
PAYLOAD = bytes(range(256)) * 256


def duration_cases():
    for minutes in MINUTES:
        seconds = minutes * 60
        frames = seconds * FPS
        chunks = (frames + MAX_CHUNK_FRAMES - 1) // MAX_CHUNK_FRAMES
        yield {"minutes": minutes, "fps": FPS, "frames": frames,
               "minimum_chunks": chunks, "frames_per_chunk": MAX_CHUNK_FRAMES,
               "minimum_pages": (chunks+MAX_PAGE-1)//MAX_PAGE, "page_limit": MAX_PAGE,
               "pcm_stereo_s16_48khz_bytes": seconds*48000*4,
               "blocked_by_frame_limit": frames > MAX_TOTAL_FRAMES,
               "blocked_by_chunk_limit": chunks > MAX_CHUNKS,
               "production_accepted": False}


def pages(frames, chunk_frames=MAX_CHUNK_FRAMES, page_limit=MAX_PAGE):
    chunks = (frames+chunk_frames-1)//chunk_frames
    for start in range(0, chunks, page_limit):
        yield tuple((i*chunk_frames, min(chunk_frames, frames-i*chunk_frames))
                    for i in range(start, min(chunks, start+page_limit)))


def walk_duration_cases():
    results = []
    for case in duration_cases():
        tracemalloc.start()
        started = time.perf_counter_ns()
        covered = count = max_page = 0
        try:
            for page in pages(case["frames"]):
                max_page = max(max_page, len(page))
                for start, size in page:
                    if start != covered or size <= 0:
                        raise AssertionError("Synthetic schedule discontinuity")
                    covered += size
                    count += 1
            elapsed = time.perf_counter_ns()-started
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        if covered != case["frames"] or count != case["minimum_chunks"]:
            raise AssertionError("Synthetic schedule coverage mismatch")
        results.append({**case, "walk_wall_ns": elapsed, "python_traced_peak_bytes": peak,
                        "max_page_chunks": max_page, "covered_frames": covered})
    return results


def overhead(iterations=200, trials=5):
    """Rotating trial order, direct vs disabled vs host vs host+GPU, same work."""
    if type(iterations) is not int or not 1 <= iterations <= 2000:
        raise ValueError("Bounded iteration count required")
    if type(trials) is not int or not 3 <= trials <= 9:
        raise ValueError("Bounded trial count required")
    results = []
    for name, raw in (("noop", lambda: 1), ("sha256_64k", lambda: hashlib.sha256(PAYLOAD).digest())):
        wrapped = measured("reel.frame")(raw)
        modes = ("direct", "disabled", "host", "host_gpu")
        samples = {key: [] for key in modes}
        sensor = []
        expected = raw()
        for _ in range(20):
            raw(); wrapped()
        for trial in range(trials):
            for mode in modes[trial%len(modes):]+modes[:trial%len(modes)]:
                ctx = observe(gpu=mode == "host_gpu") if mode in ("host", "host_gpu") else nullcontext()
                fn = raw if mode == "direct" else wrapped
                start = time.perf_counter_ns()
                with ctx as session:
                    for _ in range(iterations):
                        if fn() != expected:
                            raise AssertionError("Instrumentation changed computation")
                elapsed = time.perf_counter_ns()-start
                samples[mode].append(elapsed/iterations)
                if mode == "host_gpu":
                    sensor.append(session.report()["gpu"])
        medians = {k: statistics.median(v) for k, v in samples.items()}
        results.append({"workload": name, "iterations": iterations, "trials": trials,
                        "median_ns_per_call": medians,
                        "delta_vs_direct_ns": {k: v-medians["direct"] for k,v in medians.items()},
                        "trial_ns_per_call": samples,
                        "gpu_trials_observed": sum(x["status"] == "observed" for x in sensor),
                        "gpu_adapter_attempts": sum(x["adapter_attempts"] for x in sensor),
                        "gpu_sensor_wall_ns": sum(x["collection_wall_ns"] for x in sensor)})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args(argv)
    print(json.dumps({"format": "nvp.perf.benchmark.v1", "synthetic_only": True,
                      "overhead": overhead(args.iterations, args.trials),
                      "duration_walk": walk_duration_cases()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
