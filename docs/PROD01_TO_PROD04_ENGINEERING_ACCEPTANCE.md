# NVP-PROD-01 → PROD-04 — Deterministic production engineering

**Date:** November 2, 2026  
**Scope:** NVP Film Workspace only. **Lu work deferred until Lu v1.0.**  
**Basis:** creator-supplied `film-world-model-toolchain.md` and earlier `claude-filmproduction(1).txt`, alongside the pre-existing NVP-PROD-01 source. This document records actual code and verification; proposed research integrations are not treated as implemented.

## What is authoritative

The **creator-approved screenplay**, **Story Bible**, **production assets**, **approved base staging**, and **world editing journal** form the authoritative production ledger. The published 3D scene is a *derived representation*. It cannot silently overwrite an approved screenplay, Story Bible entry, shot, or locked human value.

This is not yet a production-grade animator or fully interactive Blender viewport. The existing React development harness provides a staging interface and a new production-authoring preview; it is not a separate consumer app. The final NVP product remains a future Lu Film Workspace DLC.

## PROD-01 — native Blender acceptance

Already available: deterministic bounded grid backtracking; named anchors; an independently checked stage; immutable approved proxy manifest; Blender `bpy` script; simple GLB proxy export.

Added `backend/nvp_blender_acceptance.py` and `tools/nvp_prod_acceptance.py`:

1. Export the **approved** manifest and generated Blender script.
2. Probe an actual Blender executable and version. A missing binary returns **`blocked_no_blender`**, never fake success.
3. Use Blender in background mode to construct and save a `.blend` file.
4. Start a **second Blender process** to reopen it and audit the baked scene: source and layout SHA fingerprints, persistent instance IDs, pose/rotation values, named anchors, camera, and floor.
5. Run a genuine Blender Workbench preview and write `preview.png`. Any failure is explicit, with step and stderr. A missing render/audit also fails.

**Acceptance status here:** The toolchain, static parse, GLB geometry, and offline tests pass. **The full Blender native acceptance gate is blocked** because no Blender executable is installed in this host and an official portable binary download attempt failed. Neither `.blend` nor Blender-generated PNG has been produced on this host. Do **not** call this gate passed.

### Running on an actual Blender machine

Blender 5.2.3 LTS is a suitable target. The portable official builds are at:
- Linux: `https://download.blender.org/release/Blender5.2/blender-5.2.3-linux-x64.tar.xz`
- Windows: `https://download.blender.org/release/Blender5.2/blender-5.2.3-windows-x64.zip`

Once the Blender binary is present, from the NVP developer checkout:

```bash
python -m tools.nvp_prod_acceptance --db /path/to/film.sqlite3 \
  --project PROJECT_ID --scene SCENE_ID --out /path/to/output \
  --blender /path/to/blender

# For real GLB assets (PROD-03):
python -m tools.nvp_prod_acceptance --db /path/to/film.sqlite3 \
  --project PROJECT_ID --scene SCENE_ID --out /path/to/mesh_output \
  --blender /path/to/blender --meshpack
```

Expected genuine outputs: `scene.blend`, `preview.png`, `blender_audit.json` or `meshpack.blend`, `meshpack_preview.png`, `meshpack_audit.json`. The exit code is **0 only if the actual Blender subprocess and audit pass**; 2 means blocked, 1 means native failure.

## PROD-02 — WorldState, layered authorship and undo

New `backend/nvp_world_state.py` tables:

- `prod_world_sessions`: (project ID, scene ID, approved base layout SHA, approved plan revision, world revision, current typed property overlay).
- `prod_world_events`: append-only revision journal of before/after snapshots, intent and creator decision.
- `prod_world_proposals`: AI-authored proposals with captured world revision and explicit accept/reject outcomes.

Typed attribute schema for MVP: `pose.x`, `pose.y` (metres), `pose.rotation` (cardinal degrees), `visible` (boolean). Values contain unit, `author` (`human` or `accepted_ai`), `provenance`, `locked`, timestamp. **Human edits lock by default**; proposed AI edits do not affect the scene; a locked human field cannot be overwritten by an AI acceptance. Coordinate edits are independently validated against original wall and anchor relations, boundaries, and collisions before commit. Existing approved PROD-01 plans are not mutated.

Human undo is a new **journal entry**, not deletion. After a new approved stage, inherited edits become **stale** until the director runs explicit rebase; rebase proves all overrides still satisfy the new geometry. Missing instance references refuse rebase. Concurrent edits must supply the exact revision.

**Limits:** This is a scene-level property overlay, not full USD composition or Blender viewport hooks. Pinned edits have precise SQLite durability and export to a Blender script. Full script/scene/shot/panel attribute inheritance, live geometry nodes, multiuser conflict merging and in-viewport ghost overlays remain future work.

## PROD-03 — real immutable GLB assets and rights

New `backend/nvp_mesh_assets.py`:

