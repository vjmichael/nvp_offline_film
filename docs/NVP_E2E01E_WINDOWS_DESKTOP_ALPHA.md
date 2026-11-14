# NVP-E2E-01E — Standalone Installed Desktop Alpha

**Implementation: initial Windows native shell + NSIS setup committed.**
**Acceptance: OPEN.** A passing headless API smoke does not substitute for
a visible native desktop window, genuine timeline work, or final movie export.

## Actual integration chosen

NVP already has a React/Vite application at `frontend/` and a local
FastAPI backend in `backend/nvp_api.py`. Do not rebuild a second UI.

The new entry `tools/nvp_desktop_alpha.py` starts the same app's API bound
only to the loopback interface on an OS-selected port. It serves the compiled
React files from its packaged resources and displays the URL in a genuine
Windows WebView2 window via pywebview. It depends on no Lu runtime, MCP,
Docker, internet service, Node/Vite dev server, or external browser tab.

The native installer is per-user and installs one prebuilt application
directory under `%LOCALAPPDATA%\Programs\NVP` with a Windows Start-menu
shortcut and uninstaller. Film projects remain outside the application under
`%LOCALAPPDATA%\NVP\Projects` and uninstall must not remove them.

The Windows CI workflow `.github/workflows/nvp-e2e01e-windows-alpha.yml`
attempts:

1. Build the existing React frontend with Vite and ensure bundled assets exist.
2. Build the original FastAPI-backed desktop executable with PyInstaller and
   native pywebview/Win32 dependencies (one-dir mode).
3. Execute an unpackaged desktop executable headless API/project smoke.
4. Build a single-click current-user Windows NSIS installer from that directory.
5. Silent-install the actual executable as a normal current user.
6. Launch the installed executable **twice** in separate OS processes:
   first `--smoke-create`, then `--smoke-reopen` with the same external
   `NVP_HOME`. Require the original SQLite project ID/title and an edited
   Fountain screenplay revision to reopen across separate app processes.
7. Launch a **real visible WebView2 window** with `--smoke-window`; the
   native page-loaded signal must occur before the test reports success.
8. Silent-uninstall and require the same original film SQLite file to remain.
9. Upload the resulting installer as a short-retention CI artifact if built.

No installer acceptance is complete until actual Windows tests produce
successful results for **both** the page-loaded and data-preservation gates.

## Known open items / exit criteria

- [ ] Real Windows 2025 CI NSIS installer build and install/uninstall succeeds.
- [ ] Real WebView2 window loads on Windows; packaged static assets render.
- [ ] Project is created and reopened in a second installed application
  process and remains intact after uninstall.
- [ ] Confirm an offline Windows 11 machine can launch with its WebView2
  runtime. Whether to bundle the WebView2 evergreen offline runtime remains
  a packaging dependency decision; no missing runtime is silently ignored.
- [ ] Complete editorial UI must expose import/cut/preview,
  color grading and approved audio/final export. The present standalone
  shell exposes existing planning/production UI but does not magically add
  unimplemented film editor controls.
- [ ] Native NVP worker binaries (FFmpeg/Blender/OCIO/DCP-o-matic) and
  license-compliant notices/payloads must be audited and packaged
  independently; the current installer is an **early shell alpha**, not an
  end-to-end offline rendering distribution.
- [ ] Reopen an original production FilmIndex with B13/B14, AUDIO-01I/J/K
  native worker receipts and verify an actual approved final film.
- [ ] Interactive Windows 11 user acceptance: install, launch, navigate
  actual app, create/save/reopen project, edit timeline, preview, render,
  inspect media, shutdown, uninstall. An automated API smoke alone cannot
  prove usability.
- [ ] Dependable native process shutdown and no lingering local webserver
  or worker process; crash/permission hardening before public distribution.

## NVP-E2E-01D I/J acceptance linkage

A consolidated native workflow
`.github/workflows/nvp-e2e01d-real-i-j.yml` requires the existing actual
AUDIO-01I master, native host/worker crashes, every PCM24 WAV delivery
filesystem/SQLite crash, AUDIO-01J picture-lock and real ProRes/PCM24 mux
host+worker crash matrices, and the real OS worker-tree termination gate.
It runs a four-cell Windows/Linux Python 3.11/3.13 matrix.

These original I/J tests were **already present in the repository**.
The newly committed workflow is the release-gating integration for them,
not a claim of newly implemented media algorithms. They use real native
FFmpeg but upstream picture fixture shortcuts in some tests; full B12/B13/B14
creator-approved film verification remains open until the separate original
film fixture passes.

**Do not mark NVP-E2E-01D or E2E-01E production accepted based solely on
committing code, a queued CI job, or an installed desktop shell.**
