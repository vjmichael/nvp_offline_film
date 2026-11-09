# P0-F-01A — responsive installed original-world model-to-draft and recovery

**Implementation checkpoint:** 2026-11-09. **Status:** SOURCE IMPLEMENTED + REGRESSION TESTS ADDED; actual native Windows/Linux execution, installed WebView2, local loaded GGUF and physical NSIS **NOT YET ACCEPTED**.

## Why this increment exists

The original `film02mg_generate_candidate` desktop IPC call waited synchronously for a loaded local-model response, forcing the director GUI to stay in its global busy state. Durable model attempt rows existed, but there was no explicit model task status/cancel interface for the installed director.

This task reuses **exactly the existing** `TrustedDesktopWO5Bridge` / WO6 local provider factory, `OriginalDistrictDrafts` SQLite WAL/FULL, approved first-party original USD district planner and original `FilmIndex`. It does not introduce another agent, project database, Python executor, native tool authorization, source editor or renderer.

## Implemented source contract

- `film02mg_start_candidate({project_id,district_id,expected_revision,direction,model_id})`: strict existing host-bound argument set, original catalog SHA, durable host-minted model attempt and one daemon generation thread at most in this installed bridge. Returns `GENERATING` with no authority, without blocking the WebView on inference.
- `film02mg_candidate_status({project_id,attempt_id})`: exact-origin/project-scoped read of SQLite status `GENERATING`, `DRAFT_SAVED`, `FAILED`, `CANCELLED` or `INTERRUPTED_REQUIRES_NEW_GENERATION`. A saved attempt is independently reopened and returns original model evidence + the real source-verified draft; no provider text, executable path or raw worker rights are returned.
- `film02mg_cancel_candidate({project_id,attempt_id})`: host-session-bound SQLite transition `GENERATING → CANCELLED`; in-memory stop flag. A late completed provider cannot commit an unapproved source draft after cancellation because `OriginalDistrictDrafts.create` requires an atomic same-session `GENERATING → DRAFT_SAVED` update in the **same transaction** as draft/evidence insertion. A losing race rolls back all inserts. A completed draft is not silently discarded by a late cancel.
- `TrustedDesktopWO6Bridge._close` revokes in-flight model-to-draft jobs before native-host shutdown; no completion from the old bridge may be applied after app stop. New host sessions reconcile orphaned `GENERATING` rows as `INTERRUPTED_REQUIRES_NEW_GENERATION` and never auto-restart inference.
- Existing synchronous `film02mg_generate_candidate` uses **the same validation and persistence implementation** for old consumers. Existing WO6 provider identity, strict JSON and original USD geometry revalidation remain mandatory.
- `ModularWorldDirector` prefers the nonblocking path when present, shows generation state and explicit Cancel, keeps ordinary editor controls responsive, polls only bounded native status, reattaches an in-process running attempt after tab switch and surfaces durable recovered states across full app restart. Older bridge versions retain their supported synchronous compatibility path.
- No native OS approval occurs during model generation, polling, cancellation or reopen. Original ActorID/01E frozen Takes, camera, dialogue, PCM and approved district revision remain unchanged unless the director subsequently makes a separate exact-source OS approval.

## Added regression cases (authored, not yet executed on native runners)

- Real first-party `pxr` / `FilmIndex` source workflow with **injected model**: start, nonblocking durable state poll, evidence/draft SHA matching, genuine USD preview, no original world publication.
- In-flight provider blocked behind an event: duplicate attempt refused; OS approval never called; cancellation persists `CANCELLED`; late valid JSON completion fails source draft admission.
- App host shutdown during provider wait: old native session cannot save late source; new host returns interrupted/cancelled receipt; no source revision, draft or auto-replay.
- React DOM: model start returns immediately, ordinary catalog controls remain responsive, terminal status reopens verified unapproved draft; explicit Cancel invokes host-owned attempt ID only and never invokes publication.
- Original F/G/H sync candidate, host origin, immutable binding and source recovery tests are preserved and must remain green.

## P0-F-01B — actual NSIS installed executable and REAL GGUF workflow (source committed; technical gate pending)

Implementation integrated on this branch with **existing** `tools/nvp_desktop_alpha.py`, `packaging/nvp-alpha.nsi`, existing WO6 local GGUF model acceptance, trusted pywebview/React host and immutable first-party FilmIndex:

