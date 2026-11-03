# NVP-PROD-06E2A — Verified anatomical leg-chain identity (before IK)

**Date:** 2026-11-03  
**Scope:** NVP Film Workspace development only, no Lu changes  
**Master authority:** [NVP_MASTER_DESIGN.md](NVP_MASTER_DESIGN.md), section 7.1  
**Implementation scope:** Authored bone identities, imported skeleton rest-hierarchy inspection and director approval. This stage **does not solve, keyframe, bake or render IK**.

## Motivation and factual asset anatomy

PROD-06D maps only seven broad retarget roles, including one role each for left and right legs. These are insufficient to define thigh, knee, ankle, terminal foot, pole/bend direction or actual stance contact.

The original Khronos Cesium Man glTF skin at pinned commit 8f492390ddc7a2ae221a1369ef560589cf8c70fb has two separate direct-parent chains:

| Side | Hip/upper leg (06D role) | Knee/lower leg | Ankle/foot | Terminal foot |
| --- | --- | --- | --- | --- |
| Left | leg_joint_L_1 | leg_joint_L_2 | leg_joint_L_3 | leg_joint_L_5 |
| Right | leg_joint_R_1 | leg_joint_R_2 | leg_joint_R_3 | leg_joint_R_5 |

[Original source glTF](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/8f492390ddc7a2ae221a1369ef560589cf8c70fb/Models/CesiumMan/glTF/CesiumMan.gltf) provides the names and parent edges. **Names do not prove anatomy by themselves**, particularly after normalization and Blender import.

## Requirements and authority

1. The current, director-approved PROD-06D character/retarget is prerequisite. The mapping is per project, scene and actor, pinned to the approved dependency digest and immutable GLB SHA.
2. The director supplies explicit left and right dictionaries, each containing hip, knee, ankle, and toe names. The eight bones are distinct and exist in the registered asset. Hip bones must match the earlier approved left/right leg roles.
3. Every edit requires the expected revision and draft status; editing clears prior inspection evidence. No silent left/right inference.
4. A **fixed, read-only Blender probe** imports the registered, rehashed GLB and observes the actual armature count, real skinned modifier, every joint name and parent, rest head and tail world coordinates, and world/local rest matrices.
5. Independent Python validation checks exact source hash, unique finite bone data, nonsingular rest bases, full immediate parent hierarchy, distinct bilateral roots, and measured thigh, shin and foot segment lengths. Crossed rest feet produce a review warning, never automatic renaming.
6. Verified observations are recorded under a revisioned SQLite plan. Only a complete, current native inspection may be director-approved. Export revalidates its source and approval digest.
7. The exported identity explicitly says ik_authorized=false; no camera keys, approved root paths, character animation, source mesh or performance actions are modified.

## Implementation

- backend/nvp_leg_chains.py — validated mappings, native probe, independent observed-anatomy validator, revisioned LegChainIdentity workflow.
- tests/test_leg_chains.py — rejection of fake/missing/overlapping bones, wrong hierarchy, invalid world matrices, nonfinite geometry, stale updates and approval without genuine Blender inspection.
- tools/nvp_prod06e2_fixture.py — pinned external Cesium Man 06D baseline followed by native 06E2A hierarchy inspection using the eight creator-specified bone identities.
- .github/workflows/nvp-production-acceptance.yml — Python regressions plus Linux and Windows native rig identity acceptance.

## Deliberate limits

This is a *rest geometry and identity proof*, not proof of gait, physical foot contact, knee dynamics or performance. No general auto-rigging, knee pole choice, moving-ground solver, foot locks, keyframe changes, visual quality evaluation or native inverse kinematics. The fixture's exact Cesium Man mapping is test-only, not a generic product auto-map. Unsafe arbitrary asset parsing still requires host-supervised OS containment before production release. The third-party sample remains separately licensed and must not be distributed as an NVP-branded actor.

## Verification and next gate

Pure Python: PYTHONPATH=. python -m unittest tests.test_leg_chains -v

Native Linux: PYTHONPATH=. python -m tools.nvp_prod06e2_fixture --out acceptance_artifacts/prod06e2 --external-glb /path/to/CesiumMan.glb

Headless Windows: add --audit-only; this does not remove actual native bone hierarchy checks.

Successful stage result: passed_native_leg_identity_only, with native Blender version, asset SHA, approval receipt, and actual rest segment measurements. Missing sample/Blender is blocked, not a pass.

**Next:** add director-approved knee poles and contact schedules, convert world/rest matrices into a constrained Blender IK application, independently reopen saved rigs, and measure foot-specific sliding and penetration over frames. PROD-06E2 as a whole is not complete until those later gates pass.

## Actual native acceptance evidence — 2026-11-03

[GitHub workflow run 41655290749](https://github.com/vjmichael/nvp_offline_film/actions/runs/41655290749) completed the PROD-06E2A dedicated **Linux and Windows Blender 5.2.3** anatomical identity steps successfully. The Linux run additionally passed its existing 06D render/retarget prerequisite; the Windows geometry-only run did not claim a Workbench preview. All eight mapped names and direct hierarchy edges survived import; the independent validator returned no anatomical warnings.

Observed segment lengths on the **separately imported, normalized source rig** (not the actor-height-calibrated production rig): left upper 0.266112830 m, lower 0.275824351 m, ankle-to-terminal-joint 0.071835975 m; right upper 0.266111587 m, lower 0.275824840 m, ankle-to-terminal-joint 0.071835916 m. Windows independently measured nearly identical values. Source asset SHA-256: b6592f42de71d5e6f0d69d6b22b96cd2b8630f2addc4adeb634ce0bdf8f04c0c. This is **not** a production limb-length measurement after actor parenting/nonuniform scaling; 06E2B must transform or remeasure the real staged rig before any IK application.

Native pass result: passed_native_leg_identity_only; ik_applied=false. This does **not** establish gait, foot contact, control rig behavior, actor motion or completed PROD-06E2.
