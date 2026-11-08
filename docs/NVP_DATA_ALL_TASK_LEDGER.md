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
| DA-01 | Replace FPS-based shot planning with tick-addressed camera/event editor | Creator can author/edit/revise shots/cuts/gaps in integer Film Time; no 24-fps authority | PARTIAL (exact-time sequence + persisted-event validation; UI migration outstanding) | OPEN |
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


### 2026-11-07 DA-07 exact-head packaged breakpoint localization

At PR #74 head `51a40e6c0261fa9ea6c07eb9fbceaa4fa6651a01`, [DATA-AV run 42338397141](https://github.com/vjmichael/nvp_offline_film/actions/runs/42338397141) completed: DA-00 dependency audit, React build/tests and all four Windows/Linux OpenUSD/PCM Python 3.11/3.13 jobs **passed**. The packaged Windows `NVP.exe --smoke-data-av` still exited `-2147483645` (`0x80000003`), before installer creation; installed Windows acceptance was **skipped**, not passed. Durable diagnostics reached `entry`, `before_native_acceptance_import`, `after_native_acceptance_import`, but not `after_native_acceptance_run`. Therefore the fatal breakpoint occurs inside the smoke execution, not its Python import; its precise native operation is not yet proven. Commits `d17510a` and `a59bf65` add and correct fsynced, opt-in stage receipts around actual Studio, OpenUSD scene publication, Take freeze, native bridge, audio-window and scene evaluation operations. This is implementation for crash isolation, **not** a crash fix or acceptance. Fresh exact-head CI must identify the last stage and support a targeted repair. DA-00..DA-07 overall acceptance remains OPEN. No FFmpeg fallback, retired proxy CI, or claim of actual device output was introduced.


