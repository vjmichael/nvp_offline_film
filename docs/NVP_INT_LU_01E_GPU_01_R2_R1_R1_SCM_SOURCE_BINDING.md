# NVP-INT-LU-01E-GPU-01-R2-R1-R1 — One original SCM LTX Job source seam

Date: 2026-11-21. **Source correction prepared; exact successor native CI and physical installed-positive NOT RUN.** No new task, PR, branch, Lu Core modification, installer key, or positive GPU receipt.

## Current qualified predecessor

- Existing PR #161 branch `nvp/mainline-convergence-20261113` at `895e5f17f176233e9df88ab675bba2fa3e08cc6c`.
- Same-SHA native IPC source/prost: [Windows and Ubuntu PASS](https://github.com/vjmichael/nvp_offline_film/actions/runs/44953629177); protected provider [both PASS](https://github.com/vjmichael/nvp_offline_film/actions/runs/44953629031); original native SCM/CNG compile and unapproved-start denial [Windows PASS](https://github.com/vjmichael/nvp_offline_film/actions/runs/44953635168).
- Prior GPU R2 exact-source Windows/Ubuntu [PASS](https://github.com/vjmichael/nvp_offline_film/actions/runs/44950451332) applies to `4a4efe5`, not the prepared successor. Other film suites are independent regression gates.
- Exact Lu source pin remains commit `60afe6908a6abe3408bb952869d85b43781313ca`, `workspace.proto` Git blob `747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1`. No synthetic Lu fixture is production authority.

## Confirmed defect and prepared minimal repair

`ProtectedLtxHandoff.run(preallocated_job_id=...)` accepted a preallocated LTX ID but still called the separate Python `launch_contained` AppContainer/Job launcher. The native CNG GPU-empty receipt issuer proves only the original separate Windows SCM Job. A matching text ID does **not** prove they are the same kernel Job. The native service also ignored SCM stop controls, preventing an owner-authorized cancellation from cleanly requesting this Job to drain.

Prepared source changes, without changing standalone/creator/audio policy:

1. In Lu-connected mode, require an installed native SCM start/cancel owner and the **exact protected machine ProgramData/NVP/POST01F/ApprovedJobs** stage and original C++ service memory/deadline. Stage source digests, immutable Take, creator scope, approved job and plan; **do not call Python `launch_contained`**. Standalone mode continues to use its original AppContainer/Job launcher.
2. `WindowsNvpGpuSupervisorBinding` passes the original user-turn `YieldIntent` into its independently installed owner for both SCM start and cancellation; reuses the same `intent.native_job_ref` already verified and reserved before asking Lu to yield VRAM. Native owner must implement `run_original_scm_ltx_job(intent,source_scope)` and `cancel_original_scm_ltx_job(intent,job_id)`, not a UI supplied callback.
3. Source-only SCM kernel-result shape requires exact job/project/plan, positive worker PID, exact native SID hash, source-reported SCM-owned Job empty and fence closed. These values are **only hints until** the existing fixed-installed CNG P-256 receipt verifier validates scope, PID, SID and nonce; the protected NVP/Lu GPU journal independently verifies release.
4. Original Windows SCM C++ service accepts STOP only through SCM, cooperatively ends its bounded wait, terminates its actual Job group, waits for `ActiveProcesses==0`, then issues the independently validated native GPU worker-stop receipt **even on job failure or cancellation**. No picture success on cancel; no GPU all-clear from service STOP alone.
5. New `test_nvp_int_lu_gpu_scm_owned_r1.py` exercises mismatched original job/plan/project/PID/SID, missing Job custody, uninstalled stage and original SCM STOP/source-order denial. The existing GPU native workflow is scoped to run those checks and native Windows compilation on the exact successor.

## Still unproven / mandatory physical Windows acceptance

- The installed OS-owner implementation that actually seals the original creator/SCM registry grant, reserves the exact job before Lu unload, starts/observes the fixed SCM service and accepts authenticated STOP is **not supplied** by these source contracts. Do not call a Python callable proof of SCM ownership.
- Actual installed Windows NSIS/SCM service name/image/configuration and protected private CNG machine key + Lu verifier pin are required; neither is provisioned here.
- Native physical R9700 driver VRAM samples, signed Core GRANTED/RESTORED receipts, real CNG stop receipt + Job kernel zero + all GPU contexts drained, actual LTX/PCM and post-restart original operation reconciliation remain **OPEN**. Cancel, failure, crash or unknown worker state must preserve UNCERTAIN and Lu no-reload fence until independent evidence.
- A CI Windows MSVC/source-negative pass is not signed installed positive proof. Only publish a single non-forced exact-SHA successor after the already running CI batch is terminal; do not stack 47 PR checks, merge main or weaken security gates.

**Next within same task:** independently inspect exact-successor Windows MSVC, Windows/Ubuntu IPC/prost/GPU negative suite and service STOP ordering; correct only confirmed failures. Then obtain genuinely installed trusted SCM owner implementation and physical R9700 Lu→NVP→Lu acceptance.
