# NVP-STACK-02C2 — Delegated Linux cgroup v2 and real descendant cleanup

**Engineering date:** 2026-11-03  
**Status:** **STRICT, OPT-IN CGROUP TECHNICAL ACCEPTANCE PASSED** — [GitHub run 41769499518](https://github.com/vjmichael/nvp_offline_film/actions/runs/41769499518): 4/4 jobs, including 4/4 real delegated cgroup tests and genuine Blender 5.2.3 under a strict cgroup. Production-by-default enablement, GPU/VRAM admission, installer and GPL release review remain open.  
**Related:** [STACK-02C host lease + Windows Blender](NVP_STACK02C_HOST_LEASE_AND_WINDOWS_BLENDER_ACCEPTANCE.md) · [Reuse-first ADR](NVP_ADR_STACK01_REUSE_FIRST_AND_ONE_INSTALLER.md) · [Blender worker ADR](NVP_ADR_STACK02_BLENDER_WORKER_USD_DEFERRED.md)

## Why the previous Linux implementation was insufficient

The earlier Linux `PR_SET_PDEATHSIG(SIGKILL)` plus `killpg` correctly protected the **immediate** Blender worker on a hard NVP host crash and cleaned up same-process-group children during normal cancellation. It did **not** guarantee cleanup of grandchildren that called `setsid()`, changed their process group, or otherwise outlived the Blender parent.

Kernel **cgroup v2** solves that process-tree identity problem: a worker that enters a cgroup before `execv` passes membership to its descendants even when they change sessions. Writing `1` to the **kernel `cgroup.kill`** file kills all processes in the cgroup subtree, with fork/migration protection. This is an established Linux mechanism, not a new NVP process-scanning algorithm.

Authoritative documentation: [Linux kernel cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html) · [systemd cgroup delegation](https://github.com/systemd/systemd/blob/main/docs/CGROUP_DELEGATION.md).

## New strict worker mode

`BlenderOperation.require_linux_cgroup_v2=True` is an explicit, source-hashed job-level requirement. Under this mode the existing contained Blender supervisor:

1. Discovers its current cgroup through `/proc/self/cgroup`, walks to the **systemd-marked `user.delegate=1`** scope and never creates files inside an unowned systemd hierarchy.
2. Requires `memory` and `pids` kernel controllers, enabling them **only within the already delegated NVP scope**; requires `DelegateSubgroup=` (or equivalent manager layout) so the host process is not in the internal controller node.
3. Creates a unique `nvp-worker-<128-bit UUID>` leaf, applies a bounded `memory.max` and `pids.max=128`, then starts an **independent guardian** outside that leaf. The guardian validates exact NVP leaf ownership and announces readiness over a dedicated file descriptor.
4. Starts the existing pinned Blender executable through a tiny Python exec shim with `PR_SET_PDEATHSIG`, moves the shim into the dedicated worker leaf via `cgroup.procs`, verifies actual `/proc/self/cgroup` membership, signals kernel admission, then calls `execv`. Blender and all of its descendants inherit cgroup membership; no image/geometry algorithms are modified.
5. Retains an exclusive cross-instance journal lease, immediate-worker cancellation and all previous content hash/FilmIndex verification. On normal job completion or cancellation, host closes the unique guardian pipe.
6. If the NVP host exits **abruptly** (including `os._exit`, where no Python `finally` code runs), the kernel closes the pipe writer. The independent guardian sees EOF and writes `1` to the leaf's `cgroup.kill`, waits for `cgroup.events: populated=0`, then removes the empty leaf.
7. The supervisor **does not store `SUCCEEDED`** until the guardian has proved cleanup. A dead guardian, missing delegated controller, ambiguous membership, wrong source SHA or unexpected cgroup state is a failure, never a quiet fallback to ordinary process-group containment.

**Key distinction:** Windows Job Objects already proved child/grandchild cleanup in STACK-02B and real Blender operation in STACK-02C; Windows uses that unchanged engine. Only Linux strict mode uses this new cgroup machinery.

## Technical acceptance protocol

- A real Linux 64-bit kernel with **delegated writable cgroup v2**, available `cgroup.kill`, `memory.max` and `pids.max` is mandatory for actual tree proof.
- Use the standard systemd user service/scope `Delegate=yes` and `DelegateSubgroup=nvp.host`, or a user session equivalently managed by the administrator. NVP must not request sudo or attempt to create cgroups in arbitrary systemd-managed parent directories.
- The acceptance test launches a real host process and real worker which spawns a **detached, new-session grandchild**. The host calls `os._exit(27)`. Both worker and grandchild must cease running and guardian must remove the leaf. A separate test checks that a worker exiting *normally* does not leave its detached child behind.
- Fail-closed tests must prove that missing delegated controllers **block** strict launch. The legacy PDEATHSIG fixture may continue in normal engineering CI for regression, but a green legacy test is **not proof** of strict full-tree protection.
- Legacy persisted journal specifications remain readable: verification hashes the original stored serialized spec before applying new dataclass defaults, so adding the strict mode flag does not silently invalidate source receipts.
- Windows CI continues all native Job Object/host-lease/worker tests; Linux native Blender baseline still proves source geometry/renderer. Final NVP release must test the actual Blender binary *within a delegated strict cgroup*, not only the synthetic detached-grandchild fixture.

### What if the CI runner does not grant delegation?

The production worker **refuses** a strict operation. The delegated test job is reported **BLOCKED / FAILED** (non-gating exploratory CI lane); it cannot be interpreted as passed. GitHub-hosted runners might not provide the required delegated controllers, even if a cgroup v2 mount is present. The engineering team must provide a properly delegated runner/user service and run the same test with `NVP_REQUIRE_REAL_CGROUP=1`. **Do not call STACK-02C2 complete on a runner that skipped these tests**.

## Recorded real acceptance — measured independently

**Four GitHub CI jobs passed in [run 41769499518](https://github.com/vjmichael/nvp_offline_film/actions/runs/41769499518)**:

- **Real delegated Linux user scope:** `systemd-run --user --scope --property=Delegate=yes --property=DelegateSubgroup=nvp.host` provided a genuine writable delegation and allowed `memory` and `pids` controller enabling. Four strict tests passed **without skips**. In particular, a real worker spawned a **detached grandchild** with a different session, the real host exited via `os._exit(27)`, and the independent guardian's `cgroup.kill` stopped both. A second test proved normal worker exit also cleans the detached descendant. A forged foreign cgroup and missing delegation were refused.
- **Real Linux Blender 5.2.3:** NVP rendered the *same production fixture twice*: the previous legacy PDEATHSIG profile and a new **`strict_linux_cgroup_tree_mode=true` profile**. The strict one produced a real 128×72 PNG and .blend, ran the approved NVP source stage and the independent second-process Blender geometry audit (**nine checks**), independently reopened its source and outputs, rejected a bad script and output tampering, and successfully cancelled another real Blender worker. All applicable operations passed inside a delegated cgroup leaf with an out-of-tree guardian.
- **Windows:** all **14** historical Job Object, host lease and durable worker tests passed unchanged. Windows continues using its already accepted Job Object child/grandchild OS guarantees; no Linux cgroup code is executed there.
- **Normal Linux runner (outside systemd delegation):** verified strict delegation refusal and all previous contract regressions. The two kernel tests rightly skip **outside delegation**; that is NOT the separate strict-scope test, which ran and passed independently.

**Native artifact:** `nvp-stack02c2-native-baseline-real-blender` in the GitHub run contains both full separate FilmIndex/SQLite worker trees and reports. The ZIP was downloaded and independently checked: **58 entries and no CRC errors**. The strict report records `strict_linux_cgroup_tree_mode=true`, independent approved stage status `passed_blender_supervised`, `audit_checks=9`, original output corruption refusal and cancellation/restart evidence. The strict production demo's rendered .blend SHA-256 was `c9df3e8630ce358d78f8057a45d27ae8d62031b6c348488b6a35db96ab197c80`; PNG SHA-256 `24874f75c8be49e4edcfaee60dd6a81efb0b2b9ddc6ff7425c36d4261fc2ba82`. The original immutable scene/geometry lineage remained intact.

**Follow-up hardening:** Source change after this run also moves the **strict Blender `--version` probe** into the same kernel cgroup, avoiding an uncontained Blender process before the main render. Its final revision CI is tracked separately; only call that change accepted after its native strict rerun is green.

**Scope distinction:** The real hard-crash test uses a process that deliberately spawns an escaping descendant. The real Blender test separately proves Blender uses the strict profile, original geometry audit and resource bounds. The native Blender acceptance report's historical `orphan_cleanup_after_real_host_crash_proven=false` field refers to the Blender fixture alone; the separate real kernel test **does** prove detached-grandchild cleanup. It would be misleading to conflate them or claim an actual Blender-specific host-hard-kill was simulated.

## Next release requirements

- Switch every production Blender/Cycles/animation operation to the strict cgroup requirement on supported Linux deployments, and add appropriate systemd user-service delegation and worker health UX.
- Repeat with **a real pinned Blender worker that deliberately launches a detached descendant** and a genuine hard NVP host kill in one combined scenario. Kernel detached-process cleanup and strict Blender execution are independently proven above; this combined Blender-specific crash replay remains an extra release gate.
- Keep a conservative host-wide RAM/VRAM admission policy: cgroup `memory.max` controls system memory, **not VRAM** or driver allocations.
- Test cgroup cleanup after failed Blender scripts, cancellation, timeouts, SIGKILL to the host, system shutdown and competing NVP hosts.
- Preserve the one-installer, GPL Blender side-script/license, source notices and offline-application constraints before retail distribution.

This design does not depend on Docker or an NVP-specific custom kernel module.
