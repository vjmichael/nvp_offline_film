# BENCH-01 — NVP's owned video index versus FFMS2 (native A/B)

**Purpose:** Test the creator's challenge: does our own SQLite source-frame index plus bounded FFmpeg seek compete with FFMS2 for the specialized task of retrieving frames from already recorded footage?

**Not the same task as DATA-TIME-01:** The authoritative NVP event ledger indexes actor actions, camera curves and dialogue in film time. FFMS2 is a video-frame decoder/indexer. It has no directly comparable concept of authored film events. Compare these products **only at the imported/video-media adapter boundary**.

## Actual test code and reproducibility

- `tools/benchmarks/run_index_compare.py`: generates one real deterministic 24000/1001 MPEG-4 long-GOP recording with B-frames, or accepts a filmmaker-supplied test file. Calculate the original source SHA once outside the timed region. Create a fresh NVP SQLite frame index and fresh FFMS2 native index; run each ordering (NVP-first/FFMS2-first) in separate temporary cache directories.
- `tools/benchmarks/ffms2_reference.py`: isolated ctypes wrapper over the **real FFMS2 native ABI**, used only in benchmark/test CI. No FFMS2 production imports, index files or runtime library are required by NVP.
- Measure first fresh index build, index bytes, warm NVP SQLite reopening versus FFMS2 index-and-decoder reopening, and identical frame-number seeks at beginning, 25%, halfway, 75% and end. Report each per-frame elapsed duration and medians.
- NVP path uses the actual `NVPFrameIndex.ensure` and `nvp_indexed_preview.extract` that produce review PNGs from FFmpeg. FFMS2 path uses a *single warm decoder* and decodes indexed frames to review PNGs. Decode both PNGs back to RGB24 **outside the timed section** and compare SHA-256 pixels and exact rational source presentation timestamps (PTS). Different PNG container compression is not a pixel mismatch.
- Emit JSON with platform, Python and FFMS2 version, exact FFMS2 DLL SHA, source bytes, source SHA from fixture initialization, build orders, timings, quality comparisons and methodology limitations. CI uploads the original JSON artifact. Do not fabricate timings or accept a skipped/reproduced-only test as proof.

## Critical fairness limitations

1. A fresh index means *no preexisting index file*, not a cold OS page cache. The second backend may benefit from memory caches despite reversed order. A proper cold-cache run requires a suitable privileged host and controlled disk I/O evidence.
2. NVP currently spawns FFmpeg per request and FFMS2 uses a warm in-process decoder. The measurement captures the true existing *user-facing preview path*, including process start, not pure index lookup. A future persistent supervised FFmpeg decoder may change these results.
3. PNG writers and image conversion may differ even though both use FFmpeg codec libraries. RGB24 parity is checked independently; any mismatch or source PTS divergence makes the particular comparison **not accuracy-accepted**.
4. A 45-second 192x108 CI recording is a smoke/performance-regression fixture; it cannot establish three-hour/4K/multi-terabyte throughput. Additional 10-, 60-, 180-minute source tests should use real H.264, HEVC, ProRes, B-frame, open GOP and VFR recordings under equal storage/network conditions. Benchmarks must include index time, warm seeks, decoder memory/process overhead and I/O.
5. If FFMS2 is faster, **report it**. We can retain NVP's owned event-first system and improve the video-media backend. Owning the index format is a product/compatibility choice, not proof of speed superiority.
6. Native FFMS2 is installed only on disposable CI machines. Its build-dependent license is not approved for NVP's Windows NSIS installer. FFmpeg distribution licensing remains a separate release gate.

## CI and acceptance

`.github/workflows/nvp-data-time01-bench.yml` runs the event-ledger tests on Windows 2025 and Ubuntu 24.04 with Python 3.11/3.13, and the native FFMS2 A/B benchmark once per OS using Python 3.13.

**OPEN:** The A/B result has not been confirmed until the actual exact-head GitHub workflow completes, its raw benchmark JSON is inspected, and equality/timings are reported. A queued run does not establish success. A result on the short fixture is not representative of studio-scale films.
