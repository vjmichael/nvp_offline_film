# USD-FILM-02M-E2 — Actual USD material import, source LOD, reviewed lighting and Cycles/OpenEXR tests

**Source status:** implementation and native verification actions committed.
**Native acceptance:** the exact-head Windows/Linux OpenUSD matrix and official
Blender 5.2.3 Cycles jobs must finish before anything here is called
renderer-verified. No actual Blender PNG/EXR or cinema master is being
claimed merely because the CI workflow was authored.

## Source-researched design

The creator supplied `Claude-response-to-Film.txt` in the IDE 18
conversation. It recommends freezing structured actor performances rather
than pixels; separating sequence/set, props, performance, shots/cameras,
lighting and FX/cache layers; deriving final images with scene-controlled
classic CG or AI-assisted image/video passes; retaining MaterialX,
OpenColorIO/ACES, multi-layer OpenEXR, OpenTimelineIO and review/render
infrastructure as long-term film-pipeline building blocks.

**What E2 actually adopts now:** immutable original OpenUSD/FilmIndex
geometry and `UsdPreviewSurface` PBR, actual material/roughness/metallic
binding checks in Blender, a separate derived lighting/view profile
without modifying original actor Takes, real Cycles CPU picture output,
a verified multi-layer original EXR with depth/normal/diffuse AOVs,
measured host CPU wall time/process peak resident memory, and strict
source material/LOD/cache SHA evidence.

**Not claimed:** MaterialX shading parity; use of an external
ACES-compliant OpenColorIO config; AI-produced photoreal human skin,
flicker/identity continuity, actual GPU/AMD ROCm support, true VRAM
measurement, full production lighting grading, cinematic source mastering
or 720-frame motion-film completion. Blender's built-in **AgX** view
transform is not automatically equivalent to ACES, and a valid
OpenEXR file does not alone establish ACES color management.
AI-assisted render enhancement stays source/ActorID/conformance
controlled and separately acceptance-gated (HSURF-00 later).

## E2-A — exact original source and real LOD geometry

`backend/nvp_usd_film02m_e2_look.py` requires an already approved
real 02M building `world` FilmIndex revision and independently reopens
every first-party source `asset` mesh and its actual authored USD
`UsdPreviewSurface` material binding. Source color, roughness and
metallic must be finite [0,1] inputs, and each original mesh has
a real native `UsdShade.MaterialBindingAPI` path.
Original near geometry layer and its shared source USD asset
blobs are copied byte-for-byte to a disposable render workspace
and checked against the approved original source SHA.

Two **genuine but explicitly approximate** geometric source LOD
layers are derived from authenticated native source bounds:
- `near.usda`: original complete front/rear/roof/interior and
  physically perforated façade/window/door mesh. **Only this is
  suitable for close-ups, interiors and through-window shots.**
- `mid.usda`: one real 12-triangle box per original mesh module,
  preserving each original source module's reviewed PBR surface
  scalar parameters and source material provenance. The mesh
  is a derived approximation: windows, openings, trim and
  internal detail are not preserved.
- `far.usda`: one 12-triangle whole-building skyline proxy,
  using an approved source façade color/roughness/metallic.
  Not camera-valid as a walk-through or inside source layer.

Those are three actual native `UsdGeom.Mesh` complexity levels,
not merely three output resolutions, image resizing or
fake artist-approved photorealistic surfaces. Original near
triangle count must be > real derived mid count > far count
before a job is admitted. Every derived `UsdShade` material
is re-opened through native OpenUSD, and the original approved
full-detail layer remains unchanged. This first smoke uses
one reviewed original 11-module shopfront+room fixture.
A stronger face-preserving LOD generator, image-space projected
error metrics and true live scene/camera-specific LOD choice
remain open.

## E2-B — real reviewed lighting/camera/quality ladder

The exact first-party source-locked technical CPU Cycles profiles
are:

| Shot/view | 3D source | Pixels | Cycles samples | Light |
|---|---|---:|---:|---|
| near_front | original full near | 640×360 | 16 | soft_day |
| near_rear | original full near | 640×360 | 16 | soft_day |
| mid_oblique | derived mid | 480×270 | 8 | soft_day |
| far_street | derived skyline | 320×180 | 4 | soft_day |
| near_front_relight | SAME original near | 640×360 | 16 | warm_side |

The first four shots use the **same** reviewed light source
while measuring changing geometry/resolution/sample costs.
The fifth switches only the **derived lighting preset**
(ambient/sun color, strength and position). It is not a
performance retake or amendment of the original source USD.
The near-front and near-relight pictures must have distinct
actual native PNG SHAs. Both reuse precisely the same
original source geometry/actor identity hashes.

