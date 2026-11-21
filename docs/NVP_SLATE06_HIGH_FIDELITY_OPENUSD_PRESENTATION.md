# NVP SLATE-06 — Higher-Fidelity OpenUSD Presentation

**Creator directive (November 6, 2026):** Produce a more faithful view of source-data-native NVP films without converting the editor into a frame editor. The frozen Take, source scene, shot override and authored Film Time remain the only source of truth. A preview is a disposable, independently verified derivative.

**Status:** Implementation and acceptance tests authored. Exact-head native CI and installed Windows UI acceptance remain open.

## Actual authored-source rendering

On a committed cut, SLATE-05 already resolves the exact source Take SHA, SHOT-01 override SHA, segment, and original source tick. SLATE-06 adds a separate **authored-geometry** profile on the same native preview host. A deterministic high-fidelity cache key includes Take/SHOT SHA, source tick, quality, chosen native camera and renderer script version. Cache lookups happen **before opening OpenUSD**, allowing the same source fragment reused elsewhere to share a verified PNG.

On a miss, the renderer opens **one** SHA-pinned composed OpenUSD stage, with the director's shot-local overrides applied. It evaluates real native UsdGeom.Cube, UsdGeom.Sphere and bounded UsdGeom.Mesh geometry, including original sizes, exact world matrices and visibility. It samples the chosen UsdGeom.Camera transform/focal length/aperture and native UsdLux.SphereLight properties at that same tick. New NVP-native scenes now author an explicit Z-up axis, and native cameras have meter-aware defaults of 50 mm focal length, 36 mm horizontal and 20.25 mm vertical filmback, and a 5 m focus distance. Old frozen source layers remain unchanged and retain their original camera/up-axis metadata. Mesh polygons are independently validated and triangulated, not replaced with generic stand-ins.

Authoring limits: at most 48 visible geometry objects; 1,200 points and 2,500 triangles per mesh; 128 KiB total sealed source manifest; preview dimensions 320×180, 640×360 or 960×540; finite source transforms and intensity bounds. Unsupported geometry or absence of real authored source geometry fails closed.

The fixed, first-party Blender script renders a new PNG through CPU Cycles. It reconstructs actual source geometry, converts row-vector Gf matrices to Blender's column-vector convention, and converts the temporary preview's native Y-up scene to Blender Z-up if necessary. It never opens arbitrary USD files or source paths from a model or browser.

## Important rendering limitations

This is materially higher-fidelity than the SLATE-05 geometric blocking proxy, **not** the final complete film renderer.

NVP's current immutable reusable asset authoring produces native USD cubes and spheres. Mesh extraction can handle bounded Mesh data already authored in the selected composed scene; it does not create an unrestricted third-party USD/texture importer. Actors without an authored mesh are recorded as unmeshed and cannot be portrayed as fully rendered. Skeleton data currently lacks skinning bindings, facial deformation and speech articulation; those capabilities remain explicitly unrendered.

The preview uses simple USD displayColor, not complete UsdShade networks and texture/PBR fidelity. Sphere lights are represented as native Blender lights with **approximate**, not physically identical, photometry. The actual USD camera position, orientation, lens and source time are preserved, but full photographic color, depth-of-field, lens distortion, volumetrics and postproduction remain separate.

Source missing a native camera, selected camera hidden or absent, invalid lens, unsupported projection, no authored mesh, excessive topology, or other unsupported source data is rejected rather than silently substituted with a low-fidelity proxy. The user can request SLATE-05 blocking separately.

## Existing worker, cache and authorizations

Both profiles now share one NativeSlatePreviewHost, ApprovedBlenderDispatcher, TaskLedger, BlenderWorkerSupervisor, OS containment, resource budget and SlatePreviewCache.

A per-preview creator authorization binds exact editor revision, source Take/SHOT, camera, source tick, resource budget, sealed manifest and renderer script SHAs. Geometry and blocking previews have different cache keys and distinct authority/presentation receipts. The consent SQLite schema is migrated safely for earlier SLATE-05 installations. Only a contained, independently audited Blender result may become a cache READY image; partial/cancelled/stale files cannot be promoted into a film preview.

The existing disk cache's LRU policy evicts **only derived PNGs**, never original Take or asset bytes. Native IPC can fetch one independently verified, bounded PNG without opening arbitrary file paths. That accessor also rechecks the sealed source manifest and returns the authoritative edit SHA, segment ID, source tick, chosen camera, and explicit unmeshed-actor/rig limits for the React pane, avoiding a second OpenUSD stage load.

A metadata-only native camera lookup returns FilmIndex camera IDs for the selected Take without loading the USD stage. The reusable React timeline pane has a separate Render Authored 3D Preview action, source-camera selector, committed-edit gating, and labels for incomplete geometry/rig coverage. Full installed desktop wiring remains open.

## CI and acceptance scope

Native tests create a real frozen USD scene with reuse-bound cube/sphere sources, animated actor translation, camera focal-length channels, light intensity and a director-approved SHOT-01 translation/lens/light change. They assert exact composed geometry, shot-local transforms, native source camera selection, original Take hash preservation, malformed Mesh rejection, no silent fallback, separate cache identities, native approval refusal, resource queue binding, cancellation, cache reuse without reopening OpenUSD and accurate preview provenance.

The Linux real Blender runner installs an actual native binary and runs CPU Cycles under the existing contained supervisor with measured RAM admission and independently verified PNG publication. A separate Windows/Linux Python3.11/3.13 matrix verifies OpenUSD composition, data/authorization integrity and legacy SLATE-05 regressions. React tests verify the camera selector, explicit render action and truthful incomplete-actor labels.

Tests with synthetic PNGs only validate cache mechanisms, not native render quality. CI must pass on the exact final head commit before acceptance can be claimed.

## Follow-on work

The next production gaps are bounded trusted mesh authoring/import, native UsdSkel mesh bindings and correct skinning, facial animation, realistic materials and renderer-matching USD lighting, background preview scheduling/cancellation, host-to-frontend PNG IPC, native detachable Windows editing pane, audio continuity, and creator-approved final presentation render.

**Design invariant:** Source film data remain immutable while present and only deliberately deletable through custody guards. The timeline is a reversible assembly of references; high-quality render outputs and their caches are disposable artifacts.
