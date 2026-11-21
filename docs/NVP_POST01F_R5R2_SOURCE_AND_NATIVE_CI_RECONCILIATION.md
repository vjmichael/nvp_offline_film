# POST-01F R5-R2-R1 — source-locked W1-G/Windows CI repair

Status: reviewable consolidated candidate. **Native acceptance remains open.**
Original source commit: `fba82b38aed7d0068c8db84d8261fde1d9b3357e`
Original PR: #161, sole convergence branch `nvp/mainline-convergence-20261113`.
Engineering issue: #162. No new branch, pull request or manually dispatched CI.

## Original CI findings, not inferred from synthetic tests

The original 45 PR-source GitHub Actions workflows exposed two independent regressions:
- `INT-02C/W1-G` #44860163965 and Gate 1 #44860164917: original W1-G launch-surface audit refused three new direct `subprocess.run` calls: 2 inside the LTX worker, 1 in the desktop independent media verifier.
- Dedicated Windows SCM/CNG #44860170995: 69 source tests passed, one failed on equivalent Windows 8.3 short/long filesystem paths; the MSVC/CNG compile was **skipped**, not passed or failed.

## Consolidated source repair

- Source-pin the **entire** revised LTX broker Git blob and the two exact FFmpeg/ffprobe call ASTs in the original W1-G launch audit. Preserve original general subprocess denial, retired source rules and G03 ACL pinned hash. The two calls require native Windows AppContainer token and Job membership before they execute; these self-checks do **not** prove SCM process ownership.
- Run desktop independent FFprobe/FFmpeg through original `backend.nvp_w1g_owned_subprocess.run_owned_subprocess` with a matching *actual original API signature*, preserving original bounded memory pipes, suspended Windows Job and release fence. No unregistered direct desktop subprocess is allowed.
- In the lock-reconciliation test, use `Path.samefile` to compare original file identity rather than Windows short/long path spelling. Keep binary/model hashes intact.
- Add source-contract tests for exact process-call count, native lowbox gate, W1-G signature and Linux refusal. No fixture-only no-WFP bypass.
- Do not permit a caller-provided executable or spoofed SCM positive report. Windows SCM ownership, CNG private key ACL, installer EFS, lowbox/WFP network denial, EFS ciphertext readback and filmmaker review still require genuine installed acceptance.

## Qualification definitions

Portable source candidate: Python compile and 75 tests pass on Linux with a **local test-only shim** matching the original W1-G public API for the absent original subprocess module. Real FFmpeg media boundary is exercised on synthetic test footage. This is **not** original W1-G audit, native Windows custody or R9700 model execution.

Required original qualification: execute the unchanged original `test_nvp_w1g_launch_surface_audit.py` plus all existing source/native workflows from a genuine checkout of one **new** reviewed branch SHA, including both Windows and Linux W1-G; obtain real MSVC/CNG compile and absent-approval SCM denial. Do not run another candidate while current CI is active.

## Still open

- Positive installed Windows SCM-owned AppContainer/Job/WFP and machine CNG signing after one-use creator authorization.
- Installed DPAPI/EFS derived picture publication, private creator review/approval/rejection/reopen and original PCM preservation.
- Full exact R1/R2 source reconciliation, licensed LTX model loading and physical Radeon AI Pro R9700 generation with authentic preview images.
- CONV-12/13/14 and all original release/continuity gates before mainline merge.
