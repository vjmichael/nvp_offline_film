# NVP — Engineering state and resumption ledger

**Purpose:** One concise, machine-readable-by-convention entrypoint for a newly started AI development conversation.

**LATEST CREATOR PRIORITY (2026-11-05): WINDOWS NSIS INSTALLER WORK IS PAUSED.** Do not attempt setup scripts, packaging or on-PC dependencies unless the creator explicitly resumes that task. Active objective: a real continuous 30–60-second NVP-produced short film, with AI-generation and production continuity verified; technical reel assembly is a stepping stone. Git commits, exact build/test logs, creator approvals and artifact hashes remain the sources of truth. This document is a **navigation index**, not proof that an effect ran.

**Status:** Initial ledger, manually reconciled 2026-11-05. A future automation/CI gate must populate SHA, test and artifact evidence reliably; do not treat this file as self-updating.

## LATEST DIRECTIVE: ZERO-FFMPEG + ordered DA-00–DA-07 closeout (2026-11-06)

NVP no longer uses FFmpeg **anywhere**. This prohibition covers native recording/playback, conventional media import, editing, rendering, mastering, conversion, and final 2D/DCP export, not just the embedded scene engine. Earlier clauses allowing FFmpeg at boundaries are superseded. Prohibited paths remain historical or disabled until rewritten with non-FFmpeg components. Main ordered engineering tasks and independent acceptance statuses: [DA-00–DA-07](NVP_DATA_ALL_TASK_LEDGER.md). Implement tasks in order; do not mark a gate accepted merely because code or a CI test exists.

## MOST RECENT creator priority — DATA-AV-01 full native migration (2026-11-06)

**Supersedes previous AV/indexing/FFmpeg native playback tasks and old
Windows NSIS pause only for a new native data-first installed-app gate.**
The creator explicitly directed an end-to-end conversion to native,
frame-independent scene/audio Film Time evaluation, while stopping stale
PRs/CI. Native A/V source authority is immutable recorded sound assets,
OpenUSD scene, exact Film Time events and frozen Digital Take; never an
FFmpeg-generated MP4 or mandatory BWF recording. See
`docs/NVP_MASTER_DESIGN.md`,
`docs/NVP_SOUND01_NATIVE_SPATIAL_AUDIO.md` and
`docs/NVP_DATA_AV01_NATIVE_MIGRATION.md`.

**PR inventory:** Old imported-video/FFmpeg-viewer PRs #47, #53–57,
#68–73 closed unmerged. Current new draft PR **#74** on
`nvp/data-av01-native-scene-playback-20261106`, stacked on native
scene/SLATE-08B PR #67. Other SLATE/USD source branches remain open.
Automation "NVP DCP CI Closeout" paused. Old media benchmark/
FFmpeg-installer workflows are manual-only **on the new branch**.
Previously running GitHub Actions on retired PRs may still finish;
the connector does not offer cancellation, so NEVER claim all CI jobs
are stopped.

**Actual code now committed:** content-addressed small PCM sound
source chunks; FFmpeg-independent exact-time scene and dialogue/sound
event evaluation; first dry 3D panning/distance mixer; in-memory native
UsdMedia SpatialAudio bindings; trusted OS-window grant and WebView2
JS→native audio data interface; UI WebAudio forward/reverse audition;
native original/two-listener tests, and new Win/Linux and NSIS-installed
exact-head native CI. Existing final presentation/export modules are
**separate**; do not redeclare legacy AVI/PNG/MP4 as core.

**NOT COMPLETE OR ACCEPTED:** real installed device playback, strict
bounded RAM/latency under long films, acoustic occlusion/reflection/HRTF,
real continuous native 3D picture alongside audio, capture-session
sound event producer, multi-track mix and real 3D→final presentation
end-to-end evidence. Do not bypass these by citing proxy CI.

## Source identity (recheck before working)

- Repository: vjmichael/nvp_offline_film
- Active development: PR #45 (draft), branch nvp/stack02c3b14-picture-conform-20261104
- Last inspected substantive source commit: 393c068988217319b978e9815b7d3753da73b95b (NVP-AI-01 tests). **The actual HEAD will change after this documentation commit; re-read it from GitHub each time.**
- Main architectural authority: docs/NVP_MASTER_DESIGN.md.
- AI-readiness review: docs/NVP_AI_ACCESSIBLE_ARCHITECTURE_REVIEW_20261105.md.
- Lu integration: deferred until Lu v1.0 host/DLC contracts are accepted. Standalone Windows desktop alpha is a separate active milestone.

## Current workstreams / what is proven

