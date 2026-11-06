# NVP-PROD-06A — Explicit BVH to procedural Blender humanoid armature

**Scope:** Film Workspace NVP only; Lu integration deferred until Lu v1.0.

## Delivered

- Project-scoped, immutable motion library. BVH is parsed as bounded DATA, never
  executed as Python. Explicit source-bone to target-role mapping is mandatory.
  Supports 10–120 fps BVH rotation samples and a controlled 7-bone humanoid preview.
- Accepts manually authored Euler keyframes with the same typed contract.
- A project/scene-scoped motion plan references the current director-approved PROD-05
  camera/actor take. Each actor receives non-overlapping, frame-addressed clip
  segments, recorded in a revision ledger; the creator must explicitly approve.
- Blender builds a real ARMATURE parented to the persistent actor proxy and
  keys its pose-bone quaternions. The approved PROD-05 root blocking continues
  to animate the actor; imported BVH root translation is intentionally discarded.
- Native Blender audit independently reopens the .blend and verifies rig identity,
  seven armature bones, sampled bone rotations and the approval fingerprint.
- Creator UI supports local BVH import, explicit role mapping, clip assignment,
  approval and Blender script export. Python and Windows/Linux native checks are
  separate; GPU-less Windows CI is geometry-only.

## Explicit limits

This is **skeletal previsualization**, NOT mesh skinning, full-body retargeting,
IK foot planting, mocap fidelity, lipsync, character faces or final performance.
Source rest poses and BVH channel orientation require human review. Licensing is
only creator-declared; NVP does not grant commercial use rights. Actors use their
existing approved root paths and keep human-authored edits protected.

## Acceptance

- Reject malformed / nonfinite / over-budget BVH and forbidden bone maps.
- Never admit clips from another project or silently change an approved take.
- No overlaps or motion beyond the sequence frame budget; stale state blocks export.
- Assert Blender script parses deterministically. Actual Blender runs must save,
  reopen and validate armature bone rotation in multiple frames; Linux preview
  rendering is an extra check, not a substitute for skeleton/geometry correctness.
