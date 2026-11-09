# CAM-FX-01/02/03 foundation — director-editable virtual rails and stronger native USD layers

**Date:** 2026-11-09.
**Status:** implementation and regression acceptance contracts **AUTHORED**, **not native-accepted**. The prior 02M-H OS/Cycles group remains queued at [#42671262108](https://github.com/vjmichael/nvp_offline_film/actions/runs/42671262108), SHA `101b4fbf31b72687362571b10e9c12702613ca0f`. F/G/H [#42650335958](https://github.com/vjmichael/nvp_offline_film/actions/runs/42650335958) and P0-F-01 [#42664870777](https://github.com/vjmichael/nvp_offline_film/actions/runs/42664870777) also remained queued at latest inspection. These are scheduling blockers, **not demonstrated USD/Cycles failures**.

## CAM-FX-01 — canonical original film-time camera rails [source implemented]

First-party module `backend/nvp_cam_fx01_camera_rails.py`:

- A typed rail pins exactly one original `FilmIndex` project, immutable 01M camera-bank ID/revision/SHA, camera identity, frozen 01E actor world Take SHA, original performance SHA and a bounded original Film Time interval. The clock is `7,056,000,000` integer ticks per second. A rail is *camera data*, not a physical rail mesh, an actor performance or an independent clip clock.
- Native segment control nodes comprise exact tick, 3D position/target in metres, optional rail world origin/rebase, incoming/outgoing tangents in metres/second, hold/linear/Hermite movement, smoothstep/linear easing, camera roll, focal length, focus distance and f-stop. Native interpolation evaluates any permitted original Film Time integer tick, independent of final output FPS.
- The host refuses invalid/nonfinite positions, nonmonotonic ticks, camera=target, unapproved camera IDs, >48 control points, >90s source shot, >250 m/s velocity, >1,400 m/s² vector acceleration, unbounded cubic overshoot, held-camera teleportation, unrecognized technique and out-of-range optics. All source metadata is recomputed before authoring a native layer. Orientation is right-handed, Z-up, USD camera looking along local -Z with an explicit stable near-vertical fallback.
- Rails are separate immutable `presentation` revisions, depending on exact source 01M camera-bank revision and single-commit original 01E world Take. A director may revise an approved rail by publishing a *new* revision after exact fresh OS approval; prior layer blobs and source Takes remain available. Optimistic revision and SHA preview guards reject stale browser/model actions.

## CAM-FX-02 — stronger actual OpenUSD director camera layers [source implemented]

First-party module `backend/nvp_cam_fx02_usd_camera_layer.py`:

- Authors a separate actual `UsdGeom.Camera` at `/World/NVPDirectorRails/<rail_id>` within a native `Sdf.Layer`, with metered Z-up coordinates, `timeCodesPerSecond=7056000000`, matrix transforms, physical filmback conversion, focus/f-stop/focal-length USD attributes sampled at derived 24fps output points **plus** exact keyed original Film Time nodes and midpoints. A sampled presentation frame is not authority for the underlying 01E performance.
- The authored layer is independently reopened from its own USD file bytes in a new native stage and compared against host-authored exact pose/orientation/optics. Its immutable bytes are SHA-addressed inside the existing project `FilmIndex` blob store, with exact rail publication dependencies; no custom filesystem editor, alternate renderer or script execution path.
- `open_approved_camera_layer` temporarily composes that distinct **stronger director layer** inside the original first-party OpenUSD world session only after validating the approved rail, blob hash, bank, original Take and 01D shot SHA. It refuses namespace collision, checks the original camera transforms, actor poses, original `/World` prim type, and source world root bytes before and after composition, then removes only its temporary sublayer opinion. It never rewrites an original actor's Usd prim, authoritative camera bank, PCM or frozen Take.
- This module does **not** implement physical tracks or collisions. Director-controlled clearance, ray occlusion and intentionally through-wall camera passage require the later CAM-FX-05 source/native geometry ray tests.

## CAM-FX-03 initial installed control surface [source implemented, no native OS acceptance]

The existing trusted `OriginalDistrictDesktopMixin` and `TrustedDesktopWO5Bridge` (same NSIS-installed NVP app) now expose exactly scoped `camfx01_catalog`, `camfx01_preview`, `camfx02_publish`, `camfx02_reopen`, `camfx02_sample` methods. Catalog includes older exact 01M bank revisions, ensuring old rail history never silently rebinds to a newer camera source. Publication requires a **new, one-use, operation-specific native Windows dialog** with exact original actor Take, bank, original Film Time interval, proposed rail and stronger USD layer SHA. Model text cannot authorize any worker/source action.

`frontend/src/CameraRailsDirector.jsx` is mounted inside the existing `ModularWorldDirector`, not a new mini-app. It presents original bank/camera selection, saved rail version, typed technique starting presets and an editable finite sequence of controls: X/Y/Z position and look target, tangent handles, exact tick, easing and hold, roll/focal/focus/f-stop, filmback/origin. Creator can insert, move, retime, remove and locally undo handles, preview the source SHA, publish a new immutable layer with a separate OS confirmation, reopen exact previous revisions and scrub actual source-time camera pose without starting Blender.

Current typed **starting presets**, not verified final cinematography: stationary, dolly, truck, crane, arc/orbit, pan/tilt, rack focus, dolly zoom, over-shoulder, POV/reaction, establishing, reveal, Dutch, custom/compound and others. These are editable numeric starting trajectories, **not** an assertion that an AI framed the intended ActorID subject, that the lens effect is correct under Cycles, or that advanced whip/handheld/focus tracking already has human-approved cinematic quality. The UI is not yet a drag-and-drop 3D path gizmo.

### Exact Film Time vs derived USD presentation samples

The host rail evaluates deterministic Hermite at any integer original Film Time tick. The stronger OpenUSD layer explicitly **authors 24fps derived presentation ticks, handle ticks and segment midpoints**; regular USD interpolation between those authored samples is not a native cubic-Hermite guarantee. `camfx02_sample` therefore returns mutually exclusive `native_layer_sample_authored_and_read_back` and `host_exact_film_time_interpolated` flags; the installed director reports which kind of camera position is being shown. No claim that an off-grid host-computed value was explicitly authored in USD is permitted. Motion blur/subframe path parity, timebase conversion and independent Cycles verification remain CAM-FX-05 acceptance rather than a claimed result of the source layer.

## Tests and acceptance, segregated from implementation

- Native regression `tests/test_nvp_cam_fx01_02_native_rails.py` builds a **real first-party 01E/01M actor/PCM/Town scene** and real USD layer; checks exact Hermite/time/optics, approved/denied/stale/changed rail revisions, source SHA immutability, independently reopened source USD, original 01D camera/ActorID matrices, and invalid/nonfinite control rejection. These tests are authored, not passed on native runners.
- React DOM `frontend/src/CameraRailsDirector.test.jsx` checks handle edit/insert/delete/undo and preview invalidation, typed source bank discovery, one-use OS grant contract, failed spoofed receipt, source camera pose and browser-only UI refusal. Mocks are UI-contract evidence only.
- Actual NSIS-installed WebView2 `tools/nvp_desktop_alpha.py --smoke-window` now can verify `NVP_CAMFX_GROUP_ACCEPTANCE=1`: exact trusted camera-rail native IPC and UI controls, without mistakenly claiming a camera was physically dragged or that an original film picture was rendered.
- **Single staged manual-only end-of-group workflow** `.github/workflows/nvp-camfx01-03-original-rails-native-group.yml` covers real Windows/Linux Python 3.11/3.13 `usd-core==26.11`, React/Vite DOM, actual frozen Windows PyInstaller/NSIS/WebView2 and original filmmaker-project preservation. **Do not dispatch for every edit or while earlier 02M-H has no native results.**
- No real native Windows/Linux failure logs exist for this new CAM-FX task yet. No 02M-HR native failure can be labeled repaired without its own actual job output. A passing source-only test does not prove a native Cycles frame, DCP or 30-second film.

## Still open — ordered work

1. **02M-H native closeout:** collect actual completed Windows/Linux/Cycles/NSIS job logs for #42671262108; fix demonstrated defects as a bounded batch, rerun only one group-end consolidated gate, inspect actual rendered pixels and independent Blender reopen before claiming 02M-H accepted.
2. **CAM-FX-01/02 acceptance:** execute the staged grouped native USD/installed workflow after queue capacity is available. Resolve any USD 26.11 Python binding differences, world-session composition, actor/camera source readback, Windows GUI and optimizer issues reported by that exact-head run.
3. **CAM-FX-03 remaining:** interactive 3D path gizmos, tangent handles in screen/world coordinates, real actor framing guides, safe areas, source scene ray/occlusion warnings and durable draft undo/redo/recovery after app restart (today's numeric undo is local).
4. **CAM-FX-04:** host-bounded AI proposal of typed techniques from independently verified original scene context; director may change or reject every value; approve only after revalidation and OS-native one-use authorization. No arbitrary model-written USD or OS controls.
5. **CAM-FX-05 and 01Q/01S/01T:** actual separate render/camera rail worker integration, real Cycles pixels for moving dolly/crane/orbit/OTS/rack focus/dolly zoom, focus/DOF/motion blur and occlusion comparison over **unchanged original actor/PCM Take**, then selected-view 30-second picture/audio film.

**Do not interpret a persisted rail revision, native USD stage or camera technique label as human film-quality approval.**