| Workstream | State at this entry | Evidence / required next gate |
| --- | --- | --- |
| FilmIndex and provenance | Implemented source/index foundation; not complete whole-film acceptance | backend/nvp_film_index.py; tests/test_film_index.py; confirm exact-head cross-platform tests |
| Screenplay editing | Editable 1-based gutter, AI excerpt numbering and line navigation are committed | frontend/src/LineNumberedTextarea.jsx; backend/nvp_story_context.py; source line tests. Native Windows WebView interaction still needs physical acceptance |
| AI-01 read-only source resolver | Initial implementation committed | backend/nvp_ai_refs.py; tests/test_nvp_ai_refs.py. Read-only Python service only, **not an authorized model tool or exposed API**. Requires host integration, more cross-revision tests |
| MASTER-01C host-owned unapproved film publication | **Implemented and locally verified; actual film/Windows remains open** | Opt-in native host-staged worker, SHA-bound real ProRes/PCM24 30s/60s, hard-exit before/after host FilmIndex commit, no replay, staging tamper refusal, cancellation before publication; 57 targeted tests across 5 groups; see docs/NVP_MASTER01C_HOST_PUBLICATION.md |
| MASTER-01B contained AV review | **Implemented and locally verified; Windows/strict Linux acceptance open** | Native creator-scoped host, queue/admission, containment, controlled cancellation, genuine hard-exit/recovery, saved source hashes. 46 Linux tests across 3 groups; see docs/NVP_MASTER01B_NATIVE_SUPERVISED_REVIEW.md |
| MASTER-01A real 30–60s technical review | Native technical assembly implemented, not a finished AI film | backend/nvp_longform_review.py, tests/test_nvp_longform_review.py; real FFmpeg/FFprobe 36s and 60s checks; 30 related tests passed, CI/native Windows still pending |
| AI-02 through AI-07 | Proposed architecture, not implemented/accepted | AI review document; staged context, capability, inventory, impact and evidence acceptance gates |
| Worker/resources | Existing supervision/journal/admission mechanisms with partial native evidence | Follow existing STACK-02, audio, Blender and E2E tests; do not generalize one test to every worker or platform |
| Windows desktop installer (paused) | **NOT ACCEPTED; PAUSED per creator 2026-11-05** | An experimental signed-unknown online NSIS bootstrapper has failed on physical Windows due to Python package problems; v3 is an attempted repair without reported successful install. The desired verified self-contained Windows installer is still open |
| Audio/DCP/full-film | Numerous source modules, tests and native-fixture results; end-to-end commercial/installed acceptance remains separate | AUDIO-01K3, E2E-01D, E2E-01E and FILM-01 gates; do not equate local tests or queued CI with exact-head native acceptance |

## Local evidence, last verified

2026-11-05 targeted Debian tests in recovered source snapshot:
- Command: python -m unittest tests.test_nvp_ai_refs tests.test_film_index tests.test_crew_roles tests.test_story_context tests.test_lu_workspace tests.test_resource_scheduler -q
- Result: **57 tests passed** (6 new AI reference tests, 51 existing related tests). Does not certify Windows installed GUI or latest exact-head regression.
- Editor React/Vite and earlier NVP smoke tests were run in earlier task checkpoints. Their exact revisions/environments are in the corresponding logs/artifacts, not to be silently promoted here.
- All paths/resources from an earlier ephemeral container are **historical** until reverified in the current runtime.

## Mandatory new-turn discovery order

1. Read PR #45 and current GitHub exact HEAD SHA, its changed files and current acceptance results.
2. Read this ledger and the master design's most recent amendments; read a subsystem doc only when its task is relevant.
3. Determine whether the task is about Windows distribution, media workers, film-authoring UX, or AI-accessibility, and inspect the matching live source and durable previous outcome.
4. Verify existing accessible source tree, required binaries, caches, fixtures and model/runtime **before downloading or reconstructing** packages.
5. Execute/tests with authentic artifacts and record the exact environment, SHA, commands, pass/fail/skip and limits; keep unavailable evidence marked unavailable.
6. Update this ledger and affected design/acceptance docs on substantive changes. Do not make a stale previous success current merely by restating it.

## Next actionable engineering sequence

**Priority A (current): MASTER-01D** — adapt authentic frozen Digital Take/Pipeline/B14 and synchronized dialogue/audio outputs into exact indexed AV reels for the new two-phase host-owned native assembler. Build a 30–60-second coherent, creator-reviewed cinematic short, not procedural color/sine fixtures. Verify selective revision, persistent character/shot identity, sound sync and editable FilmIndex source lineage.

**Windows packaging: PAUSED by creator 2026-11-05.** Earlier v3 diagnostics remain historical but NSIS and installer follow-up are not active tasks. Resume only when explicitly requested.

**Priority B (AI-readability):** extend AI-01 to other film objects and add a small read-only AI-02 capability catalog and AI-03 context bundle, with exact-provenance and stale-ref tests. No generic write executor and no premature Lu socket.

