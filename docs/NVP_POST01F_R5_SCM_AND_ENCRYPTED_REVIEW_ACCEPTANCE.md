# NVP POST-01F R5 — native LTX SCM custody and encrypted derived review

**Status: SOURCE-ONLY CANDIDATE; Windows native/SCM/physical LTX acceptance OPEN.**

Source baseline inspected: existing `nvp/mainline-convergence-20261113`, draft PR #161, SHA `62267e4a67f07dd6927f07f4b9342fbeaa845231` on 2026-11-20. The R1 and R2 exact archives were **not** available; R4 is preserved and extended, not certified as an exact-byte R1/R2 merge. Do not create another branch or PR, bypass WFP/AppContainer/EFS, or merge `main` without original acceptance. No changes to existing production code or historic test requirements are justified by this portable source batch. Only after independent review should the candidate be published in one atomic existing-PR batch with a source-lock receipt.

## R4-to-R5 implementation

- Carried forward `nvp_post01f_ltx_broker.py` and the strict native command builder, `nvp_post01f_native_custody.py`, `nvp_post01f_picture_verify.py`, the signed SCM result-envelope verifier, and the protected host `nvp_post01f_ltx_native_handoff.py`.
- `verify_signed_scm_picture_result` now carries the exact canonical signed-body SHA-256 into the host result; `admit_picture` requires that field and returns the originating `plan_sha256` and `scm_receipt_sha256`. No new UI/model-provided signature or arbitrary file path is accepted.
- New `nvp_post01f_encrypted_review.EncryptedLtxReview` is a **trusted-host library**, not an exposed web API. Inputs: the existing `LiveFilmStore` (with an active unlocked project session), exact installed host quarantine root, a callback that re-verifies the original immutable Take, a separate genuine-native/SCM-admission checker, and a separate genuine local creator-action checker. All are mandatory and fail closed. A synthetic test callback does not prove native authorization.
- `publish_pending` accepts only the exact `PICTURE_VERIFIED_UNAPPROVED` result of the native host, rechecks source bytes and EFS, authenticated native admission, and original Take identity, then streams the picture into **project-key AES-256-GCM** under a project/job/purpose-specific AAD. This creates two write-once ciphertext files: `picture.nvpsealed` and `manifest.nvpsealed`, never a new `original` record and never LTX-generated audio. It verifies encryption and full authenticated readback, then moves an encrypted scratch directory to final. A crash orphan/partial is denied, not automatically adopted.
- The existing protected live-film **encrypted SQLite `worker_receipts` table** receives the immutable ciphertext-manifest SHA-256 after the file is sealed. Reopen refuses an otherwise valid ciphertext folder unless its manifest is bound to the authenticated live SQLite HEAD, which avoids a new table or unreviewed migration. Deleted/altered files, missing anchors, unexpected audio/sidecars, foreign project/session, and mutated original Take refuse.
- `review` requires an authenticated unlocked project session, checks the whole encrypted picture and source, and returns review metadata only. `decide` requires a separate authenticated creator event and creates one append-only AES-GCM-encrypted `decision.nvpsealed` with a second independent live SQLite HEAD receipt. Duplicate approvals, approve-after-reject, deleted/altered decisions and unanchored/orphaned receipts refuse. A retry always creates another LTX job and leaves the original Take unchanged.
- No generated preview/movie is automatically displayed, inserted into editor/export, or deemed creator-approved. A separately authenticated preview streaming endpoint, UI wiring, session revocation and screenshot test remain to be designed and accepted. Current API returns metadata, **not a working filmmaker review screen**.

## Real SCM signer and process boundary: outstanding

The R4 Ed25519 envelope reader **verifies signatures only**; it cannot prove that a matching private key is held by a Windows SCM service. An SCM process **must own and supervise the actual LTX child** (or receive OS-verifiable transferred ownership under a separately reviewed kernel-native protocol), rather than signing flags supplied by a desktop process. The existing P1-F SCM Blender source broker is useful as an implementation reference for one-use consent, AppContainer SID/token assignment, WFP dynamic filters, actual Job descendant cleanup and SCM-owned negative receipts; its receipt does **not** automatically authorize LTX.

For production: implement a separate fixed-role installed SCM LTX broker, installer-controlled identity/one-use creator ticket and restricted named-pipe or equivalent protocol, original kernel AppContainer/Job/WFP audits, child/result digest and pinned stack verification, OS-owned signing key/certificate with enforceable ACLs, duplicate/replay denial, and a signed picture-specific response. The service must verify actual picture location, job/plan/project/model/picture hash, original SID and PID, WFP/no-egress, EFS and full descendant cleanup **before** signing; unexpected audio, exit failure, timeout, host/guardian death, source/credential or process-token drift must not yield a positive receipt.

