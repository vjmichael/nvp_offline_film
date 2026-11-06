# USD-02C — Time-sampled performance channels in the persistent OpenUSD scene

**Creator-approved architecture:** NVP's film scene is persistent in space, its performances are continuous in time, and shots are time-bounded camera observations. A chair is one immutable asset definition, with separately placed **instances** referencing it. Shots do not duplicate the world. NVP remains a data-first filmmaking system capable of producing multiple visual presentations from the same frozen film performance.

**Implementation status:** Native OpenUSD attribute channel authoring, immutable composition, scene state, Digital Take checkpoint freeze and alternative presentation plans are coded. Actual Windows/Linux Python 3.11/3.13 native CI is an open acceptance gate.

## What USD-02C actually implements

`backend/nvp_openusd_channels.py` implements a tightly bounded typed metadata channel contract, separate from the existing USD animated transform curves. Scene objects can author numeric time samples on exact film-time ticks:

- `face.<parameter>`: actor-only scalar 0.0–1.0, useful for expression control;
- `joint.<joint_name>`: actor-only angle in degrees, -180..180, intended as an authoring control, **not** a complete skeletal rig;
- `camera.focal_length_mm`: camera-only scalar 1–300, semantic focal parameter, **not yet** mapped to an actual UsdGeom.Camera optical property;
- `camera.focus_distance_m`: camera-only scalar 0.01–100000;
- `light.intensity`: light-only scalar 0–1000000, **not yet** a UsdLux powered light;
- `light.temperature_kelvin`: light-only scalar 1000–40000.

Each channel has exactly a declared scene path, typed property, and 2–2048 strictly increasing time/value keys. All values are finite and within known bounds. Duplicate channels, incompatible scene roles, arbitrary property names, and invalid event ticks fail closed. NVP uses **native OpenUSD `UsdAttribute.Set(..., Usd.TimeCode)`** and `Get(time)`; no 2D samples are created and no homegrown interpolation algorithm is substituted for USD's time sample semantics.

A scene with channels gains a separate strongest `nvp_parameters.usda` layer above motion and layout. Its layer SHA and manifest of typed property names are retained in immutable FilmIndex scene revisions. A scene **without** channels retains its older USD-01 two-layer composition format. This is an additive, backward-compatible schema path, not a migration that silently changes frozen work.

The temporal state evaluator now retrieves the native evaluated channel values alongside exact USD transforms and Temporal Ledger active event records. The Digital Take checkpoint freezes the parameter-layer SHA and channel descriptors, then incorporates their evaluated time-state values into the take checkpoint digest. The full `verify_take` operation independently recalculates and compares these values. The interactive presentation planner samples the same frozen channels for 24/60 fps styles without scanning the full film event ledger or rendering a picture.

## Boundaries and next tasks

**Not yet built:** a complete skeletal hierarchy, joint transforms, retargeting, facial blendshape geometry, teeth/tongue/lip articulation, optical lens behavior, physically based USD lights, motion interpolation choices beyond native scalar time samples, IK/contact correction, cloth, physically based camera exposure, voice/sound synthesis or full renderer integration.

These performance **control parameters** are valid data but do not by themselves deform a face or operate an actual light. The next step is native `UsdSkel` + `UsdGeom.Camera` + `UsdLux` bindings with explicit topology, time-sample evaluation, deterministic preview/render agreement, and freeze/verification of corresponding source data.

Original recorded footage still requires an independent PTS/frame adapter; NVP's authoring timeline does **not** become frame-based because an editor or final DCP selects a frame rate.

## Validation

`tests/test_nvp_openusd_channels_native.py` runs the actual `pxr` OpenUSD runtime. It tests four concurrent property channels (smile, head yaw, focal length, light intensity), exact midpoint interpolation, reopen and deterministic state digest, frozen checkpoint source integrity across later scene revisions, one take serving 24 and 60 fps presentation plans, role mismatches, duplicate channel refusal, nonfinite values and prior two-layer format compatibility.

`.github/workflows/nvp-usd02c-native.yml` requests Windows 2025 and Ubuntu 24.04, Python 3.11 and 3.13. It installs the pinned `usd-core==26.11`, runs the actual native channel suite, plus previous USD-01 and USD-02 regressions. Native acceptance is OPEN until green at the exact latest commit, including licensing/packaging audits before any Windows installer ships.

**Release policy:** Keep original asset identity and frozen take references; avoid duplicating source geometry for new shots. NVP OpenUSD TOST 1.0 attribution and exact bundled wheel dependency audits remain installer gates, as previously documented.
