# INDEX-TIME-04 — Film Time playback selection from imported source PTS

**Creator-approved product model:** NVP-native films are persistent, data-first 3D scenes and time-addressed performances; the Temporal Ledger remains the authority for those events. Imported camera/archival/previously-rendered footage has its own source PTS and frame index. Versioned editorial placements decide where imported frames appear on the NVP Film Time axis, without turning source frame ordinals into authored film events.

**Implementation status:** Backend selection resolver, native FFmpeg/VFR tests, the existing authorization-gated review host handoff, Windows/Linux CI, and central design update are coded. **Exact-head native CI and installed Windows desktop acceptance are OPEN.** No OpenUSD expansion.

## Reverse seek contract

A film-time request has exactly one edit identity + version + authored integer tick:

`resolve(project_id, edit_id, edit_revision, tick=...)`

The resolver uses the existing FilmTimeEditorialPublisher's `at()` index to find the versioned clip whose half-open interval includes the tick. If no imported clip exists at that time (including gaps, before start and after outpoint), it returns `EMPTY_IMPORTED_VIDEO_GAP` and **never starts a decoder**. Native performances can still exist at those same times.

For an active clip, the resolver verifies the pinned exact original FilmIndex source revision and source SHA, current registered source volume, and NVP frame-index source stamp. It uses a **bounded ordinal binary search** over the existing SQLite frame index. Midpoints are compared using the same exact integer source-PTS-to-Film-Time mapping/rounding policy as the published editorial revision; no frame-number/FPS approximation, new timebase, separate index rebuild or cumulative rounding drift. Complexity is `O(log number_of_frames_in_clip)` indexed SQLite primary-key reads, not a scan from the start of a feature film.

A source frame applies on a half-open **hold interval** `[frame_mapped_tick, next_source_frame_mapped_tick)`. At the exact next frame time, the next frame wins. A clip's last included frame is held until the saved original **out-exclusive next-frame PTS**, already required by INDEX-TIME-02. A tick at that exclusive boundary yields a gap or the next placed clip. No frame display interval is inferred by averaging frame rates or guessing the duration of the physical final original frame.

After binary selection, NVP reopens the selected frame using the source-authoritative INDEX-TIME-02 `map_clip_window` check. It rejects stale index source timebases, changed sources, incorrect in/out boundaries, mismatched selected source PTS and collapsed/ambiguous mapped frame intervals. Returned data includes exact source ordinal/PTS, current selected film tick, next-frame end tick, clip identity/revision/document SHA, source timebase and original ingest SHA, explicit rounding/precision info, and `frame_index_pts_reads` diagnostic. **This is source-stamp unverified preview metadata; no original byte hash runs during interactive seek.**

## Existing authorized preview worker handoff

`stage_review_at(existing_native_host, ..., tick=..., destination=..., creator_event=...)` selects the frame using the read-only resolver, then calls `NativeFilmTimeWindowHost.stage_and_approve` with the exact clip/ordinal, FilmIndex edit identity and requested review mode. The existing host performs independent creator-policy verification and source-plan revalidation, enqueues through ApprovedTaskBindings + TaskLedger, admits only with measured resource headroom, then uses the existing OS-contained source-window worker and native FFmpeg/FFprobe PTS-verified extraction.

A gap returns a null task ID and no job. A refused creator scope does not create a queued review. A successful queue event is **not** a worker start or a completed review. Only the host's separate `run_next()` actually launches its contained worker; its receipt can be independently reopened and verified. No new queue, subprocess runner or bypass authorization exists.

## Native acceptance tests

`tests/test_nvp_film_time_playback_native.py` generates real 120-frame VFR, nonzero-start, long-GOP MPEG4 footage and publishes two immutable Film Time placements. It verifies first-frame exact selection, mid-hold selection, next-frame boundary, last included frame/out-exclusive transition, intentional gaps, multiple placements of the same original, unchanged old edit revisions after a move, reopened project equivalence, bad-original refusal while retaining saved metadata, cross-project refusal and one-frame native OS-contained preview after explicit creator approval.

`.github/workflows/nvp-index-time04-native.yml` runs Windows 2025 and Ubuntu 24.04 on Python 3.11 and 3.13 using actual installed FFmpeg/FFprobe; Windows additionally provisions native Job Object dependencies. Regression suites include INDEX-TIME-03 worker, INDEX-TIME-02 saved editor, INDEX-TIME-01 PTS bridge and Temporal Ledger.

## Explicit non-goals

This is the **selection backend** for a future editor timeline viewer, not a complete real-time video player or a simultaneous native-3D/recorded-video compositor. It does not render, blend, color-conform, time-stretch, synchronize audio, create proxies, implement reverse playback at high FPS, guarantee frame-cached real-time throughput, or approve/publish a final picture/feature film. Those are separate editorial/player/finishing gates and do not belong to the indexing data model.

**Correctness priority:** A tick in a film's native scene can have no imported image, one imported image held until its next original PTS, and independent NVP-authored events. Keeping those concepts separate avoids rebuilding the media indexing system around output frame rates.
