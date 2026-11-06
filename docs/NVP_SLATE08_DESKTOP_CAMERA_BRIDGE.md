# NVP SLATE-08 — Native Camera Read Bridge in the Main Editor

**November 6, 2026. Stacked on SLATE-07/CAM-01 PR #65.**

The installed-style NVP planning UI did not expose the native OpenUSD camera
workbench. SLATE-08 adds a main-editor **Virtual camera** tab and a narrow
read-only FilmIndex scene browser. The browser lists only project-scoped
published native OpenUSD scene revisions with real authored cameras. It loads
ONE exact scene, revision, camera and integer Film Time via the existing
VirtualCameraWorkbench snapshot evaluator. After snapshot, spherical focal
length, sensor size, f-stop and focus changes render locally as instant
camera-space markers: NO Blender launch and NO original source modification.

## Trust boundary

The two new HTTP GET routes are read-only:
- `/api/projects/{project_id}/film/camera-scenes`
- `/api/projects/{project_id}/film/camera-scenes/{scene_id}/snapshot`

Listing never opens a USD stage, touches media files or executes a worker.
Snapshots verify source ID, exact revision, SHA, camera path, source tick and
real camera role; untrusted paths cannot name a filesystem resource.
The frontend rejects identity-mismatched/stale replies and does not expose
render, preset-save, shot-commit or Take-freeze callbacks from the unauthenticated
planning HTTP surface. A browser action must **not** mint creator authority.

The direct native `NativeSlatePreviewHost.request_camera_workbench` and
`read_camera_workbench_png` remain the approval-gated path for accurate
Blender stills; later native desktop IPC must bind an **authenticated physical
user event** to an exact-scene/tick/optics worker consent, then transfer ONE
independently verified bounded PNG. No generic process-execute or arbitrary
file-path endpoint is acceptable.

## Current truthful scope

- Actual published OpenUSD actor/camera state sampled at a selected tick;
  live, approximate projected markers (NOT GPU rasterized actor pixels).
- Editable lens controls before a Take exists. No source change, no film master.
- No fake sample camera or scene when a project has none.
- After authoring, the still-render, preset-save, apply-to-shot buttons remain
  disabled in this main-editor panel until trusted host actions are installed.
- Independent native Windows/Linux USD tests plus React UI tests are CI gates.
  **Exact-head CI and installed Windows desktop acceptance remain OPEN.**

Next: trusted local host IPC and native Windows installed path, including
creator-event provenance, cancellation, single verified PNG, and UI stale-result
rejection. Then real responsive 3D viewport and richer character deformation.