1. The normal installed `NVP.exe` already builds/loads the offline 23 · Build the world from data React panel. It now has native `film02mg_start_candidate/status/cancel` bridge methods, bounded host-owned threading and resumed/failed durable model records, all separate from native OS publish rights.
2. `backend/nvp_wo6_verified_local_model.py` adds optional source-grammar-constrained `complete_world_candidate` for the already selected real loopback provider. `backend/nvp_usd_film02m_g_model_world_candidate.py` supplies an exact trusted JSON schema derived **only** from the current independently reopened building catalog. It still strictly parses returned model text, checks reported completion vs current model identity, admits source IDs/revisions and geometry budgets natively, and refuses model-generated worker/approval authority. Neither a JSON schema nor a model self-report is actual GGUF binary attestation; the existing separate real-GGUF test hashes model/server binaries.
3. `tools/nvp_desktop_alpha.py` repairs the installed two-process source-reopen smoke (undefined `studio` and previously separate draft-test folder). It now uses the same project-local native proposal store as production. The real `--smoke-window` on an explicit disposable workspace exercises native WebView2 catalog/propose/preview/edit/reopen/undo/discard; a test-only same-process Windows UI driver triggers genuine native MessageBox **No then Yes** and independently reopens the published USD while checking original frozen Take SHA. The driver is NOT real human director consent, and can only operate within this explicit test mode.
4. With the acceptance-owned real GGUF/llama.cpp server, the same installed WebView2 page enters a source-bound request into the *actual React model UI* and clicks Generate. It must receive a real positive-token GGUF completion, produce a strict unapproved district, re-open actual native USD, and visibly show the completed unapproved draft. Failure to produce valid source JSON is a gate failure, not skipped or replaced by fixed JSON.
5. New explicit `--smoke-model-interrupt` only works in acceptance-disposable mode. Another genuine installed NVP process admits a durable model attempt, reports a marker, is **externally force-killed by Windows**, and a new installed process must classify the old attempt `INTERRUPTED_REQUIRES_NEW_GENERATION`, with neither a new draft nor published FilmIndex world. This proves a native-process journal recovery boundary, NOT the exact simultaneous full GGUF-generation kill; the blocked-provider late-response regression remains separately in native Python tests.
6. New `tools/nvp_p0f01_installed_acceptance.ps1` performs genuine installer build hash compare, silent NSIS install, installed exe x3, forced kill, WebView2 GUI, native OS dialog automation, real GGUF+server, absence of test model/server from installer, process cleanup and uninstall preserving filmmaker SQLite project.
7. Consolidated, manual-only native Windows/Linux/React/NSIS/GGUF workflow: `.github/workflows/nvp-p0f01-grouped-installed-windows.yml`; **run exactly once at task-group end**, no per-edit CI.

**Evidence remains OPEN until the actual job logs/artifacts pass.** Even green GitHub hosted Windows technical acceptance cannot substitute for a filmmaker-operated physical Windows installation and true human approval. The production-scale Qwen 7B+/27B GGUF model path is not demonstrated by the 135M acceptance-only model, and a native successful OpenUSD draft is not final Cycles film imagery. The F/G/H queued exact-head acceptance remains separate and unchanged.

## Remaining P0-F-01 task-group work

1. Run Python native tests on **Windows 3.11/3.13 and Linux 3.11/3.13** with actual `usd-core==26.11` and real first-party Test USD assets, plus React/Vite DOM/prod build. Repair demonstrated failures only, then one consolidated group-end gate. Do **not** create per-commit CI.
2. Wire the installed **real local GGUF** provider route and capture actual model/model-file identity and request/response receipt where possible, without conflating self-reported model ID with model-binary attestation. Test no model, malformed JSON, timeout, stop/cancel, source head drift.
3. Test a real installed NSIS-built Windows NVP app, not just mocked pywebview: navigate director UI, run a model attempt, cancel/retry, edit/undo/discard, native OS deny/approve and forced restart. Preserve user project data on reinstall and uninstall, while removing program files. Collect installer executable SHA, process/session state and FilmIndex revision/source hashes.
4. Test atomic source-commit interruption windows and installed native dialogs. Prove no stale approval, accidental source rewrite, duplicate world publication or leaked descendant native worker.
5. Attach the exact-head OS job logs, test counts and installed acceptance artifacts to the central ledger. Source implementation is **not** accepted without these.

**Next sequential groups after P0-F-01:** approved district in real 01D/01E camera/actor-rendered pixels; CAM-FX-01–05 OpenUSD director rails and advanced shot techniques; 01Q/01S/01T final selected-view film. Camera-rail specification: `docs/NVP_CAMERA_RAILS_SHOT_FX_AND_P0F01_SEQUENTIAL_PLAN_20261109.md`.
