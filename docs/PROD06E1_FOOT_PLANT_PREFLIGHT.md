# NVP-PROD-06E1 — Deterministic two-leg foot-plant preflight

November 2, 2026. NVP Film Workspace only. No Lu changes.

## Baseline and scope

PROD-06D established a real imported rig, director-approved rest-frame
retargeting, explicit seven-role joint ceilings, proportional height adaptation,
whole-clip skin deformation and an independently reopened Blender geometry audit.
Its `contact_frames` report the **lowest mesh point**; they are not semantic
left/right ankle or planted-foot observations. They do not prevent sliding.

This stage introduces a small, pure-Python **preflight math layer** without
altering existing approved production output or falsely claiming native IK.

- `backend/nvp_foot_ik.py`: analytic 3D two-bone solver (`hip`, `knee`, `ankle`,
  pole hint, upper/lower segment lengths), explicit bend plane, exact segment
  lengths and measured flexion; fails closed on unreachable or singular targets.
- Dense frame-by-frame world-space biped planner; separate left/right authored
  stance windows, world XY anchors from first frame of each window, fixed ground
  Z, per-frame residuals and hard maximum correction.
- Refuses nonfinite/bool coordinates, missing leg samples, sparse samples,
  overlapping/out-of-window stances, degenerate poles, impossible reach and
  foot corrections above a declared bound. Does not silently clamp/extend bones.
- Retarget approval SHA is an **optional reference**, not independently checked
  authorization. Existing `RetargetCalibration` approvals remain authoritative.
- No new UI or public API endpoint and no production change to the Blender
  output. There is intentionally no preview or native-geometry pass claim.

## Acceptance and measured CPU baseline

`PYTHONPATH=. python -m unittest tests.test_foot_ik -v`

Ten deterministic checks pass locally on Python 3.13.5. The 2,400-frame,
two-foot preflight ran in approximately **0.106 seconds** on the current
container (one run, not a performance SLA). The benchmark exercises
4,800 analytic solves, verifies reproducible exact JSON-compatible results,
and keeps drift within the declared correction budget.

## Requirements to close PROD-06E (not yet accepted)

1. Add creator-controlled **separate** left/right foot, shin, thigh and knee-pole
   bone maps to the imported rig, with rest-matrix and chain-parent verification.
   Do not silently infer anatomy from the previous seven-role calibration.
2. Bind windows and explicit foot chain choices to an immutable project/scene
   approval and the current PROD-06D approval digest; refuse stale or cross-
   project changes.
3. Build an isolated Blender foot-plant adapter, then re-open the saved `.blend`
   and independently audit foot-marker sliding, ground clearance, upper/lower
   bone lengths, knee orientation, joint ceilings and unchanged root/camera keys.
4. Repeat with the pinned, licensed Cesium Man regression fixture on Linux and
   Windows; accept audit-only on headless Windows, render PNG on Linux.
5. Measure full Blender throughput, peak memory and identity/approval invariants;
   compare baseline (retarget only) against foot IK on identical sample frames.

**Status: PROD-06E1 CPU mathematical preflight implemented; PROD-06E native
foot IK and real-character performance acceptance are NOT complete.**
