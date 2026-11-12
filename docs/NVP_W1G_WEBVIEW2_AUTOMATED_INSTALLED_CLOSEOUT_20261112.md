# NVP W1-G — Visible WebView2 and Automated Installed Windows Acceptance Closeout

**Accepted on:** 2026-11-12  
**Source branch:** `nvp/int02-w1g-native-film-package-20261112` (isolated; not merged or released)  
**Exact tested source:** [`46d59d3719363774b1e6c9b8c658bb5573230c40`](https://github.com/vjmichael/nvp_offline_film/commit/46d59d3719363774b1e6c9b8c658bb5573230c40)  
**Scope:** W1-G visible Windows desktop startup, installed application, native IPC, automated process custody and safe installer regression. **Production release acceptance remains open.**

## Original defect

The earlier Windows workflow compiled NSIS, installed the alpha, reopened the project, and completed staged rollback, but timed out while loading the full native WebView2 window. Checkpoints localized progress through OpenUSD, original PCM, Take freezing, loopback server, React bundle, native top-level HWND, EdgeChromium initialization, `shown` and `before_load`. Independent basic EdgeChromium with real React passed, while the full `TrustedDesktopCameraBridge` failed to reach the `loaded` event. Windows Python thread-stack evidence located a recursive pywebview function-inspection traversal over the bridge's public native window/FilmIndex object graph.

## Repair implemented

- `backend/nvp_webview_ipc_surface.py`: strict façade with 28 whitelisted, explicitly shaped public IPC methods and a private trusted delegate. Does not export window/FilmIndex/SQLite/host objects or a dynamic reflective API.
- `tools/nvp_desktop_alpha.py`: production and installed smoke WebViews use that narrow façade while the true trusted native bridge still binds its real OS window and performs original-source/consent/origin checks.
- `tests/test_nvp_webview_ipc_surface.py` and both native/workflow contracts: verify the public surface, exact method signatures, no exposed authority graph, origin revocation, retired camera requests, and closed-window behavior.
- Existing diagnostic receipts distinguish a healthy loopback server, real EdgeChromium/React page, JavaScript IPC verification and window shutdown, rather than treating a headless response as desktop acceptance.

## Exact-head automated evidence

| Gate | Workflow evidence | Result |
|---|---|---|
| Genuine Windows and Linux native W1-G/INT-02C contract tests | [43311316271](https://github.com/vjmichael/nvp_offline_film/actions/runs/43311316271) | PASS |
| Genuine Blender Cycles scene/frame and SHA on Linux | same four-job matrix | PASS |
| Genuine Windows Blender Cycles supervised by native Job Object | same four-job matrix | PASS |
| React bundled, real PyInstaller/NSIS packaged, executable installed and byte-verified | [43311316164](https://github.com/vjmichael/nvp_offline_film/actions/runs/43311316164) | PASS |
| Fresh installed project create/reopen; original SQLite persisted across restart | same Windows installed workflow | PASS |
| Actual Windows NSIS stage, filesystem upgrade simulation and rollback with original program/film preservation | same Windows installed workflow | PASS (simulated approval; not a production upgrade) |
| Installed original native OpenUSD and PCM smoke | same Windows installed workflow | PASS |
| Real visible EdgeChromium, mounted React, full native camera and data-first A/V IPC | same Windows installed workflow | PASS |
| Installed native executable launched/reopened under original Windows kernel Job Object custody | same Windows installed workflow | PASS |
| Silent uninstall and original creator-film preservation verification | same Windows installed workflow | PASS |

The Windows job ended `success` with **no failed steps**; the four native jobs all ended `success`. Relevant archived audit: [Windows receipt artifact](https://github.com/vjmichael/nvp_offline_film/actions/runs/43311316164/artifacts/13984809992). Do not confuse this with a separate real owner-run installed-film acceptance or signed shipment.

## Classification and remaining backlog

**CLOSED — W1-G visible WebView2 startup and automated installed acceptance.** No further implementation or CI rerun is required for this already-accepted subsection unless changing the binary, IPC method roster, WebView2 library/renderer, installer or safety-critical dependency.

**OPEN — W1-G production-release safety:** reviewed, licensed offline dependency and native-worker provisioning; real owner-authorized NSIS upgrade, locked executable / cut-power / restart and rollback evidence with kernel custody through the upgrade transaction; protected/encrypted source key custody; accepted release candidate.

**OPEN — INT-02C full film:** true source-bound multi-shot 720-frame 30-second production, original spatial PCM, production-quality actor/material/light/color/occlusion, playback/export, independent verification and quality review.

**DEFERRED/OPEN — W1-F:** actual physical human Windows installation on the creator machine and sustained production/long-duration performance, quality, recovery and film inspection.

No merging, release, publisher signing or physical acceptance authorized by this closeout. Original Digital Takes and immutable film source authority remain unchanged. No FFmpeg primary filmmaking path or retired proxy route is reintroduced.
