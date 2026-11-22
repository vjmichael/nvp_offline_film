# NVP-PROD-06E2C3B — Reviewed plantar anatomy and real triangle-BVH support geometry

**Date:** November 3, 2026  
**Master design:** [NVP_MASTER_DESIGN.md](NVP_MASTER_DESIGN.md)  
**Source baseline:** PROD-06E2C3A, verified real Blender toe-candidate correction (Linux and Windows).  
**Scope:** Create a durable, provenance-attested anatomical marker source and independently test real support geometry. **Do not claim certified anatomical foot modeling, full gait or finished biomechanical support before independent labeled anatomical data exist.**

## Research and definitions

NVP should use four **distinct plantar contact regions** per foot, with provenance for every 3D attachment:

| Contact role | Anatomical region | Example external tracking counterpart | Important distinction |
| --- | --- | --- | --- |
| `heel_pad` | Inferior calcaneal fat pad | LHEE/RHEE | Surface pad on the plantar side, not heel marker on rear of shoe |
| `mt1_pad` | Plantar region under first metatarsal head | LMT1/RMT1 | A dorsal metatarsal marker is **not** automatically the load-bearing region |
| `mt5_pad` | Plantar region under fifth metatarsal head | LMT5/RMT5 | Must distinguish medial and lateral forefoot |
| `hallux_pad` | Plantar great-toe region | LTOE/RTOE | Foot-tip articulation and actual surface geometry must be retained |