Windows CNG with machine-persisted ECDSA P-256 service-restricted key is a platform-supported design candidate (see Microsoft CNG docs); adapting from R4's Ed25519 verifier requires **an explicit new wire version with independent signature-compatibility and key-rotation testing**, not an unnoticed key-algorithm substitution. An approved pinned OpenSSL Ed25519 service provider is another option only after its license, DLL integrity, and machine key custody have been qualified. **Neither signer nor the native SCM LTX service is implemented here.** A synthetic Ed25519 fixture is never accepted as OS evidence.

## Source tests and limits

Run from candidate root:

```powershell
python -m unittest discover -s tests -p "test_nvp_post01f*.py"
python -m compileall -q backend tests
```

R4 unchanged portable baseline: 34 passed. R5 extended portable source suite: 48 passed, 0 failures in this environment (R4 + new R5). Tests for AES-GCM seal/readback use real `cryptography` AESGCM, but a **fake LiveFilmStore/DPAPI/SCM/EFS adapter**; they are **not** acceptance of the actual Windows project key, real installed G03 encrypted source, native SCM, EFS, video codecs or AMD GPU. R4's non-mocked FFmpeg 121-to-120 picture-only media test is retained. Unit tests deliberately use fake test-pattern model output, never LTX-generated frames.

## Unchanged-SHA Windows acceptance — NOT EXECUTED

1. **Exact source**: recover exact R1/R2 source archives; compare/adjudicate every relevant file and original test; publish one reviewed commit only on existing PR #161, capture SHA and source-tree hashes; do not stack CI.
2. **Installed service**: actually compile/package the pinned LTX broker and SCM service; install under independently reviewed Windows code/model/codec ACLs and machine-key/creator trust; run genuine AppContainer+WFP+Job+SCM checks. Verify no uncontained fallback and GPU access under lowbox; refuse if incompatible.
3. **Authentication**: verify signed process-derived receipt using actual SCM-held machine private key, original PID/SID/job/plan/project/model/picture, WFP, worker descendants, EFS, one-use nonce, restart/timeout/cancel races, injected receipt, foreign project, altered output and adversarial named-pipe client.
4. **G03 derived review**: verify actual Windows DPAPI/AES-GCM and EFS, encrypted SQLite HEAD receipts, publish/reopen/approve/reject/retry/lock/revoke, crash at each file/HEAD transition, orphan cleanup, denied plaintext media access, no automatic copy into immutable originals. Implement authenticated desktop preview and review UI.
5. **Real R9700**: separately provision approved LTX-2.5 model/IC-LoRA weights, Python/AMD runtime and licenses; record exact GPU model, driver, real GPU tensor kernel, loaded model hashes, VRAM/RAM/time. Generate real two-actor/camera 5-s source-backed LTX picture, show authentic stills, verify 121 model vs 120 presentation frames, original 48-kHz PCM retention, immutable Take digests and continuity across two cameras.
6. **Gates**: terminal same-SHA original Windows/Linux CI plus separate physical Windows installed receipts. No release-ready or main merge until all owner acceptance and CONV-12/13/14 exit requirements are satisfied.

## Engineering blockers

- R1/R2 exact source archives unavailable; R5 is not bytewise reconciled or in GitHub's branch.
- Current R4 launch path is a desktop-owned AppContainer/Job, while the requested genuine signer must be an SCM-owned trusted issuer. This custody conflict requires one reviewed launch owner/protocol; do **not** issue signed status based on desktop callbacks or automatically add a privileged process.
- Installed Windows hardware, genuine SCM signer/key and LTX model weights unavailable here. No native Windows/physical R9700 evidence or authentic generated images have been produced.
- R5 encrypted review is *back-end* library code with synthetic-store tests, not a completed authenticated UI or installed-film publication acceptance. Multi-process ordering, ciphertext rollback and DPAPI recovery on the actual Windows machine remain mandatory independent gates.

**Conclusion:** R5 provides a more enforceable project-authenticated *derived* review handoff and preserves the exact original Take; native SCM ownership, actual Windows implementation, UI wiring, unchanged-source CI and physical LTX generation remain open. Do not silently promote this candidate to accepted native release.
