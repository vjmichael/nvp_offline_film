# NVP SLATE-07 + CAM-01 — Skinned Characters and Virtual Camera Workbench

**Creator direction, November 6, 2026.** NVP's world, performances, and shot opinions remain immutable while present and intentionally deletable through the existing source-custody controls. The editorial timeline is a movable assembly of references to source intervals, not source-frame edits. Directors must be able to view genuine source acting and test virtual optical lenses **before** deciding to freeze a Take or approve a shot.

**Implementation state:** Native code, React components, tests and CI authored. Exact-head native Windows/Linux real OpenUSD and real Blender acceptance are OPEN. Installed NVP desktop host-to-UI wiring and interactive GPU-quality film viewport remain OPEN.

## 1. Actual skinned character geometry

The existing native `UsdSkel.Root`, `UsdSkel.Skeleton` and `UsdSkel.Animation` objects already represent a bounded joint hierarchy and joint-local translations. SLATE-07 extends a rig's typed source data with an optional **skin** descriptor containing a native authored `UsdGeom.Mesh`: bounded points, polygon topology, original joint index arrays, normalized per-vertex weights and preview displayColor.

The mesh is defined inside the **same immutable USD skeletal layer** under the original actor's `/Rig/CharacterMesh`. It uses actual `UsdSkel.BindingAPI`, a relationship to that actor's original skeleton and `jointIndices/jointWeights` vertex primvars. The source layer stays SHA-pinned by FilmIndex with its original animated Take.

When SLATE-06 renders a chosen source tick, it queries native `UsdSkel.Cache().GetSkelQuery().ComputeSkinningTransforms(tick)`, verifies the original binding and uses classic linear blend skinning to calculate a deformed vertex array. The resulting mesh points and faces are passed to the same first-party CPU Cycles Blender renderer, along with the actor's existing world transform and the director's shot-local OpenUSD override. Every tick is evaluated against the original source; no vertex positions are written back into the frozen Take or animation.

Initial skinning bounds: max 512 mesh vertices, 1,024 polygons, four influences per vertex, at most 32 joints per rig, existing rig/animation time-key quotas. Weights must be nonnegative, sum to 1, target valid joints, and have canonical typed source paths. A malformed or unsupported rig is **refused**, never represented as a mysterious human-shaped placeholder.

**Intentional limitations:** the current skeletal authoring has identity bind/rest transforms and translation-key animation. The new mesh is actual authored, weighted source geometry, but this does **not** yet support arbitrary imported DCC character meshes, general non-identity bind poses, joint rotations/scales, skin-normal/tangent recomputation, layered cloth, muscle dynamics, facial blend shapes, eyes, lips, tongue or audio-lipsync. A live posed-body proof is a real step toward acting, not a full photoreal human performance.

The editor's reusable branching pane also gains an **exact film-time pose scrubber**. Previewing several moments samples the same original Take at different ticks. This is not decoding an imported frame index or copying an animation track. It is a time-addressed performance read.

## 2. Why a virtual lens is not simply a filter

A camera model has distinct stages:

- **Geometric optics:** focal length, the filmback/sensor window, camera transform and position determine perspective projection and framing. Moving the camera changes perspective; switching to a long focal length at the same position primarily narrows the field of view.
- **Depth of field:** the f-stop and focus distance determine the blurred versus focused regions. Native USD `fStop/focusDistance` values are mapped to Blender Camera DOF. A smaller f-stop means a shallower depth of field when the rest of the optical system remains comparable.
- **Optical character:** distortion, vignetting, flare, breathing, anamorphic squeeze, bokeh shape and chromatic aberration are lens/optical effects that may require custom renderer/shaders, not merely a LUT.
- **Creative filters / color:** diffusion filters, color transforms, LUTs, grain and halation can be post-lens effects with their own versioned stack. A filter cannot generally recreate the original field of view or correct physically occluded background information.

CAM-01 introduces reusable spherical lens presets **18, 24, 35, 50, 85 and 135 mm**, with full-frame, Super35 and Micro Four Thirds sensor configurations. Director controls include custom spherical focal length, sensor width/height, f-stop and focus distance. The native scalar domain and FOV derivation are bounded and checked independently of browser values. Anamorphic imaging is **deferred** until the native renderer can implement actual squeeze and matching bokeh, rather than falsely calling a crop an optical anamorphic lens.

