# NVP POST-01F R5-R1 — source integration and native acceptance register

**Source-candidate status: portable tests PASS; native Windows-positive and installed film acceptance OPEN.**

The reviewed source was derived from the R5 ZIP SHA-256
`b6e8319e048674f346f0f7b39666c870b41336c57b207275824a7ef5d0f7de4f`,
whose R3 base was `NVP_POST01F_R3_R1R2_NATIVE_INTEGRATION_SOURCE_CANDIDATE.zip`.
The recorded existing PR #161 head was
`62267e4a67f07dd6927f07f4b9342fbeaa845231` prior to integration.
**Neither the independent original R1 archive nor the exact R2 standalone
source archive was recoverable in this environment.** R3/R4/R5 composite
source is not proof of byte-for-byte R1/R2 reconciliation. No historical
acceptance obligations or native security gates may be retired on that basis.

## New R5-R1 code and security decisions

| Component | Contract | Native/installed state |
|---|---|---|
| `backend/nvp_post01f_scm_cng_v2.py` | Strict CNG P-256 `r||s` wire v2, exact signed canonical JSON identity, installed HKLM verifier pin, no v1 downgrade, durable nonce consumer, rejects desktop-only kernel evidence | Synthetic P-256 crypto test passed; actual SCM-signed receipt OPEN |
| `tools/nvp_post01f_windows_scm_ltx_broker.cpp` | One-use HKLM approval, per-ticket durable spent journal, explicit creator detached-CMS scope, SCM-owned AppContainer/WFP/Job, pinned fixed installed broker and source, EFS, kill/drain of helpers, OS-derived SID/PID, CNG machine-key signing of picture SHA | Source candidate, **not yet independently MSVC-compiled or Windows-run** |
| `tools/nvp_post01f_windows_creator_signature.hpp` | Separate exact-scope creator certificate verification and 15-minute deadline | Needs original independent desktop creator approval and installed trust |
| `tools/nvp_post01f_windows_install_cng_key.ps1` | One-time installer ADMIN machine P-256 non-exportable key provision, SYSTEM/Admin key-file ACL and pinned HKLM public key | Not executed/provisioned; must be reviewed within NSIS installer first |
| `backend/nvp_post01f_g03_nonce_ledger.py` | Atomic durable signed-receipt nonce spend in existing encrypted G03 `worker_receipts` HEAD | Synthetic G03 store only; physical DPAPI/SQLite restart/replay OPEN |
| `backend/nvp_post01f_encrypted_review.py` | Adds independently authorized read-only director preview returned as full AES-GCM-authenticated memory bytes, no plaintext staging disk, direct model endpoint, or auto approval | Portable tests only; authenticated native desktop UI/route OPEN |
| `.github/workflows/nvp-post01f-r5r1-scm-cng-negative.yml` | SHA-locked Windows-2025 MSVC build, Python suite and negative direct/unauthorized SCM service launch | Requires actual GitHub source-ref publication and workflow result |

The existing R4/R5 files and negative tests are retained unchanged except
the addition of optional authenticated director preview in the R5 review
module and separate R5-R1 source files. Original Takes, 48-kHz source PCM,
non-destructive edit records, and project encryption may not be rewritten.
No automatic conversion of LTX-derived media into immutable original assets
or auto-creator approval is permitted.

### Full creator + process trust sequence

1. Trusted installed director UI obtains **an explicit creator action** over
   the exact immutable Take, job, model-stack lock, derived layout/look,
   conditioning and expiry. It issues a detached CMS signature to the
   protected out-of-worker `CreatorApprovals/` location. The implementation
   of that desktop issuance step is **not** complete.
2. Independent trusted admin/installer policy stages a one-use HKLM ticket
   and an EFS exact job root. SCM consumes the ticket into both HKLM and a
   write-once EFS spent-ticket register **before launching**.
3. SCM checks the independent creator PKCS7 signature against the
   installer-pinned signer certificate hash and expiry. No `--yes`,
   model-authored consent or desktop-supplied booleans can satisfy it.
4. SCM starts only fixed, hash-pinned installed NVP LTX broker code in a
   unique AppContainer with zero network capabilities, four SID-specific WFP
   blocks, and a kill-on-close Windows Job. Original-derived input files get
   read-only lowbox access; the model cannot see creator keys/signature or
   original audio. Actual AMD GPU access under this custody is unproven.
