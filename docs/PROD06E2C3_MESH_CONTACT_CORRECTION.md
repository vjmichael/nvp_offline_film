# NVP-PROD-06E2C3 — Bounded skinned-mesh contact correction

**Date:** 2026-11-03  
**Governing design:** [NVP_MASTER_DESIGN.md](NVP_MASTER_DESIGN.md)  
**Starting baseline:** 06E2A verified real anatomical leg bone identities → 06E2B actual ankle-joint IK → 06E2C1 read-only weighted sole candidates → 06E2C2 three exact heel/ball/toe vertex references and actual floor geometry audit.  
**Scope of this implementation:** real imported character's selected mesh contact points; no new actor-root movement, camera editing, arbitrary anatomy classification, unlicensed external model distribution, or Lu host changes.

## Research and engineering rationale

The [Blender BVHTree API](https://docs.blender.org/api/current/mathutils.bvhtree.html) exposes evaluated-mesh proximity and ray tests, suitable for the next **general** collider stage. This release deliberately uses the already validated, explicitly identified **NVP_FLOOR rectangular top surface**, pinned by the exact SHA of its world-space vertices; it does not substitute a fake universal Z=0 collision plane.

[OpenSim's muscle/foot models](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53090607/Mus) and [Rice University's ground-contact tutorial](https://nmsm.rice.edu/guides-and-publications/tutorials/beginner-tutorials/gcp-tutorial/) document why authentic ground support depends on heel, medial/lateral forefoot, toes, support geometry, and biomechanics. Scanned-foot resources such as [Foot3D](https://github.com/OllieBoyne/Foot3D) require separate access/rights checks and cannot silently be packaged as NVP training/geometry data. None of these studies is yet integrated or used to claim anatomical certification.

## Design: correcting the visible skinned foot

**Input identity:** exact creator-approved 06E2C2 heel/ball/toe original vertex indices, mesh names, left/right side roles, rigid floor vertex digest, source character SHA, 06E2B/06E2A receipts, approved take and approved stance windows. An anatomical label provided by an engineering fixture remains *unverified* even when the vertex itself has been measured in Blender.

**Artist-authored bounded correction:** a new revisioned, project-scoped PlantarCorrectionPlan requires explicit maximum ankle deviation (at most 3 cm), maximum solver iterations (at most 8), maximum thigh/shin quaternion rotation from the original pose (at most 60 degrees), and desired clearance. Only the explicitly approved contact roles for the side are enforced. All other named markers remain visible in the independent report.

**Infeasibility mathematics:** for each selected contact point, signed gap `g` to the floor must satisfy `-p <= g + d <= h`, where `p` is approved maximum penetration, `h` is approved maximum gap and `d` is signed vertical correction. The intersection of those allowable displacement intervals, bounded by `[-D,D]`, must be nonempty. If several supposed sole points differ too much vertically, NVP refuses the request. It does not widen a tolerance, move the floor, or silently drop a failing heel.

**Native correction:** Blender reopens an approved real ankle-locked scene, rechecks imported bone parents, skinned geometry and exact floor. At every authorized stance frame it measures the *evaluated source mesh* through the depsgraph, solves a bounded ankle target translated along actual world vertical, places the knee with an analytic two-segment solver, rotates only the actual imported thigh/shin pose bones, and re-evaluates the skinned contact markers. Each unsuccessful iteration is bounded; unreached goals, excessive joint motion, singular legs, off-floor markers or stale geometry are refused. Outside stance, original pose keys are restored/baked; actor root, rig-object transform, scene cameras and shots are not edited. Successful animation goes to a **new .blend**, never overwriting the original approved scene.

**Independent evidence:** separate Blender invocations reopen both source and output and independently inspect the entire take: per-frame actor-root/rig transforms, camera matrices/lenses, shot cut markers, local hip–knee and knee–ankle lengths, and both sides' contact and noncontact joint channels. The existing independent 06E2C2 mesh/floor observer measures source and output surface markers. A host-side comparison refuses noncontact change, camera/root drift, limb stretch, missing frames, unapproved source identity, or unresolved active marker gap.

## Explicitly scoped native acceptance fixture

The licensed third-party Cesium Man test character from prior gates has **no independently certified plantar landmark labeling**. Its 06E2C2 generated “heel” and “ball” candidates are 7–11 cm above the stage and cannot be reliably corrected by translating one ankle target a few millimeters. Therefore, the 06E2C3 fixture deliberately selects **only its toe-region candidate** as active contact while retaining all three tracked markers. This is a constrained kinematic/motion-and-mesh verification, **not** proof of full anatomical sole identity. A separate unit test proves that simultaneously requesting all three original misidentified fixture points is mathematically infeasible under the approved limits.

Success status is `passed_native_marker_floor_correction_only`, with `corrected_marker_contact=true`, `anatomical_sole_certified=false`, and `gait_dynamics_verified=false`. The original 06E2C2 three-marker fixture must continue to fail *physical* contact while passing *geometry measurement*.

## Code and verification

- `backend/nvp_plantar_correction.py`: immutable approval records, bounded scalar contact-feasibility solver, revision and upstream checks.
- `backend/nvp_plantar_blender.py`: real Blender skinned-marker iterative correction, full-take separate-native snapshot, independent geometry/continuity comparison.
- `tools/nvp_prod06e2c3_fixture.py`: real source rig fixture, through 06D/06E2A/B/C2, then independent corrected version and audits.
- `tests/test_plantar_correction.py`: infeasible multi-point contact, finite bounds, authorization/restart, and independent actor-root/camera/length/noncontact refusal.
- `.github/workflows/nvp-production-acceptance.yml`: full regression plus actual external licensed rig in Linux and Windows Blender 5.2.3.

**Commands:**

`PYTHONPATH=. python -m unittest tests.test_plantar_correction -v`

`PYTHONPATH=. python -m tools.nvp_prod06e2c3_fixture --out acceptance_artifacts/prod06e2c3 --external-glb /path/to/CesiumMan.glb`

Headless Windows runs `--audit-only`. Passing Python tests alone is never native Blender evidence.

## Release boundary and next gate

Passing toe-contact geometry **does not** establish the user's requested full “validated foot-surface anatomy.” That remaining work requires an *independent ground-truth anatomical annotation of actual heel, first/fifth metatarsal, arch and toe/sole surface* mapped to the licensed character mesh, preferably with named author and source/rights. Use authenticated or reviewable annotation and mesh-local coordinates; do not infer anatomy from imported joint names or the lowest skinned vertex. Once certified, extend to a general named collision mesh/BVH, slopes/moving floors, heel-to-toe transition, friction, whole-mesh penetration and biomechanical joint/weight-shift limits. A future proper foot mesh may need redesign or a different character rig to fulfill those constraints.

**Intended evidence state:** actual native Blender acceptance still required; do not mark whole-body realistic gait or full sole certified on the strength of a fixture.

## Actual independent native result — 2026-11-03

[GitHub workflow run 41670220453](https://github.com/vjmichael/nvp_offline_film/actions/runs/41670220453), pinned licensed Cesium Man with **Blender 5.2.3**, completed the new real-native Linux and Windows marker-contact correction steps. The input toe-candidate marker failed ground penetration tolerance; the saved/reopened corrected scene independently passed that configured marker contact tolerance on **both** platforms. It changed the **actual imported leg bone poses**, not the source asset, overall actor root, or cameras.

| Measured evidence | Linux | Windows |
| --- | ---: | ---: |
| Full source/output frame audit | 120 | 120 |
| Actually changed contact leg-frames | 25 | 25 |
| Noncontact leg-frames held unchanged | 215 | 215 |
| Maximum upper/lower segment discrepancy | 3.6157133e-7 m | 3.7776945e-7 m |
| Corrected selected marker meets floor limits | Yes | Yes |
| Anatomical heel/ball/sole identity certified | **No** | **No** |
| Moving-root gait or full-mesh collision verified | **No** | **No** |

The solver refuses mathematically incompatible heel/ball/toe offsets: the previous fixture measured “heel” +0.113 m, “ball” +0.074 m and “toe” -0.0068 m relative to the floor, not three points forming a real planar sole. Those are **invalid test-derived anatomical labels**; this correction operates only on the test-approved toe-region contact, and never declares an anatomical foot biomechanically verified. Full human anatomy remains a separate blocked gate requiring real annotation evidence and reviewed asset rights.

**Regression scope:** Linux full Python suite and React build passed at this revision; Windows native Blender passed; Windows Python suite was pending at documentation time. If its outcome changes, update this document with exact independent evidence.
