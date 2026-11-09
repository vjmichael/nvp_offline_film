# USD-FILM-02M-E1 — Generated district layers, director overrides and true USD PointInstancer source

**Status:** first-party source implementation and exact-head native OpenUSD
tests committed. **Not yet native-verified**, installed-editor accepted or
rendered through real Blender/Cycles. This is a small film-district generator,
not a complete city, a VR engine or an independently verified GPU performance
improvement.

## Why NVP is doing this

NVP's data-first world lets a director use one immutable source building
prototype in many positions. The source is not many camera-dependent
photographs. One imported building revision can support street, interior,
rear, aerial and future virtual viewpoints; a procedural repetition changes
only the assembled presentation of source data.

The three creator-provided Claude notes (OpenUSD data-first, compile/tool layer
and regional streaming) recommend source L1 state, authored layer strengths,
PointInstancer for repeated prototypes, deterministic generated districts,
manual overrides, per-cell budgets and local origins. All are directionally
useful; **headset runtime conversion, Quest GPU limits, 3D Tiles and VR output
are a different product/deployment target**, not a blocker for an original
offline NVP film.

OpenUSD itself stores composition, geometry, time samples and authored camera
views. Real production Blender/Hydra renderers execute pictures. Where a
future VR application needs runtime streaming, the runtime engine owns that
streaming after an explicitly verified compile; native USD cell payload
editing/preview in NVP is a different operation.

## Genuine source implementation

`backend/nvp_usd_film02m_e_district.py` introduces
`OriginalFilmDistrict`. It only accepts 1–8 exact previously director-approved
02M building `world` ID/revision dependencies. It opens each through
`OriginalBuildingKit.open_building` and derives real mesh vertex and
triangle counts, physically authored source bounds, immutable world document
SHA and saved USD layer SHA. No arbitrary USD path or internet source.

`plan` accepts exact explicit seed, 1–16 columns, 1–16 rows
(max 256 original building placements), lot pitch in metres, a local
cell-world origin, per-district source triangle and instance budgets,
and 0–64 director-authored operations. One SHA(seed, slot, exact source
candidate hashes) chooses each approved building prototype deterministically.
The original source prototypes MUST have a local [0,0,0] floor/root.
World origins can be large, but instance offsets remain bounded small
local metre values to limit float32 loss.

**Source budget admission** counts actual OpenUSD mesh triangles from each
original building and estimated per-instance source mesh equivalents,
not invented device GPU draw calls. District publication rejects oversize
source triangles, too many instances, invalid bounds, insufficient lot
spacing, unrecognized source buildings, fake source revisions and overlapping
manual placements. A true *visible-triangle* runtime budget, real
texture-memory inventory and renderer GPU timings remain unverified.

## OpenUSD layer stack, strongest to weakest

1. `district.usda`: composition root. Explicit 1m/Z-up and a
   content-hashed original district plan/origin metadata string.
2. `director.usda`: **stronger**, contains only `invisibleIds`
   opinions for exact generated PointInstancer IDs and additional
   approved director manual source-referenced building placements.
   A manual adjustment changes this layer and a FilmIndex revision,
   never silently regenerates or rewrites the weaker layer.
3. `generated.usda`: **weaker**, original source-prototype USD
   references under PointInstancer's `over Prototypes` parent,
   real `UsdGeom.PointInstancer` ordered `prototypes` relationship,
   source-ID `protoIndices`, local-metre `positions` and stable
   integer `ids`. The over parent prevents raw uninstanced prototype
   objects being processed as extra rendered buildings.
4. `sources/<original USD layer SHA>.usda`, plus separately pinned
   `sources/assets/<first-party asset layer SHA>.usda`. These are
   staged *only* from the FilmIndex-verified original 02M building,
   never fetched from an AI-provided filesystem path.

