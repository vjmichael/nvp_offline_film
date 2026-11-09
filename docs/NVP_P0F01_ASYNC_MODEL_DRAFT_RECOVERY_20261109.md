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

## Remaining P0-F-01 task-group work

1. Run Python native tests on **Windows 3.11/3.13 and Linux 3.11/3.13** with actual `usd-core==26.11` and real first-party Test USD assets, plus React/Vite DOM/prod build. Repair demonstrated failures only, then one consolidated group-end gate. Do **not** create per-commit CI.
2. Wire the installed **real local GGUF** provider route and capture actual model/model-file identity and request/response receipt where possible, without conflating self-reported model ID with model-binary attestation. Test no model, malformed JSON, timeout, stop/cancel, source head drift.
3. Test a real installed NSIS-built Windows NVP app, not just mocked pywebview: navigate director UI, run a model attempt, cancel/retry, edit/undo/discard, native OS deny/approve and forced restart. Preserve user project data on reinstall and uninstall, while removing program files. Collect installer executable SHA, process/session state and FilmIndex revision/source hashes.
4. Test atomic source-commit interruption windows and installed native dialogs. Prove no stale approval, accidental source rewrite, duplicate world publication or leaked descendant native worker.
5. Attach the exact-head OS job logs, test counts and installed acceptance artifacts to the central ledger. Source implementation is **not** accepted without these.

**Next sequential groups after P0-F-01:** approved district in real 01D/01E camera/actor-rendered pixels; CAM-FX-01–05 OpenUSD director rails and advanced shot techniques; 01Q/01S/01T final selected-view film. Camera-rail specification: `docs/NVP_CAMERA_RAILS_SHOT_FX_AND_P0F01_SEQUENTIAL_PLAN_20261109.md`.
