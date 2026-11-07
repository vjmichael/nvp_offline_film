# NVP-DATA-ALL — Per-task migration closeout ledger

**Creator directives (2026-11-06):** All NVP production, capture, authoring,
editing, playback, media import and final mastering must be DATA-FIRST;
**FFmpeg is not used anywhere in the resulting application.** Do not
reintroduce FFmpeg as an optional fallback, packaged dependency, PATH
discovery, executable, CLI, decoder, exporter or test prerequisite. Old
source code may remain in historical commits, but **must not be an active
product path**. Reusable third-party components are welcome provided they
are independently licensed and do not require/invoke FFmpeg.

**Source authority:** immutable Digital Film World + OpenUSD scene,
performance and exact signed-64-bit Film Time events (7,056,000,000
ticks/second), Digital Take hashes, source-signal references and
non-destructive assembly manifests. Hardware renders ephemeral samples
and visuals as requested. Only an explicit final 2D presentation freezes
output raster/video/audio; samples/frames never define a Digital Take.

## Ordered implementation and acceptance tasks

| ID | Task | Evidence required | Implementation | Native acceptance |
| --- | --- | --- | --- | --- |
| DA-00 | Supersede any FFmpeg anywhere; permanent dependency guard | Core/export/import paths cannot spawn FFmpeg; CI enforces no active dependency; no stale automatic CI | IN PROGRESS | OPEN |
| DA-01 | Replace FPS-based shot planning with tick-addressed camera/event editor | Creator can author/edit/revise shots/cuts/gaps in integer Film Time; no 24-fps authority | OPEN | OPEN |
| DA-02 | Migrate legacy capture and motion controls | New frozen take ties source OpenUSD pose/actor/mic/sound references and exact time; old fixed-frame proxy cannot be a native Take | OPEN | OPEN |
| DA-03 | Connect filming sound producer and spatial evaluator | Immutable sample chunks and source events recorded at filming; two listeners from same Take yield different data-native audio | PARTIAL | OPEN |
| DA-04 | Native 3D live picture/audio evaluation | Time-synchronized interactive OpenUSD picture and spatial sound without pre-rendered 2D movie, bounded RAM; renderer device failures contained | PARTIAL (world-state inspector, dry audio) | OPEN |
| DA-05 | Non-FFmpeg import and non-FFmpeg final 2D export adapters | Trusted decode/import with source hash; approved 3D→2D image/audio render, independent encoder/mux, no FFmpeg | OPEN | OPEN |
| DA-06 | Quarantine frame/proxy/media legacy entrypoints | No accessible editor, API, or native tool path routes to old frame-based authoring/decoding/execution; legacy data readable as explicitly labeled historical formats | OPEN | OPEN |
| DA-07 | Native acceptance and installer | Win/Linux tests; installed Windows user interactions; long seek/playback/audio and picture sync; restart/crash/recovery; no FFmpeg present | OPEN | OPEN |

Definitions: **OPEN**=not coded/accepted; **PARTIAL**=substantial code
but missing required behavior; **IMPLEMENTED**=code landed without
independent acceptance; **ACCEPTED**=exact-head native tests including
relevant installed-app evidence passed. Do not collapse these statuses.

## Migration rules

- No claim of complete migration while an active UI/API path still
  produces an authoritative `frame_count`/`start_frame` or generates
  a legacy proxy for native filming or review.
- No deletion of immutable existing source data or silent rewriting of
  previously captured projects. Old formats can be inspected/imported
  only through a separately marked migration reader.
- Prefer one shared evaluator for the same Film Time/scene function.
  Preserve first-party authorization, opaque bounded windows, SHA
  provenance and recovery; tests cannot be waived merely because
  GitHub runs are delayed.
- All work and repair receipts go into
  `docs/NVP_ENGINEERING_STATE.md` and this checklist. The live branch
  is PR #74, `nvp/data-av01-native-scene-playback-20261106`.

## Work performed and outstanding defects

The existing USD/TemporalLedger and DATA-AV-01 source chunk reader,
dry spatial PCM mixer, native sound bridge and audio-clock-linked
world-state inspector establish the data-first foundation, **not**
complete acceptance. The most recent independently observed native
CI at commit `06546564941b319ccea436be59427d213db480ab`
failed: spatial USD time-code type, native consent test assumptions,
one existing React test; Windows installed acceptance was skipped.
These are tasks to repair, not releases to approve.

