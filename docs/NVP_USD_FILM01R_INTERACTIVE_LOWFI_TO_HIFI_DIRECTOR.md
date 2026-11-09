# USD-FILM-01R — Interactive source-first director editor, low-fi to Cycles

**Implementation in PR:** Source/authenticated bridge/UI/test workflows committed.
**Status:** Source implementation; **actual Windows/Linux native results, installed
editor acceptance, full 720-frame 30-second film and human picture/audio
quality approval remain OPEN.** 01R does not certify a cinema master.

## Director experience

1. Freeze one immutable original OpenUSD world Take with ActorIDs, true
   time-sampled movement, geometry, light/material and original PCM.
2. Open **22 · Direct the data** in the existing installed NVP desktop UI.
   Pick an original 01M source camera bank and virtual camera, scrub
   Film Time 0–719, orbit the source geometry temporarily or play a
   bounded 2-fps low-fi proxy sequence.
3. Low-fi source viewer consumes actual `pxr` evaluated USD geometry,
   world transforms and camera optics at each tick. Mesh triangles are
   forwarded only within hard per-scene/mesh caps. Native cubes/spheres/
   cylinders/cones and oversized meshes become explicitly marked
   bounded geometry proxies, never a fake photographic picture. A
   CPU-only source-camera position/projection fallback exists if WebGL
   is unavailable. This is an OpenUSD staging/directing viewport, not a
   substitute for Cycles shadows/reflection/complex material quality.
4. Split the non-destructive 720-frame edit at any frame, assign another
   viewpoint to the selected cut, merge shots or undo a draft action.
   Original source Film Time and ActorID performance never change.
5. In the installed WebView, use genuine OS confirmation to create a
   one-camera source bank, add/remove a camera, and save new immutable
   `edit` revisions via the original 01M/01Q FilmIndex. Each approval
   is over the **exact source SHA and proposed edit or camera SHA**.
   No arbitrary public HTTP endpoint can write an edit, launch
   Blender or self-approve a frozen Take.
6. Choose a reviewed Cycles output profile; NVP estimates hardware
   headroom via 01S, then one explicit OS-confirmed native action can
   render the **next eight selected original frames** using the
   existing 01Q bounded, journaled BlenderWorkerSupervisor.
   A chunk is free to cut between two cameras internally. The
   director sees the separately reverified real Cycles PNG as soon
   as that approved worker finishes, alongside the low-fi source view.
7. Further original-shot chunks preserve 01Q's SHA-pinned source and
   profile identity, process cancellation/recovery broker, immutable
   edit revisions and independent PNG+journal audits. The original
   one-source 48k PCM must be included in the eventual 720-frame
   conform; nine full camera rolls are **optional stress/export only**.

## Implementation artifacts

- `backend/nvp_usd_film01r_lowfi_source.py`: project-scoped read-only
  source bank/edit/Take discovery; genuine OpenUSD camera optics,
  actor IDs and sampled geometry/bbox proxies at exact Film Time with
  hard bounds. No original world data is rewritten.
- `frontend/src/SourceUSDViewport.jsx`: Three.js source wireframe,
  original camera projection and orbit; CPU-only 2D projected fallback
  when WebGL is unavailable.
- `frontend/src/DataFirstViewpointEditor.jsx`: source-verified camera
  selection, original timeline scrub, pause/play preview, cut/split/
  reassignment/merge/undo, native camera collection changes, edit
  revisions, resource estimated shot batches, reviewed Cycles draft
  to candidate-final profile controls, source-bound real PNG readback.
- Existing `backend/nvp_api.py` adds only two **read-only** local routes:
  `GET /api/projects/{id}/film/data-first-viewpoints` and
  `GET /api/projects/{id}/film/data-first-viewpoints/{bank}/preview`.
  Public browser editing cannot assert creator approval.
- Existing installed `TrustedDesktopWO5Bridge` (inherited by
  `TrustedDesktopWO6Bridge` used by
  `tools/nvp_desktop_alpha.py`) gets:
  `film01r_catalog`, `film01r_preview`,
  `film01r_create_bank`, `film01r_revise_bank`,
  `film01r_save_edit`, `film01r_render_next`,
  `film01r_render_poll`, `film01r_render_image`. Its inherited
  exact current WebView origin and OS native confirmation are required
  for privileged writes/workers. It reuses existing host/supervisor,
  not a second native process manager.
