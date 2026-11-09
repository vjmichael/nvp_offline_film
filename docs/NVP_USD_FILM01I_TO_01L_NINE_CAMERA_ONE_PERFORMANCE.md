# USD-FILM-01I–01L — Nine original cameras / one performance / real Cycles bridge

## Blocking filmmaking target

Film the **same** 30-second original scene with nine native cameras
(angles A/B/C × wide/medium/close-up) and preserve all nine 30-second
rolls for editorial selection. Authoritative actor, physics, source audio
and Film Time must be shared. Renderers may compute views sequentially:
camera coverage is synchronized to the *same* source event, not 9 live
physical image sensors or necessarily concurrent GPU processes.

A 24fps acceptance film requires nine 720-frame source rolls = **6,480
independently rendered source frames**; the editor conforms a 720-frame
30-second finished short (source sound aligned and separately verified).
This is a blocker for longer-film acceptance, not an optional new platform.

## 01I — original nine-camera source bank [implemented; native CI OPEN]

- `OpenUSDSceneBridge.publish(native_camera_specs=...)` supports real native
  UsdGeom.Camera rotation, focal length and focus distance authored into the
  immutable original layout layer, independently reopened and verified.
- `OriginalNineCameraFilmSet` requires one exact immutable 01E world Take,
  one original 30-second scene Take, at least three ActorIDs, nine original
  01D camera plans and source-verified native lenses/directions. Source
  optics must sort wide / medium / close for each A/B/C camera angle.
- One immutable FilmIndex `presentation` binds the original world Take
  and nine camera sources, with host-authenticated exact creative scope.
  No copies of the actor performance or recorded PCM are created.
- `OriginalFilmPerformanceSampler.frame(i)` returns one original actor
  state plus nine native camera view identities at the same original tick.
- The real USD test authors one 30-second continuous Donut, Box, Sphere,
  Craft scene with original meshes, true animated position curves, nine
  UsdGeom cameras, source scene Digital Take, world Take, complete ActorID
  cast and freshly reopened SQLite/FilmIndex.

## 01J — editorial proof [contract implemented; film output OPEN]

- Requires all nine completed source rolls and receipts at every original
  frame, 6480 actual decodable and distinct PNG files, matching immutable
  camera/world/performance identifiers and identical actor-state checksum
  across the nine views at each original time tick.
- Nine 80-frame decisions select all nine original views in one continuous
  720-frame edit; FFmpeg/FFprobe independently checks an actual lossless
  30-second silent picture when genuine inputs are supplied.
- The unit fixtures explicitly produce **synthetic PNGs** to test the
  verifier. They are not native Cycles pixels, verified worker launches,
  approved film or accepted visual quality.

## 01K — original source → Blender native animated USD [implemented; native CI OPEN]

- Fully flattens only a temporary original loaded USD working set, retains
  original ActorID geometry/mesh/lights and all nine original cameras.
- Evaluates original source time-sampled USD attributes at 720 exact NVP
  film-time ticks and bakes **derived** 24fps Blender-friendly frames 1–720.
  No original source/Take layer is modified. Refuses unreviewed external
  texture paths until MaterialX source bundle support is accepted.
- Independently reopens the derived USD, checks every original actor prim
  and all nine camera prims, and compares true USD actor transforms with
  original source at 7 strategically selected frames including both cuts.
- Writes a full 720-frame source state/time audit (including native actor
  positions) and never claims the derived scene itself contains rendered
  pixels.

## 01L — native Blender/Cycles 9-camera smoke [source committed; CI OPEN]

- A first-party **fixed, SHA-pinned Blender 5.2 worker**, launched via
  existing `BlenderWorkerSupervisor`, imports 01K genuine animated USD.
- Checks actual imported camera count, original ActorID roots and scene
  geometry, actual actor world positions at selected source frame, actual
  native focal length and camera positions, then renders each of the nine
  original views using actual CPU Cycles.
- Three separately supervised worker processes test original frames
  **0, 360 and 719**; total **27 real frame targets**. Each job outputs nine
  actual native PNGs plus a saved .blend and JSON attestation, all
  independently rehashed against the source + supervisor durable journal.
- Ubuntu 24.04 workflow retrieves official Blender 5.2.3 and checks its
  published SHA. Its source/worker/PNG results must be inspected before
  accepting native camera/actor motion fidelity. Queued tests are not PASS.

## What remains before the director's multicamera blocker closes

1. Obtain actual exact-head Windows/Linux 01I/01K native results and genuine
   01L Blender rendered PNGs; repair real failures including USD import
   camera lens/orientation and moving original actor transform parity.
2. Build bounded, restart-resumable supervised **full nine-roll** renderer
   that produces all 6480 native Cycles frames in original source-time,
   with output receipts, source-preserving camera/actor checks and genuine
   job cancellation and reaping. The 27-frame smoke does not substitute.
3. Independently inspect a nine-view synchronized contact sheet and all
   intercut boundaries, correct staging of box behind donut and sphere
   through its actual hole, shadows/reflections/optics, animation, and
   movie-like pacing.
4. Mix the **single original 48 kHz PCM soundtrack** against the one
   performance, do not create nine parallel sound Takes; independently
   decode a completed 30-second picture+sound film.
5. Director visually/audibly approves one finished film. Then and only
   then close the multicamera blocker before advancing to longer tests.

Other USD-FILM-00–10 stages (modular geometry, actor rigs, motion,
physics, materials/photoreal lighting, AI-native direction, native
renderer performance, final original film masters) retain their own
independent native/visual acceptance; neither this roadmap nor passing
source metadata alone completes the entire USD-FILM family.
