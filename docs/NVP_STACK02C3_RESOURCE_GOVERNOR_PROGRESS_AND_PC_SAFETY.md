# NVP-STACK-02C3 — Memory safety, admission control and truthful progress

> **Tracking notice (2026-11-13/14):** This is a historical/technical reference, **not an active task ledger or backlog**. The sole current NVP task journal, priorities, statuses, acceptance gates and branch/PR dispositions are maintained in [NVP_DATA_ALL_TASK_LEDGER.md](NVP_DATA_ALL_TASK_LEDGER.md), through draft convergence [PR #161](https://github.com/vjmichael/nvp_offline_film/pull/161). Older branch/PR claims below are source snapshots; preserve technical evidence but do not use them to decide current task priority.


**Engineering date:** 2026-11-03  
**Status:** **Initial development gate ACCEPTED** in [CI run 41774472490](https://github.com/vjmichael/nvp_offline_film/actions/runs/41774472490): **4/4 jobs green**. Full production rollout, on-device VRAM stress and managed AI load/unload remain open.  
**Parent:** [STACK-02C2 native worker/cgroup acceptance](NVP_STACK02C2_LINUX_CGROUP_WHOLE_TREE.md) · [Reuse-first decision](NVP_ADR_STACK01_REUSE_FIRST_AND_ONE_INSTALLER.md)

## Creator-directed user experience

A filmmaker must never stare at a frozen NVP window wondering whether Blender is loading, an AI model is occupying VRAM, a film frame is rendering, or a previous task is being offloaded. The UI must show **real, grounded resource and task state** continuously.

The visible **Computer & production activity** panel is persistent in NVP's sidebar. It polls a read-only host API, and includes:

- Physical RAM used/available, drawn from the host OS;
- Selected GPU memory budget/usage **only when a device provider returns a real measurement**, including the important *DXGI per-process vs physical-global* distinction;
- NVP's **outstanding admission reservations**, separately from the OS's reported used memory;
- Active, queued, failed, interrupted and completed tasks, including clear explanations for denied admission and fresh update times;
- Operation phase, such as **checking memory → loading/warming AI → processing/generating → offloading AI**, or **preparing scene → building → rendering → verifying → releasing memory**;
- **Numeric percentages only when emitted by a real adapter**. Blender job stdout byte counts are not percent, and a model file existing does not mean it is loaded. In such cases show an accessible indeterminate meter and explanatory state. Do not calculate ETA from elapsed time alone;
- If a memory-reserved task stops sending an actual supervisor heartbeat for over 15 seconds, show **STALE_UNVERIFIED / Recovery needed** without silently freeing its resource reservation or claiming that the worker exited.

Browser users never submit arbitrary worker paths or GPU override flags to the API. The resource endpoint is read-only. It is intentionally not a source of authority for native tool execution.

## Reused OS and driver information

| Resource | Source | Meaning |
| --- | --- | --- |
| Windows RAM | Win32 GlobalMemoryStatusEx | Measured total/available host physical RAM |
| Linux RAM | /proc/meminfo MemTotal/MemAvailable | Kernel estimate of physically available host RAM |
| Linux memory contention | /proc/pressure/memory \`full avg10\` | Real memory stall pressure over 10 seconds |
| AMD Linux VRAM | amdgpu DRM sysfs \`mem_info_vram_total\` and \`mem_info_vram_used\` | Driver-wide local VRAM total/used |
| NVIDIA VRAM | Driver NVML, if optional \`pynvml\` is installed | Driver-reported global GPU memory |
| Windows VRAM | IDXGIAdapter3.QueryVideoMemoryInfo LOCAL via Win32 DXGI | OS-assigned **process** VRAM budget and current NVP-process use — not the sum of every other application's VRAM use |
| Other/unknown GPU | No verified sensor | **GPU requests queue**; never assume free capacity or fake a GPU graph |

The native Windows DXGI binding is an interface to the existing OS API, not custom GPU memory-science logic. Exact adapter selection matters on multi-GPU machines; never silently substitute a different GPU device. For GPU jobs, the *trusted producer* must declare the chosen adapter and estimated device-local allocation. The API must not infer a GPU's availability from system RAM or a model's advertised architecture.

**References:** [Microsoft DXGI budget structure](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_4/ns-dxgi1_4-dxgi_query_video_memory_info), [DXGI process budget method](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_4/nf-dxgi1_4-idxgiadapter3-queryvideomemoryinfo), [Linux PSI](https://www.kernel.org/doc/html/latest/accounting/psi.html), [kernel cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html).

## Safety policy (initial conservative BALANCED profile)

The producer must provide a bounded trusted estimate before NVP launches a heavy worker. In the new guarded path, each immutable \`BlenderOperation\` includes a **max RAM bound**, optional device-local GPU demand and exact adapter ID. No adapter ID ⇒ it cannot reserve/request GPU memory.

- **RAM:** Maintain at least **max(2 GiB, 20% of total physical RAM)** free *after* all NVP active reservations and the proposed task's estimate. Unknown OS RAM ⇒ queue.
- **VRAM:** For the selected measured adapter, maintain **max(1 GiB, 20% of the reported GPU budget)** after the task's demand and outstanding same-adapter NVP reservations. Unknown device budget ⇒ GPU work queues.
- **Memory pressure:** Linux \`memory.full avg10 >= 5%\` blocks new heavy work. RAM/VRAM dangerously low or \`memory.full avg10 >= 15%\` is a critical signal; the contained supervisor requires two consecutive critical samples (sampled about 1.5 seconds apart) before cancelling **its own** worker. It does not kill another application's AI process.
- **Host protection:** OS Job Objects on Windows and delegated cgroup/guardian on Linux remain the hard containment layer. These VRAM budgets are *admission signals*, **not a kernel-enforced VRAM cap**, a guarantee against driver failure, or substitute for reservation/OS cleanup.
- **Concurrency:** SQLite FULL synchronous \`BEGIN IMMEDIATE\` serializes admission and reservation across NVP host processes. A different NVP task in the same database cannot silently double-spend its RAM/VRAM headroom. Different GPU IDs use different reservation buckets.
- **Queued task:** It is recorded as **QUEUED, not yet started** and holds no reservation. A trusted host may retry when OS headroom changes; web UI cannot launch arbitrary native operations.
- **Crash/restart:** An ACTIVE record remains reserved until the approved supervisor verifies native worker cleanup and explicitly finalizes it. A stale active task is displayed **STALE_UNVERIFIED** rather than rendering or complete. This deliberately fails closed at the cost of reduced throughput until recovery is reconciled.

The initial safety policy favors user desktop responsiveness over maximum throughput. Later profiles may safely adapt to benchmarked model estimates, hardware class and real device-specific telemetry. No user preference may casually turn off the hard resource floor.

## AI load/unload distinction

NVP's current writing provider is an external, independently managed OpenAI-compatible loopback server such as LM Studio. NVP can **observe** its creative-inference request but does not claim to manage its model lifetime, move its weights between RAM and VRAM, or know its exact context/KV-cache memory.

LM Studio now supports a native v1 API with model load/unload and streamed model-load events. Those are **candidate APIs for a future explicit model-management adapter**, not a license to silently unload the filmmaker's model, especially when it may also be used by other applications. Before enabling the management action:

1. The user explicitly opts in to NVP owning a **particular model instance** and its load/unload lifecycle.
2. The provider supplies a sufficiently conservative memory estimate or NVP refuses the load when RAM/VRAM cannot be verified.
3. NVP journals real progress events (only a provider-emitted fraction becomes a percentage), errors, offload completion acknowledgements, and model ownership.
4. NVP does not offload an instance it did not load/control or steal a device allocation from another application.
5. The UI explains whether a task is queued for RAM, queued for VRAM, warming, running, responding, or releasing memory and allows a safe user-authorized cancellation.

Reference: [LM Studio REST v1 API](https://lmstudio.ai/docs/developer/rest), [load](https://lmstudio.ai/docs/developer/rest/load), [unload](https://lmstudio.ai/docs/developer/rest/unload), [streaming events](https://lmstudio.ai/docs/developer/rest/streaming-events).

## Implementation / tests

- \`backend/nvp_resource_guard.py\`: OS and driver-sourced probes, typed \`ResourceSnapshot\`, GPU adapter IDs, independent RAM/VRAM reserve policy, emergency pressure decision.
- \`backend/nvp_resource_ledger.py\`: FULL-sync durable cross-host \`admit\`/queue/\`retry\`/update/finalize/event records; read-only activity snapshots, heartbeat and stale display; separate observation for externally managed AI.
- \`backend/nvp_blender_worker.py\`: opt-in \`activity_ledger\` constructor argument on the **existing** contained native Blender supervisor. The guarded path admits before Blender launches, queues unsafe jobs without subprocess creation, publishes real phases, heartbeats during native processing, watches critical memory pressure and only reports success after its existing source/outputs audits.
- \`backend/nvp_api.py\`: read-only \`GET /api/system/activity\`; existing creative-model writer requests publish **observed** task phases with no invented model lifetime or %.
- \`frontend/src/ResourceActivityPanel.jsx\` and CSS: expandable, accessible RAM/VRAM meters and production task progress/queue/recovery states in the existing NVP sidebar. Respects reduced-motion preference for indeterminate animation.
- \`tests/test_resource_governor.py\`: admission math, telemetry fidelity, reservations across two ledger objects, queue retry, measured vs unmeasured percentages, stale reservation semantics.
- \`tests/test_blender_resource_admission.py\`: actual supervisor guards a trusted native job before process start, queues if insufficient memory, retries, audits outputs and releases RAM.
- \`frontend/src/ResourceActivityPanel.test.jsx\`: DOM interaction tests for genuine percentages, indeterminate Blender progress and truthful DXGI/unknown-sensor labeling.
- \`tools/nvp_stack02c3_guarded_blender_fixture.py\`: real Blender render/producer test, forced unsafe-memory queue, re-admit under actual host memory, independently reopen verified .blend/PNG and inspect durable activity events.
- \`.github/workflows/nvp-stack02c3-resource-safety.yml\`: Linux and Windows safety regressions, frontend interaction/build, native distro Blender CPU acceptance.

## Acceptance status and remaining gates

**Final code acceptance:** [GitHub Actions 41774472490](https://github.com/vjmichael/nvp_offline_film/actions/runs/41774472490) passed **4/4 jobs** on commit `b586781b3b3a6a0da7ca39c5e3ebd4170877ec79`. Windows **28/28** and Linux **28/28** backend contracts, including genuine two-process RAM-reservation contention and stale-heartbeat recovery; the two jsdom React interaction tests and Vite production build also passed. Real Ubuntu Blender 4.0.2 queued when unsafe RAM was injected, then ran only after actual OS RAM was measured, created a genuine `.blend` and PNG and passed independent output readback/release. Final native artifact `nvp-stack02c3-real-resource-guarded-blender` passed ZIP integrity verification. Cross-process stress discovered a real SQLite race from repeatedly setting `PRAGMA journal_mode=WAL`; it was fixed by configuring the busy handler first and initializing WAL only during schema setup. The final test now exercises simultaneous independent NVP processes sharing the same resource ledger. This is a **guarded CPU Blender proof**, not live Radeon GPU stress, managed LM Studio model eviction, or final-film production integration.

**NOT yet verified for retail release:**
- Windows AMD Radeon AI Pro R9700 physical telemetry and live GPU pressure, multi-adapter matching, CPU fallback of Blender GPU jobs and real 32 GiB RAM/VRAM desktop contention with local AI plus native GPU Cycles;
- Actual AI model **load/unload orchestration** and emitted load percentages; current external server observation is explicitly not managed model memory;
- Automatic priorities/queued job dispatcher, owner-authorized cancellation UI, safe preemption, true cross-engine pause/resume, thumbnail/pixel progress, and real render ETA from measured frames;
- Safe crash-recovery reconciliation of NVP-wide reservations after OS worker containment proofs; old ACTIVE reservations intentionally block further work;
- Default policy activation for **every** production/film/character/AI render route rather than the guarded supervisor's explicit opt-in path;
- OS cgroup effective-memory cap accounting, GPU driver stress and full system starvation tests, and single-installer code-signing/GPL/codec licensing.

**User-facing requirement:** Never show a fictional progress percentage or tell the creator a busy job is complete merely because its process ended. Preserve source Film World and frozen Digital Takes; resource protection may defer production but must never corrupt or approve a presentation.

**Next:** STACK-02C3B managed provider adapter + safe task admission/priority scheduler, followed by STACK-02D full engine-path integration and STACK-01E single-installer/redistribution review.
