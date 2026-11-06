# NVP — Engineering state and resumption ledger

**Purpose:** One concise, machine-readable-by-convention entrypoint for a newly started AI development conversation.

**LATEST CREATOR PRIORITY (2026-11-05): WINDOWS NSIS INSTALLER WORK IS PAUSED.** Do not attempt setup scripts, packaging or on-PC dependencies unless the creator explicitly resumes that task. Active objective: a real continuous 30–60-second NVP-produced short film, with AI-generation and production continuity verified; technical reel assembly is a stepping stone. Git commits, exact build/test logs, creator approvals and artifact hashes remain the sources of truth. This document is a **navigation index**, not proof that an effect ran.

**Status:** Initial ledger, manually reconciled 2026-11-05. A future automation/CI gate must populate SHA, test and artifact evidence reliably; do not treat this file as self-updating.

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
