# W1-G production safety — native upgrade/rollback authority, reviewed supply chain, and source protection

**12 November 2026 — implementation checkpoint, NOT production release acceptance.**  
**Branch:** `nvp/int02-w1g-native-film-package-20261112`  
**Pre-change known green:** W1-G installed Windows and native matrix at `46d59d3`, runs [43311316164](https://github.com/vjmichael/nvp_offline_film/actions/runs/43311316164) and [43311316271](https://github.com/vjmichael/nvp_offline_film/actions/runs/43311316271). These attest the visible WebView2 and installed automation slice only; they do **not** attest an owner-approved production upgrade.

## 1. Production-only upgrade authority and rollback

- The previously accepted Windows NSIS filesystem matrix deliberately used a fake creator-consent lambda and a fabricated `windows-job-object` receipt. Those are expressly TEST-ONLY. A string-tagged receipt does not prove a kernel Job handle and is insufficient for production.
- `tools/nvp_w1g_production_authority.py` adds **WindowsCreatorUpgradeApproval** (real native MessageBoxW, exact canonical operation and SHA identities, default NO, one-use scope) and **WindowsReleaseWorkerStopEvidence** (original WindowsJobProcess retained Job HANDLE, kernel ActiveProcesses==0, all explicitly supplied worker workspace leases held for the entire program transaction, and fail-closed journal scans).
- `NativeNSISActivation` now requires those exact authority types in production, an externally supplied pinned 32-byte reviewer key, and a signed redistribution review. The worker-host admission leases stay held across both native checks, the creator decision, and the atomic program renames. It cannot turn a CI Boolean into production admission.
- `tools/nvp_w1g_production_rollback.py` implements a separate production rollback that never calls the legacy simulated stopped-workers callback. It verifies active and previous program SHA, original films, OS Job/worker journal state, native consent, program-only parking/restoration, registry reconciliation, and retains failed artifacts. An interrupted operation remains **uncertain** and requires fresh owner review; it never auto-replays consent.
- `OwnedNSISRecovery` rejects bare synthetic authorization/worker-stop callbacks by default. Its older `rollback/recover_stranded_previous/reconcile` mutation paths are now explicitly **test-only**. Filesystem matrix tests pass `test_only_simulation=True`; they continue to report `human_authorization_real=False` and `kernel_worker_tree_evidence_real=False`.

**Not accepted:** the original release-wide Job HANDLE must be wired to *every* original filmmaker/editorial worker domain, not merely one sampled worker. Complete host registration, restart kernel handle continuity, physical Windows owner consent, power-cut restart/locked executable, and high-risk rollback recovery still require genuine installed acceptance. A kernel Job count without complete launch-domain coverage is not automatically production authority. Source boundary is present; there is no claim a real owner machine has used it.

## 2. Native-worker/offline dependency redistribution review

- Existing native worker roster still requires compiled amd64 PE/ELF binaries and exact SHA-256, source-only placeholders are not accepted. Additional checks reject case-insensitive duplicate worker filenames, reserved device names, drive-qualified names and symlinked internal worker directories.
- Offline dependency admission now checks wheel archive paths, symlinks, case-folded duplicates, Windows-drive entries, archive member count and expanded byte bounds before pip receives a locally hashed wheel.
- New `tools/nvp_w1g_reviewed_release.py` independently validates an **Ed25519 signature** over the entire exact release byte inventory, using a pinned reviewer public key supplied from outside the package. The signed statement includes explicit SPDX/license and redistribution references **for every installed artifact**. Neither an unsigned self-reported license flag nor a signed attestation for a different package is accepted.
- The production upgrade path verifies the signature each time. The build receipt's own `redistribution_licenses_verified` flag is NOT trusted. Missing key, missing signed review, incomplete worker roster, absent binaries, corrupt wheels or missing native cryptographic verification all fail closed.

**Not accepted:** No actual creator-reviewed signed license inventory, external reviewer public key, real PE/ELF worker roster, pinned platform-specific transitive wheelhouse, publisher signing or legal redistribution approval was supplied to this engineering branch. These remain **UNPROVISIONED**, not completed.

## 3. Protected original source — genuine EFS staging

- The original Cycles worker wrote plaintext `source.usda` into a persistent worker directory, even when the UI warned that this could expose protected source. A creator warning alone did not encrypt the worker's copy.
- `backend/nvp_w1g_encrypted_source.py` requires native Windows EFS on the dedicated exact job directory, verifies a newly created **nonsecret preflight file** inherits encryption before writing original bytes, and verifies the source, plan and trusted worker script after staging and after the native render.
- The production `NativeCyclesOriginalRenderer` now requires encrypted native scratch **by default**; Windows volumes without EFS and non-Windows paths refuse production source staging rather than silently downgrade. Tests cover fail-closed policy behavior. EFS rejection cleans the source-empty candidate directory, not original film files.
- UI consent explicitly distinguishes EFS-protected native worker scratch from intentionally unencrypted derivative picture/PCM delivery outside the project home.

**Not accepted:** actual owner EFS key availability/recovery, Windows EFS inherited encryption on the creator's physical disk, all downstream derivative confidentiality, source encryption/key-store identity, worker-crash residual cleanup, and full original-film encryption remain separate. This change safeguards the Cycles *worker copy* of the original source; it does not claim the legacy FilmIndex itself is encrypted, or that native Linux protected staging is ready.

## Acceptance status and next work

- **W1-G visible WebView2/automated installed subtask:** CLOSED at previously accepted `46d59d3`.
- **W1-G production authorization/rollback:** SOURCE IMPLEMENTED, production native acceptance OPEN, complete original worker-domain registration and physical power-cut/rollback inspection still needed.
- **W1-G native worker/dependency redistribution:** hardened admission and cryptographic review implemented; actual approved inventories and binaries UNPROVISIONED.
- **Encrypted-source staging:** default Windows EFS gate implemented; full key custody and physical/hardware verification OPEN.
- **INT-02C real 30-second production film, W1-F creator physical/sustained:** OPEN.

No merges, release authorization, signing certificate, creator key, worker binary, or physical acceptance was fabricated. No original Takes were changed, no FFmpeg-primary filmmaking path was introduced and no retired proxy execution was reopened.
