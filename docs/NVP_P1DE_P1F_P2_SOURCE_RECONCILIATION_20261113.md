# P1-D/P1-E → P1-F → P2 Source and Native Acceptance Reconciliation (2026-11-13)

## Authority and source identity
- Data-first canonical PR #74 branch: `nvp/data-av01-native-scene-playback-20261106`, inspected exact head `e29351bddb657ddc08ed180d5b2eaea94ebc525e`. **This is NOT evidence that the NVP 34 P1-D/P1-E changes landed on that head.**
- Older G07 non-destructive editing branch `nvp/g07-source-editing-20261111` at `d936d3af2382935516088bcb095ea0d2a70dc274`: 282 commits ahead, 235 behind canonical; source-only G07 editor, no PR-triggered exact-head runs returned.
- Older G09-E sustained-scale branch `nvp/g09e-sustained-scale-20261111` at `3f89493c2af993e0b03fbccb8a9b0de9a5889cd3`: 433 commits ahead, 235 behind canonical; no PR-triggered exact-head runs returned.
- Older long-film/PCM branch `nvp/wave1-longfilm-runtime-pcm-20261111` at `f2ddf5d76ed0739163463428a2d2ac8d4e5355e0`: 585 commits ahead, 235 behind canonical; no PR-triggered exact-head runs returned.
- Older G08 export branch `nvp/g08-native-film-export-20261111` at `96a39cb42ed3e6a922328b3ca8960edcf4fc6368`: 307 commits ahead, 235 behind canonical. G09-F distribution source exists at `b83ac974ae4295da32e09ea8e6ebe739c71f912b`, but native release/feature-length playback acceptance remains open.
- Do **not** wholesale merge these divergent histories, assume their API/authorization ABI matches canonical, or substitute historical CI receipts for current tests. Locate the actual NVP 34 P1-D/P1-E implementation head/PR and inspect its diff against the exact target before selective integration.

## Original canonical native evidence at e29351b
GitHub commit-associated PR workflow results inspected:
- PASS: USD-01 `43417315059`, USD-02C `43417315372`, USD-02D `43417315538`, E2E native editorial `43417315550`, E2E finishing `43417315175`, SCALE compact zero-FFmpeg `43417315456`, several SLATE and native camera gates.
- FAIL: SLATE-05 `43417315432`; SLATE-06 `43417315421`; SLATE-07 `43417315117`. SLATE-05's former tuple-comma fixture was corrected in source at e806118, but this does NOT establish corrected-head success. SLATE-06/07 creator-approval bindings and SLATE-07 document shape require original-log reconciliation, not permissive authorization changes.
- CANCELLED: DATA-AV `43417315136`. No full-source/native/installed acceptance is inferred.
- The canonical DA task ledger explicitly describes P1-A/B as DA-03 packets and does not establish P1-D/E/F as committed follow-on canonical packets. P1-D/E/F labels from the separate NVP 34 work therefore need an explicit scope/source crosswalk to G07/G09-C/G08/G09-E and PLAN-02 sequence.

## Safe integration order and test matrix
1. **P1-D original editable timeline:** Identify implementation SHA; diff only precise relevant modules/contract edges. Verify immutable Take/FilmIndex identities; edit SHA; trim/reorder/split/repeat and alternate source camera; undo/redo/reopen; missing original must fail closed; original scene/PCM SHA unchanged. Reconcile G07 source to canonical DA-00/Film Time (7,056,000,000 ticks/second) and approval scope.
2. **P1-E actor-owned audio:** Bind each original emitter to authoritative ActorID and frozen Take; validate 48k original PCM SHA/samples, camera-relative motion, mute/offset and audio clock across edited cuts; deny spoofed actor, foreign PCM, approval replay, unaudited HRTF, and after-cancel publication. Verify moving shot in genuine Cycles/native renderer and independent read-back.
3. **P1-F sustained delivery:** Reuse actual approved P1-D edit revision and P1-E audio identities; render genuine protected Blender/Cycles picture, native 48k PCM derivative, independent picture/audio verification, durable manifest/restart/guardian-loss/cancellation and zero-FFmpeg audit. Require matching Windows/Linux exact-head original process custody; do not treat synthetic source fixtures as physical hardware.
4. **P2 long film:** Verify 30-minute production first: 43,200 picture instants at 24fps, 86,400,000 audio samples/channel at 48kHz; 180 independently verified 10-second reels if using G09-E. Then 60–90-minute and 2–3-hour runs with bounded RAM/VRAM/disk, durable pause/resume, source hash and time continuity, long single-Take PCM streaming, sealed G03 encrypted assets, cross-reel playback and accessible filmmaker UI. G09-E currently rejects >64MiB original clip reader windows; native NumPy/SciPy, worker dispatch and sealed encrypted longfilm are not installed/accepted.
5. **Exact-head gate:** All source, native Win/Linux, original Blender/Cycles, independent authorization/custody/recovery, installed-app and long-duration receipts must identify **the same integrated source SHA**. Physical EFS key recovery, signed worker/dependency distribution and one-use creator NSIS approval remain separate release gates.

## Outcome of this checkpoint
- **Evidence reconciliation performed; implementation source identity remains unresolved.** No P1-D/P1-E native closeout, P1-F integration or P2 long-film acceptance is claimed.
- This is a review-only reconciliation record on a new branch. No production source, canonical branch, release branch, installer or original FilmIndex media is modified.