**Priority C (film deliverable):** maintain native AUDIO-01K.3 and E2E-01D crash/verification gates and real approved 30–60 s film acceptance. Exact-head native workflow evidence is mandatory before merge or release acceptance.

## Change log (append-only entries)

- **2026-11-05 later:** MASTER-01C two-phase staging passed 57 Linux native/related tests across 5 bounded groups (6 new host tests, 5 new staged-media tests, 9 MASTER-01B, 7 MASTER-01A, 30 existing index/scheduler/worker tests). Genuine 30s/60s ProRes/PCM24 technical reels, host publication, real OS-process crash before and after index commit, cancellation before publication and tamper refusal. Native Windows/strict Linux whole-tree results remain pending. Next MASTER-01D authentic film source integration. No new installer work.

- **2026-11-05 later:** MASTER-01B native reviewer passed 46 Linux Python tests in three targeted groups (9 new, 7 MASTER-01A, 30 existing). Actual contained 30s AV output, creator scope, strict executable selection, controlled cancellation, post-worker-stop host hard exit and no-replay restart reconciliation verified. Windows and delegated Linux cgroup whole-tree acceptance still unverified; next MASTER-01C two-phase host-owned publication.

- **2026-11-05 later:** Creator paused NSIS work and prioritized real film output. Added MASTER-01A source-indexed multi-reel technical preview. Real 36s/60s ProRes/PCM24 stream-copy assembly tested with FFmpeg, exact SHA/revision/AV clock, packet-order and decoded-PCM equality, reopen and corruption refusal, 29 related tests passed on Debian. Windows CI requested, not confirmed; next MASTER-01B worker supervision and real production-reel integration. No claim of generated acting, native installed application or approved finished short.
- **2026-11-05:** Reviewed NVP AI usability against LU-AIW-01 and existing data-first master. Added proposed NVP-AI-01 architecture review to master design. Initial read-only revision-bound screenplay reference adapter and six tests committed. Created this ledger so subsequent AI work can resume from source state instead of context guesses. 57 related local Python tests passed; Windows installer acceptance still open.

## Required evidence for any future ledger update

Record: date; actor/source (human decision, tool observation, AI hypothesis); branch; source SHA; exact command and tested input; OS/runtime/tool versions; outcome + skips; artifact SHA/path if produced; relationship to prior accepted versions; outstanding blocker; next action. Never invent a successful install, benchmark, model inference or DCP screening. A remembered resource is not a verified current resource.

## 2026-11-06 — Indexing continuity and SLATE-08B desktop IPC

- Indexing work preceding the SLATE tasks: DATA-01/SCALE-03C original FilmIndex + owned fast media index, INDEX-TIME-01–04 PTS and Film Time bridges, VFR placements, supervised preview/conform and binary seek. Earlier benchmark observation: 259,200 frames / ~4.67 MiB / ~4.53 s indexing / ~0.085 s near-end seek; external FFMS2 comparison and exact-head native acceptance not closed.
- SLATE-08A: ordinary planning UI now shows real published scene/camera identities and read-only Film Time marker projection. CI/installed acceptance open.
- SLATE-08B: native PyWebView2 JS API bridge grants scoped original-source Cycles still after native OS user confirmation, routes to existing supervisor/cache, delivers bounded verified PNG by per-window ticket, separately confirms cancellation, checks window URL and source/lens SHA, and disables rendering if no native Blender. No arbitrary native command or model-selected script, no general FastAPI mutating render endpoint, no final film approval.
- Pending: exact-head CI, real Windows installed WebView2 ↔ worker PNG acceptance, real Blender executable packaging/provenance in single NSIS, source & orphan worker restart reconciliation, plus still-open indexing gates.

## 2026-11-06 — DATA-AV-01 native migration acceptance checkpoint

- Active draft PR #74, branch `nvp/data-av01-native-scene-playback-20261106`, stacked on SLATE-08B PR #67. Original observed head `440b40f121bf7e1dfa6be24b19c4a90c643f7b06`; eight associated native workflows were **queued**, not completed (DATA-AV-01 `42307456319` plus seven USD/SLATE runs). No job logs, React acceptance, Linux/Windows OpenUSD/PCM acceptance or installed Windows `NVP.exe` acceptance could be certified at this checkpoint. Documentation update advances the head, so previous queued run statuses are not evidence for the new head.
- Authoritative source remains frozen OpenUSD Digital Take + exact Film Time + semantic emitter events + SHA-indexed original PCM, with bounded native device buffers. FFmpeg runtime, BWF, MP4 proxy, video-frame authority and whole-film RAM loading are excluded from the native path. Legacy indexed-video PRs #47, #53–57, #68–73 remain retired; do not revive their CI.
- Still open: actual filming capture, high-fidelity interactive 3D graphics, HRTF/acoustic environment, real synchronized device playback and approved 2D flattening. Native source tests or a packaged binary self-test alone cannot close these gates. See `docs/NVP_DATA_AV01_NATIVE_MIGRATION.md` for run IDs and detailed boundary.