### 2026-11-07 DA-07 packaged OpenUSD crash isolation (run 42343547516)
At inspected head `d15d3213e4e9e4838d434b922f4326619e5828a5`, [DATA-AV run 42343547516](https://github.com/vjmichael/nvp_offline_film/actions/runs/42343547516) completed: zero-FFmpeg audit, React and four native Windows/Linux Python 3.11/3.13 jobs passed. Packaged Windows `NVP.exe` failed with breakpoint `0x80000003`; NSIS and installed-app checks were skipped. Durable receipts reached `native_before_scene_publish` but not `native_after_scene_publish`. This localizes the fatal native failure to OpenUSD scene publication in the packaged process; it does not prove which USD API or DLL is responsible. Code commit `e4a41b15faaf26d0c8b778583444e3cde60400d6` adds opt-in fsynced checkpoints inside the real OpenUSD publisher (pxr import, stage creation, prim definition and composition), without recording scene content or changing the immutable Take. Await exact-head native logs to isolate and repair the actual operation. DA-00..DA-07 overall acceptance remains OPEN; actual installed Windows NVP.exe, continuous 3D/audio, HRTF, sync, capture and final 2D remain unverified. No FFmpeg path was introduced.


### 2026-11-07 DA-07 exact-head OpenUSD layer crash isolation

At exact PR #74 head `ead86a112ecbb4bd5e727e44080d463b7e2206ac`, [DATA-AV run 42348593700](https://github.com/vjmichael/nvp_offline_film/actions/runs/42348593700) completed: DA-00 no-FFmpeg audit, React build/tests and all four Windows/Linux OpenUSD/PCM Python 3.11/3.13 jobs passed. Windows packaged `NVP.exe --smoke-data-av` still failed with `-2147483645` (`0x80000003`) before NSIS installation. Durable receipts reached `usd_publish_after_pxr` but not `usd_publish_before_stage_open`; the fault is narrowed to the interval containing `Sdf.Layer.CreateAnonymous('nvp_layout.usda')`, not yet proven to be that call rather than adjacent execution. Commit `a5ea6f5ab207305f253567f173b647bd0fc7eefb` adds before/after layer-creation receipts and fixes the literal backslash-n diagnostic formatting. This is executable diagnostic code, NOT a root-cause repair or packaged/installed acceptance. The new commit awaits its own exact-head CI. DA-00 through DA-07 overall acceptance remains OPEN; live continuous 3D A/V, environmental acoustics/HRTF, real-device synchronization, actual filming and approved 3D-to-2D deliverable remain independently unverified. No FFmpeg fallback and no retired proxy CI were introduced.


### 2026-11-07 DA-07 packaged OpenUSD resource collection repair (verification pending)
At exact inspected PR #74 head `23d9e9e39fd2429668b9540cdb2f45967d91ee5e`, [DATA-AV run 42351002496](https://github.com/vjmichael/nvp_offline_film/actions/runs/42351002496) completed: DA-00 no-FFmpeg audit, four native Windows/Linux OpenUSD/PCM Python 3.11/3.13 jobs, and React passed; packaged Windows NVP.exe failed with `0x80000003` and installed acceptance was not reached. Durable stage receipts end at `usd_publish_before_layout_layer_create`, immediately before `Sdf.Layer.CreateAnonymous("nvp_layout.usda")`; the precise native crash mechanism is not proven. Commit `1e1b6d612ad083189bb105210b8e509e2c7c6dc1` changes the Windows PyInstaller command from `--collect-submodules pxr` to `--collect-all pxr` to package OpenUSD's data/plugin resources in addition to Python submodules. This is a packaging-code repair hypothesis, **not a confirmed fix**; inspect fresh exact-head packaged/installed Windows logs. DA-00..DA-07 overall acceptance remains OPEN; actual continuous native 3D picture, advanced acoustics/HRTF, synchronized hardware A/V, filming capture and final 3D-to-2D deliverable remain independently unverified. No FFmpeg fallback or retired proxy workflow was enabled.


### 2026-11-07 DA-01 persisted exact-time camera event hardening (native verification pending)
At branch head `de27f8fbf28ffe40e7938a83b01a6435a520a090`, the newly triggered PR workflow runs were reported queued, not passed. The prior verified native result remains run [42351002496](https://github.com/vjmichael/nvp_offline_film/actions/runs/42351002496): no-FFmpeg audit, React, and four Win/Linux OpenUSD/PCM jobs passed; packaged Windows `NVP.exe` failed `0x80000003` before installed acceptance. The `--collect-all pxr` packaging change has **no verified success yet**.

DA-01 code commits `aed4324` and `c91323c` now reject persisted TemporalLedger camera events with unrecognized observation patterns, non-camera subjects, or end ticks beyond the authoritative sequence duration. Tests `bd5d1f8` and `09aea98` create valid immutable ledger revisions carrying invalid native camera semantics and require `ExactTimeShotSequence.read` to fail closed. These are actual source and regression changes; the new tests have **not** been run in native Win/Linux CI yet. DA-01 is PARTIAL implementation, OPEN acceptance; DA-00..DA-07 overall acceptance remain OPEN. The underlying packaged OpenUSD crash, continuous live 3D/audio, HRTF, real-device sync, filming sound capture and approved final 2D delivery are not accepted. No FFmpeg fallback or old proxy CI was enabled.


### 2026-11-07 DA-01 persisted camera schema closure (verification pending)

Commits `5dc7d960`, `d1057402`, `2ea25b1b` harden `ExactTimeShotSequence.read` to refuse any additional camera payload keys (including historical `frame_count`/`start_frame`) and repeated shot IDs, while keeping exact decimal tick authoring, frozen source SHA, revision history and read-only legacy data unchanged. The new tests publish a valid TemporalLedger revision containing frame metadata and assert that the camera-specific reader refuses it; a repeated ID is rejected earlier by TemporalLedger's staged SQLite primary key. **Code committed, tests not independently run on this exact head.** DA-01 remains PARTIAL / acceptance OPEN. This change does not fix the packaged Windows OpenUSD breakpoint or establish real installed NVP.exe, continuous 3D A/V, HRTF, synchronization, capture, or final 2D acceptance. No FFmpeg fallback or retired CI was enabled.

### 2026-11-07 DA-01 exact-tick camera lookup / latest CI disposition

At PR #74 source SHA `42bfd6261dfbeca421e4d5807610761f33552e11`, [DATA-AV run 42367681181](https://github.com/vjmichael/nvp_offline_film/actions/runs/42367681181) ended **cancelled**, not accepted: DA-00 audit, React and all four Windows/Linux OpenUSD/PCM matrix jobs passed; the packaged Windows candidate and NSIS installer built, but the actual installation/WebView2/uninstall step was **cancelled**. This supplies no installed NVP.exe acceptance. The earlier OpenUSD packaged breakpoint fix is not independently demonstrated by an installed smoke pass.

Code commits `02b74e7a10b68a9e8039097c37d1a3fe222e60e7` and `744c7ae63cb1164b3c33cc30d318c44d23afee5e` add `ExactTimeShotSequence.camera_at_tick` and boundary regressions. Lookup uses canonical integer Film Time strings, half-open shot intervals, explicit GAP responses and SHA-bound source identity; it rejects out-of-range/floating ticks and does not invent proxy frames. **Implemented, new exact-head CI unverified.** DA-01 remains PARTIAL/OPEN; DA-00 and DA-02..DA-07 remain not fully accepted. Real continuous 3D A/V, acoustics/HRTF, sound capture, installed Windows interaction and final 3D-to-2D export are still unverified. No FFmpeg fallback or retired PR workflow was enabled.


### 2026-11-07 DA-01 exact-window camera partition (verification pending)

Code commit [1ba8288](https://github.com/vjmichael/nvp_offline_film/commit/1ba82883e7ea43fb6a2b911bdfa58b6d6513ed43) adds `ExactTimeShotSequence.camera_segments`: bounded half-open integer Film Time windows are partitioned into authored camera segments and explicit intentional GAP segments, preserving scene/timeline SHA identity without creating frames or using FPS. Regression commit [fdd8fdc](https://github.com/vjmichael/nvp_offline_film/commit/fdd8fdc5074d0037f8b3d3a3fcc276aec88e3721) checks exact boundaries, non-frame-aligned windows and invalid intervals. Both are **implemented, unverified by exact-head CI**. Earlier [DATA-AV run 42375345690](https://github.com/vjmichael/nvp_offline_film/actions/runs/42375345690) at prior head `5887c89a730368fbd96c32502955a7e395252a66` was still **in progress** at inspection; do not promote its other passing jobs or unrelated workflow outcomes to installed NVP.exe acceptance. DA-01 remains PARTIAL / native acceptance OPEN, and DA-00, DA-02..DA-07 remain overall unaccepted. The Windows installed-app result, real continuous 3D/A/V, HRTF, sound capture and final 2D delivery are still unverified. No FFmpeg fallback or retired proxy CI was introduced.


**CI status correction (2026-11-07):** Reinspection of DATA-AV run [42375345690](https://github.com/vjmichael/nvp_offline_film/actions/runs/42375345690) jobs confirms six passes (DA-00 audit, React, four Win/Linux native Python jobs), while the packaged/installed Windows NVP.exe job ended **cancelled**, not accepted. These results apply to historical head `5887c89a730368fbd96c32502955a7e395252a66`, not the newly committed camera window partition. Installed interaction and device A/V acceptance remain OPEN.

### 2026-11-07 DA-01 immutable shot revision operation (exact-head verification open)

Code commit [802116e](https://github.com/vjmichael/nvp_offline_film/commit/802116e83a8d7e78e17f65e9cdeca0ee37fe9a5b) adds `ExactTimeShotSequence.revise_shot`: an existing exact-tick shot can be replaced or removed by its stable identity using the expected immutable revision. The method reconstructs the source-bound shot plan from the verified prior revision, rejects unknown IDs, altered replacement IDs and removal of the final shot, then republishes through the existing typed camera validation and TemporalLedger compare-and-swap. It does not mutate source scene, earlier revisions, frozen Takes or introduce FPS/FFmpeg. Regression commit [5c22665](https://github.com/vjmichael/nvp_offline_film/commit/5c226656426c9e990f3f9b9e623e9c902340bf6f) tests replacement, deletion, prior revision SHA preservation, stale-CAS refusal and invalid identity cases. **Code committed, exact-head native tests unverified.** DA-01 remains PARTIAL/OPEN pending actual editor UI and installed acceptance.

At historical head `09ea0f2b6fc944775aa09c0f4cb80c6dc431d3d3`, [DATA-AV run 42380560101](https://github.com/vjmichael/nvp_offline_film/actions/runs/42380560101) had six completed passes (DA-00 audit, React, Win/Linux Python 3.11/3.13 native) while the packaged/installed Windows job was **in progress** at inspection. No installed `NVP.exe` pass or real-device continuous A/V, HRTF, synchronization, live filming sound or final 2D export acceptance is claimed. No retired proxy PR workflow was restarted.


### 2026-11-07 DA-01 exact-tick shot insertion (native acceptance pending)

At inspected source head `9366910572497bb0e09fc39ad1fd4b3664abc35f`, DATA-AV run [42384991069](https://github.com/vjmichael/nvp_offline_film/actions/runs/42384991069) has six successful jobs (DA-00 audit, React, Windows/Linux Python 3.11/3.13 native) and a **cancelled** installed Windows job. The NSIS candidate built, but its installation/WebView2/uninstall step was cancelled; no installed NVP.exe pass is established. Other older workflows failing do not establish this DA gate's failure.

Code commits `5fa54ec16fa8f8fd507366b4e9a6fd2b9a185776` and `42f60198148e30476f7e580a23707c4a6e47f496` add `ExactTimeShotSequence.insert_shot` and a regression for insertion inside an intentional Film Time gap, preserved prior revision and frozen scene SHA, half-open camera lookup, stale compare-and-swap, duplicate identity, overlap and rejected frame fields. This is a native, exact-decimal-tick operation, not frame authoring. **These commits have not received exact-head native acceptance**; the DA-01 desktop editing UI remains to be migrated. DA-00..DA-07 overall acceptance remains OPEN. Continuous visual/audio 3D, HRTF, hardware sync, capture and final 2D output are independently unverified. No FFmpeg fallback or retired proxy CI was introduced.


### 2026-11-07 DA-01 desktop precision and frozen-Take guard
At inspected PR #74 head `c31b3453df1b23d223bbd35ebe1e7a2ff3dc8372`, [DATA-AV run 42386183390](https://github.com/vjmichael/nvp_offline_film/actions/runs/42386183390) concluded **cancelled**: DA-00 no-FFmpeg audit, React build/tests and all four native OpenUSD/PCM Windows/Linux Python 3.11/3.13 jobs passed; packaged Windows installer candidate built, but installation/WebView2 acceptance was cancelled. This is not installed-app acceptance. Code commit `71f378f30819de9899fe2e052b7b3d81a6228a82` repairs the actual DA-01 React editor: appending a draft shot invalidates the previously saved timeline SHA so the native freeze button cannot approve stale saved camera timing; saved durations are no longer silently floored to whole seconds. Exact microsecond-representable durations are displayed without truncation; finer-than-microsecond durations are explicitly read-only until a precise-tick editor exists. These UI repairs are **implemented, exact-head tests pending**, not independently accepted. DA-01 remains PARTIAL/OPEN; DA-00 and DA-02..DA-07 remain OPEN overall. Continuous 3D picture/audio, HRTF, hardware synchronization, real filming and final 3D-to-2D delivery remain unverified. No FFmpeg fallback or retired proxy CI was introduced.


### 2026-11-07 DA-01 precise-tick desktop authoring (acceptance pending)

At historical head `07e5d463fd10d7c59d55a4bc337022733d379a25`, DATA-AV run [42394071476](https://github.com/vjmichael/nvp_offline_film/actions/runs/42394071476) had six successful jobs (no-FFmpeg audit, React, four native Windows/Linux Python 3.11/3.13 jobs); Windows packaged/installed NVP.exe was **in progress** when inspected, so installed acceptance remains OPEN. This evidence predates the changes below.

Commits `9222d7b`, `ce2d3ea`, and `6d70866` implement a creator-selectable exact-integer Film Time tick editor for shot start, observation length, and sequence duration, including sub-microsecond saved durations. Canonical decimal tick input is bounded to signed 64-bit; the UI never converts precise values through JS floating-point or fixed 24-fps frames. Switching from seconds preserves persisted finer-than-microsecond duration; invalid values fail closed. React regressions cover exact duration republishing and overflow rejection. **Implementation committed; new exact-head CI, native installed interaction and actual filming remain unverified.** DA-01 stays PARTIAL / acceptance OPEN; DA-00 and DA-02..DA-07 overall acceptance remain OPEN. Continuous 3D picture/audio, HRTF/acoustics, device A/V sync, filming sound capture and approved 3D-to-2D export still require independent acceptance. No FFmpeg fallback or retired proxy workflow was enabled.


### 2026-11-07 DA-01 per-observation desktop editing (exact-head acceptance open)

At PR #74 head `e0e2acc1e8402a1e067a8278e774ada7daa317bf`, DATA-AV run [42399409716](https://github.com/vjmichael/nvp_offline_film/actions/runs/42399409716) showed six completed passes (no-FFmpeg audit, React, Windows/Linux Python 3.11/3.13 native); packaged/installed Windows NVP.exe remained **in progress** at inspection. These passes predate the changes below and do not verify the installed app. Code commits [`a36a524`](https://github.com/vjmichael/nvp_offline_film/commit/a36a5246a51f00c1d586b0902eed90109669cb1a) and [`8c31c27`](https://github.com/vjmichael/nvp_offline_film/commit/8c31c272f820ee9260210ae655b8942280f378be) expose per-shot camera, start/end exact ticks, pattern and removal in the desktop editor. All draft edits revoke the previously saved timeline SHA and cannot authorize stale Take freezing. Prepublication checks reject overlapping, reversed, noncanonical and duplicate-ID shot edits; native publication remains authoritative. Draft insertion now allocates an unused shot identity after deletion. **Implementation committed; React/native exact-head and installed-app interaction unverified.** DA-01 remains PARTIAL/OPEN, DA-00 and DA-02..DA-07 overall acceptance OPEN. Continuous 3D A/V, acoustics/HRTF, real device sync, filming sound and approved final 2D output remain unverified. No FFmpeg fallback or retired proxy workflow was activated.

### 2026-11-07 DA-01 duration revision authority repair (unverified)

At inspected PR #74 head `e8e0e1b045092ee3422be60486d616e51b534ec8`, DATA-AV run [42403751235](https://github.com/vjmichael/nvp_offline_film/actions/runs/42403751235) was **in progress**; no installed Windows acceptance or exact-head pass can be inferred. Commits `9fd0dc73d6b681b7648f5534d2d7f53b5171f4db` and `9661b2078dcd9301bfb0a971dc4e4d440ff085bd` invalidate saved timeline SHA authority when the desktop duration limit changes, reject camera identities outside the immutable source scene and unsupported coverage patterns before POST, and add a desktop regression guard. These are source changes, **not yet exact-head CI accepted**. DA-01 remains PARTIAL/OPEN; DA-00 and DA-02..DA-07 overall acceptance remain OPEN. No FFmpeg path or legacy CI was restored. Continuous native 3D picture/audio, HRTF, device sync, installed app and final 2D acceptance remain unverified.


### 2026-11-07 DA-06 active camera-source still IPC retirement (exact-head verification open)

Commits [fa54925](https://github.com/vjmichael/nvp_offline_film/commit/fa54925599a8c6639a526b7624ffaec090359e84) and [b2169e5](https://github.com/vjmichael/nvp_offline_film/commit/b2169e5ba6407eed019855fe01d11182743725dd) disconnect the active `FilmCameraSourcePanel` from legacy Blender still capability discovery, request, polling and cancellation. The OpenUSD source-pose/lens inspector remains read-only; the old still button stays disabled even when a native bridge advertises availability. A React regression injects the retired native methods and asserts zero invocations. No captured source data is deleted; this is UI-path quarantine, not product-wide removal of historical APIs or acceptance of live 3D playback.

Prior source head `a753f1c40a8ffb2cad20a8f54499ed83c27ee33b` has [DATA-AV run 42407215545](https://github.com/vjmichael/nvp_offline_film/actions/runs/42407215545) **in progress** at inspection. New commits have no independently verified exact-head Windows/Linux React or installed `NVP.exe` acceptance. DA-06 implementation remains PARTIAL / native acceptance OPEN; DA-01 remains PARTIAL / OPEN, all DA-00..DA-07 overall acceptance OPEN. FFmpeg prohibition remains mandatory. Continuous 3D picture/audio, HRTF, real-device sync, capture and approved final 2D export are independently unaccepted.


### 2026-11-07 DA-01 concurrent desktop publication authority guard

At inspected PR #74 head `b5e05c2c0782c1d4f05c3db86e69d932f44cbac8`, [DATA-AV run 42411185321](https://github.com/vjmichael/nvp_offline_film/actions/runs/42411185321) completed successfully: DA-00 audit, React, Windows/Linux Python 3.11/3.13 native jobs and packaged/installed Windows NVP.exe workflow job all reported success. This is workflow acceptance for the tested head only, **not** independent evidence of actual interactive device playback, HRTF, 3D A/V synchronization, filming capture or 3D-to-2D delivery. The other legacy workflows have separate failures and were not restarted.

DA-01 code commit `39bf2c5` introduces a draft edit epoch so a delayed successful timing publication cannot restore Take-freeze authorization after the creator has changed the draft during the request. Regression commit `a62388a` exercises a delayed POST and an intervening duration edit. These commits are **not exact-head CI verified**. The regression currently checks the disabled freeze control; installed native bridge interaction and hostile concurrency acceptance remain OPEN. DA-01 implementation PARTIAL / native acceptance OPEN; DA-00..DA-07 overall acceptance OPEN. No FFmpeg fallback or retired proxy CI was enabled.


### 2026-11-07 DA-01 stale-load fencing and native authorization regression

PR #74 commits `1cca9d0` and `1dd6a2a` add a React test with an actual mocked native Take-freeze bridge, proving that changing a saved duration disables the bridge invocation, and fence delayed native-time-shot GET responses by draft epoch. Switching scene also invalidates the epoch so a prior source's pending save cannot restore SHA authority. These are code changes; **exact-head React/Windows/Linux and installed NVP.exe acceptance is not yet established**. DA-01 remains PARTIAL / acceptance OPEN; DA-00 and DA-02..DA-07 remain open. Prior head `44645d045c9b82c607bfea22dbd4f51ccfebe5b6` had DATA-AV run [42416118950](https://github.com/vjmichael/nvp_offline_film/actions/runs/42416118950) in progress when inspected; no result is inferred. Legacy workflows with unrelated failures were not restarted. No FFmpeg fallback. Continuous 3D A/V, HRTF, real-device synchronization, filming capture, and final 2D delivery remain unaccepted.


### 2026-11-07 DA-01 precise authoring unit-switch repair

At inspected PR #74 head `b61e8c2dda8085c86dcf0b6bf2d231d1bd8e952f`, DATA-AV run [42421201084](https://github.com/vjmichael/nvp_offline_film/actions/runs/42421201084) was queued; its zero-FFmpeg audit job had succeeded, while React and native Windows/Linux matrix jobs had not yet completed. This is **not** exact-head acceptance for the new changes. Commits [`2fd8b39`](https://github.com/vjmichael/nvp_offline_film/commit/2fd8b393d7d4f38490dd078ff1d04f4315a7c3b0) and [`9aa7d5f`](https://github.com/vjmichael/nvp_offline_film/commit/9aa7d5f7f471fa519d790ce1b420f7956b6832ea) repair DA-01 desktop tick/seconds switching: edited exact tick durations are converted back to seconds only if precisely representable; sub-microsecond drafts refuse lossy conversion; published duration display and precision state are refreshed from the authoritative response. Two React regression tests were added. **Implementation PARTIAL; native/installed acceptance OPEN.** No FFmpeg invocation or fallback was added. Installed Windows NVP.exe, real continuous OpenUSD picture/audio, HRTF/environment acoustics, device sync, sound filming and final 3D-to-2D delivery remain independently unverified. Retired proxy PR CI was not restarted.


### 2026-11-07 DA-01 delayed-publication draft preservation (verification pending)

At preceding head `c5fc1a5c780c43cac666d9b5955a8db70e691067`, the DATA-AV workflow [42426877142](https://github.com/vjmichael/nvp_offline_film/actions/runs/42426877142) is **cancelled**, not a passing exact-head native or installed Windows acceptance. Code commits [0bf54b4](https://github.com/vjmichael/nvp_offline_film/commit/0bf54b4153777eba9d6203dba2c8e99576198df7) and [4da1da2](https://github.com/vjmichael/nvp_offline_film/commit/4da1da2d85ba8a60e3b0914dea1aa3315ab9fc15) repair the DA-01 desktop delayed-publication race: server revision advances for future compare-and-swap, but an older response no longer overwrites a newer creator-edited Film Time duration or reports the newer draft saved. The regression checks preservation, disabled Take freeze and subsequent publication using the newer exact tick duration with the updated expected revision. **Code committed; no new exact-head React, native Windows/Linux or installed NVP.exe result yet.** DA-01 remains PARTIAL/OPEN, all DA-00..DA-07 overall acceptance OPEN. No FFmpeg path or retired proxy workflow was reactivated. Continuous 3D A/V, HRTF, real-device sync, capture and final 3D-to-2D remain independently unaccepted.


### 2026-11-07 DA-03 immutable PCM identity preflight (verification pending)

PR #74 commits `b1790076` and `5652dc15` preflight all recorded event/source identities before publishing any original PCM chunks. Duplicate source IDs and source IDs reserved for the scene, Take or timelines now fail before leaving an avoidable partial recording. Two native regression tests assert no PCM or combined timeline revision is created for duplicate/reserved sources. This is a targeted DA-03 implementation repair, **not** verified exact-head Windows/Linux or installed NVP.exe acceptance. Prior observed head `0fb775869cdc0ef644d3fb73a90e8a51476932d0` had queued DATA-AV run [42430490262](https://github.com/vjmichael/nvp_offline_film/actions/runs/42430490262); queued is not passed. DA-03 stays PARTIAL / acceptance OPEN, as do DA-00 through DA-07 overall. No FFmpeg path, proxy CI revival, device A/V, HRTF, capture hardware or 3D-to-2D acceptance is claimed.


### 2026-11-07 DA-03 all-event sound preflight (pending exact-head verification)

Code commits `09edf707`, `4cc7cd3`, and `4469a66` move full captured event identity, scene emitter, event kind, signed Film Time and gain validation ahead of *all* PCM writes. Camera-event identity collisions are now rejected before source publication; invalid second recordings cannot orphan a valid first PCM source. Native regression tests cover both cases. This is a preflight atomicity improvement, not a complete transaction: a truncated PCM iterator or approval denial may still leave unreferenced original chunks. DA-03 implementation PARTIAL; exact-head Windows/Linux and installed NVP.exe acceptance OPEN. No FFmpeg or proxy fallback. Continuous 3D A/V, HRTF, device synchronization, actual microphone capture and 3D-to-2D mastering remain independently unaccepted.


### 2026-11-07 DA-03 preexisting source and self-collision preflight (unverified)

Code commits [d1c88cc](https://github.com/vjmichael/nvp_offline_film/commit/d1c88cc1629a47e02389f44893cf7432746f72a0) and [8b3eaf0](https://github.com/vjmichael/nvp_offline_film/commit/8b3eaf0e32422827f7c94c44157833721064603a) reject sound event IDs equal to their own PCM source IDs and reject a previously published source ID anywhere in a recording batch **before** publishing the first new PCM revision. Two native regression cases assert fail-closed behavior and absence of a new combined timeline. This reduces avoidable orphan sources but does not make filming transactional; truncated iterators, publication failures and denied freeze can still leave unreferenced immutable PCM. Prior inspected commit `968751af586186b4a4143d28d3c9136bf3dd26eb` had [DATA-AV run 42440512967](https://github.com/vjmichael/nvp_offline_film/actions/runs/42440512967) queued, **not passed**. These new commits have no exact-head Win/Linux or installed NVP.exe acceptance. DA-03 remains PARTIAL / acceptance OPEN; DA-00..DA-07 overall acceptance OPEN. No FFmpeg path or fallback was added, retired proxy CI was not restarted. Live 3D/audio, acoustics/HRTF, real-device sync, actual microphone capture and final 3D-to-2D output remain independently unverified.


### 2026-11-08 DA-03 capture output preflight repair (verification OPEN)

At inspected PR #74 head `4f1f90bc99dda888be14d38f186d71ef5b39346a`, DATA-AV workflow [42444637059](https://github.com/vjmichael/nvp_offline_film/actions/runs/42444637059) was **queued**, not accepted. The source `backend/nvp_data_first_filming.py` contained literal escaped `\\n` sequences in the new source-identity preflight block; commit `f9fe5dee` repairs the malformed Python source. Commit `835e26e` also checks for already-published sound timeline and Take output IDs **before any PCM source publication**, preventing avoidable orphan source revisions when the eventual output ID is occupied. Commit `98d8c4d` adds two native regression tests for those collisions. These are committed code/test changes, **not exact-head Windows/Linux or installed NVP.exe acceptance**. DA-03 remains PARTIAL / native acceptance OPEN; no transactional rollback, live microphone capture, real-device A/V sync, HRTF, continuous native 3D or final 3D-to-2D delivery has been accepted. No FFmpeg path or fallback was introduced and retired proxy CI was not restarted.


### 2026-11-07 DA-03 materialized PCM batch preflight

At PR #74 prior head `68f40bdd0090d5f391b02541ef5f867a4c967ac5`, DATA-AV workflow [42446958914](https://github.com/vjmichael/nvp_offline_film/actions/runs/42446958914) was **queued**, not accepted. Commits [1674a0f](https://github.com/vjmichael/nvp_offline_film/commit/1674a0f4a42a84e2063de78e7310d19d803524d9) and [7e7e47d](https://github.com/vjmichael/nvp_offline_film/commit/7e7e47d621dc7e0428335cfb7a0bd69f4b3af3c1) preflight already-materialized PCM16LE chunk size/parity/count and exact event sample sufficiency across all recordings before publishing any source. Two native regressions assert malformed or short later recordings cannot publish an earlier PCM source. Streaming iterators remain bounded and cannot be preflighted without consuming them; publication failures and denied Take approval can still leave unreferenced source revisions. **Implementation PARTIAL, exact-head tests UNVERIFIED, DA-03 native acceptance OPEN.** DA-00–DA-07 overall acceptance remains OPEN. No FFmpeg fallback or retired CI was introduced. Continuous 3D picture/audio, acoustics/HRTF, device sync, real microphone and final 2D are independently unverified.

### 2026-11-08 DA-03 validated PCM snapshot race repair (verification OPEN)

Code commits `54841534` and `c8550943` snapshot materialized PCM chunk lists into immutable tuples after whole-batch validation and use those snapshots for original-source publication. A regression mutates the second host-owned list after the first source is published and checks that the second original recording still uses validated samples. This prevents mutable-list time-of-check/time-of-use corruption, but **does not** solve streaming iterator preflight, transactional rollback, denied approval or device recording. The prior `bc4ba4d` DATA-AV run [42454229008](https://github.com/vjmichael/nvp_offline_film/actions/runs/42454229008) was QUEUED when inspected, not passed. These new commits have no exact-head Windows/Linux or installed NVP.exe acceptance. DA-03 PARTIAL / acceptance OPEN; DA-00–DA-07 overall OPEN. No FFmpeg fallback or retired proxy CI was enabled. Continuous native 3D A/V, acoustics/HRTF, hardware sync, real microphone and final 2D remain independently unaccepted.


### 2026-11-08 DA-03 recording metadata TOCTOU repair (exact-head verification OPEN)

At inspected PR #74 head `2ac934c3a0886ab0e93b3712ed49ddd163441f4f`, [DATA-AV run 42457170510](https://github.com/vjmichael/nvp_offline_film/actions/runs/42457170510) was QUEUED; no passing Windows/Linux or installed NVP.exe result was available. Commits `f31a454` and `1842dfb` snapshot prevalidated event metadata and materialized PCM together before publishing any source. This closes a separate time-of-check/time-of-use defect: a host-owned later recording dictionary could previously change event identity, emitter path, start time or gain during publication of an earlier source, after preflight. A native regression mutates the later dictionary in the first publish callback and asserts the frozen timeline retains the original approved event values. These commits are CODE ONLY, not independently tested/accepted. Streaming PCM iterator transactional preflight, publication failure cleanup, denied approval, actual device microphone, continuous 3D picture/audio, environmental HRTF, device synchronization, installed interaction and 3D-to-2D delivery remain OPEN. DA-03 PARTIAL / native acceptance OPEN; all DA-00..DA-07 overall acceptance OPEN. No FFmpeg fallback or retired proxy CI was reactivated.


### 2026-11-08 DA-03 streaming prepublication spool (unverified)

At source head `5063716d8c316d07bf9c0b418236c51af084ecf5`, code commit `90f8268` changed `backend/nvp_data_first_filming.py` to preflight *every* original PCM chunk iterator into bounded-memory, spill-to-disk temporary spools, validate chunk sizes/counts and exact Film Time sample sufficiency across the full batch before publishing any immutable source. Source publication replays only the validated spool, and `finally` closes temporary spools on success/failure. Test commit `5063716` adds streaming-shortfall no-publication and successful iterator replay regressions in `tests/test_nvp_data_first_filming.py`. **Code committed, exact-head native Windows/Linux and installed NVP.exe acceptance NOT YET VERIFIED**. The previous DATA-AV workflow [42459808672](https://github.com/vjmichael/nvp_offline_film/actions/runs/42459808672) was queued at inspection. DA-03 remains PARTIAL / OPEN: source publication or creator approval failure can still leave unreferenced immutable source revisions; real microphone, continuous 3D A/V, acoustics/HRTF, device sync and final 3D→2D require independent acceptance. Temporary disk capacity and crash cleanup must also be tested. No FFmpeg fallback or old proxy CI was added.


### 2026-11-08 DA-03 exact-head native regression repair (pending verification)

At PR #74 source head `a78930dfb250829f193cd4a225d7cc5114184d23`, [DATA-AV run 42468085627](https://github.com/vjmichael/nvp_offline_film/actions/runs/42468085627) passed the DA-00 no-FFmpeg audit and React job; all four Windows/Linux native Python 3.11/3.13 jobs failed in `tests/test_nvp_data_first_filming.py` (15 of 17 tests passed). The occupied sound timeline test attempted to publish an empty `TemporalLedger`, rejected by the legitimate nonempty-event invariant. The malformed PCM test used literal backslash-x ASCII rather than invalid single-byte PCM, producing a shortfall error instead of alignment error. Commit [`ffb2f23`](https://github.com/vjmichael/nvp_offline_film/commit/ffb2f237398845ab40cdf4e72fdaf43f8f6753f0) repairs the occupied-identity fixture and PCM byte literals without weakening production validation. The Windows packaged/installed job was still in progress at inspection; do not count it as accepted. New-head exact Windows/Linux/installed verification is OPEN. DA-03 remains PARTIAL and DA-00..DA-07 overall acceptance OPEN. No FFmpeg fallback or retired proxy workflow was introduced.


### 2026-11-08 DA-03 spool integrity replay and exact-head CI distinction

At prior exact head `0ce861ebfee8f7526526748789903cb7f4b25fac`, [DATA-AV workflow 42472089396](https://github.com/vjmichael/nvp_offline_film/actions/runs/42472089396) completed **SUCCESS**: DA-00 no-FFmpeg audit, React job, Windows 2025 and Ubuntu 24.04 native Python 3.11/3.13 matrix, and the packaged/installed Windows `NVP.exe` job all reported success. This is **CI acceptance of that prior head's defined checks only**, not independent hardware, real microphone, continuous 3D A/V, environmental HRTF, audio-device synchronization or 3D→2D film deliverable acceptance. New code commits `6bff12a` and `47ea343` add SHA-256 per-chunk verification when replaying prevalidated disk-spooled PCM into immutable source publication, plus a regression that corrupts the temporary spool after preflight and requires failure before a source revision or approved Take. **New exact-head Windows/Linux/installed verification remains UNVERIFIED** pending its own run. DA-03 implementation PARTIAL / real-device and end-to-end acceptance OPEN; DA-00..DA-07 overall acceptance OPEN. No FFmpeg fallback, proxy workflow restart or claimed final delivery.

### 2026-11-08 DA-03 whole-batch spool integrity prepublication repair

Implementation commit [1563a348](https://github.com/vjmichael/nvp_offline_film/commit/1563a348012cd335cac46a9b3a55ba37a7d4758d) verifies the SHA-256 integrity of **all** fully spooled original PCM recordings before publishing the first immutable source; publication replay retains independent per-chunk integrity checks. Regression commit [b9710639](https://github.com/vjmichael/nvp_offline_film/commit/b97106390bef64f14955ee4ff84903e5241a26f6) deliberately corrupts the later spool after materialization and requires rejection without any first source, timeline or Take publication. This closes a prepublication corruption gap, **not** the separate post-preflight race, publication/approval atomicity, or crash recovery. At previous source head `84305fef0fc1a8ac34e33c541db2f7cda45494c9`, DATA-AV [run 42477347100](https://github.com/vjmichael/nvp_offline_film/actions/runs/42477347100) completed successfully; that is **previous-head CI**, not verification of these commits. New exact-head Windows/Linux matrix and installed NVP.exe outcomes remain UNVERIFIED. DA-03 implementation PARTIAL / acceptance OPEN; DA-00..DA-07 overall acceptance OPEN. No FFmpeg fallback or retired proxy workflow was enabled. Real continuous 3D A/V, HRTF, device sync, microphone capture, and final 3D-to-2D output remain independently unaccepted.
