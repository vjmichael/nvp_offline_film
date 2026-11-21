# POST-01F R5-R2-R3-R4 — prepared trusted host handoff

**Status: portable source candidate, NOT installed positive acceptance.** This source must not be integrated into PR #161 while the original `7116ffc66b2ea41ee399fea73ca1bdf3355d58c3` same-SHA CI cohort is active. No new branch/PR, forced ref update, CI stacking, automatic film approval, public plaintext URL or main merge.

## Additions

- `backend/nvp_post01f_installed_receipt_transport.py` is a bounded, read-only Windows KnownFolder ProgramData -> `NVP/POST01F/SCMReceipts/<job>.v2.json` transport. It refuses non-Windows, unexpected job/PID, redirected paths, non-EFS folders/files, replaced/oversized receipts, and never reads a UI- or worker-chosen source. The existing `InstalledScmCngV2Channel` *must* verify the exact P-256 signed body, independent HKLM host trust and durable one-use G03 nonce; reading an EFS file alone does not prove SCM custody.
- `backend/nvp_post01f_native_film_review_bridge.py` is a trusted native-host adapter for existing `EncryptedLtxReview`. It accepts only job identity; fetches the project token from the installed active-session broker, fetches separate authenticated native preview/decision events, renders video-only bytes through a trusted in-memory renderer (no paths/URLs sent to a caller), and requires explicit approve/reject for immutable decisions. It does **not** implement an OS-authenticated native event broker or a working video renderer by itself. It now checks protected session continuity again immediately before video presentation and after the native renderer returns; the installed renderer still must stop immediately if revocation occurs mid-playback.
- Seventeen portable **source/negative** unit tests with injected test services pass. These are not claims of real Windows EFS, SCM, CNG, playback, DPAPI or LTX inference.

## Gates before integration / native completion

1. Finish/reconcile all **45 original** workflows at SHA `7116ffc66b2ea41ee399fea73ca1bdf3355d58c3`, including original W1-G, CONV-12 and all remaining Windows/Linux jobs; do not update the branch during active runs. Handle true failures without waiving original tests.
2. Independently inspect and integrate this source in **one non-forced** existing PR #161 successor after the original cohort is terminal and same SHA is still head; rerun all original same-SHA workflows without stacking.
3. On a **real authorized installed Windows machine**, provision nonexportable user creator cert and service-restricted machine CNG key with independently pinned HKLM trust, admin one-use ticket, EFS key-sharing and protected ProgramData/ProgramFiles ACLs. User must manually consent to the exact approved native source scope; no unattended approval.
4. Run actual LocalSystem SCM positive job with suspended AppContainer+Job, WFP blocks, exact source/model checks, drained descendants, and CNG P-256 signed EFS receipt. Connect the fixed reader through G03 one-use nonce; verify replay, wrong PID, unexpected media, egress, cancellation, restart, revocation, key drift, EFS loss and signer denial.
5. Wire `NativeFilmReviewBridge` to an independently authenticated **installed Windows** native user event provider, unlocked G03 DPAPI session provider and safe in-memory movie renderer. Verify real AES-GCM/G03 HEAD, correct video-only playback, explicit approve/reject/reopen, crash/revocation, no plaintext disk/public URL, no modification of original Take or actor PCM.
6. Physical Radeon AI Pro R9700 native LTX 2.5 visuals/quality samples, source R1/R2 reconciliation, CONV-13 installed release and CONV-14 main convergence remain separately open.

## R4-R1 independent local qualification snapshot (2026-11-21)

- Verified existing draft PR #161 head `7116ffc66b2ea41ee399fea73ca1bdf3355d58c3`, `main` base `75611266ef2670d561b3761b3352d3d25b0b3296`. No PR/branch mutations.
- Exact-head POST01F Windows SCM/CNG workflow run `44878814831` success: Python existing suite, real MSVC SCM and creator compilation, native negative creator signoff (both exits 91), real unapproved SCM startup refusal, and no-grant marker all recorded. No positive signer proof.
- Gate 1 original Windows and Linux W1-G jobs passed at exact head; full 45-run cohort must be terminal before moving the PR ref.
- Portable 17/17 local candidate source tests passed, including denial of session revocation before and during native in-memory playback, mutable receipt data and missing EFS. Actual native render interruption is a separate physical gate.
- No installed positive Windows or physical R9700 qualification occurred. This local work cannot acquire or manufacture creator consent, installer keys, native service receipts, encrypted playable media, or LTX outputs.

**Strict publication**: do not treat this snapshot as successor CI acceptance. Inspect the exact 45 original workflow conclusions afresh; only a fully terminal, source-matched cohort permits the single reviewed non-forced fast-forward of existing PR #161.

## R4-R2 candidate review corrections (2026-11-21)

- Python 3.11 compatibility: use `os.stat(path, follow_symlinks=False)`, not `Path.stat(follow_symlinks=False)` (the latter requires Python 3.13). Portable regression simulates 3.11 `Path.stat` refusal.
- Installer/native-service parity: inspect every `ProgramData/NVP/POST01F/SCMReceipts` directory component for native Windows reparse points, but require verified EFS only on `SCMReceipts` and the final receipt. The existing SCM service explicitly encrypts those two; requiring EFS on intermediate parent directories would unnecessarily block valid installed custody. Portable tests assert unencrypted receipt directory denial.
- Independent native EOF/mutation regression checks force a receipt-file change during the read; the host reader refuses it, in addition to the existing P-256 signature and persistent nonce checks. This is a test of the source transport, not independent OS custody.
- 17/17 local tests passed and Python compilation passed after these corrections. Do not call them real Windows tests. `main` and the protected PR remain unchanged pending the predecessor 45-run cohort.
