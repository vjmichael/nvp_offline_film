# NVP-PROD-06E2B — Director-approved native ankle-lock IK

**Date:** 2026-11-03  
**Status:** **Verified for native ankle-marker IK** on real imported Cesium Man, Linux and Windows Blender 5.2.3. Physical sole contact and gait remain unverified.  
**Authority:** [NVP_MASTER_DESIGN.md](NVP_MASTER_DESIGN.md), [PROD06E2A_LEG_IDENTITY.md](PROD06E2A_LEG_IDENTITY.md)

## Scope

A complete director-authored ankle-lock motion pass on an independently verified real external humanoid. It is **not** a gait simulator and does not yet prove physical shoe-sole contact, mesh-floor intersections, stable full-body balance, skin realism, or human-accurate anatomy. Its purpose is to close the gap from an audited eight-bone leg identity to native thigh/shin pose changes that hold an ankle marker still over an authored contact window.

## Contracts and authority

1. PROD-06D approved character and rest-frame retargeting are current.
2. PROD-06E2A approved anatomical chains were inspected by actual Blender import and independently validated.
3. FootLockPlan attaches to the exact scene-scoped anatomical approval, character/retarget approvals, actor roster and approved take. Stale dependencies or a different project cannot export.
4. Each actor needs *both* authored left/right stance windows, actor-relative knee-pole offsets, a bounded positive ankle anchor pull, a hard maximum correction, and a hard maximum sliding threshold. A separate revision and creator approval are required. There is no automatic inferred gait.
5. The real Blender runtime imports the approved retargeted .blend, validates all mapped bone parent relationships, captures every original sample before writing new animation, and calculates target knee coordinates with a bounded two-bone analytic solution. It rotates and keys the actual imported upper and lower leg bones, in **armature-local** coordinates, rechecking true native segment lengths and ankle-target residuals.
6. Contact targets remain fixed in world coordinates during their explicit windows; outside those windows baseline thigh/shin rotations are restored and densely keyed. Original character source GLB, approved actor-root keys and shot camera keys are not edited.
7. The runner uses three separate native Blender invocations: inspect pristine base, apply/bake to a **new** .blend, independently reopen and inspect result. Host-side comparison verifies source-derived contact anchors, left/right slide, pose changes, limb length conservation, non-contact preservation, actor-root transforms, optical camera transforms and cut markers. A visually pleasing still is not proof of validity.

The two standalone files, source and modified .blend, remain available for audit. Blender and the real licensed external Cesium Man source must exist, otherwise native acceptance is blocked. This is a developer-only runner; arbitrary untrusted GLB loading needs supervised OS containment under Lu later.

## Implemented components

- backend/nvp_foot_contact.py — bounded typed contact-plan schema, approvals and stale protection.
- backend/nvp_foot_blender.py — native armature-space analytic two-bone IK bake, separate native audit and before/after comparisons.
- tests/test_foot_contact.py — deterministic domain validation and adversarial audit comparison tests; mocks are not called native evidence.
- tools/nvp_prod06e2b_fixture.py — the pinned CC-BY Cesium Man sample follows the complete PROD-06D and PROD-06E2A verification route, then applies a deliberate 2-cm artist-authored ankle adjustment and distinct L/R contact windows.
- .github/workflows/nvp-production-acceptance.yml — entire regressions on Linux/Windows plus genuine 5.2.3 Blender audits; Windows headless geometry audit is mandatory even without GPU preview.

## Independent acceptance checklist

- The native Blender import is tied to the content-addressed approved GLB and anatomical SHA.
- Both sides' actual thigh and shin pose keyframes change without modifying the original .blend.
- Each contact window's ankle marker stays within the approved centimeter-scale slide ceiling on all sampled frames.
- Hip-knee and knee-ankle armature-local segment lengths are maintained, no hidden stretch.
- Outside contact, original keyed poses are preserved.
- Independent baseline vs output Blender reports show unchanged actor roots, cameras, lenses and cut markers.
- The export is a new native .blend; loss of the approval/source identity aborts the process.
- Both Linux and Windows run on a genuine externally authored rig and preserve the audit files.
- Failure must remain visible as a failed result, not a silent substitute or synthetic success.

## Remaining engineering gaps

This milestone demonstrates ankle-point inverse kinematics, **not planted shoe soles**. The source sample's terminal bone is not guaranteed to be the sole collision contact point. Before production film-quality motion, add semantic foot geometry/sole marker binding, ground normals and changing-floor/platform reference frames, collision/penetration audit on the skinned mesh, smooth lift/plant blending, knee anatomical joint-limit constraints, gait dynamics, balancing, prop interaction and controlled facial performance. The user-facing director mapping UI and end-to-end Lu DLC worker containment remain future milestones.

## Verification command

Python schema tests: `PYTHONPATH=. python -m unittest tests.test_foot_contact -v`

True pinned native acceptance, from a checkout with Blender and the licensed reference downloaded:

```sh
PYTHONPATH=. python -m tools.nvp_prod06e2b_fixture \
  --out acceptance_artifacts/prod06e2b \
  --external-glb /path/to/CesiumMan.glb
```

Add `--audit-only` for Windows lacking Workbench rendering. The expected end result is `passed_native_ankle_lock_only`, not "full realistic gait". Real Blender evidence and measured residuals are recorded below. This does not certify film-grade foot biomechanics.

## Completed native acceptance and numbers — 2026-11-03

[GitHub workflow run 41659667221](https://github.com/vjmichael/nvp_offline_film/actions/runs/41659667221): both real Blender 5.2.3 **Linux** and **Windows** PROD-06E2B native steps completed successfully. Each fully rebuilt the external licensed sample, replayed the independently approved 06E2A anatomical identity, author-approved the fixture contact intent, baked actual imported thigh/shin pose keys, then used separate native Blender processes to reopen and compare the pristine and modified .blend files. The Windows test is real **geometry-only**, not a claim of GPU-rendered motion.

Both platforms independently reported **120 compared frames**, max ankle-marker distance from each target **6.336060650786549e-7 m**, max armature-local upper/lower segment-length residual **6.927575093018667e-7 m**, and observed actual quaternion component change **0.5295589566230774**. All tested actor-root transforms, camera matrices/lenses, cut markers, noncontact upper/lower-leg pose values, and approval receipts passed the independent comparison. The fixture authors a deliberate **0.02 m ankle target adjustment** for a real nontrivial IK pose change; it does *not* exercise walking actor roots or physical sole contact.

These are **fixture-specific measurements**, not universal quality guarantees or production SLA. Additional 06E2C testing must address real sole geometry, foot-floor penetration, moving actor trajectories, target changes during stance, joint ceilings, rig deformation quality, temporal subframe blending and physics. Windows physical AMD GPU / Lu DLC tests remain separate.
