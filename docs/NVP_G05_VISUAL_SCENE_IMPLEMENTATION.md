# G05 — Visual Scene Builder (implementation handoff)

**Development direction:** Build NVP as a filmmaker's application. Source implementation is present on `nvp/g05-visual-scene-authoring-20261111`, stacked on G04. This is **not** a claim of exact-head compiler, UI, native-device or installed-app acceptance; batch verification remains deferred by the creator until the full NVP application is built.

## Filmmaker's workflow

**Script (optional) → Set Up Scenes → Film Scenes → Edit Film → Export Film.**

The G04 Scene Library now contains the G05 Visual Scene Builder in the existing **Set Up Scenes** step rather than another technical application panel. The director chooses **Create Visual Scene**, sees a true Three.js interactive scene backed by NVP-authored OpenUSD, selects any object, drags it, rotates, resizes, changes color, adds procedural assets, chooses weather/daylight and gives scene/wardrobe notes. A right-click on a performer provides **Give a note**, **Change Wardrobe** and **Inspect Character**. Changes are saved as new stage versions; earlier creative decisions can be restored. **Approve Scene** creates a separate reviewed revision. It never starts filming or freezes a Take.

Scenes may have no actors and no dialogue. A creator's script scene has a source identity, stable ActorIDs for known performers, sourced dialogue references and director-approved props. An idea-only movie starts with one scene. Example starting environments include kitchens, other interiors, mountain valleys, forest, coast, desert, urban streets, farms, orbital/space and abstract worlds. These are **unapproved procedural starting layouts**, not model-proven story facts.

The native procedural preset library includes objects, trees, mountains, rocks, roads, buildings, furnishings, water, cameras, sunlight and placeable lamps. No external downloads, remote textures or arbitrary USD asset references are accepted. An unavailable 3D GPU context yields a truthful fallback while saved source remains intact. No screenshot is used as a substitute for 3D world data.

The director can **Ask AI to help arrange this scene**. The selected existing loopback local model receives host-prepared creative context, permitted preset vocabulary and current object positions. Its output is a bounded review proposal; invalid identities, model receipts, filesystem paths, unexpected object types or unauthorized characters are rejected. Individual ideas enter the stage only after explicit director approval. Without a resident model, manual scene building remains available.

If G04 source changes, the stage becomes **Needs updating**. The director can **Keep My Arrangement** (rebuild OpenUSD while keeping compatible placement, retaining only newly valid ActorIDs, and adding newly approved props) or **Build Fresh Scene**. Both preserve previous versions; no silent overwrite.

## Engineering implementation (internal only)

- `backend/nvp_g05_scene_authoring.py`: `G05SceneAuthoring` binds source/ActorIDs from `G04Preproduction`, owns a bounded typed StagePlan, authored native OpenUSD via `pxr.UsdGeom`, `UsdLux` and `UsdShade`, source provenance, reopening and source identity validation. Camera and light are actual USD schemas; actor placeholders carry exactly reviewed ActorIDs. USD material color is native `UsdPreviewSurface`, with no external payload/reference.
- Scene heads, immutable versioned plan JSON and **actual USD layer bytes** live in the project SQLite database. Protected movies use the existing in-memory DPAPI/AES-GCM sealed G03 database rather than new plaintext film files. Source hashes, notes revisions, actor IDs, cast/dialogue references, typed objects, original line ranges and approved props remain bound.
- `backend/nvp_api.py` exposes stage read/generate/edit/reconcile/restore/approve and AI object idea review for both ordinary and protected director sessions. The existing G03 lock middleware allows only `live/stage/` for encrypted movies. No new renderer, worker or frozen-Take authority is introduced.
- `frontend/src/DirectorWorldStage.jsx` + `.css` provide the Three.js Z-up live viewport and creative editor; `frontend/src/DirectorSceneLibrary.jsx` connects it into Film Home.
- `G05SceneAuthoring.native_stage(project_id,scene_id)` is the internal source handoff for G06. It refuses anything other than an exact-current director-approved stage, returns original reopened USD bytes plus exact provenance, and explicitly returns `filming_authorized=False`. G06 must separately authorize filmmaking operations.

## Constraints and remaining integration

1. **No external mesh/texture import or relink is implemented here.** Preset geometry is self-contained and offline; richer asset imports, skeletal performers, advanced MaterialX/Hydra parity and final film quality belong to later production/quality work.
2. The stage viewport is a native-data 3D authoring presentation, not a photorealistic Cycles rendering or an approved frozen performance. Weather effects in the viewport are visual guides, not filmed scene motion. Voice, rigging, spatial audio and immutable Takes are G06 work.
3. Native Windows device acceptance, real loaded-GGUF model output, regressions and installed acceptance remain **unexecuted/deferred by creator policy**; no pass/fail claim is made from source code.
4. G03's protected worker completion and historical-film migration, and G02's Lu integration, remain separate backlog items. No canonical PR merge or full-app release is authorized.

**Next build group:** G06 Film Scenes — select an approved G05 stage, direct performers and/or environmental events, author source-time performance, capture native original spatial PCM where applicable, and freeze immutable Digital Takes with approval/recovery. Continue build-first; defer combined verification until NVP is functionally complete.
