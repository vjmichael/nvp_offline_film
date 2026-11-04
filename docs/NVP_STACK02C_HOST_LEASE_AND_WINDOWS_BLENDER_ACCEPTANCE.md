# NVP-STACK-02C — Exclusive worker ownership and genuine Windows Blender acceptance

**Date:** 2026-11-03  
**Status:** Development work / CI acceptance; the complete Linux cgroup and VRAM gates remain open  
**Architecture:** [STACK-001 reuse-first](NVP_ADR_STACK01_REUSE_FIRST_AND_ONE_INSTALLER.md) · [STACK-002 Blender worker](NVP_ADR_STACK02_BLENDER_WORKER_USD_DEFERRED.md) · [STACK-02B OS containment](NVP_STACK02B_OS_WORKER_CONTAINMENT.md)

## Purpose

After STACK-02A established a durable, independently checked external Blender worker and STACK-02B proved OS process containment, two production risks remained:

1. Two NVP desktop host instances might access the **same** durable journal and one might falsely reconcile the other's actively running Blender process as INTERRUPTED.
2. STACK-02B tested **real Windows Job Objects** with Python worker processes, but the original Blender 5.2.3 executable and authored NVP scene were only run on Linux. A genuine Windows Blender renderer/audit is a separate gate.

STACK-02C protects the shared worker journal using standard **kernel filesystem locks**, and it runs actual Blender Windows portable 5.2.3 (SHA-checked against its official release manifest) through the **same** approved scene/independent-audit and OS Job Object pipeline. No new 3D renderer or custom process-control algorithm is introduced.

## Cross-process worker-owner lease

`backend/nvp_worker_host_lease.py` uses the stdlib OS facilities `fcntl.flock(LOCK_EX|LOCK_NB)` on Linux and `msvcrt.locking(LK_NBLCK)` on Windows. The fixed `worker_host.lock` file is never deleted while active. This is a true kernel lock, **not a PID file**, best-effort time-based lease, or a hand-managed heartbeat that can expire during a slow render.

`BlenderWorkerSupervisor.run` and `BlenderWorkerSupervisor.recover_interrupted` both own this same exclusive lock **from entry to completion**:

- A live worker from another NVP instance cannot be claimed, launched over, or reclassified as interrupted.
- If the host crashes via `os._exit` (or a genuine process exit), the kernel releases its lock automatically; a successor may then reconcile stale jobs as INTERRUPTED, never SUCCEEDED.
- Rejected second hosts do not execute Blender scripts or modify the journal; read-only inspection and independent SHA validation remain possible.
- Acquiring this lock for the whole job **intentionally serializes Blender worker operations in a workspace**. Parallel workers require an explicit task/job-scoped coordinator, not accidental concurrent host ownership.
- Tested on one machine with local filesystem semantics. Network shares, distributed machines or modified clients bypassing this protocol are **not supported**.
- A kernel lock is not a replacement for cancellation or crash containment: STACK-02B remains responsible for those processes.

## Real native Windows Blender package and provenance

The native Windows acceptance downloads `blender-5.2.3-windows-x64.zip` and its official `blender-5.2.3.sha256` from `download.blender.org/release/Blender5.2`, rejects a checksum mismatch, extracts the portable application into the CI workspace, and identifies the **real** Blender executable. The independently pinned executable SHA-256 and exact Blender version are then checked again by the worker supervisor before running scripts.

This is a **test-only pinned downloaded binary**. The official GPL Blender executable is not copied into the proprietary NVP source tree or claimed to be legally redistributable in the future retail installer. Windows Job Objects launch Blender suspended, establish job membership and memory limit before resuming, and prohibit uncontained fallback.

`tools/nvp_stack02a_worker_fixture.py` exercises the existing genuine Blender source/preview/audit path and the original `ProductionScene` source → Blender scene build → independent reopen/geometry check. The same fixture runs on Linux through kernel PDEATHSIG. The accepted Blender-side Python adapter is kept narrow and separately subject to GPL script/license review.

### Headless Windows renderer compatibility

The first official Windows portable Blender native run reached the real Blender script and wrote a `.blend` file, then crashed with `EXCEPTION_ACCESS_VIOLATION` while its **Workbench** preview renderer initialized a WGL/OpenGL context on the GPU-less GitHub Windows runner. The observed stderr includes repeated `WGL_ARB_extensions_string` failures. This does **not** prove a Job Object crash or renderer independence.

The fixture and existing independent scene audit now select **Blender's native Cycles CPU renderer** on Windows only, with a one-sample smoke-test configuration; Linux retains Workbench for the previous exact fixture. This is still native Blender rendering. A GPU-capable, high-fidelity Windows workstation/Cycles run must be tested separately before claiming final movie visual quality.

## Test matrix

| Lane | Required evidence |
| --- | --- |
| Linux cross-process lease | Genuine competing Python process; refuse active foreign lock; release after hard `os._exit`; existing OS containment and six durable-worker regressions |
| Windows cross-process lease | Same genuine lock, crash release and exclusive recovery refusal; Windows suspended Job Object worker+grandchild termination and memory enforcement |
| Windows native Blender | Official SHA-matched portable Blender, real Job Object child, two independent `bpy` source/audit processes, actual scene/PNG, 9 original geometry/identity checks, cancellation, hash tamper and restart |
| Linux native Blender | Existing approved NVP scene + independently reopened/audited real Blender worker under the new exclusive lease, original source-preservation tests |

**A green Windows Job Object Python test is not evidence that the native Windows Blender scene passed.** Keep native artifact and job logs distinct.

## Explicit open production gates

- **Linux whole-tree crash cleanup:** direct `PR_SET_PDEATHSIG` does not kill detached grandchildren. A delegated cgroup v2 or a properly supervised OS guardian/cgroup manager with *actual multi-level descendants and hard-host-crash* acceptance is required. This is **STACK-02C2**, not implicitly solved by a worker lock.
- **RAM/VRAM system protection:** Windows Job committed-memory and Linux RLIMIT_AS are different resource policies, not proven VRAM budgets. Add host free-memory preflight, conservative device-specific VRAM allocation and safe queue backpressure before high-resolution renders.
- **Windows hardware renderer:** the acceptance runner has no real GPU device; separate an actual GPU/Cycles grading and high-fidelity test from this CPU-only CI proof.
- **All Blender production routes:** migrate rendering, animation, character retarget, full-motion capture and media finishing paths to the same supervisor once direct call-site inventory is complete. Source/take authorization and effect custody must remain intact.
- **Installer and GPL:** one-click offline bundle, pinned full Blender artifact, notices/source offers, LGPL/GPL review, install/uninstall, update strategy and secure UAC/runtime worker directories remain separate STACK-01E acceptance.
- **Multi-machine/distributed storage:** single-host local filesystem lease is not a global distributed lock.

The user-facing NVP editor remains the unified product. Blender is a separate licensed production engine, never a library linked into the proprietary core.
