# NVP alpha closeout — authoritative handoff (2026-11-04)

This document is a continuation checkpoint for NVP development. It deliberately separates **implemented**, **native-verified**, and **release-accepted**. The target is a **standalone Windows PC film-production application**, not a browser product. The browser/React interface is a temporary or embedded UI surface; a WebView2 shell does not by itself constitute installed-desktop acceptance.

## Priority / next execution

**First close the exact-head native acceptance for PR #45 (AUDIO-01K.3), followed by E2E-01D crash recovery and E2E-01E installed Windows desktop alpha.** Do not merge a draft PR or mark cinema release-ready based on queued CI or local fixture output. Do not delay useful code work solely because GitHub Actions is backlogged.

Reference branch: `nvp/stack02c3b14-picture-conform-20261104`
PR: https://github.com/vjmichael/nvp_offline_film/pull/45

### Gate 1 — AUDIO-01K.3 real cinema deliverable
1. Capture the exact PR head SHA before the run and recheck it when judging results; older green jobs are non-authoritative.
2. On actual Linux and Windows executors, prove native DCP-o-matic can encode a source-bound SMPTE JPEG2000 DCP with correct frame rate and duration. Inspect real MXF + CPL + PKL + ASSETMAP, not just filenames.
3. Independently inspect with DcpDoctor (strict QC). Verify channels (six-channel cinema mapping), sample rate, sync offsets, duration parity and audio/video frame lineage against the original approved picture/mix.
4. Reopen the delivery from a **fresh** FilmIndex process; verify all committed source hashes and graph edges.
5. Tamper with one MXF after publication and prove verification refuses it. Include missing-asset and manifest-mismatch refusal.
6. Capture encoder/QC executable version + SHA, job URLs, exact commit and media hashes. If a tool cannot provision, classify **BLOCKED — dependency** rather than PASS.

### Gate 2 — E2E-01D native crash/recovery acceptance
1. Test true terminated worker trees on Windows Job Objects and Linux process containment, not mocked return codes.
2. Inject crashes at AUDIO-01I/J staging/write/fsync/rename/SQLite transaction/receipt boundaries; verify post-restart reconciliation classifies each job accurately.
3. Preserve the last creator-approved output, avoid exposing partial output as committed, and release reservations only after confirmed OS process exit. Test timeout, cancellation and restart.
4. Report a failure matrix with per-case logs and zero unaccounted orphan workers.

### Gate 3 — E2E-01E installed Windows desktop alpha
1. Build a **real NSIS installer** with the NVP native app, WebView2 runtime strategy, Python/native worker dependencies and production entrypoint. Verify the installer contains those files.
2. Install on Windows without a source checkout; launch the visible native application and create a project.
3. Save, exit, relaunch and reopen the project from its durable on-disk state; show that no temporary browser server is required for the final installed app lifecycle.
4. Prove local creator-action authorization reaches a **real** native worker. Run at least one representative end-to-end picture/audio job; check task progress, exit, receipt and restart recovery.
5. Uninstall and confirm program binaries are removed **while user film projects remain intact**; perform reinstall/reopen.
6. Attach installer SHA, installed executable SHA, app screenshots, fresh-process logs and OS-specific evidence. A CI-built installer without install/run/reopen/uninstall is not acceptance.

### Gate 4 — Full approved film workflow
Blender original source → frozen take → scene-linear EXR → ACES2 transform → edited OTIO → immutable picture conform → source-linear audited edited ProRes → audio mix/final approval → matched DCP. Source identity, creator approval, lineage, picture and sound duration, crash recovery and FilmIndex reopen must all agree. Do not conflate a 120-frame fixture with a fully approved 30–60-second film.

### Gate 5 — consolidation
Run exact-head Windows/Linux native regressions. Reconcile stacked draft PRs #40–45 against the accepted base, prevent duplicate workflows/branch drift, and merge only when gates are proven. The Lu↔DLC integration is expressly deferred until after Lu v1.0.

## Current evidence at handoff
- PR #45 remains draft/unmerged.
- The observed PR-head checkpoint was `cd650771b0511c5d6456be1613881d657af05140`; **re-read the head after this documentation commit**, since it is no longer authoritative.
- On inspection, runs 41962241478 (Linux cinema), 41962241466 (Windows cinema), 41962241742 (Windows installer), 41962241738 (E2E-01D) and 41962241725 (AUDIO crash matrix) were **queued**, with no passing native evidence yet.
- Earlier local work reports native DCP-o-matic 2.18.51 production/verification of real DCPs including MXF tamper rejection. This is useful local evidence but does not substitute for independently audited exact-head Windows/Linux + DcpDoctor delivery acceptance.
- Local NVP checkout and Windows tools were **not** available inside the present execution container, and outbound Git cloning was unavailable. No installed Windows run has been claimed from this checkpoint.

## Resumption discipline
Start each new conversation by reading this file, PR #45 head, latest exact-head CI jobs and the last actionable failure logs. Work on the first **unproven** gate, not the oldest PR description. Do not schedule duplicate hourly checks. Record every meaningful checkpoint with: branch / head SHA / changed files / actual tests run / skipped or unavailable tests / remaining blockers / next precise action.
