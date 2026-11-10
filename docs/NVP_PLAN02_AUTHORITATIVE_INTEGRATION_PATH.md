# NVP PLAN-02 — Authoritative data-first integration and source evidence map

**Decision:** 2026-11-09 America/Phoenix / 2026-11-10 UTC. **Status:** ROUTE ESTABLISHED; selective implementation ports and integrated native acceptance OPEN.
**Canonical development branch:** `nvp/data-av01-native-scene-playback-20261106` / draft [PR #74](https://github.com/vjmichael/nvp_offline_film/pull/74).
**Inspected source snapshot, not an installed release:** `bf4cd892d5a2c7f1268af1e594ed828b52ecea8a`.
**Machine-readable evidence snapshot:** [PLAN-02 integration manifest](NVP_PLAN02_INTEGRATION_MANIFEST.json).

## 1. Single governing path

PR #74's OpenUSD / FilmIndex / exact signed-int64 Film Time / original SHA-addressed PCM / trusted desktop execution model is the **only production integration baseline**. New integration work targets the latest verified head of PR #74 (or a short-lived review branch descending from that exact head and deliberately returning to it). **Existing CAM-FX, USD-FILM, WO6, DA-05B and DA-05/06 side branches remain development/evidence sources, NOT alternate production integration trunks.** Do not merge entire divergent branch stacks to make GitHub ancestry appear integrated.

Hard contract:
1. One authoritative OpenUSD Film World and immutable FilmIndex Digital Takes; original ActorIDs, original performance, native sound source SHA and source revision are never silently rewritten.
2. Film Time uses exact signed integer ticks (7,056,000,000 ticks/second). Native cinematography, capture, events, motion, lighting and audio are **time-addressed source data**, not a mandatory 24fps or 720-frame sequence. Frame numbers, PNGs and 24fps pictures are **derived bounded presentation samples**, never Digital Take source identifiers.
3. **Zero FFmpeg anywhere active**, including import, rendering orchestration, preview, conform, codec library, executable, helper, or final 2D export. No optional FFmpeg fallback. Existing `tools/nvp_no_ffmpeg_contract.py` is the DA-00 enforcement entrypoint; fix gaps in that guard rather than inventing a second guard.
4. Original source editing and native worker effects remain in the existing trusted NVP host: exact project/source/revision hashes, first-party typed operations, fresh human OS approval, resource admission, bounded process custody, and durable no-replay recovery. GGUF output and browser data never grant permissions.
5. Rendered pictures, source-audio device windows, AVI/image sequences, DCPs and later movie encodes are derivative presentations. Every new delivery adapter must be independently licensed, audited, no-overwrite, original-source-verifiable and **FFmpeg-free**. Unsupported presentation formats remain unavailable.

This explicitly **supersedes older 01T and other branch assumptions** that require FFmpeg/ffprobe to produce a film or use output picture frames as source-of-truth. An original 30-second film remains the acceptance milestone, but its 720 sampled pictures at 24fps are a chosen *delivery cadence* only.

## 2. Existing canonical components — preserve, do not rebuild

| Capability | Existing authoritative code on PR #74 | State |
| --- | --- | --- |
| Film source/time and approvals | `backend/nvp_film_index.py`, `backend/nvp_exact_time_shots.py`, native Film Time events | Source exists; whole-film integration open |
| Immutable filming / durable source publication | `backend/nvp_data_first_filming.py`, `backend/nvp_filming_publication_journal.py`, `backend/nvp_filming_worker_custody.py` | Source exists; whole-device/worker recovery open |
| OpenUSD scenes and sound events | `backend/nvp_data_av_scene.py`, `backend/nvp_data_av_usd.py`, `backend/nvp_data_av_source.py` | Source exists; advanced 3D A/V quality open |
| Trusted desktop and visual state | `backend/nvp_data_av_desktop.py`, `backend/nvp_data_av_visual.py`, `backend/nvp_slate08b_native_camera_ipc.py` | Native smoke tested; camera React regression open |
| Native final derivative package | `backend/nvp_final_2d_native.py`, `backend/nvp_native_cpu_raster.py`, `backend/nvp_native_color_decisions.py` | FFmpeg-free derivative primitives exist; accepted final film master open |
| No-FFmpeg graph audit | `tools/nvp_no_ffmpeg_contract.py` | 7/7 DATA-AV-01 jobs passed at inspected SHA; not product-wide integration acceptance |

**Exact-head baseline evidence:** [DATA-AV-01 run 42742932991](https://github.com/vjmichael/nvp_offline_film/actions/runs/42742932991), 7/7 passed (DA-00 audit; React; Windows/Linux Python 3.11/3.13; installed Windows CI smoke). This verifies only that workflow's tested source and installation fixtures, not physical creator microphone, continuous 3D sound/picture, cinematic quality, or all other SLATE/USD branches.

## 3. PLAN-02 donor disposition and required compatibility adapters

| Donor | Disposition | What to retain | What must change / is prohibited |
| --- | --- | --- | --- |
| [PR #75 DA-05B](https://github.com/vjmichael/nvp_offline_film/pull/75), [#76 DA-05/06](https://github.com/vjmichael/nvp_offline_film/pull/76) | SELECTIVE PORT after rebase/review | Native verified PNG/PCM packaging, bounded no-clobber publication; live source capture, spatial sound, 3D playback and color decisions | No whole-branch merge; reconcile with newer PR #74 filming publications and original Film Time; no assumption an AVI/PNG is the authoritative Take |
| [PR #83 DA-02E](https://github.com/vjmichael/nvp_offline_film/pull/83) | SELECTIVE PORT | Independent audio-device ADC-clock evidence, drift handling, native capture UI | Verify exact host Time mapping and device permissions; no shared-clock or mock-device acceptance claim |
| SLATE-08B source/UI | REPAIR IN CANONICAL STACK | Approved native source camera IPC, stale-result/cancel boundaries | Fix four failed React camera-native-bridge tests before camera/rail integrations |
| CAM-FX-01–05 (`7b4c3683`) | ADAPT SOURCE-FIRST | Director camera rails, edit layers, source-locked render/camera proofs | Translate film-frame-specified rails to exact Film Time; preserve FilmIndex source revisions; keep Cycles picture windows derivative; independent branch pass is not integrated pass |
| CAM-FX-04 genuine GGUF (`7ed65308`) and WO6-07A/C | ADAPT READ-ONLY/REVIEW | Genuine GGUF inference, source-grounded typed shot proposal, manual editing and OS-review separation | Model suggestions never publish USD or authorize worker; existing 0.5B smoke is not representative 7B+ quality or installed human acceptance |
| [PR #104 WO6-07F](https://github.com/vjmichael/nvp_offline_film/pull/104) | SELECTIVE PORT | First-party CPU scene-linear OpenUSD raster and original PCM audio-clock playback window | Replace frame-bound source/editor contract with canonical Film Time + exact Take/source hash; ensure native zero-FFmpeg end-to-end; playback frames remain disposable |
| [PR #139 01S](https://github.com/vjmichael/nvp_offline_film/pull/139) / [#142 01T](https://github.com/vjmichael/nvp_offline_film/pull/142) | EXTRACT MECHANISMS, REWRITE CONFORM | Source-bound SQLite tickets, RAM/VRAM admission, independent Blender receipts, source-camera evaluation, no-replay recovery | **REJECT** 01T's FFmpeg/ffprobe final conform, frame-index source authority, hard-coded source 720×24fps, and permissive custody fixtures; exact Film Time→derived output frame adapter required |
| [PR #143–148 USD-FILM-02M](https://github.com/vjmichael/nvp_offline_film/pull/148) | SELECTIVE PORT AFTER SOURCE CONTRACT | Reusable USD geometry/modules, director-approved source-layer variants, preview/diff/undo and safe proposal revisions | No wholesale merge of the 01T-ancestry stack; audit asset path/references and native data-first time/authorization contract first |
| Imported 2D frame-index/proxy and old master paths | RETIRED ACTIVE PATH | Historical code/compatibility reader only with explicit segregation | No restart of mandatory frame-index workflow or FFmpeg path |

**Status semantics:** “selective port” means a proposed independent implementation/reconciliation task, **not implemented on PR #74**. Donor CI and previous-head artifacts are evidence of a *different exact source*, not acceptance of the assembled product.

## 4. Evidence conflicts / open defects

- [SLATE-08B run 42742933208](https://github.com/vjmichael/nvp_offline_film/actions/runs/42742933208), **same inspected PR #74 SHA:** four native Win/Linux Python jobs passed; the React camera native bridge job failed (render-ticket invocation, stale image, cancel button, invalid-scope error expectations). Reproduce and repair source/test contract; do not simulate a passed WebView2 physical session.
- [01T run 42748959937](https://github.com/vjmichael/nvp_offline_film/actions/runs/42748959937), **different head `f7b07ed4`:** React passed, all four source/queue matrix jobs failed and full Cycles/720-frame gate failed on Blender exit code 70. Its legacy FFmpeg conform is incompatible. Preserve the failure receipts; do not spend a new whole-film render on its old contract.
- WO6 planner on the 01T branch shows deterministic scene/temporal ordering mismatch; do not promote it to a PR #74 current-source defect without reproducing it there.
- CAM-FX-05 real moving Cycles gate and CAM-FX-04 genuine GGUF smoke passed on **their own** heads only. Source-level isolated success does not prove Film Time, source, audio, native installed or human approval integration in PR #74.
- Native positive descendant custody, audio device latency, physical Windows approvals, real 7B+ inference, professional GPU Cycles, full 30-second native non-FFmpeg delivery and human creative screening remain separate acceptance gates.

## 5. Ordered integration seams / implementation task groups

**PLAN-02-A — Canonical path + native source invariants.** Keep PR #74 as the only integration target. Maintain the manifest and link it from master/engineering/DA ledger. Keep DA-00 guard, typed Film Time and immutable original-source identity. Reproduce and fix the SLATE-08B React failures on the canonical source. No merging old branch heads.

**PLAN-02-B — Data source and synchronized native A/V.** Review/port #75/#76/#83 only where source-time, SHA, licence and authorization contracts match. Complete original microphone/PCM production, source publication/custody and uninterrupted OpenUSD picture + native spatial sound under one original audio clock. Follow DA-01–DA-04.

**PLAN-02-C — Reviewed camera and AI.** Port CAM-FX rails/edit/visual verification and WO6/CAM-FX genuine local model advice as *typed, unapproved proposals*. Use `backend/nvp_exact_time_shots.py` for shot intervals; require new human consent for committed source opinions and worker execution. Negative tests for stale source, refusal, replay and source mutation.

**PLAN-02-D — Source-selected presentation renderer and durable queue.** Adapt 01S/01Q/01T reusable supervisor/SQLite/receipt logic and #104 native source renderer to take **exact Take/Film Time source windows** and produce approved derivative views. Persist selected camera/source hashes; never require every optional camera roll or make 24fps frames native source state. Verify OS descendant custody before retry, not `lambda *_:True`.

**PLAN-02-E — Native non-FFmpeg final delivery + 02M authored scene.** Integrate approved native 2D derivative packaging/color/independent decoder; port 02M reusable world/asset/creator authoring by source-layer contract. Create one 30s film whose output codec/cadence are presentation choices and whose original actor/audio/scene data remains immutable. No FFmpeg fallback.

**PLAN-02-F — Consolidated acceptance + cleanup.** Run **one** grouped Windows/Linux native gate at a final SHA for each completed task group; verify installed Windows WebView2, refusal, cancellation, complete original 30s production and independently reopened finished sound/picture. Eliminate legacy CI fanout in scope and record passes/failures with exact artifacts. Genuine physical creator interaction and cinematic quality remain distinct gates.

## 6. Exit and release rules

- PLAN-02 **documentation/evidence mapping is not a port, a passing compiler test, or film acceptance**.
- Before any source port: inspect both heads, trace dependency/import closure, list what will be copied/reimplemented, provide a source/ABI and Film Time adapter contract, check DA-00 on the resulting assembled head, and require source-immutable negative tests.
- Full branch fast-forward/cherry-pick of 01T or 02M stacks is **forbidden without explicit compatibility reconciliation**. Prior CI passes cannot be inherited.
- At the end of each **implementation** task group, run one exact-head consolidated native Windows/Linux acceptance gate; do not dispatch a CI workflow for every small change. The 30-second finished-film, physical creator human approval and 7B+ GGUF tests are independent gates.
- Stop and report after the requested group: what changed, what passed, what failed, and the next group.

**Next implementation task:** PLAN-02-A — repair the canonical SLATE-08B native camera-bridge React failures, then prepare the source-time adapter for camera rail/EDL ports. All later phases stay unaccepted until independently executed.

## PLAN-02-A — repair of canonical SLATE-08B camera interface

Implemented in canonical source, pending grouped native acceptance: the read-only React source lens panel now enforces exact `project_id` as well as existing scene/revision/SHA/tick/camera identity. Retired native Blender still request, poll and cancel entrypoints deny all requests after the native-window origin check; capability discovery advertises `supports_cancel: false`. The old positive worker tests were replaced with seven active source-bound/nonprivileged React regressions, while native tests now reject forged historical poll/cancel tickets. The existing DATA-AV-01 grouped React gate includes the full migrated test file. This **does not** re-enable the old renderer, accept CAM-FX rails, or imply physical Windows approval. Record exact-head CI outcomes separately.

## PLAN-02-A exact-source CI closeout

[SLATE-08B grouped run 42755225015](https://github.com/vjmichael/nvp_offline_film/actions/runs/42755225015) completed **SUCCESS, 5/5 native Windows/Linux and React jobs** for `16d8778ea80daa6e9326f68391cde5e6127ba4f8`; its React suite passed **17/17**, and the grouped DATA-AV React suite passed **20/20** and the no-FFmpeg audit passed at that SHA. The broader DATA-AV Windows installed acceptance remained pending at time of report. **Camera regression accepted only in this scope**: no reactivated old Blender IPC, no claim of actual rendered camera footage, CAM-FX rails or physical OS interaction. Next PLAN-02-B original-data A/V integration. Historical PR-triggered CI fanout is a separate hygiene issue.