5. SCM verifies the real child PID/AppContainer SID/Job, successful process
   exit, descendants drained, EFS, original input/plan/model pins unchanged,
   no unapproved sidecars and exact `picture.mp4` hash. Its own machine CNG
   key signs the canonical v2 receipt **outside worker-controlled files**.
6. Trusted host independently checks installed public key, receipt signature,
   exact project/job/source/model/picture/PID/SID, nonce spend in encrypted
   G03 SQLite, genuine model/GPU evidence and independent video decode/24fps
   PTS/zero-audio. All of those conditions must pass, not just SCM signature.
7. NVP puts generated **picture only** into separate immutable AES-GCM
   derived media, then privately offers the authorized director a read-only
   preview. Explicit creator approve/reject/retry is separately signed or
   authenticated. Original actor PCM/dialogue remains authoritative.

## Source evidence obtained here

From the local candidate root:

```text
python -m unittest discover -s tests -p 'test_nvp_post01f*.py' -q
70 tests passed, 0 failed
python -m compileall -q backend tests
passed
```

The tests include strict v2 P-256 interoperability, v1 refusal, malicious
signature/model changes, nonce replay and cross-project rejection, actual
AES-GCM tamper failure with synthetic G03 storage, locked user refusal and
read-only creator preview, and R4's 121-model-frame to 120-picture-frame
FFmpeg re-encode/PTS/no-audio test. They do **not** validate live Windows
KSP/DPAPI/EFS, SCM ownership, actual USB/driver/GPU, key provisioning,
private desktop UI, NSIS installer, or real LTX model execution.

## Unchanged source and physical Windows acceptance gates

- **GATE 1 (source):** recover exact independent R1/R2 source and reconcile
  all historical interface/test semantics against R3/R4/R5/R5R1; one reviewed
  source-lock commit on existing `nvp/mainline-convergence-20261113` draft
  PR #161 only. Do not create another branch/PR or merge main.
- **GATE 2 (native negative):** MSVC `/W4` build, real SCM service install,
  missing ticket refusal, direct CLI refusal, replay, expired/foreign creator
  signature, sidecar and tamper refusal, malicious key and invalid key ACL.
- **GATE 3 (native positive):** actual ADMIN-installed machine key/SCM CNG
  sign, original independent creator action and approved ticket, AppContainer
  SID/WFP four filters/Job draining/desktop token audit, actual EFS source
  handoff and genuine direct LTX broker model load. Service stop/cancel,
  guardian death/restart, host/worker crash and source-mutation races must
  be independently qualified. **No positive native result exists yet.**
- **GATE 4 (encrypted director):** real Windows DPAPI-unlocked G03 source,
  first-start/reopen/restart/revoke, authenticated local editor endpoint and
  visual playback, ciphertext-metadata-head crash consistency, approve/reject
  history and full original PCM return after derived picture.
- **GATE 5 (R9700 physical):** separately provision licensed weights and
  AMD stack, record driver/hardware/VRAM, perform genuine LTX image/video
  output on Radeon AI Pro R9700, capture **authentic** preview stills, confirm
  121 model/120 presentation frames at 24fps, no generated audio publication,
  immutable original Take/actor voice, and continuity across two cameras.
- **GATE 6 (consolidated):** terminal non-stacked original Windows/Linux CI
  and real installed physical acceptance at **one unchanged commit SHA**;
  reconcile all prior CONV and POST gates; no main release/merge if unmet.

## Known engineering holds and release blockers

- Existing R4 desktop-owned `ProtectedLtxHandoff` is **not an SCM owner**;
  it cannot be treated as the launch method for the positive v2 service
  without a reviewed **SCM-only host submission, completion and cancellation
  protocol**. The native signer source does not itself connect React/NSIS.
- The Windows machine key provisioning script is an installer candidate,
  not yet integrated with NSIS/rollback/recovery or compiled/installed.
  `SignerTrust` and creator-cert HKLM pins must be owner-reviewed and
  independently protected; never inject synthetic keys to production.
- The Windows broker source and its `/W4` compile and native negative test
  have **not** been run in this container. Model/GPU execution under Session 0
  or EFS current-user encryption is uncertain and may fail closed.
- Original R1/R2 separate archives remain unavailable, so no *exact* source
  reconciliation can be declared. The earlier R3 tested composite is
  preserved, but an R3-only contract is not identical to independent R1/R2.
- This is a **source/code review candidate**, not installed film, playback UI,
  authentic LTX sample, verified SCM key custody, or a release acceptance.
