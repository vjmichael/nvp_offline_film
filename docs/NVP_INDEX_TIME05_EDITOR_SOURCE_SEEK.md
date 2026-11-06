# INDEX-TIME-05 — Main editor Indexed Footage and exact Film Time seek

**November 6, 2026 — implementation submitted; native and installed-app acceptance pending.**

## Purpose

Return from SLATE feature development to the creator's earlier **original
source indexing** workstream. DATA-01/SCALE-03C and INDEX-TIME-01–04 already
hold authoritative original-video PTS, source ingest SHA, PTS/timebase,
ordered frame/keyframe index, and durable revisioned editorial placements.
This wave gives NVP's main human-first editor a way to inspect those sources
rather than relying on Python tests, scripts, or raw SQLite queries.

The Indexed Footage tab exposes only real `nvp.edit.imported_film_time.v1`
FilmIndex edits, their current exact head revisions and bounded source
clip pages. The user can select a Film Time tick or inspect the start of a
source clip; the existing `FilmTimePlaybackResolver` maps that tick by
binary search to the held **original VFR PTS**, source-frame ordinal and
out-exclusive film interval. An empty editorial range stays an explicit gap,
not a black filler source frame or inferred constant-fps substitute.

## Custody and 64-bit time

- Original video remains on its original registered volume. The browser
  receives **no path, volume-root, FFmpeg executable, device/inode stamp or
  disk cache filename**.
- Every read is project scoped and checked against its source FilmIndex
  revision and document SHA. A complete indexed clip manifest is verified
  from SQLite rows against the immutable edit document. Row tampering and
  stale-revision commands fail closed.
- **Ticks, source PTS and frame ordinals are transported as decimal strings**.
  React validates user ticks with `BigInt` and URL-encodes the exact decimal,
  rather than silently rounding at JavaScript's 2^53 integer limit.
- The full film-time seek uses the **existing** NVPFrameIndex and registered
  source-availability checks, bounded ordinal binary search, and original
  timebase. It is explicitly a fast *stamp-checked but source-SHA-unverified*
  metadata selection.
- Browsing pages does not require FFmpeg and cannot start native execution.
  Explicit seek may require a trusted installed `ffprobe` to build/reuse
  an existing frame index. It does **not** decode video frames, commit Takes,
  create previews, invoke models, or approve film masters.
- No new worker pool or native media-write API. INDEX-TIME-03 remains the
  creator-approved, resource-governed OS-contained preview/conform service
  for later native IPC wiring.

## Implementation

- `backend/nvp_index_time05_desktop_read.py`: guarded source list, full
  indexed manifest audit, paged clips, source-SHA-locked exact Film Time seek.
- `backend/nvp_api.py`: three GET-only routes; no remote/native render launch.
- `frontend/src/FilmTimeIndexPanel.jsx`: real edit selection, source PTS
  and 64-bit tick viewer, explicit source gaps, incremental source clip pages.
- `frontend/src/App.jsx`: new **Indexed footage** workspace tab.
- `tests/test_nvp_film_time_playback_native.py`: actual VFR and B-frame
  original movie, first/mid/end selection, intentional gap, pagination,
  same-project custody, cross-project refusal, DB row tampering and 64-bit
  display source coordinates.
- `frontend/src/FilmTimeIndexPanel.test.jsx`: no eager decoder,
  decimal BigInt correctness, source-mismatch denial and UI gap honesty.
- `.github/workflows/nvp-index-time05-editor.yml`: Windows/Linux 3.11/3.13
  real FFmpeg/FFprobe tests + React build/Vitest on exact head.

## Acceptance and non-goals

Draft until native exact-head tests pass on Windows and Linux, source
indexing/FFMS2 comparative evidence is available, and an installed editor
can ingest and inspect an actual imported video without developer CLI.
New source registration, a trusted desktop media import picker, native
approved image presentation, installer FFmpeg/FFprobe provisioning and
feature-film conform remain **separate gates**, not silently marked complete.

This wave does not replace SLATE's OpenUSD authored sparse event ledger.
Original imported footage and authored NVP film data are distinct sources
and converge through versioned Film Time placements.
