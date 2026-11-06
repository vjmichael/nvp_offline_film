# NVP SLATE-05 — On-Demand Low-Fi Visual Previews and Bounded Cache

**Creator direction — November 6, 2026.** NVP edits only **source-data references**: the timeline is a small, revisioned assembly of immutable but explicitly deletable frozen Takes, shot-specific OpenUSD opinions and exact source-time intervals. Preview rendering is a derivative, not the source of truth. An editor should not load the whole film or all alternative Takes into RAM to move the playhead.

**Status:** Preview staging, contained native worker bridge, disk cache, display component and acceptance tests committed. **Exact-head CI, installed Windows desktop wiring, native host-to-image bridge, real character mesh rendering, continuity and audio remain OPEN.** This milestone adds low-fi blocking proxies, NOT a full NVP 3D character film renderer.

## Low-cost cache-hit path

The editor's exact committed cut is resolved by `SlateLazyPreview.select()`. The ticket includes the original frozen Take SHA, optional SHOT-01 layer SHA, exact source time, edit SHA, source segment, and quality. SLATE-05 derives a second deterministic cache key from the **source SHA/tick, shot SHA, trusted proxy renderer version and script SHA**, including quality/resolution. The key is computed **before** opening any OpenUSD layer; identical source data used multiple times on an edit can reuse the same preview PNG.

`SlatePreviewCache.lookup()` checks the project namespace, READY state, PNG dimensions, size and SHA on disk. It returns only a verified derivative or a cache miss. Missing/corrupt PNGs are rejected and removed from cache ownership for safe re-render. Cache hits do not authorize or launch workers, load source geometry or alter original data.

## Cache-miss rendering path

`capture_proxy()` revalidates the source ticket against FilmIndex and opens only the selected frozen scene and optional approved shot override, sampling up to **16** role-selected native OpenUSD prims at the exact original source tick. It captures only finite bounded camera, actor, prop and light world translations. Its first-party `BLENDER_SCRIPT` maps them to obvious procedural **proxy shapes** and a review camera, producing a thumbnail (256×144), interactive preview (512×288) or inspection preview (640×360). This is a real Blender Workbench PNG when a worker completes, **but not the source USD mesh, true skeletal performance, pose, facial acting, physical lighting, sound or final picture**. Camera framing is approximate, especially for non-native schema cameras.

The trusted native host stages an exclusive SHA-pinned JSON snapshot and fixed NVP script within a fresh job directory and creates a bounded `BlenderOperation` with one input manifest and one PNG output. The only allowed worker arguments are the existing `--manifest` and `--preview` flags. No arbitrary scripts/executables, untrusted USD references, source paths or model-selected files are run.

The host's authenticated creator event binds the exact edit revision, source/shot SHA, source tick, quality, manifest SHA, script SHA, operation SHA and memory request to a **durable, expiring consent**. The existing `ApprovedBlenderDispatcher` and `TaskLedger` handle queueing, measured resource admission, source/approval recheck before launching, and the existing `BlenderWorkerSupervisor` handles Windows Job Object or Linux contained execution, cancellation and journal/recovery. This is **not a new unsupervised process runner**.

A QUEUED job is not a worker start or a rendered PNG. Only after `supervisor.verify_completed(job_id)` independently verifies the worker specification, original pinned inputs and PNG SHA does the cache copy its verified PNG to its content-keyed project location through no-clobber publication. The cache performs an additional PNG/size/dimension and SHA check before it becomes READY. The native host provides a bounded **one-PNG** byte accessor for trusted desktop IPC rather than letting a browser dereference worker file paths.

## Bounded caching and crash recovery

The cache defaults to **256 MiB or 1,024 READY images**, whichever ceiling is reached first; both are tunable within explicit budgets. Its SQLite metadata uses FULL synchronous durability and stores source SHA, recipe SHA, cache key, worker ID, verified image SHA, size, state and LRU timestamps. Eviction removes only generated PNG derivatives. It never touches FilmIndex source blobs, frozen Takes, performances or the active edit.

A crash between successful native rendering and cache acceptance leaves a PENDING entry. Recovery does **not relaunch** Blender or trust partial bytes. It can mark READY only when the old supervisor's independent SUCCESS receipt and output audit still pass. Otherwise it records INTERRUPTED. Cancellation requires another trusted creator action; queued tasks can be cancelled without launching the worker, while running worker cancellation uses the established contained process cancellation path. No output is marked READY until termination and audit are proven.

The UI's low-fi preview pane can display only image bytes provided by the trusted host for the **exact committed edit SHA and selected segment**. A stale preview, an uncommitted draft, or a queued render must not replace the current viewed shot. The callback and visual component exist, but the installed app still needs its native adapter to convert verified PNG bytes to a short-lived display URL or in-memory object.

## Acceptance plan

1. Windows 2025 / Ubuntu 24.04 Python 3.11 and 3.13: real OpenUSD actor/scene/SHOT sampling, exact-time source SHA cache identity, trusted consent rejection, durable queued job binding, denied tampered staged JSON, queued cancellation, old Take unchanged.
2. Crash and media tests: PNG proper bytes/dimensions/SHA verification, corruption rejection, cache reuse without USD load, LRU eviction only of derivatives, recovery of independent worker success after host interruption, fail-closed incomplete jobs.
3. Separate Ubuntu runner installs **actual Blender**, runs the NVP-generated proxy script through the established contained native supervisor with real OS RAM admission, then independently reopens the PNG receipt and cache.
4. React build/Vitest: preview QUEUED versus READY labels, correct committed edit SHA and selected-segment gating, no random external media URLs, and existing copy/cut/paste metadata UI regressions.
5. Installed desktop acceptance remains open: live source scrubbing, native low-fi renderer queue, preview image IPC, cache eviction controls, worker cancellation, crash reopening, real 3D actor meshes and audio sync.

## Non-goals and next milestones

SLATE-05 is a **low-fi composition proof** generated from source Take data. It is not an exact USD-geometry renderer. The next production renderer integration must preserve the exact Digital Take/SHOT layer composition and native camera/light/material/rig channels, using supervised Blender or another approved offline engine, then add camera-accurate visual presentation, adaptive proxy-resolution policies, deduplicated background prefetch near the playhead, sound, and final color/output approval.

**Invariant:** Edit an ordered list of references. When needed, resolve one source time, stage one approved renderer operation, cache one verified derivative, and evict it freely without rewriting any source of truth.
