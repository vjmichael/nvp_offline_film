# SCALE-02C.2 — Atomic compact editorial source bindings

**Status:** Implemented on the NVP draft branch; real Windows/Linux exact-head acceptance pending. AI Assistance Layer remains deferred.

## Operational contract

`backend/nvp_bound_editorial.py` adds `BoundEditorialPublisher`. A native trusted caller supplies compact clip decisions `{source_id,source_revision,source_first_frame,frame_count}`. The publisher resolves **each source object and exact revision** through the authoritative `FilmIndex.read_revision`, requires the external-source asset format from `SourceFilmBridge`, and checks source/edit frame-rate compatibility and a conservative FFprobe-reported source-duration bound. It rejects nonexistent, cross-project, non-asset, mismatched-rate, out-of-range, negative and overflowed source intervals.

Clips are staged as **disk-backed compact rows**, not expanded into one row per film frame. The staging manifest hashes the exact ordered source IDs, revision numbers, FilmIndex document SHA-256 values and source/output half-open frame intervals. One compact FilmIndex `edit` revision records the aggregate SHA, total frames, clip count, frame rate and explicit `creator_approved=False`, `rendered=False`.

### Crucial crash-safety boundary

The new publisher inserts:
- `scale_editorial_revisions` compact timeline summary,
- `scale_editorial_clips` exact source interval references,
- `scale_editorial_source_bindings` exact FilmIndex source revision **document SHA**, and
- the authoritative FilmIndex `edit` record

**in a single SQLite write transaction** using the existing trusted `FilmIndex.register_revision(..., precommit_guard=...)` path. A failed guard, conflicting revision, missing source or interrupted transaction must not publish a partial edit. A content-addressed manifest blob could be left orphaned if the database transaction fails; this is not a committed film revision and requires normal verified blob garbage collection.

The source-to-edit reverse lookup is indexed, and `FilmIndex.direct_dependents` now includes these exact-revision references in `FilmIndex.impact`. Repeated clip references do not need one of the legacy 128 JSON dependency slots apiece; no whole-film frame-map document is created.

### Read and audit

- `BoundEditorialPublisher.clips(... first_frame, limit)` uses the existing indexed predecessor seek and returns a bounded page with source identity, revision and immutable document SHA.
- `verify_revision` streams the **entire** compact clip manifest through a bounded SQLite cursor and recalculates source bindings, clip order, source hashes, frame continuity, totals and aggregate manifest SHA. An altered or missing row is rejected.
- Files can be offline while a filmmaker opens or revises editorial decisions. In this state the source remains referenced but **cannot** be accepted as decoded or rendered. Before production work, the trusted native worker/host must require source bytes, exact revision authorization and independent content integrity checks.

### Genuine limitations and remaining work

The source extent check uses container metadata, not independent decoded frame-count evidence. Variable-frame-rate sources, mixed source timebases, speed changes, retiming, transitions, and audio conformance are not yet supported by this bound-edit publisher. None are silently flattened. The bounded FilmIndex commit document stores normalized edit summary, not a final picture master or human approval.

The original `EditorialCatalog.publish` remains available for old metadata fixtures, but it does **not** by itself establish authoritative FilmIndex edit/source binding. Production uses `BoundEditorialPublisher.publish`.

The indexed binding tables are trusted internal SQLite state; creators must not permit arbitrary direct SQLite mutation. An independent `verify_revision` audit is required before consuming a revision. Any future migration must preserve these source references and recovery semantics.

### Acceptance coverage

`tests/test_nvp_bound_editorial.py` exercises real native generated video metadata and FilmIndex external source publication; exact 24-fps source clips; reordered/repeated ranges; 450 clips referencing a source; indexed seeks; FilmIndex reverse dependencies; offline edit reopening; mismatch and cross-project refusal; revision conflict rollback; and binding-tamper refusal. The four native cells in `.github/workflows/nvp-scale01-02.yml` are requested; green exact-head CI evidence is mandatory before acceptance.

**Next task:** Bind approved, contained B14 source-window processing to these exact bound edits; reconcile external-media availability and source SHA immediately before worker execution. Integrate real source frame/keyframe indexes and durable work-unit receipts for studio-scale processing. Source-file paths and removable-volume locations must remain outside immutable source identity.
