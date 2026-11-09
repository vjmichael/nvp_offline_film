# USD-FILM-02M-F — Installed director + typed AI scene authoring

**Source implementation committed. Actual exact-head Windows/Linux OpenUSD
execution, browser/installed WebView2 physical-user acceptance and full
film integration remain OPEN until native OS job artifacts are inspected.**

This implements a director's first usable source-first building district
editor inside NVP's existing **22 · Direct the data** workflow, now with
a **23 · Build the world from data** panel. It is not a new external app,
MCP requirement, game/VR editor or alternative Blender process manager.

## Data and access boundaries

- Approved reusable geometry remains first-party original 02M-A/B/C
  `asset`/`style`/`world` FilmIndex revisions. 02M-D real
  door/window/interior geometry and 02M-E1 actual USD PointInstancer
  generated districts + stronger director layer are source records,
  NOT final pixels. Their immutable source and all actor Take history
  cannot be edited by this feature.
- `backend/nvp_usd_film02m_f_authoring.py` adds durable per-project
  host-owned `SQLite WAL + synchronous=FULL` proposal journal.
  Unapproved proposals are **NOT published `FilmIndex` objects**:
  a source plan remains data even if supplied by an AI. Every draft
  has a host-minted 24-character random draft ID, project/district,
  exact approved original base revision and SHA, bounded source
  parameter JSON, separate bounded director opinions, version,
  SHA-256 plan + generated/root USD-layer receipts, undo snapshots,
  timestamps and state.
- Only typed first-party NVP authoring operations:
  `propose`, `preview`, `diff`, `hide_generated`,
  `unhide_generated`, `place_original`, `remove_manual`,
  `undo`, `discard`, `reopen`, and an explicitly scoped
  `approve_and_commit`. Scripts, custom USD paths, arbitrary
  filesystem writes, worker executables, generated source shaders,
  tool grants or arbitrary shell commands are **not permitted
  original model outputs**.
- Actual 02M E1 `OriginalFilmDistrict.plan` validates every
  proposed seed, source building ID/revision, style-independent
  original mesh SHA, bounded instances/triangle counts, lot
  footprints and overlap. `._stage` reopens genuine
  `UsdGeom.PointInstancer`, source mesh references, authored
  stronger override `invisibleIds`, and native USD layer SHAs.
  The preview is not accepted solely from JSON metadata.
- A draft can be edited and undone repeatedly across app restarts.
  The current proposal and its source SHA are reverified against
  actual 02M source layers on each reopen. A stale proposal
  version/approved base revision or unexpected source bytes
  fail before a new operation.
- On a proposal based on an existing approved district, its
  stronger director opinions are **inherited** by default rather
  than silently cleared. Changes produce a proposed next
  immutable FilmIndex revision only after director approval.
  Prior revisions and original actor performances are untouched.

## Same installed NVP bridge; single-use native director approval

`backend/nvp_usd_film02m_f_desktop_mixin.py` is inherited by the
existing `TrustedDesktopWO5Bridge` (and its WO6 descendant).
Every method calls `_wo5_project` / `_native_window` and uses
the same exact first-party pywebview origin check; no new HTTP
mutating route. The browser cannot submit `creator_approved`,
`approve=true`, a native OS authorization receipt, command
line, file path, arbitrary Python script or worker binary. It
submits only typed proposed source data and identifiers.

**Exact approval workflow:**

1. Native installed host verifies the latest director draft version,
   original FilmIndex base revision SHA, source-plan SHA and
   genuine OpenUSD composed root-layer SHA.
2. The trusted host mints one in-memory identity token for this
   operation. `OriginalFilmDistrict.publish` may call back with
   that token exactly once and must match the whole current plan,
   source-layer, district, project and expected base revision.
3. The installed OS window presents a real confirmation dialog with
   district, draft/version, base approved source, exact proposed
   plan SHA, exact USD root layer SHA, instance/triangle bounds,
   director opinions, and the warning that **AI plans never grant
   approval**. Negative/cancelled approval publishes NOTHING.
4. Once approved, the draft journal durably enters
   `APPROVED_PENDING_PUBLISH` **before** the separate FilmIndex
   transaction commits the new immutable `presentation` district
   revision. An interruption cannot replay the one-use grant.
5. After independent genuine native district source reopen and
   matching committed FilmIndex document SHA, the journal
   records `COMMITTED`. For a restart at the narrow boundary
   between two databases, reopening a pending draft verifies the
   exact single succeeding original FilmIndex revision and
   source/derived USD SHA; only that may reconcile to COMMITTED,
   *without another authorization*. If no publication occurred,
   the state becomes `INTERRUPTED_NEEDS_NEW_APPROVAL`. If a
   different source/revision appeared, it becomes
   `CONFLICT_NEEDS_REVIEW`. Both are terminal for the old grant.
6. A discarded source draft is a durable tombstone, not an
   accidental hard delete, and cannot be committed/reused.

OS confirmation is not delegated to Lu, an LLM, a browser checkbox,
a terminal tool or an MCP service.

