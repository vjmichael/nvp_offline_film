# NVP-STACK-02B — OS-enforced external Blender worker containment

**Status:** **OS-containment technical acceptance PASSED** in [GitHub CI 41766014441](https://github.com/vjmichael/nvp_offline_film/actions/runs/41766014441): **3/3 jobs green**; Linux 10 regressions (9 passed, 1 Windows-only skipped), Windows **10/10 passed** including a real hard-host-exit **child+grandchild** check; native Blender 5.2.3 scene and original ProductionScene audit also passed. More extensive production containment and commercial redistribution remain open.  
**Architecture:** [ADR STACK-002](NVP_ADR_STACK02_BLENDER_WORKER_USD_DEFERRED.md); predecessor [STACK-02A](NVP_STACK02A_DURABLE_BLENDER_WORKER_ACCEPTANCE.md).  
**Implementation principle:** standard operating-system facilities and maintained pywin32—not custom process-control mathematics or a new renderer.

## Contract

Every production Blender execution is launched by the already accepted NVP external-worker supervisor from a fixed SHA-verified Blender executable, using pinned script/input hashes and one durable SQLite job ID. The supervisor now requires **OS containment before source processing**. There is **no fallback to plain uncontained `subprocess.Popen`** on unsupported platforms or containment failure.

The typed `BlenderOperation.memory_limit_mb` defaults to 8192 MiB (creator/host configurable between 256 and 65536 MiB), and is part of the immutable job specification hash. Memory limits concern the worker *process/job*, not Blender GPU VRAM. The worker still performs the original native Blender/Cycles operations, while NVP owns authorization, I/O lineage, cancellation, output verification and audit.

### Windows

Uses established [pywin32](https://pypi.org/project/pywin32/) bindings to native Windows APIs:

1. Configure a unique Win32 Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and `JOB_OBJECT_LIMIT_JOB_MEMORY` prior to spawning.
2. Create the exact pinned executable with `CREATE_SUSPENDED` and explicit file-backed standard output/error; **the child cannot execute before containment assignment**.
3. Assign the suspended process to the job, independently verify membership, then resume its primary thread.
4. Keep the Job Object handle owned by the NVP supervisor until completion; close it even after child exit to terminate any descendants. On abrupt host termination the operating system closes the last job handle, terminating associated processes. Cancellation uses `TerminateJobObject`, not an uncontrolled `taskkill` command.
5. Reject the entire operation if any Job API fails. The output is not trusted merely because a process exited; the SQLite receipt still requires exact content and independent audit.

The selected wrapper **pywin32 311** is a Windows-only dependency. The retail installer must vendor the pinned wheel and its binary DLLs with a separate license and security audit.

**Limitation:** The Windows Job **committed-memory** cap cannot guarantee GPU VRAM availability, physical RAM pressure from other apps, device-driver stability, or that all Windows codecs/third-party subprocesses obey the same resource budget. Explicit hardware guardrails remain required.

### Linux

Uses a small launch shim that sets kernel `PR_SET_PDEATHSIG(SIGKILL)` before replacing itself with the actual Blender executable via `execv`, with an immediate parent-PID race check. A hard NVP host/thread exit triggers the kernel signal and kills the directly supervised Blender process. Live cancellation still kills the process group. Optional `RLIMIT_AS` caps virtual address space; in contrast to Windows committed-memory limits, this is **not** an RSS or VRAM quota and may reject workloads with large virtual mappings.

**Critical scope limit:** `PR_SET_PDEATHSIG` protects the **direct Blender child**; it does **not prove termination of detached grandchildren**. Process-group cancellation covers descendants that remain in its group while NVP is alive, but crash-wide descendant containment requires cgroups v2 delegation or a separately supervised persistent worker. Do **not** label Linux whole-tree crash cleanup or multi-process GPU memory protection complete.

### Restart and immutable source custody

After supervisor restart, any journal state `RUNNING` or `CANCEL_REQUESTED` is `INTERRUPTED`, and abandoned work cannot be accepted by a recovered process. Completed outputs are independently rehashed, media-magic-checked, and Blender-side source/scene audit reports checked before they can become an NVP technical presentation. Film World and frozen Digital Takes remain unmodified; neither a worker receipt nor a grade grants creative approval.

## Acceptance matrix (required)

| Test | Linux | Windows |
| --- | --- | --- |
| Actual OS child process (not mocked) and cancellation | Kernel process-group test | Win32 suspended job + TerminateJobObject |
| Abrupt `os._exit` of actual supervising host after child signals ready | Direct child receives PDEATHSIG | Job handle closure kills child/descendants |
| Attempted allocation above configured kernel memory limit | RLIMIT_AS refuses it | JOB_OBJECT_LIMIT_JOB_MEMORY refuses it |
| Existing durable worker tests | 6 test contracts | 6 test contracts |
| Actual Blender 5.2.3 technical render, approved NVP scene and independent reopen | Native CI Blender | Future real Windows Blender integration |

A kernel crash test is **not** satisfied by mocking termination or injecting a fake PID into SQLite. Native Blender acceptance still requires the previously accepted source identity/scene audits with a real pinned renderer, and a separate actual post-crash signal test.

### Measured evidence — 2026-11-03

The latest independently measured **code revision** was [GitHub Actions run 41766014441](https://github.com/vjmichael/nvp_offline_film/actions/runs/41766014441), built from commit `934b65ff941f2b31bec8bf3369a0c7d3ffc61b32`. The three lanes passed. Windows tests `test_actual_hard_supervisor_exit_kills_running_worker` and `test_windows_job_closure_kills_child_and_grandchild` both passed by **actual subprocess exit** and subsequent process-status verification, not mocking a process ID. Linux validated kernel PDEATHSIG on its direct child and bounded RLIMIT_AS against an oversized memory allocation. Both platforms also passed all six previous durable-worker/idempotency/tamper tests.

The native Linux job reused [STACK-02A's genuine Blender acceptance](NVP_STACK02A_DURABLE_BLENDER_WORKER_ACCEPTANCE.md) **through the new containment launcher**, producing a real 128×72 PNG, Blender file, approved NVP scene, second-process independent reopen, and **nine scene-identity/geometry checks**. Its native artifact is `nvp-stack02b-real-blender-contained-evidence` in that GitHub run. Independently inspected artifact values: external Blender binary SHA-256 `b8b07a190fb25db76aae6de08dbc6c2b3d64e22e82bed6ba90de9545859f3431`; reviewed source manifest SHA-256 `fcdb905b3d58ccfe2ac027aaa159c831e099e652cd9b8a3f3681b029e8611c82`; technical audit 9 checks. The underlying native report retains the historical STACK-02A format and correctly does **not** purport to prove Linux whole-tree crash cleanup; kernel parent-death evidence is in the OS contract lane.

**Do not extrapolate:** Windows used real suspended Job Object processes and real child/grandchild crash tests, but did **not** run a full Windows Blender/Cycles native scene. GPU/VRAM limits, Linux detached-child containment, NVP multi-instance ownership and LGPL/GPL retail packaging remain separate gates.

### Proof links and current progress

- [GitHub Actions STACK-02B workflow](../.github/workflows/nvp-stack02b-os-containment.yml) — actual Linux, Windows and native jobs.
- [PR #26](https://github.com/vjmichael/nvp_offline_film/pull/26) — source and tests.
- The OS containment tests and native Blender run passed for the code commit above. Final documentation-only commits should be checked on their own latest source SHA before closure; failed iterations remain available as regression evidence.

## Remaining work, separate from this gate

1. **Linux entire worker-tree containment:** cgroups v2 with controlled delegation or persistent kernel-backed supervisor; test orphaned grandchildren under hard parent death.
2. **Windows Blender on the real containment backend:** deploy actual pinned Windows Blender binary under a Job Object, independent render/audit plus hard host crash test; Windows CI currently uses Python process contracts.
3. **User PC safety:** VRAM preflight, available RAM reservations/guardrails, GPU backend selection and user-configurable resource budgets, before full-resolution movie renders.
4. **Multi-instance ownership:** enforce cross-process exclusive ownership/lease of the journal and jobs, preventing a second running NVP instance from marking another host's active worker interrupted.
5. **Full worker migration:** route capture, character retarget, animation, Cycles, EXR, compositing and final exports through the same host control, keeping existing acceptance.
6. **Single installer and license review:** pinned binary manifests/sha256, GPL Blender and any bpy adapters' source/notice obligations, pywin32 and transitive dependency notices, NSIS install/uninstall and offline upgrade verification. Commercial distribution still requires review.

**Launch criteria:** CI tests passing on both Windows and Linux do not prove a commercially redistributable installer, full VRAM safety or complete Linux grandchild cleanup.
