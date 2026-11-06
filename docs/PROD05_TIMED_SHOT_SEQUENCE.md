# NVP-PROD-05 — Timed proxy shots and editable cinematic coverage

**Date:** 2 November 2026. **Scope:** NVP Film Workspace only; no Lu source, IPC, worker, or runtime modifications.

## What is implemented

The underlying PROD-01–04 work has an approved screenplay-linked world, persistent typed edits, optional immutable GLB assets, collision-checked actor marks, and measured camera projections. This milestone adds **one durable creator-approved shot sequence per screenplay scene** with a frame-accurate (24 fps) cut list, explicitly scheduled dialogue starts, and an executable Blender scene generator.

Every shot references a previously solved PROD-04 camera by its stable ID. Each dialogue cue references a real screenplay dialogue ID and its explicitly measured duration, never an estimated word count. A validator checks a continuous cut timeline, missing or overlapping cues, unresolved speakers, actor blocking continuing after the sequence, drifting subjects at the beginning/middle/end of shots, potential 180-degree line crossings, near-identical cuts, and speakers who aren't the main subject of an overlapping shot.

Warnings are **not proof of filmmaking errors**. The director explicitly acknowledges the exact warning codes before approving a sequence. Acknowledgement cannot be reused if the plan changes. Hard errors cannot be acknowledged away. Approval is stored with a digest of the sequence and dependencies; a new scene revision, changed WorldState, new/changed camera, blocking move, or dialogue timing invalidates old export authority. The creator can fork a new draft from an approved version, remove shots, or reset stale draft dependencies; earlier revisions remain durable.

The Blender exporter starts with the approved deterministic proxy scene. It creates one Blender camera per shot, places camera switching timeline markers at exact frames, sets frame range and FPS, and animates each approved actor proxy along the existing PROD-04 A* path using distance-proportional location keyframes and linear interpolation. This is **movement previs**, **not** a rig, skinning, motion capture, spoken audio, facial expression, lip sync, physics, a finished performance, or final film export.

## Code

- `backend/nvp_shot_sequence.py`: typed cut and dialogue timeline, independent validation, approval ledger, time-dependent character XY, Blender generator, real-Blender acceptance harness.
- `frontend/src/TakeSequencePanel.jsx`: creator panel for shots, dialogue cue timing, continuity warning acknowledgements, approvals, and Blender script export.
- `backend/nvp_api.py`: film-project scoped endpoints under `.../production/scenes/{scene_id}/sequence`.
- `tests/test_shot_sequence.py`, `tests/test_prod05_api.py`, `tests/test_prod05_blender.py`: deterministic tests and a native Blender acceptance case.
- `.github/workflows/nvp-production-acceptance.yml`: Linux and Windows native Blender verification jobs including PROD-05; Linux renders a preview and Windows GPU-less runners audit geometry/animation without claiming an image.

## Acceptance gates

1. Python: sequence must be a creator-approved snapshot. Stale world/cameras/dialogue cannot export; incomplete cue coverage and unacknowledged warnings block approval.
2. Python: actor interpolation follows the actual A* polyline, not a straight line through obstacles. Every camera cut starts at a validated integer frame.
3. Blender 5.2.3 Linux: **actual** save/reopen, shot camera IDs, focal lengths, cut timeline marker frames, evaluated actor positions against independently computed samples, and Workbench screenshot at sequence midpoint.
4. Blender 5.2.3 Windows hosted: real save/reopen and evaluated camera/motion checks; **no Workbench preview claim** on a GPU-less WGL runner.
5. Vite production build on Linux and Windows; physical Windows UI and AMD Radeon AI PRO R9700 HIP/Vulkan remain separate acceptance gates.

## Limitations and next engineering target

Current shots use **static cameras** and basic proxy actors. The camera solver's 2D footprint visibility is not a raytraced pixel-space guarantee. 180°/30° checks are conservative warnings, not editing laws. Dialogue has measured duration but there is **no TTS/audio source** and no audio synchronization/export. Assets remain still unless their actor proxy is moved; full animated GLB rigs are not used.

**Next:** NVP-PROD-06 should add rig binding, skeletal motion clips, and/or a licensed CPU-compatible motion library. Then actor performance cards, gaze and visemes can drive performance and editing rather than simply proxy root motion. Real camera trajectories and OpenTimelineIO can follow after verified frame-level scene footage.

This file is a specification and verification record; actual CI results must be reported from GitHub runs, never inferred merely from source presence.
