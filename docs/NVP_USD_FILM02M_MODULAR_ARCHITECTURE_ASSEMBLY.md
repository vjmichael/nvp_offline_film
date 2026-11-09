# USD-FILM-02M — modular, parameterized architectural asset composition

**Status:** Approved creator concept, **design task recorded and implementation deferred** until USD-FILM-01 family source→render integration; HSURF stays deferred until the USD-FILM work family is completed. This is filmmaking set construction, not procedural game-level generation or real-world geographical truth.

## Core idea

A building need not be one indivisible model. It may be composed from original, reusable, independently revisioned parts: **street-facing façade**, rear and side wall modules, structural floor/roof, corner/frontage pieces, storefront/door/window bays, stair/elevator cores, interiors, trim, signage, weathering and distinct material/decoration variants. The parts are true reusable OpenUSD source assets; scene placement uses references/payloads/variants/instances in the persistent NVP world and source-locked FilmIndex manifest.

The system can mix and match **compatible, named modules**, using actual dimensions and connection orientation. Example: a 12 m wide street frontage has 3 × 4 m architectural bays; an upper floor socket and roof edge accept only the defined compatible connectors. The camera-facing façade may carry more geometric and texture detail than the rear/hidden body, but both remain original project-owned sources with geometrically valid corners and parallax. Repeated assets may be USD instances; shot-specific damaged/unique buildings require distinct authored source/overrides as needed.

## Proposed typed module contract

- `building_module_id`, exact `revision`, `document_sha256`, `role` (`facade`, `core`, `floor`, `roof`, `corner`, `bay`, `interior`, `trim`, `window`, etc.), `style_family` and optional director constraints.
- Native **metre units, Z-up** local anchor and actual, verified geometry bounds: `size_m: [width, depth, height]`; a *bounding box alone is insufficient* to certify physical fit.
- Named, oriented **connector sockets** with transforms, outward normals, span dimensions, connector type/gender or symmetric fit policy, story height, tolerance and required clearance. Rotations must obey typed allowed orientation/handedness; disallow silent nonuniform stretching of doors, windows, stairs or human-scale features.
- Material slots and PBR/MaterialX compatibility, UV/UDIM conventions, LOD and shot-quality variants with separate original SHAs. No missing/fabricated textures or exterior/interior light leaks.
- Reuse metadata including variation family, repetition limits, compatible climate/architectural style (art direction, not asserted geographical accuracy), and semantic interior/exterior relationship.
- Source authority: project/ActorID links if applicable, exact source layer and FilmIndex project, original approved director world/take reference and immutable output module-placement manifest. **Never trust an AI-supplied arbitrary filesystem/URL reference.**

## Deterministic assembly algorithm (planned, not implemented)

1. Read the director's region/lot/height/story count/style constraints and **exact approved original module catalog** through a bounded native query.
2. Choose compatible base modules: foundation/core + street frontage + optional bays/side walls + floor/roof. Only assemble if each touching connector pair has matching type, orientation, spans and tolerances; reject overlaps, open gaps, unsupported support load assumptions, invalid doors/egress/scale where important to the film image.
3. Use an explicit **seed** and original source revision list to choose among allowed variants. Save the deterministic ordered solution, not just a seed; record module and solver version hashes. Different seeds are new candidate art-direction alternatives, not edits to previously approved geometry.
4. Produce a **disposable OpenUSD proposal layer** with references/variants/payloads and named transforms. Reopen it with genuine USD, compare bounds, connectors/UVs, mesh normals/materials and relevant visible geometry. No acceptance based merely on syntactically valid USDA.
5. Evaluate actual NVP camera distance, screen coverage, required silhouette/interiors and director art direction. Distinguish visually important street frontage from a low-detail back **without hiding a background object's absence in reverse angles**. Build camera-specific derived set views only after the original building is complete/verified.
6. Present controlled procedural alternatives for director selection, verify real Blender/Cycles pixels of multi-angle street and reverse shots, then commit a new immutable FilmIndex asset/world revision. Changes in the module catalog invalidate affected derived caches; past Takes retain exact old module versions.

## Building-cell interface

Partition full architecture into **set/cell assets**, not arbitrary cell-only identity: an individual building can span multiple cells, but its authoritative world transform and module graph have one original identity. Stage reusable façade tiles and background architecture through USD references and PointInstancer where safe. Load/unload governed by camera cells with **hysteresis**: a cell stays loaded after crossing the load radius and unloads only beyond a larger release threshold. Director-required sets and next shot/source Takes always override culling, avoiding flicker and vanished actors. Distinguish distance-based heuristics from true camera frustum/occlusion geometry; don't claim HLOD or VRAM paging without real render evidence.

## Acceptance workgroup (OPEN)

- **02M-A** catalog/module/socket/schema with true source/mount and unit/axis tests; reject wrong facades, roof spans and invalid orientation.
- **02M-B** deterministic seed-backed assembly and source SHA manifest; audit collision/gaps and modules across Windows/Linux and reload, test source revisions.
- **02M-C** real native OpenUSD reference/payload/variant composition for ≥4 visibly different street buildings sharing original parts and preserving exact source identities.
- **02M-D** source-aware procedural variation, original exterior/interior relationships and set/cell boundary integration with 01C/01D.
- **02M-E** Blender/Cycles multi-angle/reverse-shot render of identical saved building source, source/MaterialX look verification and creator review; no acceptance on a front-only façade still.
- **02M-F** AI-native `compose_building`, `query_compatible_modules`, `preview_variants`, `approve_assembly`, `undo` through existing WO6/USD-FILM-07 host-supervised operations and director creative decisions.

**Priority:** complete ongoing USD-FILM-01F native world-to-render work and the wider USD-FILM sequence first; HSURF-00 and the full Human Surface / AI Material Authoring program remain explicitly **deferred until the USD-FILM family is finished** per creator instruction. 02M is a queued USD-FILM-02 geometry feature, not a new NVP product branch.
