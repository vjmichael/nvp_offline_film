# USD-FILM-02M-D — Real 3D door/window geometry, reusable interiors and camera-aware native cells

**Status: SOURCE IMPLEMENTATION + NATIVE TESTS/BLENDER WORKFLOWS COMMITTED.**
Actual Windows/Linux source results, Blender output and installed interactive
director acceptance are **NOT YET VERIFIED**. An authored camera, a passed
ray test or a queued GitHub job does not itself prove cinema-quality picture.

## What the director gains

NVP's original building is **real data, not a facade-only camera illusion**.
The same approved OpenUSD geometry can be viewed from the street, across a
window, through an open doorway, inside the room, behind the building and from
above. An aperture is **actual removed wall topology**, not opacity or a
camera mask. Interior rooms have true walls, ceilings, floors and a rear;
their **front wall is deliberately open** to the original exterior doorway.
The parent building's exterior side and rear modules still occupy real 3D.

A building can have different façade treatments, numbers of storeys
and window bays. The director's exact alternatives/seed/source modules
determine its geometry. NVP saves the complete authored source
manifest and actual chosen geometry so an old Take never changes
when a later version gets a new storefront or interior.

## 02M-D1 — actual source apertures and procedural variations

`backend/nvp_usd_film02m_d_openings.py` adds a reviewed geometric
wall mesh generator for source-authored window/door/storefront
rectangles. Given metre-scale overall width, thickness and height,
the generator partitions the real wall into solid cells and physically
omits void cells from the original indexed triangle mesh. It builds
front/back wall faces **and real internal thickness/jamb triangles**;
no source transparency map, absent facade or stand-in image.
Window borders retain an actual physical pier/sill and doors touch
the original floor boundary. Misplaced, overlapping, oversized,
off-wall or undersized apertures are refused.

The independent `original_through_opening` barycentric triangle-ray
check probes the actual original wall geometry at multiple points in
each source aperture, and also demands a solid outer wall pier.
A fabricated "opening" JSON with a fully solid wall **fails**.
This is a CPU source-geometry test, not false pixel-level ray
tracing acceptance.

`facade_layout` deterministically authors 1–4 storeys, 2–6 bays,
three reviewed treatments (`residential`, `shopfront`,
`industrial`) and an explicit director seed. It records every
physical door/storefront/window's dimensions and position. Alternate
source seeds are distinct, reviewable **original mesh designs**,
not last-minute texture substitutions. The fixed source mesh
budgets from `OpenUSDAssetRegistry` still apply.

## 02M-D2 — source-authored interior and immutable design records

`room_shell_mesh` writes a true 3D room with source floor, ceiling,
two sides and rear wall, and an intentionally open front portal.
A wall aperture leads to a real authored interior; it does not
require separately capturing a new actor performance. Interior
is a reviewable **reusable original module** under 02M's normal
connector, scale, style and parent-socket rules. Its bounds must
not collide with source exterior wall/roof/floor modules.

`publish_facade_with_detail` and `publish_room_with_detail`
create an ordinary first-party native OpenUSD **asset** and
a separately immutable FilmIndex **presentation** design
record, preserving the exact authored layout/seed/source asset
ID/revision/document SHA, USD layer SHA and original geometry
fingerprint. The existing `OriginalBuildingKit.publish_module`
now optionally requires the exact source design record and pins
it into a second FilmIndex dependency before the director approves
the module revision. Reopening a module regenerates its original
geometry from source parameters and verifies EVERY authored
vertex/triangle and immutable SHA. Older 02M source modules
remain compatible; no frozen asset layer is silently overwritten.

The original asset author now explicitly writes **1 metre per USD
unit and Z-up** metadata, and verifies it on reopen for newly
authored source assets. Historical immutable assets that predate
those metadata fields remain readable unchanged.

## 02M-D3 — actual native OpenUSD cell loading, retained shots