- Accepts **self-contained GLB v2** only (no remote URI downloads, no archive extraction, no model-generated Python).
- Header/length checks and resource caps: **32 MiB per GLB**, <=128 meshes, <=200,000 faces. Bounds must be finite, positive, and within sane metric limits.
- Compares inspected mesh bounding-box dimensions to the immutable corresponding proxy asset ID (2% or 1.5 cm tolerance). A material geometry change must create a new asset identity.
- Content-addressed SHA-256 mesh storage with `fsync` and atomic rename, persisted under the local NVP project data directory. Existing geometry and its rights metadata are immutable.
- Creator-declared licenses from a bounded list: CC0, CC-BY, creator-owned, commercial licensed, evaluation-only. Attribution and source required for relevant external licenses. **A declared license is not independently verified legal clearance.**
- A portable package with `manifest.json`, `licenses.json`, `assets/*.glb`, and typed Blender mesh-import `build_scene.py`. Missing/corrupt source blobs stop export.
- Secondary real-Blender mesh audit verifies imported geometry bounds, root transforms, IDs, anchors, and rendered preview, but **has not run here**.

**Limits:** Runtime parser isolation still needs a supervised OS worker. The Blender import/export path is generator-tested and geometrically checked by `trimesh`, **not by actual Blender**. Skinned meshes, animation, UV/material fidelity, complex collision and imported model executability are not verified; heavy model imports should be contained. Asset licensing should be reviewed by the creator, not inferred from metadata.

## PROD-04 — actor blocking, dialogue and virtual cameras

New `backend/nvp_blocking_camera.py`:

- Stable dialogue IDs anchored in current screenplay lines; canonical cue-to-registered-actor matching with explicit unresolved speakers. **No invented listeners or speech timings.**
- Creator-assigned listener IDs, measured dialogue durations (with origin `director_measured` or `tts_measured`) and optional audio SHA-256. Estimates are not mislabeled as recordings.
- Actor blocking marks with scene-local XY targets, optional set-anchor relation, facing target, timestamps, action label and a **deterministic 0.25 m grid A*** path. Every node checks the actor's footprint against all staged static obstacles; temporal mark overlap is rejected. Subsequent paths begin at the previous mark rather than the original pose. Movement must satisfy the declared time interval under a conservative **2.5 m/s maximum**; `stand`/`turn` cannot teleport.
- Virtual camera proposals use metric XYZ positions, 18–135 mm focal length, sensor width/height, shot-size targets calculated from registered actor height, a pinhole projection model and screen-target refinement. Candidate viewpoints are bounded by room geometry; footprint occlusion and camera collision are rejected. One- and multi-subject solutions report **actual per-subject residuals**, maximum residual and if all targets fit in frame. An impossible exact composition is *not* silently reported as perfect.
- A 180° axis validator flags sign flips across cuts (including ambiguous cameras on the line).
- Marks and camera solutions are persistent and tied to a world-state SHA; changed staging makes them stale, never automatically authoritative.

**Limits:** Previsualization uses static proxy geometry; no actual skeletal rigging, motion animation, dynamic actor collision, final camera raster verification, lip sync, sound mixing, transitions, or finished footage. Pinhole residual measures a read-point location, not visible full-body framing. These remain separate acceptance gates.

## API and UI

Added project-scoped HTTP endpoints for world edits, locks, proposals, undo, rebase, mesh upload, dialogue timing and listeners, blocking and cameras. Binary mesh upload is streamed and enforces the byte limit even if the client omits Content-Length.

`frontend/src/ProductionAuthoringPanel.jsx` provides creator controls with a top-down preview and candid status labels. It is imported into the NVP development app's **Direct the scene** tab. Its JSX passed a TypeScript JSX parser check; the complete Vite production bundle and physical interaction tests have **not** yet run.

## Verification procedure

From project root:

```bash
PYTHONPATH=. python -m compileall -q backend tests
PYTHONPATH=. python -m unittest discover -s tests -q
```

The complete suite includes all 200 prior PROD-01/WR tests plus targeted new tests for native harness refusal, world edits, mesh import, asset provenance, actor routes, camera residuals, API behavior, and cross-module restart/continuity scenarios. **Local result: 264 Python tests, all successful except one intentionally skipped native-Blender test**; 263 executed tests passed. A skipped gate is not a pass. A frozen 15-case single-subject metric-space conformance set has ≤ 0.015 normalized-frame-point error, and three harder two-subject cases report their actual errors rather than silently claiming exact framing. Neither benchmark is equivalent to Blender pixel-level validation.

**Acceptance sequence required for production release:**

1. Run both proxy and meshpack Blender subprocess tests on official Blender 5.2.3 LTS; inspect `audit.json`, `.blend`, preview PNG.
2. Verify imported real mesh materials, units, rigs and anchors against the authoring tools in an interactive Blender session.
3. Build React/Vite and test UI interactions and state reconciliation on Windows.
4. Evaluate multi-shot/actor paths with actual scene fixtures and dynamic geometry; record 180° and framing deviations.
5. Establish a frozen 30-second dialogue scene with audio, camera coverage, storyboard and editing timeline (not delivered by PROD-04).

### Why the design follows Claude's conventional toolchain

The creator-supplied plan suggests *typed scene state plus independent deterministic geometry*; this implementation adopts that boundary. Model output never supplies raw coordinates to an executable Python evaluator or unrestricted `bpy` interface. Model creativity is expressed as data proposals; the software validates before commit. The source recommendations of Holodeck, Infinigen Indoors, PACE and StateFlow remain architectural references, not imported dependencies or claimed matching benchmark results.