`tools/nvp_usd_film02m_e2_blender_look.py` is one fixed
first-party protected NVP Blender worker, not a browser
script or model-provided Python. It pins all stage/material
source layer SHAs, checks reviewed exact camera/render
profiles, imports the actual authored native USD surfaces,
requires real imported Principled/Cycles node values to
match the original `UsdPreviewSurface` diffuse RGB,
roughness and metallic within an explicit tolerance
and refuses absent or substituted source materials.
It renders actual five PNG images, and records imported
triangles/meshes, camera positions, profile controls,
Blender version, original source SHA, CPU render wall
seconds and process-level peak RSS MiB. These are
**actual worker measurements only if the job executes**,
not projected GPU performance or Blender-subprocess
memory attribution from NVP alone.

For the near-front original source, the worker runs a
separate genuine Blender `OPEN_EXR_MULTILAYER` render
at 32-bit float with true depth/normal/diffuse passes.
The worker **parses the actual OpenEXR channel table**
and must find depth, normal and diffuse pass channels
instead of accepting only the EXR file magic.
All images and EXRs are captured via the existing
SHA-pinned/OS-contained `BlenderWorkerSupervisor`,
with independently audited PNG/EXR magic, byte hashes
and a bounded human-readable `audit.json`. The output
is explicitly *technical-quality*, not final cinema
exposure, tone/ACES, skin, material or artistic approval.

## E2-C — same district instancing → actual Cycles street pictures

`backend/nvp_usd_film02m_e2_district_render_view.py`
explicitly solves one Blender USD scene-interoperability issue:
the project must not assume every USD importer treats native
`PointInstancer` and stronger layer overrides identically.
It opens the original E1 `OriginalFilmDistrict` from FilmIndex,
verifies its source instancer `protoIndices`, per-instance
positions/ids and director `invisibleIds`, and compiles
**only visible** instances plus approved manual
original-source placements into a disposable 1m/Z-up USD
working view with real native references to original
source buildings and their PBR asset layers. The authoritative
PointInstancer and director override layers are NOT
replaced or overwritten. A maximum 24 render instances
with bounded source-layer bytes prevents attempting to
expand arbitrary whole cities in one low-power scene job.

`tools/nvp_usd_film02m_e2_blender_district.py`
is a second fixed first-party worker. It checks the
exact compiled source SHA, all original building/asset
USD layer SHAs and expected 3D mesh counts, imports them
into actual Blender/Cycles, requires at least three
source-derived Principled materials and 12+ real faces
per original part, then renders **true front and reverse
street PNGs** from identical approved source geometry
with measured CPU wall time and process RSS.
The sample six-building district has six generated
original identities, one hidden generated building,
and one hand-placed original building, giving six
visible/hand-placed source buildings and 60
composed source module meshes.

The renderer-specific expanded USD view makes **NO
claim of GPU instancing/draw-call savings**: it is a
bounded disposable render adaptation. Real Blender
raw PointInstancer direct import/draw-call/VRAM parity
requires a separate profiler and acceptance result.

## Exact native acceptance and artifacts

`.github/workflows/nvp-usd-film02me2-real-look-quality.yml`
runs actual Win2025 and Ubuntu24.04 Py3.11/3.13
native `pxr` shader binding and real near/mid/far
topology tests, frozen original revision checks,
real E1 PointInstancer→source/Blender view integrity
and denied budget/source cases.

The second Ubuntu run downloads **official Blender
5.2.3** with upstream SHA-256 validation, uses
Xvfb for the headless GPU-free desktop and runs both
real protected native workers. It must produce
five independent actual original building PNGs,
one original multi-layer OpenEXR,
two actual instanced-district camera PNGs,
audits and visual contact sheets before the
artifact is eligible for creative review.

The full acceptance sequence is:
1. Obtain exact-head native Win/Linux/Blender job statuses
   and repair actual compile/runtime/missing-material/API
   failures. A queued job cannot pass a gate.
2. Inspect the actual downloaded pictures, including
   original near façade/window relief, source rear,
   correct light transport, proof that shading changes
   under relighting, and absence of duplicated
   uninstanced geometry at the district origin.
3. Compare real Cycles wall time/RSS against true
   near/mid/far source triangles on CPU and
   low-power test hardware. Expand to measured
   Vulkan/HIP/AMD GPU only after reliable
   device/custody/profile admission.
4. Add a real reviewed OpenColorIO/ACES project
   config before claiming ACES color pipeline,
   plus MaterialX renderer parity and proper
   multilayer pass-grade review. Guard HDR values
   and display/exposure conversions.
5. Integrate source/LOD/lighting into one frozen
   **01E actor world + 01D director working set**
   and 01R/01Q/01T selected shot workflow.
   The complete original 720-frame movie with
   its one original 48k PCM still has its
   own pending native/human acceptance.
6. Complete **02M-F** creator+AI typed native
   `preview/diff/undo/approve/commit/discard`
   controls on these real sources, without
   mandatory MCP, arbitrary Python execution
   or unreviewed high-powered mini-app tools.

**Gate remains open** until genuine native file results and
installed-app/human art-direction checks are inspected.


