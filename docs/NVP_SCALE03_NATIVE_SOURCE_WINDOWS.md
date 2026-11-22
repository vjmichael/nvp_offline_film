# SCALE-03A/B — Exact source-window native review extraction

**Implementation:** `backend/nvp_source_window_preflight.py`, `backend/nvp_source_window_decode.py`, `backend/nvp_source_window_native_host.py`, and `tools/nvp_source_window_worker.py`.  
**Gate:** OPEN until actual native Windows/Linux tests and independent review/output verification pass. Neither FILM-01 nor studio-scale rendering is accepted by these changes.

## Production requirement

A 1-minute or 3-hour film is edited and produced through the same **small window** abstraction. Opening the project/scene is metadata-only. A native source review can select 1–96 consecutive *output* frames without expanding an entire edit into per-frame records. At an edit cut, the window contains ordered, exact source slices; trim/repeat/reorder source decisions come solely from committed compact editorial intervals and FilmIndex source revision hashes.

## Implemented execution chain

1. Trusted `SourceWindowPreflight.prepare` independently audits the complete indexed edit SHA/clip manifest, pages only the relevant output interval, and rehashes the current original source files associated with the requested frames. OFFLINE, CHANGED, cross-project or missing originals refuse native work.
2. `NativeSourceWindowHost.stage_and_approve` asks the host-supplied creator-policy callback to authorize the **exact** project/edit revision SHA, frame interval, output destination and RAM budget. It writes an immutable canonical worker plan, hashes Python/worker/FFmpeg executables, persists an expiring approval grant, and enqueues it using NVP's existing `ApprovedTaskBindings` and `TaskLedger`. Enqueue does not start a worker or reserve RAM.
3. `run_next` revalidates the sealed spec and source window after admission, then launches a worker using `launch_contained`, under `wait_guarded` resource-pressure and timeout supervision. Revoked/changed grants or sources fail closed.
4. The contained worker recreates FilmIndex and inventory from SQLite, rechecks all source digests and exact edit bindings, then invokes pinned FFmpeg to decode the selected ranges to independent PNG review frames. It verifies the source files again after decoding each slice.
5. The worker writes a canonical `review_receipt.json` with SHA-256 and byte size for each output frame. The host rechecks the source and calls `verify_review_window` to independently inspect each produced PNG, its number, header, size and hash. Only this check can mark the TaskLedger operation successful.
6. `verify_completed` opens a previously published receipt after restart and refuses tampering. A failed operation leaves ambiguous output for trusted reconciliation, not automatic overwrite or a fabricated successful film.

## Narrow meaning of success

The result is **verified unapproved source-review PNG frames**. It is **not** a source-linear scene render, graded Rec.709 master, accurate VFR/retimed conform, synchronized film, DCP or artist-approved picture. Outputs are not automatically added to FilmIndex as final masters. Exact FFmpeg frame selection is currently restricted to a source with one video stream and a matching constant nominal frame rate. The existing `BoundEditorialPublisher` validates source duration using reported FFprobe metadata; full source-frame/keyframe/timecode indexing and VFR detection remain necessary before general professional footage support.

**Performance limitation:** The first FFmpeg `select(n,...)` decoder starts from the beginning of the original source. The output work is bounded to 96 frames, but decoding a late interval in a many-hour camera original is **not** yet O(window). Add validated keyframe-based seeks/timestamps and truthful indexing before describing this as efficient studio-scale random access.

**Safety limitation:** Windows Job Object and Linux process-group supervision use the established NVP containment APIs. Strict Linux whole-descendant cgroup kill is a separately configured gate; ordinary Linux host hard-exit handling cannot claim detached-grandchild cleanup. FFmpeg itself is a child of the worker; nested process crash/fault acceptance is still open. The existing user-approved source-root confinement and OS-native path/volume anti-substitution work also remains open.

## Tests and evidence

- `tests/test_nvp_source_window_preflight.py`: real native FFmpeg source clips, cross-cut source slices, edit tail seek, offline SD-card source, same-size changed source, oversized window, project isolation and no hash-bypass.
- `tests/test_nvp_source_window_native.py`: real contained FFmpeg extraction from source-bound exact FilmIndex edit; TaskLedger authorization/approval, restart, receipt tamper, stale/offline input and refused creator event.
- `.github/workflows/nvp-scale01-02.yml`: Windows Server 2025 + Ubuntu 24.04 at Python 3.11 and 3.13, native FFmpeg and FFprobe, with pywin32 provisioning on Windows. The workflow is intentionally not a compile-only gate.
- Green CI on each exact-head cell must be inspected before acceptance; a queued/skipped job is not a pass.

## Next production milestones

1. Close actual native tests and fix errors; add independent FFprobe decoded-frame count/dimension evidence and FFmpeg binary hash verification at exit.
2. Replace whole-source decode-before-window with validated source frame-index/keyframe accurate seeking, including VFR and camera timecode policy.
3. Add source-volume root confinement and safe external-media read leases, handling hot-unplug during worker work.
4. Add per-window source-linear/OCIO high-resolution processing and downstream FilmIndex review-presentation custody, with exact edit and clip manifest SHA.
5. Upgrade output assembly, audio synchrony, partial invalidation and streaming feature-length mastering on the same work graph.

**The AI Assistance Layer remains paused.**
