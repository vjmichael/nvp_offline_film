# INDEX-TIME-03 — Native preview and source-verified conform preparation

**Product architecture:** NVP's Film Time and Temporal Ledger remain authoritative for native performances; source-indexed imported media are observations placed on the same authored clock. FilmIndex owns exact source IDs, ingest SHA, project isolation, immutable source/edit revisions and their impact graph. OpenUSD source expansion is not part of this milestone.

**Status:** Production implementation, real FFmpeg native tests, worker dispatch, and Linux/Windows Python 3.11/3.13 CI committed on an INDEX-TIME-02 stacked branch. **Native acceptance remains OPEN until exact-head CI passes.**

## Integrated path (no second execution engine)

1. FilmTimeWindowPreflight takes the existing versioned FilmTimeEditorialPublisher and selects exactly one imported clip ordinal, 1–96 consecutive original frames, and either preview or conform_prepare mode.
2. It re-verifies the complete saved edit manifest and sealed FilmIndex source revision, reopens original source PTS and exact in/out boundary from the existing NVPFrameIndex/IndexedSourceFilmTime, and produces a canonical source-time plan. Every planned PNG review slot corresponds to an **actual original source-frame PTS and authored film-time tick**. Output review slot indices are not new authoritative film frames.
3. NativeFilmTimeWindowHost calls the native host's creator policy verifier with an exact edit/revision/document SHA, clip/time window, mode, destination and RAM budget. A denied creator decision publishes no task and starts no worker.
4. The host reuses **ApprovedTaskBindings, TaskLedger, AdmissionRequest, launch_contained, wait_guarded** and the existing tools/nvp_source_window_worker.py entrypoint. No shell fallback, unmanaged subprocess or separate job queue is added. Native FFmpeg/FFprobe/Python/worker entrypoint hashes are pinned to the approved job. The approval spec and exact plan hashes are stored in durable SQLite task/grant records.
5. Native worker reconstructs the same source edit and plan from Studio/FilmIndex/source inventory; rechecks the exact sealed plan before decoding and again before receipt publication. It uses the existing NVPFrameIndex and nvp_indexed_preview.extract accurate-seek FFmpeg decoder; no frame-number/FPS approximation is allowed.
6. The decoded review images are reconciled frame by frame against original PTS, source frame ordinals and Film Time ticks. The worker writes a canonical review receipt and independently verifies actual PNG signatures, bytes/size/hash, PTS, film-time coordinates, source SHA identities, output order and manifest digest. The host independently repeats receipt verification and seals the receipt SHA in TaskLedger's grant record.
7. A completed task can be re-opened and re-verified after restarting the desktop process without rerunning FFmpeg or rewriting its original source edit. A failed job is not a successful receipt. The host can explicitly **revoke a queued creator grant** and cancel it before worker admission. Running workers instead use the supervised cancellation hook; a task that loses its supervisor retains the ACTIVE memory reservation until a **trusted OS process-tree-fencing proof** permits explicit INTERRUPTED reconciliation. A new creator approval is required for retry.

## Integrity modes

**preview:** Fast native review. NVP verifies source-inventory/FilmIndex revision identity and inexpensive file/index stamps; original footage is **SOURCE_STAMP_UNVERIFIED_PREVIEW** and not rehashed in this path. It refuses offline, changed-stamp, wrong-project, wrong-version and wrong-PTS sources. It cannot claim original-byte custody.

**conform_prepare:** Explicitly rehashes the entire original source against FilmIndex SHA at the host preflight and worker before decoding, and repeats original SHA verification **after** decode before publishing its receipt. The receipt status is FULL_SHA_VERIFIED_BEFORE_AND_AFTER_REVIEW. This is the **preparation/verification** of source frames at exact authored time, not presentation rendering, audio mux, approved final conform, final mix or DCP output. Both modes produce *unapproved PNG source review media*, not a finished film.

This separation avoids escalating permission into final authority. Imported-video editor tasks are authorized to inspect/prepare specific media only. Their receipts explicitly set approved_final=false and native_film_events_modified=false.

## Existing modules reused, new files

- backend/nvp_film_time_window_preflight.py — bounded exact-time film-source preflight.
- backend/nvp_film_time_window_decode.py — contained worker read/decoded-PTS/receipt/PNG verification.
- backend/nvp_film_time_window_host.py — creator approval, durable grants, resource admission and OS-contained supervision.
- tools/nvp_source_window_worker.py — existing contained source-window worker entrypoint, extended with one film_time_index decoder route.
- tests/test_nvp_film_time_window_native.py — actual VFR/B-frame native source, preview/conform receipts, altered receipt rejection, refused creator approval, queued cancellation, source mutation refusal, contained worker/restart receipt verification, and explicit OS-fenced crash reconciliation.
- .github/workflows/nvp-index-time03-native.yml — real FFmpeg/FFprobe on Windows 2025 and Ubuntu 24.04, Python 3.11 and 3.13; Windows provisions pywin32 for Job Objects; also runs INDEX-TIME-02/01 and Temporal Ledger regressions.

## Not part of this milestone

No automatic creator approval, full feature-film rendered frames, mixed audio conform, per-track retiming, crossfades/overlays, live OSC/SDI timeline, optical correction, final mux, final DCP, broad codec assurance, backend throughput winner or desktop editor UI. Those retain their existing separate production authorizations and native acceptance gates.

**Remaining acceptance:** exact-head native CI (and any API failures); installed Windows host entrypoint/manual reviewer acceptance; host-grade OS-fenced crash recovery matrix including real forced worker death; acceptance of source-derived final physical frame boundaries; saved editorial UI move/trim controls; real FFMS2-vs-NVP quantitative benchmark/codec matrix.

**Governing rule:** one authored film-time clock; source images indexed by original PTS; immutable versioned placements; preview is provisional; conform preparation verifies source bytes; master publication always needs separate creator approval.
