# USD-FILM-01Q — Data-first selected-view editorial rendering

**Implementation:** source committed; **native Windows/Linux tests and actual Cycles
pixel verification OPEN**. This replaces the *mandatory* 6,480-frame
multi-camera-roll render assumption for normal film production. The original
nine-camera complete-roll export remains optional and available through 01O.

## What a Digital Take records

One immutable, complete performance: original ActorIDs, actor and prop
geometry and movement, source animation/physics, light/material and sound
sources, shared Film Time, original world Take and all source signatures.
A camera is a revisioned **virtual viewpoint**. A director can add a new
camera after acting has finished, without changing source event/ActorIDs.

## Director edit: persistent source and camera choices

`backend/nvp_usd_film01q_selected_view_edit.py` publishes an immutable,
FilmIndex-owned `edit` revision with explicit dependencies on one exact
original 01M camera bank **revision/SHA** and immutable 01E world Take.
An editor cannot send a bare script or set of paths and declare an edit
approved; an authenticated host-supplied director decision must match an
exact proposed document SHA.

Cuts use original 24fps source time and a single 720-frame continuous
timeline: each says camera ID, original in/out and edited in/out, with
no actor time shifts, gaps or overlaps. A later camera/edit revision
remains independent and leaves all prior FilmIndex revisions intact.
The original shared PCM belongs to the performance, not camera streams.

## Render 720 selected images, not 9 × 720 unselected images

`selected_render_plan` independently opens the true original 01O
720-frame native USD animation source and verifies the exact world Take,
FilmIndex camera bank, actor-performance SHAs and source USD bytes.
For every frame 0–719, it selects ONE original camera from the edit,
retains original Film Time, actual source actor-state hash, selected camera
native USD path/animated position, lens and exact per-camera wall-primary
ray exclusions. The result has **90 bounded eight-frame shot chunks**.

A single eight-frame chunk may contain a cut (for example source frame
0–3 Camera A, source frames 4–7 Camera B). Its per-frame camera changes
do **not** require rendering both full 8-frame source rolls. Each frame
has a source+view+render-profile-based cache identity; a changed
camera/edit can preserve unrelated frame-view cache keys. Cross-revision
**cache re-use is not yet enabled** until the native worker, provenance
and original source stability checks cover it.

`tools/nvp_usd_film01q_blender_selected_views.py` is a fixed first-party
Blender/Cycles worker: imports source USD once per chunk, selects the
actual native camera **per frame**, checks source ActorIDs/poses/camera
positions, applies only selected camera primary-ray wall masks and
restores visibility immediately after each frame. It outputs exactly
eight genuine 320×180, eight-sample Cycles PNG **technical smoke-profile**
pictures and one exact source-linked audit. These pixels are not yet
hi-fi-quality cinema masters; scalable final-quality rendering is a
later acceptance gate.

## Protected native execution and recovery

`backend/nvp_usd_film01q_selected_view_host.py` uses existing
`BlenderWorkerSupervisor` and original 01O USD source staging.
It requires fresh per-chunk director authorization (exact edit document
SHA, source USD/performance, eight source frames, original camera
choices and job ID), OS-contained and SHA-pinned script/inputs,
time/memory limits and durable journal. Native CPU/GPU admission remains
under the existing Resource Guardian; the separate adaptive 01S
resource-batching control does not grant renderer permissions.

A completed job must have independently verifiable source inputs,
Blender audit and all eight real 320×180 PNGs. After restart, only a
successfully completed, **reverified** journal entry can be reused.
Interrupted/failed jobs are not replayed; the next attempt needs a
new ID, fresh approval and independently verified OS worker custody.
The host provides bounded `progress`, `run_next` and `gather`
methods; it never declares a film because files merely exist.

After **all 90 selected chunks / 720 actual pictures** pass, the host
revalidates every source-selected camera/ActorID/time and native worker
receipt, independently runs FFmpeg/FFprobe to encode a 720-frame
FFV1 picture and muxes the **ONE original source 48k PCM sound**.
The decoded film must contain 720 original pictures and exactly
1,440,000 PCM samples with the same original mix essence SHA.
Director visual/audio review stays explicitly unapproved.

## Actual acceptance still OPEN

1. Exact-head Windows/Linux 3.11/3.13 real source USD/FilmIndex
   tests. Exercise new camera/edit revision and unchanged original
   ActorID/Take, changed-frame-only view-cache keys, and invalid camera/
   gaps/auth refusals.
2. Actual verified Blender 5.2.3 8-picture smoke: four pictures from
   one original camera and four from a different original camera,
   with a cut **inside one eight-frame chunk at frame 4**, accurate
   actor pose/optics/wall ray state and fresh-process re-verification.
   The workflow publishes actual PNG/USD/plan/audit artifacts for
   independent inspection. Queued source/CI tests are not accepted.
3. Install NVP and connect the authoritative editor EDL to 01S
   resource-adaptive scheduler and interactive low-fi preview (01R),
   preserving user choice of batch sizes and verified source identity.
4. Execute all 90 genuine selected-view chunks on representative
   workstation hardware, independently verify movie and original audio,
   review direction/lighting/actors/pacing and obtain director approval.
5. Expand renderer quality beyond smoke profile (proper film resolution,
   samples, Materials, lights, view-dependent effects) under measured
   CPU/GPU budgets. The optional 9×720 full-roll stress export remains
   deferred until qualified GPU hardware.

**Outcome:** a film can be edited without first rendering nine
camera recordings. Low-powered PCs preview more perspectives than they
can render concurrently and can produce selected source frames serially.
This is a source-authored technical pipeline pending genuine native
execution, not a claimed finished feature-quality movie.
