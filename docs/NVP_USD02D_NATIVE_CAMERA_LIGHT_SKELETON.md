# NVP USD-02D — Native OpenUSD camera, light, and skeletal animation schemas

**Product rule:** NVP is a data-first filmmaking system capable of generating multiple visual presentations from the same frozen film performance. A scene contains **persistent objects and their timed state**, and camera shots are observations of that world. No duplication of the scene for each shot.

**Status (2026-11-05):** Native code, exact-source freeze integration, regression tests, and 4-cell Windows/Linux CI committed. Native acceptance, full rigged deformation, renderer integration, installed app packaging, and licensing audit remain OPEN.

## Native scene types

The previous USD-02C channels were custom scalar metadata attached to ordinary USD Xforms. USD-02D adds an **explicit opt-in** `OpenUSDSceneBridge.publish(...,native_schemas=True)` that authors real `UsdGeom.Camera` and `UsdLux.SphereLight` prim types. Earlier USD-01 / USD-02 scenes continue to use original two- or three-layer layout with no forced reinterpretation.

NVP stores the same typed source `camera.focal_length_mm`, `camera.focus_distance_m`, `light.intensity`, and `light.temperature_kelvin` controls, but authors corresponding real USD schema attributes in the stronger parameter layer. Reopening the scene checks native schema identities, time sample values, and authored control/schema parity at exact film times.

**Units:** NVP's new native-schema scenes set `metersPerUnit = 1.0`. USD focalLength uses *tenths of a scene unit*, so an authored focal length of 35 mm is stored as USD native focalLength `0.35` for 1-meter scene units. Focus distance remains in scene units (meters). We must preserve this conversion in all import/export boundaries. Earlier generic Xform-only stages are not silently assigned this unit policy.

**Native camera movement:** A stronger motion layer emits standard `xformOp:translate` and `xformOpOrder` as **untyped over opinions**. It does not redefine a `UsdGeom.Camera` into a generic Xform, ensuring camera optics remain visible to downstream native renderers.

**No overclaim:** These are actual OpenUSD camera and light schemas and their authored inputs, not a full optical lens, tone mapper, or physically verified rendered-lighting test. A different renderer can interpret light transport/units differently. Perceived exposure and color still require image-level acceptance.

## Bounded UsdSkel hierarchy

`backend/nvp_openusd_skeleton.py` creates actual `UsdSkel.Root`, `UsdSkel.Skeleton` and `UsdSkel.Animation` prims under declared actor scene paths, with native topology validation, immutable joint ordering, rest and bind transforms, and an explicit `UsdSkel.BindingAPI` animation-source relationship.

The first authoring contract is deliberately small: at most 8 actor rigs per USD scene, 32 ordered joints/rig, 256 exact-tick key times, and full per-joint local **translation** matrices. The native USD `Animation.SetTransforms` API converts those orthogonal transforms into standard animation channels. `UsdSkel.Cache.GetSkelQuery` and `ComputeJointSkelTransforms` evaluate the composed hierarchy at requested NVP timeline ticks. NVP does not bake video frames or invent a custom interpolation algorithm.

Native skeleton composition has its own strongest USD layer only when a scene declares skeletal rigs. The layer is SHA-256-addressed and project-scoped inside FilmIndex, and the manifest stores rig paths, joint names, sample counts and layer SHA. Scene open validates that each pinned skeleton and its animation are still evaluable.

**Not implemented:** skinned/deforming meshes, bone orientations and articulated rotations, IK/foot contacts, retargeting, fingers, facial blendshapes, tongues, lips, hair/cloth, performance physics and digital human appearance evaluation. The first rig establishes a real native interchange and time-evaluation path. Further asset/rig work must preserve character identity and filmmaker approvals.

## Frozen data-first Digital Takes

`nvp_openusd_time_state.py` returns native camera optics, native light inputs and evaluated skeletal poses alongside the older USD world matrices and semantic actions. `nvp_openusd_take.py` freezes the exact native schema tag, skeleton layer SHA, joint topology manifest, per-checkpoint native attributes and evaluated poses together with already-pinned scene/temporal FilmIndex revisions.

Full `verify_take()` deliberately recomputes those checkpoints and checks SHA agreement. An ordinary presentation window does **not** rerun a full feature-length manifest audit. `nvp_openusd_presentation.py` samples the frozen take at the presentation's own output cadence; two differently styled outputs can share source state and take SHA while their raster images will eventually differ. **No raster frames are generated in this milestone.**

## Native test gate and source ownership

`tests/test_nvp_openusd_native_schemas.py` exercises native OpenUSD Camera, SphereLight and Skeleton types, USD unit conversion, timed camera movement that preserves the Camera type, mid-time light/camera values, evaluated parent/child joint motion, reopen-from-SQLite equivalence, exact frozen-take SHA evidence, two style/output-rate plans, a later revised camera scene preserving the old frozen take, and invalid topology/scope refusal.

`.github/workflows/nvp-usd02d-native.yml` runs actual `usd-core==26.11` on Windows 2025 and Ubuntu 24.04 with Python 3.11/3.13, plus regressions for USD-01, USD-02 and USD-02C. No mocked `pxr` implementation qualifies. Do not claim pass until exact-head green logs exist.

The scene authoring contracts deliberately reject arbitrary filesystem USD imports and unchecked external references. Under TOST 1.0, NVP must preserve OpenUSD's license/attribution and audit exact packaged native dependencies; sample models have separate asset licenses. FFmpeg and unrelated media tool license gates are separate.

## Next work after native acceptance

1. Fix any exact-head native API/runtime failures in this PR.
2. Add skinnable USD mesh source assets with native joint weights and blendshape bindings, then verify real mesh vertices respond consistently at authored time.
3. Connect camera lens and light schema samples to a supervised native Hydra/Blender low-fidelity renderer and produce two *actual* pictures from one unchanged frozen Digital Take.
4. Validate skinning/retargeting/contact and audio sync on meaningful actor motions over longer captures.
5. Integrate the scene tree, camera selection, performance curves, and director approval UI into the installed Windows desktop application.

**Governing rule:** keep the film in source data; use scenes and events to evaluate time; render a selected presentation only at the chosen output boundary.
