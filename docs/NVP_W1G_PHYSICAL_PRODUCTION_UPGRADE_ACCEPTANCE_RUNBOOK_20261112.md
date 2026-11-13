# W1-G physical production-upgrade acceptance — owner runbook

**Implementation checkpoint: 12 November 2026. No physical Windows release, license permission, EFS key recovery or creator approval is claimed by this document.**

This runbook begins only after the exact-head **native** and **automated installed NSIS** workflows pass. Those workflows are developer tests, not creator authorization. These operations must occur on the creator-controlled Windows installation, outside CI, and must never be invoked by Lu/model/browser automation.

## 1. Supply inputs before any mutation

The owner/reviewer must separately provide:

- A *compiled*, hash-matched Windows amd64 PE worker for **all five** original roles: `original_capture`, `scene_render`, `editorial`, `audio`, `delivery`. Test stubs and one worker used for five roles are refused.
- An offline platform-locked, SHA-pinned complete wheelhouse. `tools/nvp_w1g_native_dependencies.py verify` validates a reviewed lock without contacting PyPI. `provision` writes to an unused private runtime; it must not be pointed into creator originals.
- A staged real NSIS `NVP.pending` release whose audit receipt enumerates each exact installed byte, native worker manifest and release custody marker. No binary may be altered after the build receipt and review signature.
- A genuine external signed per-artifact redistribution/license review; the independent Ed25519 **public** key is pinned outside program, film, journal and worker workspace roots. No reviewer private signing key is generated, imported or requested here. Test-generated signed reviews are not legal redistribution approval.
- A pre-existing `NVP` installation with the required build marker, distinct later candidate version, matching Windows registration, original film inventory, and all five real journal/workspace paths.

Example verification against owner-provided, reviewed artifacts (placeholders are not files NVP supplies):

```powershell
py -m tools.nvp_w1g_worker_package verify --bundle "D:\Programs\NVP.pending" --platform windows-amd64
py -m tools.nvp_w1g_native_dependencies verify --platform windows-amd64 --lock "D:\OwnerEvidence\wheel-lock.json" --wheelhouse "D:\OwnerEvidence\wheelhouse"
```

Do not treat a successful package/lock verification as proof of executable worker operation or redistribution rights.

## 2. Physical EFS and key-recovery acceptance

Use the actual Windows account and same storage volume intended for original source staging. The disposable fixture writes **only nonsecret randomized test bytes**. Choose an owner-approved EFS-capable volume and a receipt outside the test stage:

```powershell
py -m tools.nvp_w1g_windows_efs_proof prepare --parent "D:\ProtectedScratch" --receipt "D:\OwnerEvidence\w1g-efs-test.json"
# Sign out/restart Windows, then independently reopen the original test.
py -m tools.nvp_w1g_windows_efs_proof reopen --receipt "D:\OwnerEvidence\w1g-efs-test.json"
```

The `reopen` command now refuses the same Windows boot: a distinct, conservative native boot-time observation and encrypted-file reopen are both required. A changed wall clock can affect the estimate, so this is **not** independent physical-owner authentication or key recovery evidence. It does *not* prove that the owner has independently backed up and restored the EFS certificate/private key. The creator must verify that recovery separately through their OS-approved secure backup/recovery process. Never upload private EFS keys, decrypted films, or recovery secrets to GitHub, a model, or a CI artifact.

Original Windows filming PCM now stays in bounded RAM by default. Long recordings must provide a dedicated `encrypted_pcm_scratch` directory admitted by `require_efs_stage` before PCM is written; an ordinary system temp spill is denied. Original FilmIndex key custody, derivatives and full-project encryption remain independent requirements.

## 3. Non-mutating native owner preflight

Run **on the real Windows installation** with the installed GUI closed. `--journal` names a durable **directory**, not a JSON file. Supply **all five distinct** original worker workspace directories using repeated `--workspace` arguments.

