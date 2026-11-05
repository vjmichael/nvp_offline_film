# NVP — Engineering state and resumption ledger

**Purpose:** One concise, machine-readable-by-convention entrypoint for a newly started AI development conversation.

**LATEST CREATOR PRIORITY (2026-11-05): WINDOWS NSIS INSTALLER WORK IS PAUSED.** Do not attempt setup scripts, packaging or on-PC dependencies unless the creator explicitly resumes that task. Active objective: a real continuous 30–60-second NVP-produced short film, with AI-generation and production continuity verified; technical reel assembly is a stepping stone. Git commits, exact build/test logs, creator approvals and artifact hashes remain the sources of truth. This document is a **navigation index**, not proof that an effect ran.

**Status:** Initial ledger, manually reconciled 2026-11-05. A future automation/CI gate must populate SHA, test and artifact evidence reliably; do not treat this file as self-updating.

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

**Priority A (current): MASTER-01C** — move technical review media publication out of native worker into host-owned prepared/verified/committed steps with crash/fault injection. Then bind original captured Digital Takes, real performances, dialogue and AI-generation outputs and prove a creator-reviewed continuous 30–60-second short. Current procedural color/sine fixtures are not finished-film evidence.

**Windows packaging: PAUSED by creator 2026-11-05.** Earlier v3 diagnostics remain historical but NSIS and installer follow-up are not active tasks. Resume only when explicitly requested.

**Priority B (AI-readability):** extend AI-01 to other film objects and add a small read-only AI-02 capability catalog and AI-03 context bundle, with exact-provenance and stale-ref tests. No generic write executor and no premature Lu socket.

**Priority C (film deliverable):** maintain native AUDIO-01K.3 and E2E-01D crash/verification gates and real approved 30–60 s film acceptance. Exact-head native workflow evidence is mandatory before merge or release acceptance.

## Change log (append-only entries)

- **2026-11-05 later:** MASTER-01B native reviewer passed 46 Linux Python tests in three targeted groups (9 new, 7 MASTER-01A, 30 existing). Actual contained 30s AV output, creator scope, strict executable selection, controlled cancellation, post-worker-stop host hard exit and no-replay restart reconciliation verified. Windows and delegated Linux cgroup whole-tree acceptance still unverified; next MASTER-01C two-phase host-owned publication.

- **2026-11-05 later:** Creator paused NSIS work and prioritized real film output. Added MASTER-01A source-indexed multi-reel technical preview. Real 36s/60s ProRes/PCM24 stream-copy assembly tested with FFmpeg, exact SHA/revision/AV clock, packet-order and decoded-PCM equality, reopen and corruption refusal, 29 related tests passed on Debian. Windows CI requested, not confirmed; next MASTER-01B worker supervision and real production-reel integration. No claim of generated acting, native installed application or approved finished short.
- **2026-11-05:** Reviewed NVP AI usability against LU-AIW-01 and existing data-first master. Added proposed NVP-AI-01 architecture review to master design. Initial read-only revision-bound screenplay reference adapter and six tests committed. Created this ledger so subsequent AI work can resume from source state instead of context guesses. 57 related local Python tests passed; Windows installer acceptance still open.

## Required evidence for any future ledger update

Record: date; actor/source (human decision, tool observation, AI hypothesis); branch; source SHA; exact command and tested input; OS/runtime/tool versions; outcome + skips; artifact SHA/path if produced; relationship to prior accepted versions; outstanding blocker; next action. Never invent a successful install, benchmark, model inference or DCP screening. A remembered resource is not a verified current resource.
