# INDEX-TIME-06 — Trusted Desktop Footage Import and Source Frame Review

**November 6, 2026. Draft implementation; exact-head real Windows/Linux/installed NSIS acceptance pending.**

## Creator workflow

1. Open a saved film in the installed NVP Windows desktop application.
2. Select **17 · Indexed footage**.
3. Click **Import original footage…**; the operating system opens a native
   file picker for MP4, MOV, MKV or WebM. NVP shows the exact picked filename,
   size and custody statement in a separate native Yes/Cancel approval.
   Browser JS never sees the original path or an executable selector.
4. The existing external media catalog creates a project-scoped full SHA
   record; media inventory attaches the logical original-volume identity,
   uses installed FFprobe for normalized metadata, and rehashes before and
   after probe. The existing SourceFilmBridge publishes a version-1 immutable
   FilmIndex asset only after full hash custody, then NVPFrameIndex indexes
   the true PTS/keyframe ordinals without a repeated whole-file hash on
   each later interaction.
5. An initial immutable Film Time imported-video edit is created at zero,
   using **nearest** rounding policy for source timebases that cannot
   exactly resolve to NVP integer ticks. The original indexed source is
   never copied or rewritten. With the current INDEX-TIME-02 contract,
   the last indexed frame cannot be placed without a measured *next-frame*
   out-exclusive PTS; it remains in the complete original frame index and
   is explicitly reported as unplaced rather than inventing a frame duration.
6. The editor immediately refreshes and selects this versioned imported
   source edit. The director can browse all indexed placements, seek exact
   Film Time or inspect the source PTS/held frame interval.
7. **Preview actual source frame** performs a second, separate native
   OS confirmation for the **exact edit ID/revision/SHA, ordinal, absolute
   original PTS and source Film Time**. The host consumes a single-use,
   short-lived, exact-scope token under its existing
   `NativeFilmTimeWindowHost` creator authorization check. One source
   frame goes through the existing TaskLedger, ApprovedTaskBindings,
   admitted and OS-contained FFmpeg worker. The host independently
   reopens the approved source and verifies the PNG/receipt/source PTS.
   React only paints a SHA-consistent, bounded base64 PNG delivered through
   the current WebView2's `pywebview.api`. Changing selection clears the
   previous picture and rejects late results.
8. **Cancel source preview** triggers a native confirmation, revokes a
   queued grant atomically or signals the running contained worker and
   waits for its durable termination/receipt. Closing the desktop signals
   all owned jobs; failed/unproven cleanup does not fabricate READY output.

## Trust and limits

- **No new POST HTTP file picker, file path parameter, renderer launcher,
  arbitrary subprocess API or browser-signed permission receipt.**
  `backend/nvp_api.py` retains its three INDEX-TIME-05 GET-only metadata
  routes; native actions are bound to an origin-verified window and OS UI.
- Import and review methods do not serialize original absolute paths,
  logical volume roots, per-job folders, worker scripts, or tool locations
  to the browser, including when native exceptions occur.
- Fast preview still declares
  `SOURCE_STAMP_UNVERIFIED_PREVIEW`, not full-current-original SHA
  acceptance; the ingest itself performed a full source hash and final
  picture conform still requires its separate exact creator approval.
  All PNGs are explicitly **unapproved review derivatives**.
- Real-source ingest is synchronous in a background native pywebview API
  call and can take substantial time for very large originals. An
  interrupted import may leave durable catalog/index entries; it must never
  fabricate a completed import. A separately designed resumable import
  transaction is a later robustness task.
- 12 MiB maximum native IPC PNG, 8192-pixel dimensions and one-frame
  review limit; larger picture candidates fail closed rather than exhaust
  WebView IPC memory. No video playback or final frame/audio master claimed.
- Multiple imports create separate source identities, even for the same
  media file. Automatic duplicate detection/relinking can be added later.

## Installed Windows one-click execution

The original native worker was written for `sys.executable=python.exe`.
A PyInstaller Windows GUI executable cannot naively execute a loose
Python script with that command. This wave adds a dedicated
`NVP.exe --trusted-film-time-worker <exact_script_sha>` entry that runs
the **same raw native source-window worker file** using runpy only after
checking its SHA. The existing supervisor still pins the executable,
worker file, original FilmIndex plan, FFmpeg/FFprobe SHA, and resource
approval. The executable is contained in the same OS Job Object lifecycle.

NSIS's audited PyInstaller one-directory payload now includes actual
FFmpeg/FFprobe binaries at `_internal/ffmpeg/` and the hash-pinned
source worker at `_internal/tools/`. The native app discovers its
bundled tools before PATH. Installer audit rejects Chocolatey shims or
missing/fake x64 PE binaries. An installed-process acceptance
`--smoke-source` creates disposable VFR/B-frame footage, routes it
through the same source-index/worker path and independently checks the
PNG and unchanged original. `--smoke-window` uses an actual WebView2
window and visits the camera-independent Indexed Footage tab to require
the installed native import action to appear. This test fixture does not
fake a visually clicked real OS picker; human physical picker acceptance
remains open.

**Third-party distribution:** FFmpeg/FFprobe binary license/configuration,
notices, corresponding-source obligations and any GPL/LGPL requirements
must be audited before releasing the installer publicly. CI bundle
integrity is not a substitute for license acceptance.

## Exact changed files and verification

- `backend/nvp_index_time06_native_desktop.py`
- `backend/nvp_film_time_window_host.py` frozen launch adaptation
- `tools/nvp_desktop_alpha.py` JS API, isolated smoke, pinned worker entry
- `frontend/src/FilmTimeIndexPanel.jsx`, `FilmTimeNativeBridge.test.jsx`
- `tests/test_nvp_index_time06_native_desktop.py`
- `tools/nvp_e2e01e_validate_installer_payload.py`
- `.github/workflows/nvp-index-time06-native.yml`
- `.github/workflows/nvp-e2e01e-windows-alpha.yml`

**Do not mark accepted until:** actual exact-SHA Windows/Linux 3.11/3.13
native tests, React tests, real installed NSIS WebView2 tab, real
frozen child VFR import/PNG, failure/cancellation/recovery receipts,
original source hashing and public-distribution license checks have
been reviewed. This workstream is separate from SLATE-08B #67; no
unverified Slate renderer acceptance is inherited.
