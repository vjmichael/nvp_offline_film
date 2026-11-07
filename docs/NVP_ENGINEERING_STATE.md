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