Grounding: the [KIT Whole-Body Human Motion Database marker set](https://motion-database.humanoids.kit.edu/marker_set/) separately documents LHEE/RHEE, LMT1/RMT1, LMT5/RMT5, LTOE/RTOE, and ankle markers. [OpenSim's experimental data guidance](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim24/pages/54001691/Collecting%2BExperimental%2BData) and its [Gait2392/2354 models](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53086215/Gait%2B2392%2Band%2B2354%2BModels) provide a useful independent clinical/biomechanics nomenclature and model framework. These are **location definitions**, not pre-labeled indices for the Khronos Cesium Man rig.

[Foot3D](https://github.com/OllieBoyne/Foot3D) lists 118 foot scans and a request-based download. Its public code repository carries an MIT license; **do not assume that the separately requested scans, subject imagery or trained model weights inherit the same redistribution/commercial permissions**. [Blender 5.2's Mesh API](https://docs.blender.org/api/5.2/bpy.types.Mesh.html) supports `calc_loop_triangles()`, and its [BVHTree API](https://docs.blender.org/api/main/mathutils.bvhtree.html) supports geometry ray-casting against true triangles. These are directly usable conventional tools, requiring no new runtime dependency in native Blender.

## Implemented: provenance and anatomical attachment

`backend/nvp_plantar_landmarks.py` adds a SQLite-scoped, revision-controlled foot attachment linked to the **exact 06E2C3A correction, C2 plantar plan, and 06E2A rig approval SHA**. For each approved actor and left/right side it requires all four role names, an exact imported skinned mesh name and four distinct original source mesh vertex indices. Across both sides, no vertex can be assigned to both feet.

The evidence packet records a separate anatomical reference file SHA256, explicit source/rights identifier, annotation method, and different annotator/reviewer IDs. Fixture-generated names or same-person review are refused. The data validator cannot authenticate reviewers' medical credentials or validate license grant scope; it **never** sets `clinical_anatomy_certified=true` or distribution rights approved.

`backend/nvp_plantar_anatomy_blender.py` provides an independent, **read-only** native Blender survey of the already corrected external character. Before native inspection, the developer host rehashes the *actual reference-file bytes* (8 MiB maximum). Native Blender verifies actor/asset/rig approvals, skin modifiers, exact original vertex indices and side-specific deform weights; measures evaluated mesh positions and normals; and compares them with the imported leg-chain's foot axis. The independent host rejects degenerate heel-to-hallux length, narrow/contradictory metatarsal breadth, wrong heel→forefoot ordering and dorsal/upward-facing surface points in upright reference stances. An accepted geometry attachment is stored durably and may be exported with explicit **no-clinical-certification / rights-not-cleared** limits. Neither the test nor the code invents reviewed anatomical vertices for Cesium Man.

**Critical limitation:** anatomical geometry tests catch some obviously wrong points, not subtle morphological errors. Obtaining an independently reviewed point set and cleared source rights for our actual character remains an external acceptance dependency. This gate is intentionally blocked for *true anatomical certification* until supplied.

## Implemented: real triangle BVH and supported surfaces

`backend/nvp_surface_bvh.py` invokes native Blender 5.2.3 against a fully IK-corrected real character and exact registered floor mesh. It triangulates the evaluated support geometry in **world space** and uses `BVHTree.FromPolygons` and downward gravity ray casts to measure the visible, skinned foot-marker gap to the corresponding triangle. The original C2 SHA of the entire floor's world-space geometry is rechecked, preventing a stale surface substitution.

The current native fixture tests, separately:

1. Actual NVP_FLOOR top face with a +12 mm hovering point and −9 mm penetrating point.
2. A **12-degree** in-memory inclined polygon with +14 mm above and −11 mm below distances.
3. A point beyond that surface (must reject as no support).
4. A **70-degree** inclined surface under a maximum declared 35-degree grade (must reject as unsupported).
5. The original **corrected, real Cesium Man** plantar toe-candidate vertex during every approved left/right stance frame, matched against the existing C2 geometric tolerances.

The newly created slope is **only a geometry probe**; no real moving human is retargeted onto or animated up this incline. It is intentionally not saved into the authoritative scene. No arbitrary flat-world assumption, axis-aligned bounds pretending to be collision or secretly relaxed tolerances are used.

Even a passing BVH ray result is a **signed vertical height relative to the first downward triangle hit**, *not* mathematically general point-to-manifold signed distance, closed-volume collision, contact force, static balance, or proof of sole coherence.

## Files, commands, acceptance

- `backend/nvp_plantar_landmarks.py`: reviewed anatomical role/provenance contract and SQLite approval.
- `backend/nvp_plantar_anatomy_blender.py`: read-only licensed character source/mesh anatomy observation.
- `backend/nvp_surface_bvh.py`: triangulated world-space floor/slope and actual skinned marker contact audit.
- `tools/nvp_prod06e2c3b_fixture.py`: existing native C3A acceptance followed by new BVH proof on real external rig.
- `tests/test_plantar_landmarks.py`, `tests/test_surface_bvh.py`: adversarial geometry, source, stale-approval and surface refusal.
- `.github/workflows/nvp-production-acceptance.yml`: full Python/React plus real Blender on Linux and Windows.

Python:

`PYTHONPATH=. python -m unittest tests.test_plantar_landmarks tests.test_surface_bvh -v`

Native Blender (licensed external Cesium Man required):

`PYTHONPATH=. python -m tools.nvp_prod06e2c3b_fixture --out acceptance_artifacts/prod06e2c3b --external-glb /path/to/CesiumMan.glb`

Headless Windows adds `--audit-only`.

**Acceptance classification:** if native BVH and original real-character toe-contact tests pass, mark *triangle surface geometry verification* passed. Do **not** mark independent, real plantar anatomy certification complete. Full future production scope needs a genuinely reviewed and licensed four-region anatomical attachment for a real rig, moving-root/foot-roll gait, named inclined/moving colliders, whole skinned-mesh penetration and realistic biomechanics.

## Native Blender acceptance, November 3, 2026

[Workflow 41674405456](https://github.com/vjmichael/nvp_offline_film/actions/runs/41674405456) completed and passed its **real Blender 5.2.3 Linux and Windows** surface acceptance stages on the pinned licensed Cesium Man. The native stage was reopened after real imported-leg ankle IK and its previously accepted C3A corrective animation. All new BVH flat/slope/outside/steep tests passed on both operating systems.

| Measured criterion | Linux | Windows |
| --- | ---: | ---: |
| Actual corrected plantar *candidate* marker samples | 25 | 25 |
| Maximum signed gravity gap above real NVP_FLOOR | 0.000272578 m | 0.000272582 m |
| Maximum penetration below actual floor | 0 m | 0 m |
| Flat-floor test | +12 mm / -9 mm | Pass |
| Separately generated 12° slope test | +14 mm / -11 mm | Pass |
| Off-support and 70° steep grade | Refused as unsupported | Refused as unsupported |
| Expert-annotated Cesium Man heel/MT1/MT5/hallux mesh | **Not available** | **Not available** |

**Scope decision:** `passed_real_character_bvh_geometry_only` verifies the new surface engine and the original corrected toe-candidate contact. It is **not** evidence of clinical/gait validity, an integrated human on a sloped floor, whole-mesh floor collision, or any approved foot data license. A true four-region anatomy attachment requires a supplied reviewed source reference file matching its exact SHA, reviewed source vertex indices, and independent actual native geometry inspection.

The Linux Python regression suite ran **409 tests: 402 passed, 7 skipped**. React production build passed. Windows Python acceptance status is tracked independently in the workflow; no implied pass is claimed before its actual completion.
