# NVP E2E-01E — Recovered offline frontend and source-mode acceptance (2026-11-04)

**Status: source desktop/UI acceptance PASS; genuine Windows installer NOT BUILT.**

This document is a durable handoff for future development sessions. Before
re-downloading any toolchain, consult Library
`/Jan Mod - Lu/Delivered/README_WINDOWS_BUILD_TOOLCHAIN.md` and
`/NVP/Packages/BUILD_STATE_20261104.md`.

## Provenance and recovered assets

- Original NVP branch: `nvp/stack02c3b14-picture-conform-20261104`.
- Recovered NVP source ZIP in Library: `/NVP/Packages/nvp_offline_film-nvp-stack02c3b14-picture-conform-20261104.zip`.
- Saved **new complete source snapshot with compiled UI and test harnesses**:
  `/NVP/Packages/NVP_E2E01E_Local_Desktop_UI_20261104.zip`.
- Source ZIP SHA-256: `05b47cc9a4bf102c39a3715e9e239646a521f7bb53eda909abfdde7f8cc0902d`.
- Recovered all six `Lu_L13_Yarn_part*.zip` archives and `Lu_L13_UPLOAD_MANIFEST.json`
  from `/Jan Mod - Lu/Delivered`. A verified offline recovery script is included
  under `build-support/offline_yarn_cache_installer.py` in the saved NVP checkpoint.
- Restored 59 frontend packages from the Lu Yarn archives. Used Vite 5.4.20 to
  compile **the actual NVP frontend**, 53 modules transformed; output in
  `frontend/dist/index.html` and `frontend/dist/assets/` in checkpoint.

**Compatibility warning:** The Lu cache included React 19.0.0 but NOT the
React 18 range in the current NVP package.json. The smoke compiled and
executed with React 19; the release build must resolve and audit its
intended dependency versions. This smoke is not a dependency lockfile.

## Verified executable behavior (Linux source mode, not Windows)

- `python tools/nvp_desktop_alpha.py --smoke`: pass.
- `python tools/nvp_desktop_alpha.py --smoke-create`, then
  `--smoke-reopen` in a fresh OS process with the same `NVP_HOME`:
  pass, durable creator project and edited screenplay in SQLite.
- Managed Chromium cannot navigate to HTTP sites here; a Playwright
  request-to-FastAPI bridge therefore loaded the **original compiled React
  JavaScript/CSS in a real Chromium DOM**, forwarding its API calls to the
  real NVP FastAPI server. Verified:
  initial render, create film, open from sidebar, edit screenplay, save,
  reopen with exact text preserved, zero JS page errors.
  This is *not* an installed Windows WebView2 acceptance.
- Focused Python regressions: **40 tests and 15 subtests passed**, with
  5/5 abrupt process-death tests after correcting the resource-only
  reservation check.
- Subsequent complete local E2E-01D crash suite (`test_nvp_e2e01d_*.py`):
  **14 tests run, 2 skipped, zero failures** in 100.022 seconds on Linux.
  The two skips remain unverified; this is not Windows 10 native acceptance.

## Source repairs committed

- `99fb51b`: E2E-01D process crash child import path independent of test runner;
  resource-only crash test no longer assumes a FilmIndex table exists.
- `be57797`: NVP desktop source launcher finds its backend in source mode
  without setting PYTHONPATH; frozen PyInstaller import paths remain unchanged.
- `8e0c12f`: 17-tab film pipeline navigation scrolls horizontally with
  legible labels rather than squeezing into narrow unreadable columns.
- Prior native editorial/finishing corrections: `41bb27a`, `b104c6a`,
  `7021a53`.

## The remaining real Windows blocker

The available Debian environment has LLVM, Windows SDK, MSVC CRT, NSIS 3.11
and NVP source/frontend, but **no authentic Windows AMD64 CPython 3.11
runtime/PyInstaller onedir application**, nor Windows pywebview/Win32 wheels.
It cannot turn a Linux Python executable into a Windows executable by
linking against the Windows SDK. Direct outbound package downloads are blocked.

Do **not** ship a placeholder `NVP.exe`, a Lu EXE, or only static UI assets.
The existing `tools/nvp_e2e01e_validate_installer_payload.py` rejects
placeholder bundles and requires the genuine Windows Python DLL and React
assets.

Next: produce/obtain the authentic Windows onedir bundle at `dist/NVP/`,
run the payload validator, then invoke the already-restored NSIS compiler
through `packaging/build-nvp-nsis.sh`. Finally verify install, real WebView2
render, project create/edit/reopen, clean shutdown and uninstall on Windows 10
x64. A queued GitHub CI run and a Linux Chromium DOM test do not count as
Windows installed-app acceptance.