**Zero-FFmpeg clarification:** prior statements that FFmpeg could
remain for external media or final export are explicitly withdrawn.
A decoder/encoder must come from another suitable library or a native
format adapter; where none exists, the operation remains unavailable
until implemented instead of silently invoking FFmpeg.

## 2026-11-06 native CI diagnosis and repair

At historical head `06546564941b319ccea436be59427d213db480ab`, DATA-AV workflow run [42307683019](https://github.com/vjmichael/nvp_offline_film/actions/runs/42307683019) **failed** on both Windows and Linux Python matrix. Native test `test_native_usd_spatial_audio_overlay_is_ephemeral_and_sha_bound` raised OpenUSD `Type mismatch ... expected GfTimeCode, got TfPyObjWrapper` while writing `UsdMedia.SpatialAudio.startTime`. DA-03 code repair commit `e50029bbd4f0e4a762012f7482c01911643088ac` replaces the Python wrapper with the USD value type `Sdf.TimeCode` for start and end attributes. This repair has **not yet passed exact-head CI**. Other native permission tests failed (`READY` vs `DENIED`, `DENIED` vs `READY`); the React `FilmCameraSourcePanel.test.jsx` test expected two API calls but observed one. These failures remain unresolved pending investigation. The installed Windows `NVP.exe` job was **skipped**, not accepted. DA-00 through DA-07 native acceptance remain OPEN; no full migration claim.


### 2026-11-06 exact-head CI follow-up (DA-06 retirement test repair)

Observed PR #74 head `897632bad2eae498b2bd0166446886f14d90c42b` in GitHub Actions [DATA-AV run 42316012851](https://github.com/vjmichael/nvp_offline_film/actions/runs/42316012851). The DA-00 no-FFmpeg audit **passed** and React source-audition suite **passed** (12 tests); all four native OpenUSD/PCM jobs **failed** and installed Windows `NVP.exe` **failed** after installer creation because `--smoke-data-av` returned nonzero. Linux native log specifically shows seven obsolete SLATE-08B tests invoking `request_camera_still`, which now deliberately raises `PermissionError` to retire external proxy capture. This is a test-contract migration, not a reason to reenable the old renderer.

Commit `898ef25b2c56f30bf6ea9b0f94f79516f8748d53` replaces those seven obsolete delivery assertions with four fail-closed regression tests: no host/consent side effects, retirement capabilities, origin rejection, and closed-window rejection. The original tests remain in Git history. **This new commit is not yet independently CI-accepted.** Other native failures and the installed executable's underlying smoke failure require fresh exact-head logs and repairs; installed-device output, live continuous OpenUSD A/V, acoustics/HRTF, precise sync, capture and approved 2D deliverable are unverified. DA-00 implementation remains in progress despite audit pass; DA-01..DA-07 are not accepted. No FFmpeg fallback or legacy CI was introduced.


### 2026-11-06 exact-head CI triage (DA-06)

At PR #74 head `8bb43a39ea3e6962d7776ce7054c701e511cc060`, DATA-AV run [42320410090](https://github.com/vjmichael/nvp_offline_film/actions/runs/42320410090) completed: DA-00 dependency audit and React tests passed, but all four Windows/Linux native matrix jobs and installed Windows NVP.exe smoke failed. Linux Python 3.13 job `128244354511` shows all four new retirement tests failing at bridge construction with `TypeError: Actual native FilmIndex required`; this is a test fixture error, not evidence that the retired renderer should be restored. Commit [`8221663`](https://github.com/vjmichael/nvp_offline_film/commit/8221663c5bf59a0e3b06ab409fe21d4ec7157efb) creates a real temporary `Studio`/`FilmIndex` for the bridge and retains fail-closed assertions. This repair is NOT yet exact-head CI accepted. Windows installed job `128245486381` completed installer creation but failed the installed `NVP.exe --smoke-data-av` invocation; its root cause is still unproven and must be diagnosed separately. DA-00..DA-07 acceptance remains OPEN. Do not infer real device audio, continuous USD picture, HRTF, sync, capture or final 2D acceptance from these tests. No FFmpeg fallback was added.


### 2026-11-06 DA-07 installed smoke failure visibility

At exact inspected head `24a6ae8ded0eeab37293671bf9a8191138ac0350`, [DATA-AV run 42324419194](https://github.com/vjmichael/nvp_offline_film/actions/runs/42324419194) completed: DA-00 no-FFmpeg audit, all four Windows/Linux Python 3.11/3.13 OpenUSD/PCM jobs, and React passed. NSIS installer built, installation and installed executable hash check passed; installed `NVP.exe --smoke-data-av` returned nonzero and prevented WebView2/uninstall checks. The windowed executable suppressed the underlying Python exception in CI, so root cause remains **unproven**. Code commit `c5e73afa` adds opt-in exception diagnostics to the packaged entry point; workflow commit `5f7851bb` prints the diagnostic file when installed smoke fails. This is a diagnostic implementation repair, **not** an installed acceptance pass. Reinspect the next exact-head Windows log and repair the actual exception. DA-00 through DA-07 overall acceptance remains OPEN; real device A/V, continuous graphics, HRTF, capture and final 2D are unverified. No FFmpeg runtime or fallback was added.


### 2026-11-07 DA-07 Windows GUI-process exit-code repair
At exact inspected PR #74 head `7c0a14dc2e8551f13dd032f18fb5a58f6d211473`, DATA-AV run [42329066286](https://github.com/vjmichael/nvp_offline_film/actions/runs/42329066286) completed with DA-00 zero-FFmpeg audit, four Windows/Linux native OpenUSD/PCM Python 3.11/3.13 jobs, and React **passed**; installed Windows job **failed**. Its log explicitly showed `Installed native Digital Take and sound playback failed (exit )` (empty exit value), not a demonstrated nonzero Python exit. The workflow invoked a **windowed** PyInstaller NVP.exe using `&` then checked `$LASTEXITCODE`, which can be unset for GUI processes. Commit `4bd8c60224d05a8ed03e86d13999f255e306021d` replaces both packaged and installed smoke calls with `Start-Process -Wait -PassThru` and checks actual `.ExitCode`; diagnostics remain available. This fixes an observable CI harness defect, but the smoke result and installed WebView2/uninstall checks on the **new** head remain unverified until CI finishes. Do not treat prior empty `$LASTEXITCODE` as evidence of an application crash, and do not claim installed acceptance. DA-00 through DA-07 overall acceptance remains OPEN; continuous 3D, real audio device sync, advanced acoustics/HRTF, filming capture and approved 3D-to-2D delivery remain independently unverified. No FFmpeg invocation or fallback added.


### 2026-11-07 DA-07 packaged native breakpoint triage

At PR #74 source head `c6d09db04bd30ad2e2e6bad9cced9c53ea8a6102`, [DATA-AV run 42334747289](https://github.com/vjmichael/nvp_offline_film/actions/runs/42334747289) completed with the DA-00 FFmpeg audit, React, and all four Windows/Linux OpenUSD/PCM matrix jobs **passing**. The Windows packaged executable job **failed before NSIS installer creation**: the freshly bundled `dist/NVP/NVP.exe --smoke-data-av` exited `-2147483645` (Windows exception `0x80000003`, breakpoint). This is a native process failure, **not** the previously suspected empty PowerShell exit-code artifact; no installed-app test ran. The Python exception diagnostic file was absent in the job output, so the faulting module/call remains unknown. Commit `0ee0940fce9dc3e29c2afe98601c1fafbe87b9fc` adds fsync-backed opt-in stage receipts before and after the native acceptance module import and execution, preserving Python tracebacks in the same diagnostic file. The existing workflow already prints this file before checking the process exit. The next exact-head job must use these receipts to isolate the crash, then repair its native cause; this diagnostic patch is **not** crash resolution or acceptance. DA-00 through DA-07 overall acceptance remains OPEN; continuous native 3D, HRTF, synchronized device A/V, real capture and approved final 2D remain unproven. No FFmpeg fallback or retired proxy CI was introduced.
