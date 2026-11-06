# INDEX-TIME-02 — Durable imported-video film-time editorial placements

**Creator-approved architecture:** The Temporal Ledger indexes NVP-native performances, and OpenUSD evaluates the persistent 3D world. Imported footage has its own PTS/frame index and is placed on the authored Film Time axis without turning media frames into authoritative native film events.

**Milestone state:** Backend, native tests and CI are committed. Exact-head Windows/Linux native acceptance is OPEN.

## Saved source decision

A trusted native host supplies ordered clip entries containing:
- the source ID and exact immutable FilmIndex source revision;
- the source first-frame ordinal and an **out-exclusive** source-frame ordinal;
- the filmmaker-selected Film Time inpoint tick;
- an explicit exact/floor/ceil/nearest quantization policy.

The original path is resolved only through the registered native source inventory; it is not supplied by arbitrary AI/model instructions or stored in the edit manifest.

NVP reads **actual indexed source PTS** for inpoint and out-exclusive endpoint. The clip end is mapped from that PTS difference using exact integer rational arithmetic, not frame count divided by assumed FPS. Source FilmIndex document SHA, original content SHA, source ordinals, PTS, timebase, film start/end ticks and rounding policy are persisted in normalized SQLite rows. Each row has a digest and the entire ordered clip manifest has a SHA pinned to a FilmIndex **edit** revision.

The current single-video-lane contract permits gaps but refuses overlapping imported video clips and playback-speed changes. A recording can still coexist temporally with native 3D performances. The source out-exclusive frame must exist; **this first format cannot include a source's final physical frame** without separately measured final-frame duration evidence. We refuse to guess.

All row inserts happen inside the same FilmIndex revision commit transaction. A crash before commit rolls back both the normalized clip rows and the edit revision. New placements create new edit revisions; previous versions are immutable. Exact source-revision impact queries find all dependent versioned edits.

## Backend APIs

- `publish(project_id,edit_id,clips,expected_revision=0)` — publish an entire draft film-time edit with exact project/source identities.
- `clips(...,after_ordinal,limit)` — page saved placement metadata even when removable media is offline.
- `at(...,tick)` — identify one active imported video clip (or an empty film-time interval).
- `verify_revision(...)` — stream the entire sealed clip manifest, check per-row hashes, source revision identity and FilmIndex summary SHA; does **not** verify current source bytes.
- `map_clip_window(...,clip_ordinal,first_zero,count)` — reopen 1–96 actual source-frame timestamps and verify stored source inpoint/outpoint against the current source stamp and indexed metadata. Offline/changed originals refuse source frame reading.

Older fixed-FPS bound editor revisions remain supported unchanged in their separate data format. INDEX-TIME-02 uses `nvp.edit.imported_film_time.v1` and new `nvp_time_editorial_clips` tables; it does not silently reinterpret existing authored edits.

## Native acceptance

`tests/test_nvp_film_time_editorial_native.py` uses native FFmpeg and FFprobe to create a variable-rate, B-frame MPEG4 camera original with a nonzero presentation timestamp. It tests multi-placement source reuse, exact time, restart persistence, source revision impact, offline-safe browsing, tamper detection, crash-injected transaction rollback, illegal overlap, unknown source ends, cross-project refusal, preview boundaries and pagination.

`.github/workflows/nvp-index-time02-native.yml` runs Windows 2025 and Ubuntu 24.04, Python 3.11 and 3.13, plus PTS bridge and Temporal Ledger regressions. **Do not mark verified until the exact latest-commit jobs pass.**

## Limits and next required work

This milestone is a **durable metadata decision**, not creator approval, a rendered shot or a final master. The publishing document explicitly sets creator approval and rendered status to false. Preview uses indexed original-file stamps and labels the original as **UNVERIFIED**; final conform still needs a fresh full-media hash and host-approved authorization.

Remains open: native exact-head acceptance; authoritative last-frame duration evidence; media overlays/retiming and synchronized sound; editor UI drag/move/trim; approval-scoped native worker delivery and crash recovery; real FFMS2-vs-NVP native A/B results and production-codec benchmarks; installed Windows desktop acceptance. No new OpenUSD feature work is included in this PR.
