# NVP-PROD-06D — Rest-frame retargeting and independent external character acceptance

November 2, 2026. NVP Film Workspace development only. **No Lu changes.**

## Motivation

PROD-06C proved a previously exported NVP preview GLB could be re-imported and driven by exact bone mapping. That does **not** show that independently authored humanoid skeletons work. Their rest bone axes, joint lengths, animation tracks and mesh dimensions differ. Passing a same-rig round trip is not production retarget acceptance.

## Implemented contract

- A separate project- and scene-scoped SQLite calibration plan is built only from a currently approved PROD-06C character plan (which itself depends on the approved PROD-06B skin and PROD-06A motion).
- Every actor has seven **explicit**, bounded joint ceiling values in degrees, director-selected contact frames, contact tolerance and ground penetration allowance. Updates require optimistic revision checks. A separate approval receipt pins the complete plan and upstream character SHA. Approval is not silent.
- Blender reads **actual imported bone rest matrices** and transforms the approved source quaternion into the target bone's rest coordinate system using `q_target = align * q_source * inverse(align)`. The preview rig remains; approved actor root paths and shot-camera timelines are unchanged.
- The imported visual geometry is independently scaled to the existing actor's approved height, and aligned at the initially designated contact frame. No source asset or root motion is rewritten.
- Native Blender reopens the result and independently audits rest-basis quaternion agreement, explicit angle ceilings, actual armature modifier, measured mesh deformation, ground clearance, declared foot-contact frames, provenance/approvals and target body height. An audit failure remains a failure; Windows hosted CI may omit the GPU-dependent Workbench render but must complete the geometry audit.
- The licensed source GLB and approved motion files are content-addressed. The source animation (if any) does **not** become an authorized NVP action. No Blender code is executed from model payloads; only NVP's fixed exporter and audit scripts run under the trusted test host.
- The API exports a self-contained ZIP with the source GLB (if already registered), license report, approved calibration and fixed build/audit scripts. A React development panel exposes calibration controls.

## Independent reference model: Cesium Man

The regression fixture is **Cesium Man**, from KhronosGroup/glTF-Sample-Assets, pinning upstream commit `8f492390ddc7a2ae221a1369ef560589cf8c70fb` and source blob `8586c4e6a59bf8ef585c2a685c50a80d28503216`. It is explicitly credited to **Cesium**, CC BY 4.0. The model includes a Cesium logo/trademark caveat and must not be redistributed as NVP branding or presented as a production-ready original character. The GitHub workflow downloads it temporarily for CI, verifies its Git blob SHA1, and normalizes away the embedded animation using trusted Blender. NVP then registers the derived test GLB with its own digest and the correct upstream source citation. This asset is *not included in the NVP source repository*.

The seven exact joint assignments for this external fixture are defined in `tools/nvp_prod06d_fixture.py`. They are for a frozen test only; the consumer UI requires explicit director bone mapping and does not silently guess among unrelated rigs.

## Current known limits

- This is bounded seven-role retargeting of approved quaternion rotations, **not** general humanoid rig inference, mesh weight painting, corrective shape keys, realistic locomotion, facial animation, automatic prop interaction, a physical IK gait solver, or production-grade performance.
- The joint ceiling is an engineering safety/quality check. It is **not** a medically based human joint model.
- Foot contact is measured as the lowest evaluated mesh vertex against the configured floor. That is a conservative geometric proxy, **not** semantic foot identification or physical ground-reaction simulation.
- A single static initial height and floor alignment may fail when the model's authored origin, footwear, rest pose, or active geometry differs. Fail closed and provide the audit residuals.
- Source bytes still require OS process containment before accepting arbitrary untrusted production assets. The declared asset license is not legal certification.

## Acceptance

Local: `PYTHONPATH=. python -m unittest discover -s tests -p 'test_retarget*.py' -v` and `test_external_retarget.py` (native asset test skips if source absent).

GitHub: Linux and Windows CI must download and hash-verify Cesium Man, normalize the original animated GLB, then build an NVP director-approved character, run the post-retarget Blender script, re-open and audit. Linux additionally renders a PNG. **Do not mark external acceptance complete before reading the resulting audit.**
