# NVP-PROD-06E2C1 — Real skinned foot-region candidate geometry

**Date:** November 3, 2026  
**Authority:** [NVP Master Design](NVP_MASTER_DESIGN.md), Sections 7 and 9.  
**Baseline:** Verified PROD-06E2B real ankle-marker locking on Linux/Windows Blender 5.2.3.  
**Scope:** Read-only geometry investigation; **not** physical sole recognition, rig authoring, IK modification, or gait-quality certification.

## Why this gate exists

PROD-06E2B achieves precise world-space ankle-marker locking over explicitly
approved contact windows. An ankle point is **not a shoe sole**. A foot may
still penetrate or hover above a floor even when its ankle stays locked. The
articulated, skinned geometry must be evaluated independently rather than
mistaking joint coordinates for collision.

## Implemented engineering slice

- **Native deformation inspection:** Independently reopen the already-verified
  ankle-locked Blender scene. Verify the exact approved foot-lock receipt,
  anatomical identity receipt, and content-addressed character asset.
- **Per-side candidate regions:** Use the actually imported mesh's explicit
  ankle and terminal-foot vertex groups for each side. Require both names,
  bounded skinned geometry, actual bone-weight membership, and at least
  three candidate vertices per side. No name guessing or automatic masking.
- **Frame-wise evaluated mesh:** For the union of authorized contact windows,
  evaluate Blender's armature-deformed mesh through the depsgraph and record
  each side's lowest weighted vertex and regional vertical range. All values
  are in world-space metric coordinates.
- **Independent host audit:** Match all actor/asset/approval identities,
  frame lists, record shapes and finite quantities. Measure the minimum
  region clearance, maximum clearance and lateral movement of its minimum
  vertex over the side's authored contact frames.
- **No unsound claims:** A weighted vertex population is an *anatomy candidate*,
  not a creator-approved plantar region. The lowest vertex may change
  identity between frames. Tracking its XY position is therefore **not** a
  reliable shoe-slip metric, and the published result explicitly sets
  physical_sole_contact_verified=false.
- **Full regression:** The same pinned, licensed Cesium Man GLB is
  independently imported, 06D-retargeted, anatomically approved, IK-baked and
  independently audited before this additional read-only survey.

## Source and evidence

- backend/nvp_foot_sole.py — native evaluated weighted-vertex region survey
  and independently validated observation.
- tests/test_foot_sole.py — malicious/invalid evidence refusals; synthetic
  tests do not count as native geometry acceptance.
- tools/nvp_prod06e2c_fixture.py — real pinned external character runner.
- .github/workflows/nvp-production-acceptance.yml — Linux and Windows native
  acceptance jobs. On Windows, the missing GPU display does not waive
  actual geometry verification.

Expected status when the native observation succeeds:
passed_candidate_region_survey_only. If the real imported asset lacks
bilaterally distinguishable ankle/toe deform weights, the step must **fail**
and report the unavailable anatomy signal. It must not invent a mesh mask.

## Next design gate: actual foot sole authoring

The creator must approve a physically meaningful foot-surface region (or
authored heel/ball/toe attachment markers) in **rig/mesh-local space** with
correct units, stable skinning correspondence and right/left provenance.
Then the collider/floor reference can be tied to each stance's target
surface and measured over all relevant frames, including moving floors,
slopes, turning, dynamic actor roots, motion blends and independent skinned
mesh-floor penetrations. A successful IK ankle lock does not supersede these
requirements. A realistic skeleton alone also does not establish muscle,
tendon, weight shift or visually convincing acting.

## Native acceptance and measured limitation — November 3, 2026

[GitHub workflow run 41662467122](https://github.com/vjmichael/nvp_offline_film/actions/runs/41662467122) has successfully completed the new real Blender **Linux** and **Windows** PROD-06E2C stages on the pinned licensed Cesium Man. These are read-only evaluations of an actual previously IK-baked, skinned external humanoid. The final full-suite result is recorded separately from these individual stage results.

Both native runs returned status **passed_candidate_region_survey_only** and explicit **physical_sole_contact_verified=false**.

- Linux: left stance 12 frames, minimum candidate-region Z **-0.0068229414 m**; right stance 13 frames, minimum **-0.0067292908 m**. Maximum left/right clearance was also negative. Measured XY motion of the *lowest candidate point* was 0 in this controlled fixture.
- Windows: left minimum candidate-region Z **-0.0068229893 m**, right minimum **-0.0067293001 m**; minimum-point XY motion likewise 0.
- The assumed reference plane for these numbers is **world Z=0**. Negative clearance of about 6.8 mm is a **candidate-region below-plane observation**, not yet a certified collision with an authored floor collider. No shoe sole, collision patch, dynamic balance, or gait realism was established. If the floor geometry is offset, the comparison must be adapted.

**Interpretation:** These measurements show exactly why locking the ankle is not enough. The next milestone should author true plantar markers/weighted foot regions and a named collision floor, then independently evaluate the skinned mesh against that surface and its normal at every foot plant. Do not translate this report into an unearned 'feet are physically planted' claim.
