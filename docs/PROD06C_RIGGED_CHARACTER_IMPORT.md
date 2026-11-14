# NVP-PROD-06C — Imported Skinned Characters and Explicit Bone Remapping

**Date:** 2026-11-02. **Scope:** NVP only; Lu remains frozen until v1.0. This is a conventional film-making production slice, not generative video or a character generator.

## Purpose

Our PROD-06B preview looked like a stick insect because it used **seven extruded geometric tubes** to prove Blender mesh skinning. PROD-06C replaces the displayed geometry with a **user-supplied rigged GLB character** while retaining director-approved frame timing, actor blocking and motion clips. The glTF file is imported by Blender after validating its checksum and the creator's explicit joint mapping; no LLM chooses transforms or runs untrusted Python.

## Delivered architecture

1. **Rigged GLB inspection**: bounded GLB 2.0 JSON+BIN chunks, single self-contained buffer, no remote image URIs, no required extensions, no embedded animations, one skin, typed POSITION/JOINTS_0/WEIGHTS_0, checked accessor count/bounds, valid named joints, ≤32 MiB / ≤128 joints / ≤250k skinned vertices. Strict first slice deliberately refuses sparse accessors, arbitrary extensions and multiple skins.
2. **Content-addressed asset registry**: stores source GLB under SHA-256 and a film-scoped `CHR_*` ID. Licenses/attribution/source recorded. Rights classification is **creator-declared**, not independently proven. No name collision overwrites another asset.
3. **Director binding layer**: maps seven NVP preview roles to explicitly selected unique source joints, records character scale, keeps optimistic revision and append-only plan history; approval receipt binds to the already-approved PROD-06B skin source SHA. An unapproved, stale, foreign-project or corrupt-source file cannot be exported.
4. **Portable Blender bundle**: manifest, source GLB(s), license report, deterministic generated build and audit scripts. The original approved shot sequence, root movement and motion clips remain unchanged; source animation is rejected. Blender imports the skinned mesh and mapped armature, keys target bones from the **already approved and calibrated** source preview, hides the previous seven-tube body, and preserves actor ID and timecode.
5. **Native acceptance**: a Blender-generated source GLB is exported and reimported through NVP; independent Blender process reopens the produced `.blend`, verifies actor/asset digests, armature/mesh modifier, all seven mapped bones and actual evaluated vertex displacement at two distinct motion frames. Linux also requires a Workbench PNG preview; hosted Windows audits geometry without pretending to provide a GPU render.
6. **Development UI + API**: upload from a local file, declare provenance and rights, select a project scene and approved actor, map seven roles with selectors, approve, and download a complete offline Blender bundle. No network asset search and no arbitrary Blender code endpoint.

## Critical limits

- **Not production retargeting**: Mapping bone names and transferring quaternion pose values works for compatible skeleton axes. It **does not** infer joint orientation conversion, T/A-pose offset, relative bone length, foot contacts, ground alignment, advanced nonuniform scale, or a realistic acting performance. Neutral rest poses and imported coordinates require human checking before footage can be considered production-ready.
- **Not a real human asset in the fixture**: The native CI source GLB is intentionally generated from PROD-06B's crude seven-tube humanoid to prove the import/deform pipeline. This says nothing about the quality or license of commercial character libraries.
- **No external URIs**; all GLB data must be packaged locally. Imported meshes/materials are untrusted and require OS-supervised Blender worker containment before production deployment. A JSON structural validator does not prove a mesh safe to render.
- **No Lu changes**; the Python/FastAPI/React architecture remains the isolated development harness.

## Local tests

```bash
PYTHONPATH=. python -m unittest tests.test_character_assets tests.test_character_api tests.test_character_native -v
python -m compileall -q backend tests tools
```

The native test skips only if Blender is not present; CI installs verified official Blender binaries and must run it. The full Python suite should also run on both OSs, and the React production build must pass on Linux and Windows.

## Next work: PROD-06D

Add **bone-axis/rest-pose calibration, stance and contact constraints, skeleton height normalization, pose residuals and a readable rig preview**. Do not claim generic high-quality retargeting until independent visual and metric acceptance on multiple licensed third-party characters (with different skeleton conventions). Then add performance cards and clip blending.
