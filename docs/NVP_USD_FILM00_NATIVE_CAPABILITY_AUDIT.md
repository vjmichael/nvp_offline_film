# USD-FILM-00 — real OpenUSD and Blender capability audit

**Status (2026-11-08): executable source probes, four-cell Windows/Linux CI and independent real-Blender roundtrip job committed; exact-head native results and artifacts OPEN.**

**Scope:** Build NVP's existing OpenUSD filmmaking infrastructure toward an editable, consistent, photorealistic virtual world. Do not create a new scene/physics/rendering engine or add digital-twin, geographic reconstruction, VR game, scientific platform or legal-permission systems without a distinct creator decision.

## Capability levels, not marketing claims

The new tools/nvp_usd_film00_probe.py imports the real pinned usd-core 26.11 native pxr extension and creates/reads genuine USD stages and layers. It records the exact runtime version, Python/OS, reported CI SHA, source probe SHA and per-feature time. The report exposes PASS, NOT_AVAILABLE or FAIL for each attempt. A normal API import is not successful scene execution. The following probes exercise actual native USD operations:

| Feature | Actual native operation | What this does NOT prove |
| --- | --- | --- |
| Geometry, camera and light | Author mesh points/faces, meter scale, Z-up, camera focal length, SphereLight intensity; save and reopen | Photographic pixels, lens/shader parity |
| Layer composition | Compose a strong override over an unmodified weak source; evaluate the composed value | NVP scene/asset source resolver |
| References and payloads | Reuse an authored source USD asset, open a Stage with payload unloaded, load it, then re-read the original sphere radius | NVP-authorized multi-shot payload scheduling |
| Variants | Save two real opinions, reopen, select and evaluate both | Director-facing variant UX or complex scene revisions |
| Point instancer | Author shared prototype and three positions/indices, save/reopen | Large-scale crowd rendering, per-actor uniqueness |
| Skeleton and blendshape weight | Author real UsdSkel joints and sampled facial weights; save/reopen | Mesh deformation, eyes, acting, lip-sync or IK |
| UsdShade | Author/read a typed UsdPreviewSurface diffuse source | Material binding, PBR/MaterialX renderer parity |
| Physics, Volumes, Spatial audio, Render settings | Attempt real schema author/save/reopen individually | Physics simulation, rendered volume, audio mix, or engine execution |
| Hydra/ImagingGL/MaterialX module imports | Query actual optional module availability | Any delegate actually rendering pixels |

Optional schema features may honestly report NOT_AVAILABLE or FAIL on usd-core. A native schema that imports, authors and reopens receives **schema-only** classification. We do not mark these as working solvers.

The JSON explicitly sets renderer_verified=false, blender_verified=false, hydra_delegate_render_verified=false, materialx_renderer_parity_verified=false, photorealism_verified=false and nvp_source_indexed_asset_resolver_verified=false. A schema probe never implies film or director approval.

## Evidence generation and native jobs

**.github/workflows/nvp-usd-film00-capability-audit.yml** runs four native usd-core cells across Windows 2025/Ubuntu 24.04 and Python 3.11/3.13. Tests/test_nvp_usd_film00_capabilities.py independently executes true USD author/reopen, verifies the source-contract baseline and asserts that no renderer/photorealism claim can escape the report. Each job uploads the JSON and native source USD fixture, even if other checks fail.

A separate actual Ubuntu Blender job downloads the official Blender 5.2.3 archive and checks its Blender-published SHA. Native usd-core authors a real Mesh/Camera/SphereLight fixture. **tools/nvp_usd_film00_blender_probe.py** opens that fixture inside the actual Blender Python process, checks the real import/export operator options, imports the original mesh/camera/light and exports a new USD stage. A **separate external native usd-core process** independently opens that Blender export and verifies real geometry/camera/light survive, including output SHA and version details.

That is a meaningful Blender **geometry roundtrip**, not an UsdSkel import/export proof, fully matching MaterialX shaders, final rendered frame, performance benchmark, or photorealistic image. Existing FILM03-09D covers the actor mesh/shape-key path and remains independently unaccepted until actual CI passes. The native renderer parity and visual quality gates remain USD-FILM-05, 08 and 09.

## Reuse existing code; no replacement stack

NVP already has these source components; they should be reused and separately tested instead of replaced: backend/nvp_openusd_scene.py; nvp_openusd_take.py; nvp_openusd_time_state.py; nvp_openusd_assets.py; nvp_openusd_native_schemas.py; nvp_openusd_skeleton.py; nvp_openusd_skinning.py; nvp_wo3_materialx_integrity.py; nvp_wo2_materialx_resolver.py; nvp_blender_worker.py; nvp_film03_facial_rig_compositor.py. FilmIndex and the Production Bible retain authority for actors, sources and original Takes; OpenUSD is the composed 3D scene substrate.

## USD-FILM-00 closeout conditions

1. Obtain completed passing native source/contract tests at **one exact final SHA** for all four Windows/Linux Python cells, plus actual evidence JSON. No credit for queued, skipped, canceled or compiler-only passes.
2. Obtain a real Blender process record with independent usd-core re-opened USD export. Check original/roundtrip hashes and primitive counts. If Blender fails, mark Blender CLOSED? **NO** — mark the Blender interoperability gate OPEN, repair the actual native failure and retry.
3. Distinguish native USD, schema-only and unavailable modules; do not infer imaging/runtime support from usd-core package name.
4. Reconcile observed results against the existing NVP adapters, preserve original Take integrity, and record next genuine integration gaps in USD-FILM-01.
5. Continue FILM03-09E genuine speech-to-mouth and prior WO5/WO6 native acceptance separately.

**Next after audit:** USD-FILM-01, project-scoped content-addressed resolver plus referenced assets, variants, payload lazy loading and measured large-world resource behavior. The initial temporary test asset paths are intentionally not production-authorized scene data.

References: docs/NVP_USD_FILM_WORLD_FULL_INTEGRATION_MASTERPLAN.md; docs/NVP_DATA_ALL_TASK_LEDGER.md; Blender 5.2 Python API https://docs.blender.org/api/5.2/bpy.ops.wm.html ; OpenUSD instancing reference https://openusd.org/release/user_guides/schemas/usdGeom/overview.html
