# INDEX-TIME-01 — Imported Video PTS on NVP Film Time

**Creator decision:** Two indices serve distinct purposes. NVP-native film performances are addressed by the authored, sparse Temporal Ledger and scene state; imported live-action/archival/already-rendered video is addressed by its exact source-frame PTS/index. An imported frame remains a **source observation**, not a new authoritative performance frame.

**Implementation:** `backend/nvp_source_pts_film_time.py` adds `IndexedSourceFilmTime.map_window(...)` and `pts_to_film_tick(...)`.

## Explicit mapping

For a selected imported clip:

- Exact source inpoint ordinal `source_in_frame_zero` is resolved from the existing project-scoped `NVPFrameIndex`.
- A creator-selected film inpoint tick `film_in_tick` anchors the source clip.
- For each requested original frame, use its **actual source PTS**, not `frame_number / fps`, and calculate the exact rational film timestamp:

`film_tick_exact = film_in_tick + (source_pts - source_in_pts) * time_base_num * 7_056_000_000 / time_base_den`.

All multiplication and division are integer operations; there is no floating-point drift or accumulation of per-frame rounding errors. A 24fps output does **not** change the imported source PTS or the time-addressed authored film.

**Loss-aware clocks:** The default `rounding="exact"` refuses nonrepresentable source timebases rather than silently changing time. `floor`, `ceil`, or `nearest` must be **explicitly requested** when quantization is needed. Every returned frame retains the original source PTS, original source rational elapsed seconds, whether it was exactly representable, and the *signed rational quantization error* in NVP ticks. It refuses collapsed or unordered rounded frame timestamps. No source duration is guessed for the last frame.

**Provenance:** Both the source inpoint and frame window are opened with `NVPFrameIndex.window` and their cache identity/source stamps/timebase must agree. The returned mapping includes project, source ID and ingest SHA, source-ordinal identities and source-index metadata. It explicitly sets `source_sha_verified_this_operation=False`; no whole-media hash runs during interactive scrubbing. The final creator-approved conform still separately verifies external source custody. The mapping does not publish new FilmIndex/Temporal Ledger revisions or grant author/editor approval.

**Scope:** 1–96 source frame observations per request. One source frame may be placed at different film times by different clips without altering the original PTS or source identity. The native 3D scene and temporal events remain independent.

## Acceptance tests

- `tests/test_nvp_source_pts_film_time.py` covers VFR/nonzero PTS origins, source trims, 90kHz and 30kHz source timebases, nonrepresentable 1/11s PTS with explicit rounding and exact quantization error, overflow rejection, near-100-frame no-drift time mapping, source placement offsets, and malformed/corrupted source metadata.
- `tests/test_nvp_owned_frame_index.py` additionally maps real FFprobe-indexed VFR MPEG4 B-frame footage with a +3 second source time origin into a film anchored at 5 seconds. It checks source ordinals, precise inpoint PTS and strictly increasing film ticks without a 2D frame-rate assumption.
- `.github/workflows/nvp-index-time01.yml` requests real FFmpeg/FFprobe native integration on Windows 2025 and Ubuntu 24.04, Python 3.11/3.13, plus Temporal Ledger regression.

**Open until native CI:** Native Windows/Linux exact-head results, application-facing saved editorial binding of clip inpoint and FilmIndex source revision, playback synchronization/audio and time stretch, import codec matrix, and actor/3D compositing integration. This milestone is a **correct source-time coordinate conversion**, not a completed full mixed-media conform/editor.

## Why this matters

An imported film may begin at 01:00:00:00, use variable PTS spacing, or be trimmed from the middle. We must not pretend its source frame number is an authoritative NVP film event coordinate. Instead, its original PTS and a filmmaker-selected clip inpoint establish one explicit mapping to NVP Film Time. At the presentation boundary, that scene/time state may then be sampled at the chosen output FPS.

This preserves the architecture: **native world performance is film data; imported footage is media measured against it.**