## 2026-11-06 — DATA-AV native OpenUSD type repair

DATA-AV workflow [42307683019](https://github.com/vjmichael/nvp_offline_film/actions/runs/42307683019) at historical source SHA `06546564941b319ccea436be59427d213db480ab` completed **failure**. Windows/Linux Python tests hit `UsdMedia.SpatialAudio.startTime` value-type mismatch (`GfTimeCode` expected, `TfPyObjWrapper` supplied). Commit [`e50029b`](https://github.com/vjmichael/nvp_offline_film/commit/e50029bbd4f0e4a762012f7482c01911643088ac) changes the native USD adapter to author `Sdf.TimeCode` start/end values. This is a code repair, **not yet a verified test pass**. Two permission tests and one React camera test also failed. Installed Windows NVP.exe acceptance was skipped. Do not approve DA-03, DA-07 or any overall migration gate until fresh exact-head evidence and real installed A/V acceptance exist. No FFmpeg fallback is authorized.


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

### 2026-11-07 — DATA-ALL DA-01 exact-tick shot revision implementation

- Source: `backend/nvp_exact_time_shots.py` commit `802116e83a8d7e78e17f65e9cdeca0ee37fe9a5b` adds `revise_shot(project_id,timeline_id,expected_revision,shot_id,replacement)`. The verified prior timeline determines source scene identity and exact duration; complete replacement data is validated by the existing immutable TemporalLedger publication and CAS. Deletion is allowed only if at least one camera observation remains. Old revisions and captured Take history remain intact.
- Regression: `tests/test_nvp_exact_time_shots.py` commit `5c226656426c9e990f3f9b9e623e9c902340bf6f` checks exact-tick replacement, removal, SHA preservation, stale expected revision and invalid IDs. **Not independently run at this new head.**
- Historical CI: [DATA-AV run 42380560101](https://github.com/vjmichael/nvp_offline_film/actions/runs/42380560101) at `09ea0f2b6fc944775aa09c0f4cb80c6dc431d3d3`: DA-00 audit, React, Windows/Linux native Python 3.11/3.13 jobs passed; Windows packaged/installed job was in progress at inspection. Do not claim installed acceptance from the other six jobs.
- Status: DA-01 PARTIAL / acceptance OPEN; DA-00 and DA-02..DA-07 not fully accepted. Real installed `NVP.exe`, continuous 3D/audio, environmental acoustics/HRTF, device synchronization, microphone capture and 3D-to-2D deliverable remain independent gates. No FFmpeg invocation/fallback introduced, and old proxy workflows remain retired.


## 2026-11-07 DA-01 continuation — exact-tick insertion

PR #74 head inspected before changes: `9366910572497bb0e09fc39ad1fd4b3664abc35f`. [DATA-AV run 42384991069](https://github.com/vjmichael/nvp_offline_film/actions/runs/42384991069): six successful audit/React/Win/Linux native jobs, installed Windows NVP.exe job cancelled during installation/WebView2/uninstall after candidate packaging; **installed acceptance unverified**. DA-01 source commits `5fa54ec` and `42f6019` implement and regress immutable CAS-checked exact Film Time shot insertion into a gap. DA-01 UI migration and exact-head tests still OPEN. DA-00 through DA-07 independent overall acceptance OPEN; no FFmpeg path restored, no old proxy CI restarted. Next: native test results on this head, migrate actual desktop shot editor, and establish installed-app continuous A/V/device and approved 2D evidence without proxy authority.


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


### 2026-11-07 DA-03 preflight-before-PCM implementation

PR #74 branch now validates all proposed sound events before publishing any source revision: camera-event collision, duplicate/reserved source/event identities, scene emitter membership, supported event type, exact Film Time bounds, and finite gain. Added native regressions for invalid later events and camera collisions. Code commits: `09edf707`, `4cc7cd3`, `4469a66`. **Unverified on exact head**: Windows/Linux native matrix, installed NVP.exe and real devices. Prior inspected head `c82bc34a6cc3d9dc8b0b112c948c759db12f6490` had DATA-AV workflow #42434435689 queued; queued does not mean passed. DA-03 remains PARTIAL/OPEN; DA-00 through DA-07 acceptance OPEN. No FFmpeg. Native continuous 3D visual/audio, HRTF, device A/V sync, hardware sound capture and final 3D-to-2D delivery still require independent acceptance.


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