- `backend/nvp_usd_film01r_quality.py` defines reviewed CPU Cycles:
  technical 320×180/8 samples/2GiB, draft 640×360/16/3GiB,
  candidate-final 1280×720/48/6GiB and 1920×1080/96/12GiB.
  Native worker inputs, render-plan SHA, per-frame view cache identities,
  unique worker IDs, independently expected PNG dimensions, authorization
  and time/memory boundaries are profile-specific. An unreviewed browser
  script/quality/GPU backend is rejected. These are technical candidate
  settings; "final" in a preset name is NOT creative cinema approval.
- 01M virtual cameras now author a matching native 36×20.25 mm
  camera aperture in addition to their focal length. Before this
  repair, default USD camera apertures could cause materially
  incorrect low-fi FOV even when the numeric focal length matched.
- `tests/test_nvp_usd_film01i_ninecam_take.py`: direct native
  USD source geometry and original camera FOV, exact fake OS window
  approval/denial and foreign-origin rejection, new viewpoint after
  freezing performance, FilmIndex old revisions, quality-keyed cache
  and worker identity. Optional real official Blender 5.2 test
  renders **only 8 original selected pictures** with a cut after
  frame four, at 640×360/16-sample draft profile, and checks
  imported source/camera/PNG and restarted host journal evidence.
- `frontend/src/DataFirstViewpointEditor.test.jsx`: Vitest editor
  split/change camera, source-only browser write refusal, native OS
  approved edit and RAM-limited rendering. Standard Vite build
  checks that the director tab is included.
- Native CI: Win 2025 + Ubuntu 24.04 Py3.11/3.13 USD source; real
  React UI tests/production build; one official SHA-verified Blender
  5.2.3 Ubuntu eight-frame draft smoke with PNG artifacts.
  **Exact-head results must still be inspected.**

## Resource and protection boundaries

- The LOW-fi scene/data viewer does not need Blender or a dedicated
  high-power GPU. Geometry is bounded for low-power machines and
  browser without WebGL still has a simple projected view.
- The requested shots-per-batch and parallel-worker cap are respected
  for **resource estimates and native admission** through 01S
  `safe_parallelism`; current desktop 01R worker executes **one
  source-verified eight-frame job per OS-authorized request**, not an
  unbounded automatic production queue. Browser grouping settings are
  not worker permissions.
- NVP's original OS-contained Blender supervisor (not Lu) owns
  process execution, RAM limits, cancellation and journal recovery.
  01R cannot reuse expired permissions or silently restart an
  interrupted Blender process. GPU render mode is not enabled
  until actual Blender/Cycles-compatible device admission passes.
- On native source approval, typed source identities are independently
  reverified by the 01M/01Q host after the browser's proposal.
  No arbitrary file path, worker script, model tool, or signed
  permission passes through 01R frontend requests.
- Lu may read NVP's independently reported RES-01 process usage;
  NVP↔Lu model unload/reload resource handoff remains the separately
  deferred `POST-LU-1.0` requirement, not implemented by this GUI.

## Next acceptance and workflow tasks

1. Obtain exact-head native CI and Vite/React results; fix genuine
   OS compilation, native OpenUSD camera optical transforms,
   mesh/proxy, source time interpolation, Blender worker input,
   original ActorID pose and output discrepancies.
2. Prove installed Windows WebView2 01R tab, actual source scrubbing
   latency, CPU memory use, editing with OS confirmations, source
   revision reopening, real Blender preview picture and worker
   cancellation/recovery. Test a genuinely low-power PC.
3. Bind approved EDL shot-group **batches** to the durable 01S
   queue (not just estimates); each finished native chunk must be
   source-checked and safely resumable without 90 manual editor
   clicks. Handle chunk boundaries that cross edited shot cuts.
4. Execute all 90 genuine selected eight-frame jobs, assemble the
   original 720-frame 30-second picture with exactly one original
   48k PCM soundtrack, independently inspect visual and audio
   quality; only after human director signoff close first-film
   blocker. Nine full camera rolls remain an optional stress test.
5. Confirm final production look: representative materials, lights,
   reflections, secondary motion, performance continuity, exposure,
   genuine film resolution, render quality under actual GPU/CPU
   measurement. Longer scenes remain blocked until this passes.

No source-only test, estimated capacity, invented picture or queued
GitHub result is counted as film-production acceptance.
