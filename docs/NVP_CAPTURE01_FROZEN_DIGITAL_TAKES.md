# NVP-CAPTURE-01 — Real Approved Timed Digital Take Freeze

**Date:** November 3, 2026  
**Scope:** Approved NVP real Studio/WorldState/BlockingCamera/ShotSequence proxy-source capture into durable FilmIndex.  
**Classification:** **CAPTURE-01A source, frozen storage and native Blender replay verified** against a real approved proxy-film fixture on Linux and Windows Blender 5.2.3. The full regression run is linked below; this is **not** a finished hi-fi video/voice adapter or final film pipeline.

## Why this gate matters

NVP's world is structured editable data. The low-fi Blender view is how the director previews that data. **A digital take must freeze the actual approved world/camera/actor/dialogue instructions—not simply record preview pixels.** That take can then drive multiple future render and voice adapters without silently rereading an altered scene.

DATA-01 previously established the immutable film source index and revision graph. CAPTURE-01 binds actual pre-existing director-approved production services to that index.

## Implemented contract

**Module:** `backend/nvp_digital_capture.py` — `DigitalCapture(Studio, FilmIndex)`.

`capture(project_id, scene_id, take_id)` does the following:

1. Calls real `ShotSequence.export` (which already enforces current director-approved scene and measured dialogue timing), and obtains independently checked world, camera/shot timeline, actor marks/paths, dialogue cues, warnings and approval plan.
2. Reads the source SQLite approved sequence row to bind its exact revision, approved digest, world/dependency digests and project/scene IDs.
3. Runs a saved-source coherence audit over world digest, plan hash, approval digest, 24-fps timeline, ordered shot boundaries, real solved camera data, actor IDs/motion records and measured spoken lines.
4. Stores an immutable **world source snapshot** (`kind=world`) and an immutable **approved timed performance snapshot** (`kind=performance`) in the existing FilmIndex. Source IDs derive from SHA-256 content; identical sources can be safely reused for multiple takes.
5. Registers a new **single-commit `kind=take` record** with exact typed dependency links to the frozen world/performance. At the take's final `BEGIN IMMEDIATE` transaction boundary, an internal trusted guard rereads the currently approved source. If the performance/camera/timing or its approved proof changed, **no take row is committed**.
6. Independently reopens the just-committed take from stored bytes, reruns the offline audit, and returns both the register receipt and audit.

`reopen(project_id, take_id)` does **not** need the current screenplay, director-approved live stage, actual Blender process, model weights, network or GPU. It follows the frozen take's FilmIndex typed world/performance edges, rechecks both actual content hashes and SQL/JSON provenance, validates the source Director approval digest, revisits frame/cast/dialogue structural checks, and returns the original historical world and camera/performance data.

The original take remains intact after a director begins a new shot-sequence revision or alters the living WorldState. A new capture requires a **new take ID**, preserving original approvals. A cross-project lookup fails, missing source/revisions fail, and tampering with stored take/performance metadata fails on independent reopen.

## Independent frozen-source native Blender replay

**Native fixture:** `tools/nvp_capture01_fixture.py`, using `run_frozen_take_acceptance` in `backend/nvp_digital_capture.py`. The fixture creates a **real approved 120-frame** NVP production scene with a moving actor, two different-lens camera shots, measured dialogue and explicit director approval. It captures and reopens the take, **modifies the live WorldState to invalidate the original source**, then creates a new Studio/FilmIndex and sends ONLY the saved old world/camera/motion data to the trusted Blender generator.

Blender saves a real `.blend`, reopens it, and audits shot markers, camera IDs and lens/pose, frame duration and source digest, and actual evaluated actor XY positions at multiple time samples. Linux also renders and checks a Workbench PNG. GPU-less Windows performs native geometry/camera checks without claiming to render a preview.

**Verified:** both Linux and Windows CAPTURE-01 native acceptance steps completed successfully in [workflow run 41688771494](https://github.com/vjmichael/nvp_offline_film/actions/runs/41688771494). A passing scoped step is not by itself a completed film pipeline.

## Exact contents and limitations

**Frozen world:** approved metric world manifest, stage rooms, actor/prop instances, source actor names and scene geometry/placements, digests and all present WorldState overlays.

**Frozen performance:** one real approved `nvp.production.timed_proxy.v1` export, including 24-fps ordered shots (stop frame is exclusive), actual solved camera recipe/solution per shot, actor initial positions and path/mark tracks, dialogue line identity, speaker, measured duration, timeline start, original director approval plan and receipt, plus the source review.

**What is NOT yet captured:** sampled real facial animation, physical waveforms and microphones, licensed hi-fi model assets, exact audio-sample alignment, human biomechanics, universal cinematic timecode, 3D engine render passes or generative video media. Existing proxy track limitations are deliberately inherited and explicitly reported; CAPTURE-01 must not claim photorealistic or vocal results.

**No media render here:** a frozen take is structured capture, not final footage. It can later be fed to Blender and to capability-negotiating sound/video AI adapters. Such adapters must interpret the data through their actual supported interfaces.

**Resource profile:** capture uses SQLite, immutable small JSON blobs and Python; it does not run a GPU, video diffusion model or high-poly scene. The project's future final render may have much higher resource requirements.

## Security and recovery

`FilmIndex.register_revision(..., precommit_guard=...)` now supports a trusted **in-process-only** source-approval recheck after dependency resolution and before take row commit, while SQLite holds the write lock. Do not expose this callback as a model-authored tool or arbitrary script. It is not a substitute for future Lu worker authorization.

FilmIndex's source blobs use no-clobber atomic disk publication and SHA-256 integrity checks, and the SQLite graph validates IDs and foreign keys. A capture that fails late may leave **unreferenced or immutable, correctly indexed source snapshots** but must not publish a false-approved take. Garbage collection of such orphans is deliberately deferred; no silent deletion of committed source history.

## Regression coverage

`tests/test_digital_capture.py` uses actual approved production scenes, two registered characters, two measured dialogue lines, two shots/solved camera data, and approved 120-frame sequence. The suite checks:

- Capture and independently reopen a genuine source and timed take after Studio DB restart.
- Reuse identical content-hashed source snapshots for separate captured take IDs.
- Reject attempted in-place recapture of a frozen take.
- Preserve original capture through a new draft sequence and a new/stale WorldState.
- Force a source change between initial export and final record commit; assert **no take exists**.
- Reject foreign project, missing take and malformed take IDs.
- Independently refuse tampered digital-take metadata, source approval receipts and corrupted performance bytes.
- Follow typed world -> performance -> take -> presentation dependencies with correct impact queries.

This expands the Linux/Windows full Python regressions and retains existing Blender/React gates. The **new CAPTURE-01 native fixture additionally** rebuilds and audits the original stored take after its live source is invalidated. It is still an audited **proxy visualization**, not a hi-fi AI presentation.

## Next gate

**NVP-PIPE-01A** should consume a `DigitalCapture.reopen` result and produce a real deterministic presentation through a trusted Blender adapter, with output media hashes and an indexed `presentation` record linked to the exact captured take. Then perform a real **selective rerender** of only one chosen shot and prove unchanged source/take/other-shot hashes. User-selected video and voice model adapters follow with explicit capability and licensing checks.

**Acceptance evidence:** the initial source/data suite passed 428 Linux tests (421 passes, seven skips) in run 41687890590, which was later superseded/cancelled before finishing all jobs. The latest all-platform run is https://github.com/vjmichael/nvp_offline_film/actions/runs/41688771494 at code commit `f97e7607`. Both the Linux and Windows **CAPTURE-01 native Blender replay steps passed**. Check the complete workflow conclusion separately.