## 3. Preview BEFORE a Take

A native `VirtualCameraWorkbench.snapshot` opens **one authored scene revision** at one exact tick, evaluates the chosen actual native camera and its visible scene subjects into camera-space coordinates, then returns a bounded marker set. The React `CameraLensWorkbench` uses these camera-space markers to show an immediate approximate projected view. Once the snapshot is fetched, changing focal length, sensor/f-stop/focus cues is local and instantaneous; no whole film, 3D asset library or model runtime is loaded for every slider adjustment.

**This instant view is an educational real-time projection diagram, not actual rasterized pixels of the actor.** The quick blur cue is explicitly approximate.

A button **Render accurate optics still** requests a native higher-quality still when needed. It uses the very same SLATE-06 first-party Cycles script, BlenderWorkerSupervisor, TaskLedger, native approval/cancellation, OS containment and SHA-verified derivative cache—not an independent camera runtime. Only one selected source scene opens, optics are temporarily applied to its in-memory USD **session layer**, skinned geometry/camera/lights are evaluated, and an approved CPU Cycles PNG is produced. It never creates a Take and never writes lens changes into the original scene.

The native authorization identifies a scene revision SHA, chosen camera path, source tick, exact optical-settings SHA, bounded manifest, fixed script SHA, worker spec and resource limits. These pre-Take consents have a **separate durable record** from previously committed edit/Take previews. A scene+optics+time+camera+renderer cache key is computed before loading the scene, allowing repeated stills to reuse a verified derivative. Crash reconciliation, queue cancellation and memory limits reuse the existing native worker.

The workbench shows a completed image only if it matches the **current scene SHA, camera, tick and all lens settings**. Altering the lens immediately makes an old image ineligible to appear as the current one. A verified PNG can be delivered through trusted native IPC; the installed desktop adapter still needs integration.

## 4. Save preset versus Apply to shot

- **Try optics / scrub lens**: volatile, local, no approval and no source modification.
- **Save lens preset**: director approval writes an independent, immutable revisioned FilmIndex presentation object describing exact lens optics; it does not rewrite any scene or film.
- **Apply to shot**: only possible after a Take is frozen, and only if the target Take references **the exact same scene ID/revision/SHA** as the tested setup. Existing SHOT-01 director authority approves a stronger shot-specific OpenUSD opinion for `focalLength`, `fStop`, `focusDistance`, horizontal/vertical filmback. The shot interval, continuity choice and reason stay recorded. Underlying Take/performance/scene remains untouched.
- **Finished film master**: still requires separate creative/artistic and technical approvals; no preview permission grants final render authority.

The separate editor component exposes callbacks for native host approval/preset/shot actions. It cannot self-authorize or directly mutate FilmIndex.

## 5. Verification and scope

Native test fixtures author a real actor with weighted mesh, two-joint skeleton, time-varying joint animation and motion at the actor's root. Native OpenUSD tests prove a skin-bound source vertex changes at the expected tick *while its mesh and frozen world SHA remain identical*. A frozen Take screenshot recipe must contain the deformed source geometry with original actor transform, and facial/skinning flags must be true only for actual supported features.

CAM-01 tests exercise correct wide-versus-portrait field-of-view math, exact scene/camera source, temporary session-layer lens opinions, approved immutable presets, disallowed pre-Take shot application, source-matching shot commit, rejects of untrusted actor/joint source data and previews with no frozen Take. A separate Linux runner installs **real Blender** and must produce an independently verified CPU Cycles still containing the rigged actor with the selected lens/DOF. Windows/Linux Python 3.11/3.13 matrix tests and React/Vitest camera live-framing/stale-image/pose scrub regression accompany it.

**Pending:** green exact-head CI and an installed desktop demonstration with real skinned character geometry, native viewport render output, working host-to-React image conversion, measured responsive camera adjustment, director lens preset persistence, and advanced 3D character rig features.

**Governing invariant:** The performer, stage, camera, shot and scene are versioned original data. The timeline and optics workbench select and interpret those data. Rendered frames and cached previews are disposable, never replacements for the original frozen performance.