```powershell
$common = @(
  '--programs','D:\Programs',
  '--original-films','D:\NVPOriginalFilms',
  '--journal','D:\OwnerEvidence\NVPUpgradeJournal',
  '--workspace','cycles=D:\NVPJobs\cycles',
  '--workspace','filming=D:\NVPJobs\filming',
  '--workspace','editorial=D:\NVPJobs\editorial',
  '--workspace','audio=D:\NVPJobs\audio',
  '--workspace','delivery=D:\NVPJobs\delivery'
)
py -m tools.nvp_w1g_owner_windows_acceptance preflight @common --reviewed-receipt 'D:\OwnerEvidence\reviewed-build.json' --pinned-reviewer-public-key 'D:\ExternalTrust\reviewer-ed25519.pub'
```

`preflight` independently re-verifies exact staged bytes, signed review, all five real native executables, film inventory, installed version and real release-wide Windows kernel custody under held worker leases. It **never** writes an upgrade journal or invokes a creator approval dialog. It releases its Job/lease locks immediately afterward. Its result is **not reusable** as authorization: activation must remeasure the actual OS and obtain fresh native consent.

The NSIS program root, original-film root and upgrade-journal root must be pairwise disjoint, even when Windows resolves directory aliases; never store a production journal inside an original-film tree. An old or interrupted activation journal also blocks a fresh preflight.

If provisioning is absent, source bytes differ, EFS is unsupported, journal recovery is uncertain, a worker survives, or the reviewer key is not externally pinned, stop. Do not weaken the guard to pass.

## 4. One-use owner approval and real upgrade/rollback

Only after the preceding evidence and separate EFS/key-recovery review pass, the owner may individually choose to execute:

```powershell
py -m tools.nvp_w1g_owner_windows_acceptance prepare @common --reviewed-receipt 'D:\OwnerEvidence\reviewed-build.json' --pinned-reviewer-public-key 'D:\ExternalTrust\reviewer-ed25519.pub'
py -m tools.nvp_w1g_owner_windows_acceptance activate @common --pinned-reviewer-public-key 'D:\ExternalTrust\reviewer-ed25519.pub'
```

The preparation gate now checks independent signed review **before** writing its journal. Activation re-verifies it, holds all five original leases plus release-wide kernel admission, prompts the owner with exact SHA/version scope (default NO), rechecks the original film identities, and preserves `NVP.previous`. An activated release remains `PROMOTED_UNACCEPTED` until physical installed, rollback/restart and filmmaker evidence are independently reviewed.

For a separately authorized rollback of this exact promoted candidate:

```powershell
py -m tools.nvp_w1g_owner_windows_acceptance prepare-rollback @common
py -m tools.nvp_w1g_owner_windows_acceptance rollback @common
```

Read-only `inspect` and `inspect-rollback` actions do not require the reviewer key. On interrupted rename, registration mismatch, power loss, unresolved original worker Job journal, lost EFS access or other ambiguous state, **inspect first**. Never replay an old approval, delete `NVP.failed`, purge original films, forge a kernel receipt, or automatically resume an uncertain mutation.

## 5. Required acceptance ledger

Record actual owner-machine evidence separately:

1. Native exact-head Windows/Linux source and Cycles tests, plus installed NSIS/WebView2/film reopen automation (exact commit and native logs).
2. Actual complete five-role native worker and SHA inventory, offline wheelhouse and license review signed by a real external reviewer.
3. EFS disposable test after restart, **independent EFS recovery backup** inspection, and original source/derivative confidentiality policy.
4. Real owner modal decisions, genuine original Windows Job-process tree emptiness and no unresolved domain journals, precise program/film hashes before and after activation.
5. Physical NSIS version/registration, installed GUI and original USD/PCM reopen, interrupted installation and rollback with preserved `NVP.previous`/`NVP.failed`, and repeatable restart recovery.
6. W1-F human filmmaker assessment and sustained 30-minute-to-feature production separately; automated film-source audit is not acceptance of a finished movie.

**Current classification:** The physical artifacts and owner actions remain **unprovided/unverified** until genuine local execution and reviewed receipts exist. No production upgrade is authorized by a code commit, a green CI workflow, or this runbook.
