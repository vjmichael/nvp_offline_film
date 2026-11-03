# NVP-PROD-06E2C2 — Explicit plantar mesh markers and measured floor contact

**Date:** 2026-11-03  
**Architecture authority:** [NVP_MASTER_DESIGN.md](NVP_MASTER_DESIGN.md), performance and independent acceptance rules.  
**Prior verified milestone:** 06E2C1 native candidate foot-region geometry: real Cesium Man lowest weighted region lies approximately 6.8 mm below a nominal Z=0 plane (Linux and Windows), even though ankle IK is stable.  
**Scope:** Read-only real mesh/floor geometry inspection; no automatic pose adjustment, no unapproved character remodeling or Lu changes.

## Why this matters

The previous foot-lock solver correctly anchors anatomical ankle points, but neither a knee/ankle joint nor a skinned weighted region is necessarily a shoe or anatomical plantar contact patch. The actor may still penetrate or hover relative to the actual geometry of a floor. NVP needs independent **surface geometry** and persistent heel/ball/toe identifiers before it can claim contact with the world.

## External engineering and anatomy research (retrieved 2026-11-03)

1. [Blender BVHTree API](https://docs.blender.org/api/main/mathutils.bvhtree.html) supports evaluated mesh proximity/raycast and overlap. It is appropriate for a **later** general polygonal/slope/moving-platform collider, whereas this first adapter restricts itself to the existing explicitly named, flat rectangular NVP floor.
2. [OpenSim Gait2392 documentation](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53086215/Gait%2B2392%2Band%2B2354%2BModels) and the [OpenSim model catalog](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53090607/Mus) provide biomechanical knee/ankle and musculotendon references. Catalog lists the Gait2392 model as CC BY 3.0; this is a **research input**, not an integrated mesh or downloaded software component.
3. [2024 dynamic gait-foot study](https://pmc.ncbi.nlm.nih.gov/articles/PMC11218950/) uses five distinct contact spheres: heel, arch, two ball-of-foot regions, and toes, with chosen positions informed by plantar pressure and anatomy. Shows why three markers are an initial model rather than a full dynamics representation.
4. [Rice University ground-contact modeling tutorial](https://nmsm.rice.edu/guides-and-publications/tutorials/beginner-tutorials/gcp-tutorial/) explicitly uses heel, toe, medial and lateral references and a load-bearing contact surface, supporting more contact points and a body-load model as subsequent steps.
5. [Foot3D](https://github.com/OllieBoyne/Foot3D) reports 118 high-resolution scanned feet and 14 scan/multiview evaluation pairs. The data require a request; **no reuse license is assumed**.
6. [Dryad foot shape-function data](https://datadryad.org/dataset/doi:10.5061/dryad.g4f4qrfwt) includes minimally and fully weight-bearing foot scans and foot/ankle mechanics. Licensing and participant/derivative reuse restrictions must be reviewed per release before importing into a product.
7. [Parametric CT-derived foot CAD model](https://doi.org/10.5281/zenodo.5192130) is listed by the US National Library of Medicine dataset catalog as CC BY 4.0. This is a useful separate anatomical reference, not a directly compatible Cesium Man rig.
8. [SMPL-X academic model license](https://smpl-x.is.tuebingen.mpg.de/modellicense.html) restricts ordinary commercial use, and a separate [SMPL-X Body license](https://smpl-x.is.tue.mpg.de/bodylicense.html) exists. Do not confuse two license categories or assume distribution permission for the full model.

No third-party scanned foot data, body model weights, or other licensed anatomy assets are bundled or committed in this phase.

## Implemented data contract

- PlantarContactPlan is scoped to exactly one film project/scene and the existing director-approved PROD-06E2B ankle-lock + 06E2A imported anatomical identity and take. The SHA digest changes if those approved dependencies change.
- Every actor has exactly two explicit sides, each with a named imported **skinned mesh**, three **distinct original mesh vertex indices** named **heel**, **ball**, **toe**, and an explicit nonempty subset of active markers for contact windows. Marker selection is a *director action*, not inferred from bone names. Source mesh and asset SHA are checked in native Blender.
- Both sides declare maximum penetration, maximum gap and maximum horizontal marker motion tolerances. Floor uses an exact object name, currently **NVP_FLOOR**, and a SHA-256 digest of its observed world-space box vertices. Changes to its transform or mesh invalidate the native evidence.
- Approval requires a revision match, valid input schema, exact actor roster, and current source; old approvals are not silently recycled. Export grants no independent authorization to change animation.
- A separately invoked Blender 5.2.3 process reopens the approved ankle-locked stage, verifies the existing actor/leg/footlock receipts, floor identity, skinned mesh modifier, exact vertex indices, and ankle/toe weight influence. It measures every selected vertex on each frame in the union of the authorized stance windows using the actual evaluated mesh.
- Host-side independent validation compares submitted frame/actor/source/floor identities and computed signed vertical clearance from the actual floor top, XY marker drift and whether each artist-selected active point meets its individual tolerance.
- **Two statuses must remain separate:** the native mesh/floor *measurement* may succeed even if the actual physical-contact *tolerances fail*. Reports must not call a suggested vertex position anatomically correct or physically planted by default.

## Fixture honesty and acceptance

The pinned licensed Cesium Man acceptance fixture has no independently labeled plantar region. It uses a **deterministic engineering-only proposal**: select three distinct low skin-weighted vertices across the projected ankle-to-toe axis. A fixture approval then exercises durable authoring and native validation logic; the chosen vertices are **not certified heel/ball/toe landmarks**.

**Passing this first gate means:** explicit indices survive the real asset import and animation, the floor top and XY bounds are independently measured from the actual 3D stage, and the full contact-window residuals are quantified on Linux and Windows.

**It does not mean:** complete collision-free body geometry, true plantar sole segmentation, exact biomechanics, center-of-pressure, heel-strike/toe-off dynamics, friction, sole tissue compression, joint torque limits, or automatic correction of penetrations. There is no developer-authorized movement change in this phase.

## Code and commands

- backend/nvp_plantar.py — exact authoring schema, approval table, fixture candidate probe, native floor/mesh observer and independent measurement validator.
- tests/test_plantar.py — adversarial schema/source/tamper/geometry/approval validation.
- tools/nvp_prod06e2c2_fixture.py — licensed external rig round trip through 06D → 06E2A → 06E2B, followed by read-only authored-vertex measurement.
- .github/workflows/nvp-production-acceptance.yml — native Linux and Windows Blender 5.2.3 acceptance.

Run Python tests: `PYTHONPATH=. python -m unittest tests.test_plantar -v`.

Run licensed native acceptance: `PYTHONPATH=. python -m tools.nvp_prod06e2c2_fixture --out acceptance_artifacts/prod06e2c2 --external-glb /path/to/pinned/CesiumMan.glb`. Add `--audit-only` on headless Windows.

## Follow-on engineering gates

1. Establish an **artist-certified plantar mask or heel/first-and-fifth-metatarsal/toe surface anchors** in stable mesh-local coordinates, versioned by character and representation.
2. Replace the flat-box-only floor adapter with a verified named mesh/BVH collider and signed surface distances for slopes, props, multiple surfaces and moving platforms, without allowing unknown support geometry.
3. Solve actual pose/contact corrections subject to ankle/knee direction, bound-checks, pelvis/root continuity and independent **full skinned mesh** penetration testing.
4. Benchmark static stance, heel-strike/toe-off, rolling contact, walking/turning roots, stairs, changing floors, camera consistency, and purposeful artistic overrides.
5. Distinguish visual anatomy, biomechanics and movement quality rather than conflating one metric with finished realistic acting.

**Stage status:** real native acceptance must pass before asserting a verified read-only geometry adapter. Only a separately accepted geometry correction/biomechanics gate can claim production-quality sole contact.

## Measured native acceptance — 2026-11-03

[GitHub Actions run 41665538274](https://github.com/vjmichael/nvp_offline_film/actions/runs/41665538274) completed the individual new PROD-06E2C2 native Blender 5.2.3 stages on **Linux and Windows** successfully, using the pinned third-party Cesium Man, the independently audited real ankle-locked .blend, original character skin weights, and the actual NVP_FLOOR object. A separate regression revealed an incorrect exception type for approval of an empty draft; corrected in the following revision. Do not treat the initial workflow as globally green.

The selected synthetic fixture-proposed marker positions (unverified anatomical labels) were measured relative to the **actual floor top Z = 0.0 m**:

| Marker | Linux left | Linux right | Interpretation |
| --- | ---: | ---: | --- |
| Proposed heel | +0.11314 m | +0.11324 m | Far above contact, wrong for a planted heel |
| Proposed ball | +0.07396 m | +0.07405 m | Above contact, wrong for a planted metatarsal pad |
| Proposed toe | -0.006823 m | -0.006729 m | About 6.8 mm below floor |
| Maximum marker XY shift during contacts | 0.0 m | 0.0 m | Static fixture stance only, not walking evidence |

The Windows native run independently returned the same overall measured status: **passed_native_plantar_floor_measurement_only**, **contact_meets_configured_tolerances=false**, and **anatomical_sole_certified=false**. This is a *successful failure detection*, not an accepted physical foot placement. The heel/ball labels are particularly unreliable because the fixture uses only skin weights and approximate toe-axis sorting. Creator-approved plantar marker placement, a validated anatomical mesh, or genuine ground-truth marker labels are necessary before changing the solver to follow these contacts.

For the future *accurate architectural structures* track, current external references include [IfcOpenShell/Bonsai](https://github.com/IfcOpenShell/IfcOpenShell) for typed IFC building geometry and [Poly Haven](https://polyhaven.com/license) for CC0 scanned textures, HDRIs and 3D props. These are candidate set-production inputs with their own license and version verification—not packages silently installed or integrated into NVP.
