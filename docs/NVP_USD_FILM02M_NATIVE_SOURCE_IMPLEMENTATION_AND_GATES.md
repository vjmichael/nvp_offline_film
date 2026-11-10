# USD-FILM-02M A/B/C — real source-locked, modular 3D architecture

**Implementation status:** 02M-A/B/C code and real native acceptance
workflows committed. Actual Win/Linux OpenUSD test results and authentic
Blender/Cycles images remain **OPEN**; 02M-D/E/F further integration
and creative acceptance are not claimed.

## Creator design

A director assembles a reusable, multi-angle, real 3D building from
street façade, rear, side walls, corners, floor, roof and later
interior/window/storefront detail modules. Each is genuine reusable
FilmIndex-authored native OpenUSD mesh content. The building persists
as a deterministic assembly graph, not as a text-only image or a
single textured flat façade. A director may swap façade appearances
without refilming an existing actor performance or rewriting the
previous approved world revision.

The **current bounded implementation** accepts 6–48 modules per
building, 1–8 explicitly enumerated equivalent source candidates
per slot, up to 16 typed connectors per module, cardinal Z-up yaw
rotations (0/90/180/270), explicit seed and exact source asset ID,
revision, document SHA and USD layer SHA. Future more expressive
per-shot construction remains limited by actual NVP project memory.

## 02M-A: source-preserving module catalog and real fit contracts

`backend/nvp_usd_film02m_modular_buildings.py` reuses
`OpenUSDAssetRegistry` and `FilmIndex` only. Every original module
has a first-party `style` revision with one exact `asset` dependency,
real native triangle mesh and verified body dimensions in metres.
The declared bounding box must match actual 3D mesh point bounds
in the source layer. Its socket metadata has:
- name and type, gender (male/female/universal);
- three-axis local metre position on an actual mesh boundary face;
- unit cardinal outward normal, physical span in metres and ≤2 cm
  fitting tolerance;
- physical role and same approved style family for alternatives.

The host binds the proposed module manifest SHA, source mesh revision
and originating asset SHA into an explicit director approval. Foreign
USD/URL references and browser-selected file paths never enter this
catalog. Nonuniform dimension stretching and free-angle rotations
are not accepted in this first reviewed assembler.

## 02M-B: deterministic candidate assemblies

The ordered original building blueprint starts at one true floor.
Every next module must explicitly name its existing parent, parent
and child sockets, quarter-turn yaw and a bounded set of approved
source module alternatives. The selected option index is derived
from a SHA-256 hash of seed + node ID + exact candidate list. Saving
a **world** FilmIndex revision records:
- original seed and complete blueprint,
- EVERY selected module ID/revision/source SHA and candidate option;
- exact local metre position/yaw, authored connector pairing and
  translated real 3D bounding extent;
- original module dependency edges, selected source style and
  native USD root-layer byte SHA;
- genuine source mesh count and native composed layer reference receipts.

All source modules must be the same compatible style family, and
a building must include a floor, façade, rear, **two sides**, and a
roof. Touching face seams are accepted, but volumetric overlapping
solid module bounds over the 2 cm fit limit are rejected. Missing
connectors, rotated normals facing the same direction, mismatched
spans, missing original mesh, source identity changes, invalid USD
prim names and denied director operations fail closed. This is
source/geometry integrity, **not** structural load capacity,
fire-code correctness, watertightness, inhabitability or proof
of accurate architectural engineering.

A different seed or director blueprint produces a **new immutable
world revision**. Prior approved versions and their source
dependencies survive unchanged.

## 02M-C: real native OpenUSD reusable references

`open_proposal` and `open_building` stage original source asset
USD layers by content SHA in a private disposable directory. The
composed root is 1 metre per unit, Z-up, and creates a genuine
`UsdGeom.Xform` per source module with reviewed placement/rotation
and an **OpenUSD reference to that same original /Asset source**.
Neither model-supplied absolute paths nor unverified package
contents are trusted. The native stage is saved and reopened,
verifies the source-authored `UsdGeom.Mesh` for every module
under `/World/Buildings/<ModuleNode>/Geometry`, tests native
vertices/triangles and checks root USD file SHA again on subsequent
world revision open. Original source assets are not overwritten
by any derived assembly.

The source test creates FOUR distinct saved building world instances
in true 3D with different facade color/material source revisions,
shared floor/rear/sides/roof/corner modules, real world metre-scale
placement and the same original building style family. Test stages
are rebuilt through independently reopened FilmIndex records and
real `pxr` OpenUSD references. A building is not accepted from
a matching manifest alone.

## 02M-E initial genuine multi-angle rendering smoke — native proof OPEN

`tools/nvp_usd_film02m_blender_three_views.py` is a fixed first-party
Blender worker. The existing SHA-pinned NVP `BlenderWorkerSupervisor`
receives a real native assembled building stage and independently
pinned original USD assets. A genuine Blender 5.2/Cycles CPU import
must reveal 10 separate original 3D module meshes and at least
120 actual mesh faces, then render **front, rear and oblique**
technical images (320×180, eight samples) from one identical
saved assembly. Three different PNG SHA values plus a native
audit are required. No synthetic procedural PNGs or screenshots
are counted as native evidence. A temporary render sun/ambient
is *technical lighting scaffolding*, not an edit to original
film world/actors. If Windows/Linux/Blender does not complete
and the images are not independently reviewed, source alone
does not close 02M-E.

The source and Blender CI are in:
`.github/workflows/nvp-usd-film02m-modular-architecture.yml`.
The workflow tests native OpenUSD sources on Windows 2025 and
Ubuntu 24.04 with Python 3.11/3.13 and uses upstream-SHA-verified
official Blender 5.2.3 on Ubuntu for three genuine pictures and
downloadable native audits/scene artifact.

## Work still open

1. Actual exact-head CI, source reflection/renderer import repairs,
   independently checked front/rear/oblique Cycles pixels and
   director assessment of visual quality, seams, appearance and
   camera-correct parallax.
2. **02M-D** strengthen interior/exterior relationships, real
   window/storefront openings (not solid facade boxes), procedural
   bay/floor counts, building shell closed-boundary verification,
   source-aware art-direction variants, world/cell streaming and
   retained-camera shot views. No claim of functional doors,
   stairs, architecture load limits or sealed physics colliders yet.
3. **02M-E** measured repeated rendered geometry, PBR/MaterialX
   parity, real lights, textured materials and original audio/scene
   context. The first 3-angle smoke is not finished cinema quality.
4. **02M-F** expose constrained `compose_building`,
   `query_compatible_modules`, `preview_variants`,
   `approve_assembly` and `undo` through the existing
   trusted NVP director/WO6 host and typed AI execution broker.
   No free-form AI file writes or implicit creator approvals.
5. Reintegrate modular building sets with the existing 01C/01D
   camera-driven scoped USD working sets, 01Q/01T original film
   source and installed 01R director editor, then obtain actual
   installed scene performance and full original film acceptance.
6. Complete the essential USD-FILM 00–10 native, temporal, 3D
   visual, sound and director creative gates before HSURF-00.

**Scope:** An offline film-set construction system, not a city-wide
physical infrastructure or standalone architectural CAD product.
