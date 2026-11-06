# NVP INDEX-CLOSEOUT — Temporal Index + Imported-Footage Index

**Creator decision, November 2026:** NVP's authored film is a frozen time-addressed performance with OpenUSD scene state and semantic Temporal Ledger events; render/presentation frame grids do not replace source performance data. Imported live-action/archival/previously-rendered recordings still require a media-frame/PTS/keyframe adapter. Both indices are retained with **separate authority**.

**State:** Repairs, tests and benchmark runners committed on the indexing-closeout branch; actual exact-head Windows/Linux GitHub CI and native FFMS2 A/B artifact remain OPEN. Do not merge or call the complete gate green solely because source files exist.

## Workstream A — DATA-TIME-01

- `backend/nvp_temporal_ledger.py` indexes immutable, project-scoped semantic events and exact source revision digests in SQLite. Its clock uses 7,056,000,000 integer ticks/s rather than an arbitrary video FPS.
- `backend/nvp_temporal_projection.py` derives bounded presentation sample positions when pictures are requested, without making those frames an authoritative world model.
- Tests cover a 3-hour/10,000-event sparse timeline, active-event lookup and pagination, 24fps/60fps re-projection from the same frozen source, transaction rollback and tamper detection. Unchanged FilmIndex and OpenUSD take contracts remain authoritative for source revisions.
- **Not a dependency on FFMS2 or FFmpeg.** The existing Git PR stack includes PR #47 for historical branch ordering; the runtime temporal-index implementation does not import the custom video indexer.

## Workstream B — SCALE-03C

- `NVPFrameIndex` owns a versioned SQLite index of imported-video source ordinals, exact PTS, timebase, keyframe flags and packet offsets. Full original SHA is established at ingest; interactive warm lookup, preview preflight and preview decode use a cheap **unverified** file stamp, not a new whole-original SHA.
- Native FFprobe provides first-time decoded frame metadata. FFmpeg performs bounded image review seeks and validates every observed decoded PTS against the indexed source. Offline/stale/changed external media remain distinguishable from previously frozen FilmIndex source identity. Accepted final masters still require independent custody verification.
- Recovery: a per-asset `.building` lock now records source stamp/identity and native builder PID. Interrupted builds do not silently restart; `reconcile_interrupted(...,confirm_builder_terminated=...)` requires the trusted host to assert the exact worker has stopped. It cleans only prefix-bound partial staging files, or retains an already published index after verification. General-purpose tool/model callers do not receive a self-authorizing way to bypass worker supervision.
- Added SQLite row-order/ordinal/keyframe integrity checks in each bounded returned frame window, without scanning/hashing the entire original during scrubbing.

## Benchmarks and correctness

`tools/benchmarks/run_index_compare.py` compares the actual NVP SQLite/FFmpeg path against FFMS2 C ABI at identical source ordinals. It measures:

1. Fresh index build (reverse build order in second pass);
2. Warm index/decoder open;
3. **Indexed metadata lookup alone** (NVP source-stamped SQLite read versus FFMS2 warm in-memory index);
4. Deterministically shuffled bounded GOP seek and actual review-PNG production, with per-position and median timings;
5. Rational source PTS equivalence and decoded RGB24 image equivalence; source SHA at fixture creation only.

FFMS2 C API prototypes and success conventions were checked against the upstream `include/ffms.h` and `doc/ffms2-api.md`: in particular, `FFMS_DoIndexing2` already had the correct indexer/int/error arguments; no ABI change was necessary. Reference library is benchmark-only and **not part of NVP's Windows installer**.

`tools/benchmarks/run_temporal_scale.py` benchmarks the **actual NVP FilmIndex + TemporalLedger**, publishing 10,000 source-bound authored actions across a three-hour film. It measures transactional publication, point and interval lookup medians/p95, and deliberate whole-ledger provenance audit separately. It generates no film frames and does not call FFmpeg. CI now uploads this measured JSON alongside the separate imported-video indexing fixture.

`tools/benchmarks/run_feature_duration_index.py` separately generates a three-hour 1fps 64x64 MPEG-4 B-frame **sparse timeline fixture**, indexes all 10,800 frames, measures warm reuse/SQLite window latency and seeks/decompresses its last frame. It may accept a creator-provided actual film source. **This is not a substitute for 3-hour 4K/24fps/high-bitrate media**, GPU workers, multi-terabyte media libraries, or real-world storage latency. Use full-length production sources under controlled media/storage systems for those acceptance gates.

### Local supporting native-media observations

On a Linux container with FFmpeg/FFprobe 7.1.5:
- A real 150-frame, 24000/1001 MPEG4 long-GOP B-frame clip was produced. Explicit FFmpeg accurate seeks matched FFprobe PTS at frames 0, 1, 37, 75, 129, 148 and 149.
- A separate real VFR B-frame clip with +3-second start time, 120 frames and deliberately irregular presentation timestamps was produced. FFprobe PTS matched FFmpeg's first decoded PTS at frames 0, 1, 9, 10, 11, 29, 30, 59, 88, 117 and 119. A regression now exercises the **actual NVP NVPFrameIndex+extract** path on such footage in native CI.
- A real 3-hour/1fps 64x64 long-GOP clip (9,258,696 source bytes) was generated in 1.176 s. A simple FFprobe-to-SQLite scan of 10,800 PTS records took 0.297 s; same-open-connection SQLite ordinal lookup median was 0.0015 ms, p95 0.0036 ms; a standalone FFmpeg last-frame seek/decode took 0.065 s and matched the final source PTS. **These are standalone local component measurements**, not benchmark results from the full NVPFrameIndex, not results against FFMS2, and not predictions for high-bitrate 3-hour features.
- A separate **three-hour / 24fps** tiny 64×64 MPEG4 B-frame recording contained **259,200 frames** in approximately 77.57 MiB. Local FFprobe-to-SQLite indexing took 4.53 seconds, yielding a 4.67 MiB index and 5,401 keyframes. Same-open-connection raw SQLite point-query median was 0.0039 ms. An exact seek/decode of the final source frame took 0.085 seconds and its observed PTS matched the index. Generation took 26.14 seconds. **These are standalone local FFmpeg/SQLite component measurements, not the complete production NVPFrameIndex overhead, not 4K/24fps high-bitrate decoding, and not an FFMS2 comparison.** The CI fixture now covers this 259,200-entry case using the real NVP index and review decoder.
- No actual FFMS2 shared library is installed locally. Its native A/B run is configured for GitHub CI; **no FFMS2-vs-NVP speed or RGB-parity result is confirmed yet**.

## Actual acceptance gate

`.github/workflows/nvp-index-closeout.yml` adds Windows 2025 / Ubuntu 24.04 on Python 3.11/3.13 for native indexed B-frames, VFR with nonzero time origin, partial/crash recovery, no repeated full original hash, and complete preview receipt/host integration. An Ubuntu job produces the real three-hour sparse source index benchmark JSON artifact.

The separate existing `.github/workflows/nvp-data-time01-bench.yml` runs FFMS2 A/B on Windows/Linux and produces raw JSON artifacts; this closeout branch modifies the benchmark tools, so the PR triggers that workflow as well.

**Remain open until:** exact-head native CI green, FFMS2 DLL/SO actually loaded, measured raw JSON inspected, RGB24 and PTS agreement on relevant codecs, representative 24fps/4K/long-GOP/VFR imported footage, scoped host recovery wired into installed app, and pre-release FFmpeg/FFMS2 license/dependency audit. A 'queued' GitHub job proves none of those results.