The root composes `./director.usda` ahead of `./generated.usda`.
On native reopen NVP re-generates both exact USD layers from the
FilmIndex plan, verifies root/generated/override layer byte SHAs,
source dependencies, PointInstancer population and masks, and proves
the old source module geometry still exists in the referenced stage.
No original actor performance or frozen audio Take is altered.

`publish` creates a new immutable FilmIndex `presentation` revision
with exact original building dependencies after the director accepts
the exact source plan/layer SHA. A second approved manual change
makes a new FilmIndex revision. Tests demand unchanged
`generated_layer_sha256` and changed
`director_override_layer_sha256` across that revision boundary.
Previously saved director edits remain reopenable.

## Native acceptance requirements

`tests/test_nvp_usd_film02m_modular_buildings.py` now exercises
real native `pxr` source building reuse, six real instances and
two exact original 3D prototypes, invisible generated IDs,
one true manual USD source reference, local world origin with a
million-metre global source coordinate, authentic prototype meshes,
OpenUSD layer strength and SHA-stable revision changes. It also
tests source triangle and instance budget refusal, non-origin
prototypes, overlapping manual source buildings, invalid instance
ID and denied native director permission.

`.github/workflows/nvp-usd-film02me-layered-district-source.yml`
runs genuine USD/FilmIndex test matrices on Windows 2025 and
Ubuntu 24.04, Python 3.11/3.13. **Await actual exact-head test
results and inspect any real failures before acceptance.**

## Follow-on workgroups

- **02M-E2 real film look:** define first-party reviewed near/mid/far
  source meshes/LOD, true material/texture bindings and camera-specific
  render-quality profiles; measure source memory and GPU/CPU/VRAM,
  then inspect genuine Blender/Cycles street, reverse, window-to-room,
  aerial and interior pictures. Do NOT claim PointInstancer reduces
  actual Cycles memory/draw calls without measured native results.
- **02M-F original director/AI tooling:** expose tightly typed
  `generate_district`, `preview_district`, `district_stats`,
  `lock_region`, `list_assets`, `place_original`,
  `hide_generated`, `diff`, `undo`, `commit`,
  `discard` through the existing NVP WO6 native broker with
  authenticated creator approval. AI only proposes a bounded
  layer revision; NVP owns original files, authority and execution.
  MCP remains optional; do not add a required server process.
- **Film-world integration:** the generated layer/cells must
  be explicitly bound to the same frozen 01E actor performance,
  original 01D camera working set, true 01R low-fi editor and
  01Q/01T hi-fi selected camera render before declaring a
  complete film-set pipeline.
- **Future separately gated runtime/VR export:** per-asset
  hash-keyed optimized LOD cache, exact target coordinate
  conversion and asymmetric calibration, compiled room/cell
  chunks, actual platform texture/compressed mesh formats,
  official usdchecker, measured in-device budgets. Do not
  silently turn NVP's offline film master USD layers into
  a headset runtime requirement.
- **Large-world enhancement:** asynchronous prefetch and
  directional lookahead, generated region cells, material-only
  shared source looks, actual local-origin/floating-origin
  accuracy measurements, true point instancing and
  independent per-cell resource limits. A dense street
  can require distant stand-in skyline geometry even when
  most source cells are unloaded.
- **Frozen scene semantics:** keep L1 actor/animation/events
  canonical, L0 seeds for optional re-simulation, L2 heavy
  motion/volume caches and L3 edited pictures/audio as
  derived products. Visibility is time-sampled when an actor
  appears/disappears; `prim.active` is not treated as an
  animated control. Alternative director branches remain
  separate layer/FilmIndex revisions.

**Unfinished gates:** native exact-head CI, source USD ↔
Blender/Cycles prototype render parity, real proxy LOD,
material/light/look quality, installed creator workflow,
full 01T authentic 720-frame PCM film, low-spec and
VRAM/cell-origin benchmarks, director review and final
USD-FILM 00–10 integration. None is closed by this E1 source commit.