### USD-FILM-02M-F — Actual installed native director source scene authoring, typed AI proposals, preview/diff/undo/discard and one-use OS publication [SOURCE COMMITTED / NATIVE AND PHYSICAL INSTALLED GATES OPEN]

**Current architecture:** same existing `TrustedDesktopWO5Bridge` → WO6 installed WebView, not a new browser HTTP writer, MCP server, or Blender mini-app. First-party `backend/nvp_usd_film02m_f_authoring.py` creates durable per-project host-owned SQLite WAL/FULL unapproved proposals with project/district, exact approved original FilmIndex base revision/document SHA, generator params, original source plan SHA, real native root USD layer SHA, source-authorable stronger director operations and bounded undo history. AI or human may **propose** only validated original buildings/seed, grid/cell geometry and typed `hide_generated`, `unhide_generated`, `place_original` or `remove_manual`; no script/process/filesystem/worker authorization and no implied approval. Drafts survive restart. Stale versions or changed FilmIndex source fail closed. An approved existing district's stronger manual/hidden opinions are inherited for subsequent proposals rather than silently discarded.

**Director**: `frontend/src/ModularWorldDirector.jsx` is mounted as **23 · Build the world from data** within existing `DataFirstViewpointEditor`, obtains exact original building/district catalog via native host, configures source-bound deterministic district, previews the actual reopened 02M-E1 native USD PointInstancer instance/layout and separate generated/director layer SHAs, displays typed added/removed changes, makes/undoes/discards manual original building placements and hidden generated source IDs, and resumes durable drafts. `frontend/src/ModularWorldSourcePreview.jsx` adds interactive low-power Three.js **source-bounding-volume** orbit and source-footprint SVG fallback; these are truthful proxies, not full high-poly geometry/Cycles imagery. Source preview launches zero Blender workers; final publish requires exact current preview source-plan/root-layer SHA and user click.

**One-use installed consent:** `backend/nvp_usd_film02m_f_desktop_mixin.py` supplies only typed exact-origin WO5/WO6 source draft methods, with no HTTP source write. Exact creator OS confirmation reveals film project, district, proposal version, approved base source SHA, proposed source-plan SHA, exact native root USD SHA, original instance/triangle bounds and director opinion count. `OriginalFilmDistrict.publish` callback requires exact host-minted in-memory grant event, operation, film, source, revision and layer SHA; AI/browser `creator_approved` is never accepted. Negative confirmation publishes no FilmIndex. Positive one-use grant first durably transitions draft to `APPROVED_PENDING_PUBLISH`; only then does an immutable `presentation` source world revision get committed and independently reopened. If OS/process crashes after grant but before/after FilmIndex commit, reopening reconciles ONLY a matching previously authorized exact new source revision; missing publication becomes `INTERRUPTED_NEEDS_NEW_APPROVAL` and mismatched source becomes `CONFLICT_NEEDS_REVIEW`, with no old permission replay. Previous original actor Take, geometry assets, generated district layers and film master history remain unchanged.

**Real independent native tests and CI:** `tests/test_nvp_usd_film02m_modular_buildings.py` adds actual native `pxr` FilmIndex source/district preparation, source SHA/SQLite draft/undo/discard/reopen, manual placed/hide/unhide/remove and unchanged generated layer, invalid AI script/footprint denial, OS confirmation denial and separate explicit approval, old/new immutable revisions and inherited director opinions, crash simulation/reconciliation after durable OS grant, stale version and foreign installed WebView origin rejection. `frontend/src/ModularWorldDirector.test.jsx` exercises browser-only read-only gate, original source proposal→verified preview→hide→undo→SHA-bound native commit and discard without grant. `.github/workflows/nvp-usd-film02mf-native-director-authoring.yml` runs Win2025/Ubuntu24.04 native Py3.11/3.13 + Windows bridge-origin test + React/Vitest and production Vite build. **Actual exact-head CI and physical installed Windows WebView2 acceptance remain OPEN** until completed OS results, genuine startup/forced termination/reopen/click/uninstall logs and independent human look review exist.

**Important honest limitations:** The `proposed_by='ai'` field denotes a user/host-submitted AI-suggested data plan, NOT independently proven loaded Qwen/GGUF planner output or ANSF provenance. Actual loaded AI planning → native typed model-tool invocation remains open. Current source preview is wireframe authored bounds, not full triangle-interior interactive viewport or a Cycles image. Unfinished 02M E1/E2 material/LOD/real native Cycles/physical GPU acceptance, integration of 02M district cells into the **same** 01E original actor world + 01D camera working set + 01R/01Q/01T film, and real 720-frame+48k PCM director creative movie acceptance remain blockers. Keep HSURF-00 deferred. Full implementation/acceptance: `docs/NVP_USD_FILM02MF_INSTALLED_DIRECTOR_AI_SCENE_AUTHORING.md`.
