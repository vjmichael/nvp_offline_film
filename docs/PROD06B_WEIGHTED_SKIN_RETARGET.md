# NVP-PROD-06B — Weight-painted preview silhouette and explicit neutral-pose calibration

**Purpose:** Continue NVP's conventional filmmaking pipeline without changing Lu. Build on the PROD-06A approved armature/BVH stage, and distinguish real mesh deformation from animated bone transforms alone.

## Implemented

- Project- and scene-scoped **skin proposal** pinned to the immutable PROD-06A motion export SHA, with optimistic revision checks, durable snapshots, explicit director approval and stale-source refusal.
- A **single procedural Blender mesh per moving actor**, with seven named vertex groups, three rings of eight vertices for each of seven body segments, an `ARMATURE` modifier, and normalized weights. Joint bases blend into their parent bone rather than behaving as unweighted props.
- **Quaternion neutral-pose correction** for explicit director-supplied source/target rotation calibrations per role: `q_target = q_target_neutral * inverse(q_source_neutral) * q_sample`. This is *not* inferred automatically from BVH naming, coordinates or performer shape.
- Original actor instance ID and approved root blocking movement preserved; exporter hides the original actor proxy from rendering without overwriting its animation.
- Blender save/reopen audit checks armature links, group weights, approval hashes, calibrated bone rotations and actual evaluated vertex displacement across motion frames. The Linux job also requires a real Workbench PNG. GPU-less hosted Windows audits geometry without falsely claiming a rendered preview.
- Narrow API and creator-facing skinning panel, with no raw LLM-generated Blender code.

## Explicit limitations

- This is a **seven-bone stylized sectional preview mesh**, not a reusable skinned humanoid purchased from an asset library, not smooth organic body skinning, not generic rig retargeting, not footwear/hand interaction, and not a production performance.
- BVH motion clips have varied axis conventions, bone rest orientations, skeleton proportions and scale. A deliberately limited quaternion rest offset corrects neutral rotation for a selected role, but **does not solve coordinate-system conversion or true full-body retargeting**. The creator must manually inspect and calibrate before approval.
- Blender native validation must run, not be inferred from successful Python script parsing. Windows WGL/OpenGL headless rendering remains separate from actual save/reopen/deformation acceptance.
- Asset rights are declared, not independently verified; commercial film distribution requires separate license review.

## Acceptance criteria

1. A director must approve an up-to-date PROD-06A motion layer before creating a skin layer.
2. Reject malformed calibration, foreign actors, stale revision and changes after approval.
3. Reopening the SQLite database preserves approved skin and neutral-pose provenance.
4. Real Blender builds the mesh, binds a valid armature modifier with seven normalized-weight groups, saves and reopens the project.
5. The auditor verifies bone quaternion calibration and actual evaluated mesh vertex displacement for nontrivial motion, rather than checking only keyframe data.
6. Linux preview rendering and Windows native geometry audits remain independently labeled.
