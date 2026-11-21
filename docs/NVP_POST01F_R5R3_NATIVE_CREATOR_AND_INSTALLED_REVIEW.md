# POST-01F R5-R2-R3 — native creator signoff and installed film-review gate

Status: native Windows creator CMS source and negative qualification prepared. Positive installed SCM signing, real encrypted filmmaker UI and physical LTX generation OPEN.
Source baseline: existing draft PR #161 at c0541502fcf47a741f5b3714ad25c5d1bd23a443; do not publish while its 45-run cohort is active.

## Unchanged-source CI
At investigation, 40/45 original PR-head workflows passed with no failures; CONV-06, CONV-12, WO3, WO4 and DATA-AV-01 were still running. Exact-head W1-G / INT-02C, Gate 1 and Windows SCM/CNG compile plus unapproved SCM/direct-launch refusal passed.

## New native implementation
tools/nvp_post01f_windows_ltx_creator_signoff.cpp implements a standalone visible native Yes/No creator action for one exact LTX picture job. It requires an installed HKLM source approval, one-use ticket, exact plan/project/job/model/input digests, a separate pinned independent user certificate with private key, and a 15-minute expiry. It signs the SAME nvp_post01f_creator::message(scope) detached CMS contract checked by the LocalSystem SCM signer; writes only one CREATE_NEW EFS CreatorApprovals/<job>.p7s in the fixed installed protected inbox; rejects missing trust, unapproved flags, replay, expired or foreign source, missing certificate and failed EFS. No automatic model or CLI creator approval, no original Take/audio modification. A picture is NOT approved merely because generation is authorized.

tests/test_nvp_post01f_r5r3_native_creator_signoff.py pins source invariants. The original Windows SCM/CNG negative workflow was extended to genuinely MSVC-compile this exact native creator-signoff source and refuse both flag-driven and missing-admin-trust invocation before continuing its ORIGINAL SCM negative tests. This is source and denial qualification, not a real positive CMS signing event.

## Real installed positive qualification still required
1. An independently reviewed native installer must provision immutable ProgramFiles NVP/LTX binary/model/runtime digests; HKLM admin one-use grant; CreatorTrust certificate pin; nonexportable user creator signing key; nonexportable machine ECDSA P-256 CNG signer with service-only private-key ACL; and actual EFS ApprovedJobs, SpentTickets, CreatorApprovals and SCMReceipts directories with appropriately restrictive creator/SYSTEM EFS access. The existing PowerShell machine-key provisioning is source-only; it has not been installed.
2. A physical Windows filmmaker must explicitly click Yes for one approved, source-bound visual job in the new native creator window. Denial/default-No, certificate drift, expired approvals, logout, replay, missing EFS rights and original source drift must be observed, not simulated.
3. The real SCM service must verify the detached CMS, consume the one-use HKLM/spent-ticket grant before starting, own the suspended AppContainer process and nonbreakaway Job/WFP four filters, prove zero network and unauthorized file access, drain all descendants, verify exact EFS picture and source/model hash, and issue a signature via the SYSTEM-controlled CNG machine key. Test cancellation, sidecars, source modification, signer denial, crash/restart and stale tickets.
4. The installed trusted host must use a reviewed authenticated SCM receipt channel (not a worker-provided dictionary). Existing backend/nvp_post01f_scm_cng_v2.py verifies strict canonical P1363 ECDSA, HKLM public pin and durable G03 nonce, but InstalledScmCngV2Channel still requires a real OS-installed transport and independent custody input; it is not sufficient by itself.
5. Existing EncryptedLtxReview backend can seal derived picture into original project-key AES-GCM and authenticated G03 SQLite HEAD, then provide a separately authenticated preview/approve/reject/reopen. A real trusted Windows UI/IPC and on-disk EFS/DPAPI end-to-end qualification are still absent. Never show a synthetic picture as LTX output, expose plaintext via a public URL, automatically approve or modify the original actor PCM.
6. Genuine licensed LTX 2.5 generation on physical Radeon AI Pro R9700, authentic visual samples, historical R1/R2 source reconciliation and all original acceptance gates remain open.

## Publication gate
Wait for terminal dispositions of all 45 predecessor CI runs. Only then, if PR #161 has the exact source head, advance one reviewed non-forced SHA; inspect original W1-G/Windows SCM/CNG workflow and new native creator source compile+negative test on genuine GitHub Windows. No stacked CI, no new PR/branch or mainline merge.
