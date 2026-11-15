# SLATE-08B — Trusted Desktop Rendering Integration

> **DA-06 / PLAN-02-A supersession (2026-11-09 MST):** The historical native still-rendering design below is NOT an active native filming contract. Canonical PR #74 retires the external still request/poll/cancel IPC and uses read-only OpenUSD lens projection pending independent continuous native 3D visual acceptance. Do not revive the legacy worker to satisfy obsolete positive tests. See [PLAN-02 map](NVP_PLAN02_AUTHORITATIVE_INTEGRATION_PATH.md).

**November 6, 2026 — native bridge implemented, acceptance pending.**

Stack: INDEX-TIME original source identities → real immutable OpenUSD scene +
native camera → CAM-01 exact optical settings → SLATE-08 read-only browser →
**SLATE-08B WebView2 native IPC** → the existing
`NativeSlatePreviewHost`/`ApprovedBlenderDispatcher`/`TaskLedger`/
`BlenderWorkerSupervisor`/`SlatePreviewCache`.

## Technical decisions

The standalone NVP Windows desktop is an installed PyInstaller Python
process with a pywebview EdgeChromium window and loopback FastAPI serving
bundled React. The new `TrustedDesktopCameraBridge` is bound using
`webview.create_window(..., js_api=bridge)` from the **trusted desktop
entrypoint**. There are no new FastAPI POST routes for rendering,
cancellation, file serving, native command execution, director approval,
or executable discovery.

A renderer request carries only the exact project, scene, revision, SHA,
source Film Time tick, authored camera path, and canonical physical optics.
The native bridge independently reads that scene from FilmIndex and rejects
mismatched source identities, extra fields, unapproved optical effects and
unsafe time/camera requests.

A native OS confirmation shows exact scene/tick/camera/lens parameters before
creating a **single-use 60-second grant**. The preexisting native preview
host verifies that grant against the operation and the approved source/cache
key; the trusted worker still independently verifies fixed first-party
script SHA, source manifest, resource admission and scene consent. The native
window's live URL must match the installed app's exact loopback origin.

The bridge returns only an unguessable, in-memory session ticket (not a
path). A single native dispatcher executor reuses the existing resource-
admitted Blender host. Polling the ticket is allowed only from that same
window. A resulting PNG must have accepted source scene identity, exact
optics and time, original worker receipt, bounded PNG dimensions and an
independently checked cache SHA before conversion to a bounded base64 data
URL. React refuses stale images after lens changes. A separate native OS
confirmation is required to cancel a queued or running native render.
Unproven termination or interrupted output is reported as recovery-required,
not fabricated success.

The **native bridge is a privileged desktop surface**: content from ordinary
web browsers cannot call its methods. Main-project React provides the same
fast read-only diagram in both desktop and ordinary browser contexts, but
only the native window with a discovered Blender binary enables real still
rendering. Lens preset save, applying optics to a frozen shot, final film
masters and arbitrary imported actor rigs remain outside this gate.

## Indexing continuity

Pre-SLATE indexing was not superseded or discarded:
- DATA-01/SCALE-03C — authoritative indexed original sources and measured
  bounded frame-index fast seek.
- INDEX-TIME-01 through 04 — PTS→Film Time bridging, durable VFR editorial
  placements, native preview/conform, binary-search Film Time seek.
- Native OpenUSD scene/Takes → SHOT-01 → SLATE-01–08A then 08B build
  **on top of** source indexing rather than replacing it.

The earlier 259,200 frame / ~4.67 MiB / ~4.53s / ~85 ms near-end
indexing measurements are **reported benchmark observations, not full
production acceptance**. Exact-head native indexing gates and FFMS2
comparisons remain a separate open workstream.

## Acceptance still required

- Windows/Linux real native usd-core 26.11 + Python 3.11/3.13 suite.
- React/Vitest and bundled Windows WebView2 JS-API smoke.
- A real installed Windows NVP, with an approved trusted native Blender
  installed, renders one animated source actor through selected lens optics,
  cancels an active render, tests hostile navigation and source changes,
  restarts/reconciles worker receipts, and reopens its unchanged FilmIndex
  records. No such installed-app physical test is claimed in this draft.
- Blender is *not bundled in the existing single-click NSIS alpha*. Until
  its binary provenance/packaging is solved, missing Blender disables native
  stills with an explicit UI explanation.
