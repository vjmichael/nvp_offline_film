# PERF-03A — bounded long-film scheduling and verification foundation

## Scope and compatibility

P2 original-film source planner now uses a compact immutable-segment prefix index (maximum existing 500 editorial segments) and binary search to seek the first chunk of a page or bounded reel grant. Preserve original v1 canonical chunk rows, six-digit chunk identity, digest, approved plan format, exact 24fps and 48kHz source clocks, shot splits, immutable FilmIndex revision and independent creator confirmation. No stored schedule-wide array of frames or chunks; no cross-session cached authority. Maximum 64 rows per page, at most eight chunks under the existing one-use native reel grant. Source-only address safety is derived from the existing million-entry six-digit chunk namespace and exact signed/IEEE-754 film tick bounds, rather than an arbitrary two-hour/12,000-chunk restriction. This is not a promise of arbitrary-duration mastering.

Standalone page/reel requests still independently reopen source and hash the exact canonical manifest once per request. Full audit opens the immutable schedule and hashes its manifest once before scanning, streams per-page independent native receipts and canonical completion digest, and reopens source and exact plan SHA before returning success. It fails closed on missing output, clock gaps, corrupt source, incorrect chunk ID or changed final plan; cancellation checked during manifest scan and existing chunk audit. Finite grants rederive their page from the same verified snapshot and repeat checks after original creator approval. No new render launch, authorization, automatic replay or changed custody.

Chunk verification now hashes PNG/PCM in bounded 1 MiB blocks, preserving original effective raster size/dimension limits, actual SHA, clocks and native worker receipt checks. WAV hash bound is expected finite PCM plus 64 KiB container allowance (native writer uses a small header). Manifest reads capped at 2 MiB plus one refusal byte. Completion proof derives from the same parsed manifest bytes and checks unchanged manifest at end, then binds chunk/source/continuity/edit/camera/listener to the requested schedule. Directory enumeration rejects excess entries immediately. These bounds address reading oversized tampered files and avoid a whole PNG allocation; the existing renderer still returns a finite PNG byte array, and this is not a general TOCTOU or untrusted filesystem hardening proof.

## Locally measured synthetic schedule-only benchmark

Linux CPython 3.13.5; single source segment. Median of five last-page seeks of 64 rows. Baseline original row generator skipping prefix vs new indexed page, excludes immutable source reopening and canonical digest. Full digest remains deliberately O(chunks). Separate page walk tracemalloc is Python allocation only, not process RAM, actual USD composition, image decode, or native rendering throughput.

| Duration | Frames | Chunks | Old skip ms | Indexed seek ms | Full digest ms | Page allocation peak bytes |
|---|---:|---:|---:|---:|---:|---:|
| 30 min | 43,200 | 1,800 | 0.9954 | 0.0368 | 8.1981 | 27,496 |
| 1 h | 86,400 | 3,600 | 1.8490 | 0.0338 | 16.7833 | 26,096 |
| 3 h | 259,200 | 10,800 | 7.3303 | 0.0337 | 50.9781 | 25,984 |
| 6 h | 518,400 | 21,600 | 10.8525 | 0.0335 | 97.4497 | 26,048 |
| 8 h | 691,200 | 28,800 | 13.6266 | 0.0346 | 136.7861 | 26,048 |

All rows walked; old/new canonical digest matched on eight-hour synthetic cut. Extended existing R2 benchmark arithmetic also completed 12-hour (1,036,800 frames, 43,200 chunks), all 64-entry page bounded, no claim of real film rendering. Existing R2 evidence recorded previous limits; do not rewrite historical results.

## Remaining scaling gates — explicit, not waived

- Separate P1FReelPlan and P1DEConform (3h cap, 48-segment conform path, list-backed reel plan) are not changed. Port to compact indexed immutable representation with backward-compatible source receipts and migrate all consuming P1F durable reel queues before advancing that path.
- SlateSequenceAssembly 500 segments, DigitalSlateBranches 256 nodes/64 groups, continuity 500 cues, FilmIndex 1 MiB documents/128 dependency edges; need hierarchical paged immutable editorial manifests with bounded source validation for real footage with many cuts rather than merely a single long take.
- P1F verifier still independently reopens source preflight for each verified derivative; profile actual source I/O, repeated continuity/Take/USD reads and cancellation latency before a safely scoped optimization. Do not omit native custody reopens.
- Production journal 12,000 segments, independent audio-worker 2h cap, WO4 mastering resource budget 12h/288 reels (untested), classic RIFF PCM <4 GiB and per-reel mastering bounds; eight-hour stereo PCM16 alone is 5,529,600,000 bytes. Use bounded separate reel files or reviewed RF64 where truly supported; never allocate whole sound/picture stream, truncate at 32 bits, or silently convert source. Audit restart, disk reservations, publishing manifests, native codec limits and final packaging separately.
- Native 8h plan fixture authored using existing real OpenUSD/FilmIndex/director fixture, no renderer; local PXr unavailable, CI needs to prove actual publication, reopened final page and absent-media refusal. Full-duration render/delivery/restart, physical GPU, long-film throughput and physical filmmaker acceptance remain unproven.