`backend/nvp_usd_film02m_d_cells.py` publishes a typed
`presentation` revision listing 1–16 exact original 02M
building worlds. A cell pins the building's immutable world
revision/SHA, complete original source 3D bounds and native
mesh count. A native load opens each building through the old
02M source verifier, stages ONLY SHA-verified project-owned
`building.usda` and `assets/<SHA>.usda` files in a disposable
directory, and builds a real USD stage with one **payload**
per cell. All cells initially start unloaded.

The camera working set uses **two thresholds**: a smaller
load distance and a larger unload distance. This hysteresis
avoids chattering while a camera moves along a cell border.
Optional near-camera cells fit within a configured cap;
**current director-required and next-shot-required source
buildings are always loaded**, even if outside distance
thresholds. Too-small capacity fails closed instead of
silently hiding required architecture.

The host may supply an **actual 01M camera bank revision,
camera ID and bounded original Film Time frames**. NVP uses
native UsdGeom camera transforms, not guessed camera positions,
to calculate distance-based prefetch. But **these are still
prefetch hints**: frustum/occlusion solving is not claimed,
and integrating the 02M building world into an *actual 01E
frozen actor Take/01D shot* remains a separately open task.

An optional actual OS process-RSS budget is checked before
and after source USD loads. If an original payload is invalid,
RAM exceeds the cap or geometry fails reopen, NVP tries to
roll back to the prior true loaded native cell set and verifies
that rollback. If rollback itself fails, the session is closed
rather than returning a false picture/approval receipt. Process
RSS is not claimed to be USD-only VRAM or exact renderer
memory attribution.

## Independent native acceptance

New tests live in
`tests/test_nvp_usd_film02m_modular_buildings.py`:

- Actual 1/2/3-storey source façade through-wall triangle
  geometry, three architectural treatments, transparent
  voids with solid jambs and painted-fake-window refusal.
- True FilmIndex original source asset plus reproducible
  aperture/room detail revision; approved 11-module building
  with a reused floor, genuine front aperture, actual rear
  room and tested original 3D scene reopen.
- Three genuine source city buildings with different façade
  types, persistent original cell manifest, actual USD
  payload load/unload, checked native mesh counts, retained
  director/next-shot sets, over-budget capacity refusal
  and a simulated independent RSS trip that forces
  actual native rollback.
- Genuine Blender 5.2 native source/technical Cycles test
  `tools/nvp_usd_film02m_d_blender_aperture_smoke.py`:
  reopen same 11-module USD building, raycast an original
  door into the real room rear and a pier against the solid
  original façade, then render actual 320×180 eight-sample
  **doorway, interior and rear-angle** PNGs. Three
  distinct image SHA values and source/Blender worker
  receipts are required, then visual review by director.

`.github/workflows/nvp-usd-film02md-real-openings-interiors-cells.yml`
runs the real `pxr`/FilmIndex source suite in Windows 2025 and
Ubuntu 24.04 with Python 3.11 and 3.13, and a separate official
SHA-verified Blender 5.2.3 Ubuntu true camera/source render.
The artifact is a real Cycles picture set **only after the
native OS job has actually completed**, not a generated claim.

## Still open

1. Exact-head CI and any actual native compiler/runtime failures.
   Source code or a queued workflow does not close this gate.
2. Inspect actual three camera angles for interior visibility,
   correct light transport through opening, proper geometry seams,
   roof/side occlusion and honest real-glass look; repair native
   Blender/USD importer differences before visual acceptance.
3. **02M-F** actual installed director/AI-native typed operations,
   interactive 3D building editing and reviewed approval/undo.
4. Integrate assembled original source buildings into the same
   01E world Take and **01D** source set/camera admission as actors.
   Cell prefetch is source-verifiable but not yet an original
   film-world, shot-to-shot scene composer.
5. Improve materials, real door/window trim/glazing, multi-storey
   floors/stairs, physical geometry intersections, room partition
   continuity, architectural structure and actual human film look.
   These are not being declared production-grade architecture.
6. Existing 01T authentic 720-frame original film + source PCM
   render remains separately queued/unaccepted, as do 00–10
   USD-FILM integration gates. HSURF-00 remains deferred.

**No buildings are declared structurally safe, inhabited or cinema-ready.**