## Actual director interaction

`frontend/src/ModularWorldDirector.jsx` is mounted directly
inside the existing `DataFirstViewpointEditor`. The director
can select 1–8 original approved reusable 3D building prototypes;
choose deterministic seed, rows/columns, local lot pitch,
actual source triangle/instance budgets and a separate
large-world metre origin; submit a typed director or
AI-suggested proposal; and reopen a durable draft from the
source catalog.

`frontend/src/ModularWorldSourcePreview.jsx` draws a low-power
Three.js orbitable **3D wireframe of source-verified building
bounding volumes**, with an SVG plan-view fallback when
WebGL fails. The native preview also includes the true
reopened USD PointInstancer instance count, hashes of
generated/stronger layers, original source geometry SHA,
hidden instance flags, provenance, real source-reference
module counts, and an exact typed diff against the
approved base. Actual mesh topology is **not drawn as
true triangles in this 02M-F viewport**; the bounding
volumes are real-derived placeholders. Do not call them
Blender shading, full 3D camera review, Cycles pixels,
structural engineering or final artistic approval.

Director can hide/restore generated instance IDs; add/remove
manually placed buildings from exact original source prototypes
with bounded X/Y/Z metre position and quarter-turn yaw; undo
the last draft operation; discard unapproved proposals; and
press **OS director approval · publish exact world revision**.
That last control is enabled only after the proposal has
a current source-verified native preview with the exact
draft version and both immutable source-plan and USD
root-layer SHAs. An OS dialog (not the React button) still
decides whether publication is permitted.

The "AI-suggested" origin selector allows reviewable
structured candidate data. **It does not prove a particular
local AI model generated the plan.** Binding a genuine loaded
GGUF/VLM/agent tool invocation, planner provenance, ANSF
memory and authorization receipts to this exact NVP draft
interface is a separately open real agent-integration gate.
AI proposals cannot publish scenes by themselves.

## Independent test design and acceptance gates

`tests/test_nvp_usd_film02m_modular_buildings.py`:
actual native `pxr` source builder, E1 PointInstancer
proposal + SHA reopen, OS-denied approval, authorized
native publish, immutable FilmIndex old/new revisions,
source-accurate diff, hide/unhide, manual placed/removed
original reusable building, geometry collision denial,
version/approval replay rejection, discard and undo;
new real service instance survives restart; injected
crashes before/after FilmIndex publication test
consent-preserving recovery. Existing installed pywebview
origin checks reject foreign URL even with a valid draft
and separately require native dialog approval.

`frontend/src/ModularWorldDirector.test.jsx` exercises
browser-only read-only behavior, typed AI-suggested draft
input, original source preview, native layer hide/undo,
discard, the exact SHA-bound commit request, and the
production editor's native bridge dependency. These are
UI/bridge *contract* tests, not a physical user observing
Windows WebView2 in an installed binary.

`.github/workflows/nvp-usd-film02mf-native-director-authoring.yml`:
Windows2025+Ubuntu24.04 Py3.11/3.13 native OpenUSD tests,
separate actual Windows bridge-origin tests, React/Vitest
installed-director DOM tests and genuine Vite production
bundle build. **Acceptance remains OPEN until each exact
head native test finishes and its actual output is inspected.**

## Still open before final USD film-system approval

- Execute native CI, repair genuine Python/pxr/OpenUSD/React/Windows
  failures. Do not treat queued jobs or source-only reviews as pass.
- Physical installed Windows WebView2 launch, actual user click and
  OS confirm, force termination/reopen/recovery and uninstall tests.
  The bridge mock/native Windows test does NOT prove this.
- Real loaded AI planning output piped into these typed native
  draft APIs, with real model/provider/ANSF provenance and
  independently checked source/tool outcomes; no model-origin
  security label from a user-supplied string.
- Actual editable full-mesh 3D/doorway/interior USD viewport,
  interactive geometry picking, practical LOD/lighting preview
  and source diff visualization at shot level. Current F
  source bounding-wireframe is a truthful low-fi editor.
- Same source building/district referenced into original
  **01E frozen actor Take + 01D camera working set** and
  final **01R/01Q/01T** selected-camera footage, followed by
  720 genuine Cycles pictures, original 48k PCM,
  installed OS recovery and director picture/sound acceptance.
  Those existing blockers remain separate.
- Keep original E2 native material/lighting/real geometry
  LOD+OpenEXR and E1 PointInstancer OS CI and actual
  material/visual/GPU/RAM acceptance open; do not claim
  cross-renderer parity until their pictures and receipts
  are inspected.
- The subsequent **USD-FILM 00–10** family is not considered
  complete until the scene/render/camera/audio authoring
  acceptance proves one genuine finished original film.
  HSURF-00 remains deferred until essential film-world gates.

**NVP is not a game engine.** Original OpenUSD performance/source
data remains primary and reusable; derived lighting/pictures and
AI source suggestions remain separately controlled and reviewable.
