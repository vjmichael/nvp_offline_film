# NVP-PROD-01 — Screenplay → deterministic 3D scene proxy

**Date:** 2026-11-02. **Development-only:** NVP Film Workspace; all Lu development is deferred until Lu v1.0.

## Basis and design

The creator-provided *claude-filmproduction(1).txt* recommends not asking the
LLM to calculate geometry. Instead the LLM proposes structured film forms
and conventional tools (Blender, OR-Tools, trimesh, named spatial anchors,
asset libraries) execute deterministic set construction. This milestone
implements the smallest *working* slice of that contract without downloading
assets or relying on an AI model. It **does not implement** the proposed
Holodeck/Infinigen room dressing, OR-Tools optimization, character rigging,
set-asset search, Blender physics or photorealistic rendering.

## Delivered

- `backend/nvp_production_scene.py`: a local SQLite production asset registry.
  Each asset receives an immutable, project-scoped `AS_<UUID>` ID with
  creator-provided name, category, proxy size, named anchors, and provenance.
  Source kind is **procedural_proxy only**, not a secretly imported external mesh.
  A changed asset geometry requires a **new asset ID**, so existing stage plans
  and footage references do not silently mutate.
- Structured scene plans reference the existing screenplay scene `SC_*` ID,
  a scene-text SHA-256 hash, screenplay revision, explicit room XYZ dimensions
  (metres), and a list of named `instance_id` → `asset_id` placements.
  Scene cues from the conservative Fountain parser match only registered
  character assets with exact case-insensitive names. **Unresolved cast is
  reported**, never hallucinated as new meshes or a trustworthy identity.
- An instance may declare `wall = north|south|east|west`, or an explicit
  `attachment` with `target_instance`, `target_anchor`, `self_anchor`, and
  `max_gap` (metres). Anchors are local XYZ points on the asset's proxy; only
  XY-distance constraints are solved. Attachments are topologically sorted;
  nonexistent anchors and cyclic dependencies are rejected.
- Deterministic **bounded backtracking** solver, using a 0.5-metre base grid
  plus exact wall/anchor candidate seeds, enumerates four cardinal rotations.
  A separate `verify_layout` performs room-boundary, geometry-height,
  clearance/collision, wall and anchor checks. Search budgets are finite and
  exhaustion is reported explicitly rather than returning a bad layout.
  No OR-Tools installed/required for this baseline; a CP-SAT adapter remains
  a later optimization option, not an unverified claim.
- Revisioned *proposed* layouts and archived predecessor plans. A director
  must explicitly approve a fully verified proposal before export. An
  approved plan cannot be edited in place; explicit resynchronization archives
  it, preserves its asset choices, and invalidates geometry and approval.
- Screening for stale screenplay source and concurrent edits before geometry
  is committed. The bounded solver runs outside an SQLite write lock, then
  revalidates source and plan revision under the write transaction.
- Deterministic JSON **scene manifest** with stable IDs, dimensions, proxy
  positions, rotations, license declarations, and SHA-256 layout digest.
  Approved source, room, asset definitions and placements are checked against
  the digest again before export. Corrupted layouts are refused.
- Self-contained Blender `bpy` Python script with primitive proxy geometry,
  an establishing camera, one area light, floor/room guides, and visible named
  anchor empties. Values are embedded as inert JSON string data—no generated
  Python from actor names, network, model loader, shell command or automatic
  external mesh importer. Use a **Blender-equipped machine** to create `.blend`.
- NVP's local FastAPI staging endpoints and creator-facing `SceneStagePanel.jsx`
  with a top-down proxy scene preview, asset registry, room definition,
  optional anchor relation, solve/approve, and export controls.

## API (development harness only)

All endpoints are project-scoped:

- `GET/POST /api/projects/{project_id}/production/assets`
- `POST /api/projects/{project_id}/production/scenes/{scene_id}/stage`
- `GET /api/projects/{project_id}/production/scenes/{scene_id}`
- `POST .../instances` (requires `expected_plan_revision`)
- `POST .../solve` (requires revision; optional `max_nodes`)
- `POST .../approve` (requires revision)
- `POST .../resync` (archives original and invalidates approval)
- `GET .../manifest`, `GET .../blender-script`, `GET .../history`

For the simplest example, register a 2×1×0.75-metre `furniture` asset, stage a
screenplay scene inside `[8, 6, 3]`, add a `table_1` instance with wall `north`,
solve, approve, then download the Blender script. Position and rotation choices
are reproducible for identical inputs.

### Running the exported script in Blender

On a Windows/Linux machine with Blender installed:

```sh
blender -b -P NVP_SCENE_script.py -- --output NVP_SCENE.blend
```

The script does not save `.blend` without `--output`. A headless Blender
installation was **not available** in the current development runtime; `bpy`
execution, Blender version compatibility, GPU rendering and physical Windows
UI acceptance remain **unverified gates**. The script itself is Python AST
parseable, independent of the Blender runtime.

## Measured acceptance

From the local development checkout:

```sh
PYTHONPATH=. python -m unittest discover -s tests -q
python -m compileall -q backend tests
```

**200 Python tests passed (170 prior + 30 PROD-01).** PROD-01 tests cover
asset persistence, exact cast linking/unresolved cues, anchor validity and
cycle detection, repeatable solve, non-overlap, floor and wall constraints,
unsatisfiable layouts, explicit budget exhaustion, corrupted plan rejection,
optimistic locking, concurrent screenplay edits, director-approval gating,
no screenplay/shot mutation, cross-project isolation, JSON and Blender script
export, and local API end-to-end flow. JSX syntax parsed with TypeScript;
full Vite/React production build is **not yet verified**.

## Deliberate limits / next production milestones

1. Static **axis-aligned proxy** footprints and four 90-degree rotations,
   not arbitrary angled convex meshes, occlusion, or articulated geometry.
2. No animation, inverse kinematics, actor blocking, facial performance,
   lighting continuity, licensed asset import, automatic scenery, audio,
   or final movie render. The `license` field records a creator declaration,
   not verified rights clearance.
3. Bounded scenes: maximum 18 stage instances and 16×16×8-metre room. The
   current grid solver is reproducible but does not optimize aesthetics or
   performance in large scenes. Search exhaustion is different from proof
   of mathematical infeasibility.
4. `parse_screenplay` currently identifies headings/cues but is **not** a
   full Fountain/FDX/PDF grammar. The creator must confirm cast, setting,
   assets and relations in the staging panel.
5. Next: procedural set templates and supported Blender execution/smoke
   fixture; then import licensed real meshes, mesh BVH collision, navigation
   paths, cameras and story-beat-driven actor blocking.

**Host boundary:** This is NVP film-specific code. No change to Lu, its DLC
runtime, models, transport or installer until Lu v1.0.
