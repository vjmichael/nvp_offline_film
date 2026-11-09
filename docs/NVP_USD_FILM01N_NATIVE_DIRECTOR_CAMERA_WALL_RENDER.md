# USD-FILM-01N — Native Cycles director-camera shot and through-wall comparison

## Real cinematography requirement

A director's arbitrary camera is not limited to the optional 3×3 preset.
NVP's same original authored performance may be viewed from a reverse, OTS,
low, high, aerial or custom camera. Cameras do not generate meshes or physical
collisions. Camera moves through scenery are allowed. **Seeing through
scenery** is an independent, explicitly selected shot-local camera-ray
decision, not global visibility deletion.

## What this task connects (implementation committed; native CI OPEN)

- `stage_original_director_camera_frame` verifies the original FilmIndex
  01M camera-bank revision, its one original 01E actor-world Take, original
  ActorIDs and source tick. It opens the original loaded USD world, authors
  virtual camera prims ONLY in the session layer, and derives a temporary
  flattened one-frame stage for Blender. Actor poses and camera position,
  native lens and orientation remain source-locked. Unbundled external
  texture paths fail closed. The original world, camera revisions and
  takes stay unchanged.
- A new fixed first-party Blender 5.2 Cycles worker imports the original
  source geometry, checks ActorID transforms, native camera focal/position
  and forward direction, and renders the selected camera. It never
  synthesizes camera equipment meshes or replacement performers.
- On a camera with explicit wall exceptions, the trusted 01M helper
  maps the source-authenticated original USD wall hierarchy into Blender
  objects and sets only `visible_camera=False` on matched mesh objects
  while the picture is rendered. The prior states are restored even on
  render failure. Original wall geometry, other camera views, source data
  and shadow/glossy/diffuse flags are untouched.
- `ReviewedDirectorCameraCycles` binds exact camera-bank SHA, original
  Take/performance SHA, source tick, per-camera mask paths, frozen USD
  SHA and job IDs to a director-authenticated approval. It launches
  existing SHA-pinned BlenderWorkerSupervisor jobs with bounded memory,
  timeout, durable journal and post-run independent file/hash verification.
  It never accepts a Blender worker's audit without matching original
  FilmIndex-derived input and independently hashed actual PNG/.blend.
- A dedicated native CI source fixture creates `WallNormal` and
  `WallGhost` cameras at the same position/time/lens over the same
  original 30-second ActorID performance. `WallGhost` excludes ONLY
  the source environment Wall from primary camera rays. The test requires
  two genuine 320×180 Cycles PNGs, different image hashes, native
  mask application/restoration, original actor and camera parity,
  and actual .blend and JSON/source artifacts. It explicitly marks both
  results **UNAPPROVED** until actual artifact inspection.

## Remaining gates before full filmmaking acceptance

1. Inspect exact-head Ubuntu 24.04 official Blender 5.2.3 CI job,
   fix real import hierarchy/mask/actor-motion/camera issues. Confirm
   actual frames show the intended wall behavior and preserved lighting.
2. Prove camera equipment does not enter other cameras' renders.
3. Provide installed UI director camera list/add/remove/rename/move/undo
   and original source-locked per-shot visibility controls.
4. Extend the same pinned native worker pattern to all selected frames of
   director-approved camera rolls, with bounded resumable chunks,
   OS-process recovery and independent source/frame authenticity.
5. Conform a playable original-source 30s film with synchronized 48 kHz
   original sound, edit decisions, full camera coverage receipts and
   human direction/shot continuity review.
6. USD-FILM-00–10 still have their own native geometry, actors,
   MaterialX/lighting, cinematography, physics, performance, quality,
   world streaming and long-form film gates. HSURF remains after the
   broader USD-FILM line as directed.

A source-authentic one-frame shot is neither full multicamera footage
nor the film master. Synthetic metadata and queued CI never pass as pixels.
