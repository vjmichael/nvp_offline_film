# POST-LU-1.0 — NVP ↔ Lu recoverable model/resource handoff contract

**Status:** Deferred design contract only. No Lu v1.0 interface changes. No implementation or claim of tested power-cut recovery. NVP remains independently executable until this future integration.

## Goal

A single-machine coordinator must be able to suspend Lu's local inference, safely recover its RAM/VRAM, admit a specialized NVP production model, run a source-bound production job, unload that model, and restore Lu's inference **without losing durable conversational goals, task progress, permissions, production references or any committed artifacts**. This must recover conservatively after crashes, forced worker termination or power loss; it must never overload a host by speculative double-loading.

## Responsibility boundary

- **Lu:** owns its conversations, semantic memory, task plan, pending model inference, authorization decisions, and durable task/effect journal. Lu alone initiates a safe suspension checkpoint and decides what model state is reconstructible.
- **NVP:** owns its production data, FilmIndex revisions, Digital Takes, specialized model requirements, production jobs and verified artifact receipts. NVP requests an allocation rather than ordering Lu to kill its model.
- **Host-level resource broker/supervisor (future interface):** arbitrates exclusive or shared GPU/RAM leases, hardware telemetry, lifecycle transitions, OS-owned worker containment, measured unload/reload and recovery. NVP and Lu cannot independently assert a resource lease was released. Broker itself must persist leases and survive process restarts.
- **Creator:** can approve/deny handoff, cancel or pause safely, with policy-defined automation boundaries; neither assistant-generated JSON nor discovery constitutes authorization.

## Crash-recoverable state machine

`RUNNING_LU → HANDOFF_REQUESTED → LU_CHECKPOINTED → LU_WORKER_STOPPING → LU_RESOURCES_VERIFIED_FREE → NVP_ADMITTED → NVP_RUNNING → NVP_CHECKPOINTED/COMMITTED → NVP_WORKER_STOPPING → NVP_RESOURCES_VERIFIED_FREE → LU_RELOAD_ADMITTED → LU_CONTEXT_REHYDRATED → RUNNING_LU`.

Each transition is a transactional, monotonic journal event with unique handoff ID, generation/fencing token, exact model/backend identities, resource budget, source task IDs, approvals, prior checkpoint receipt, and observed worker lifecycle. A crash never implies cleanup, and a stale agent must not advance a newer handoff or release another worker's lease. Before transition to an externally visible COMMITTED state, checkpoint content and manifest must be fsynced/atomically published or equivalently durable on the configured store.

## Quiescence and context integrity

- Stop accepting new model turns, persist the prompt/response boundary, queued turns, active tool operations, explicit permissions, stage outputs, goals, source refs, and summaries/beliefs with provenance.
- A partially generated response is explicitly **incomplete**, not an authoritative completed turn. On restart, resume from durable task boundary or regenerate it with clear status; no duplicate tool side effects.
- Distinguish semantic context from KV cache: persist enough prompt, references, memory and decision state to **reconstruct** model context. Reusing exact KV cache is optional and backend/version dependent, never guaranteed.
- Pending native tools need idempotency keys and prepare/commit receipts; treat unknown completion as **verify/reconcile**, not blindly retry.
- Models should not inherit permissions simply because Lu restores the prior conversation.

## Safe handoff admission

- Only after Lu's model worker and owned children have actually released resources (OS verified cleanup or verified backend unload) may the broker admit NVP's new model.
- Measure available physical RAM and GPU budget at admission and during work, reserving OS/user headroom; unknown GPU telemetry means no speculative load.
- Account for shared-memory GPUs, backend caches, pinned allocations and allocator release delays. Never assume process termination instantly clears measured GPU use.
- A refusal or slow unload leaves the request queued and Lu's durable task safe; there is no uncontained fallback.
- Prioritize desktop responsiveness. Use NVP's existing resource guard, TaskLedger, safe work-batching and OS containment as a starting point; integrate with the *future common broker*, not two competing resource authorities.

## Persistence and reconciliation after interruption

On restart, read the latest durable handoff generation, verify which OS workers are actually alive, reconcile physical resource leases conservatively, confirm FilmIndex output/checkpoint hashes and original task/event journal, then choose the only safe next transition. Do not assume NVP succeeded because a file exists; a committed output must have an independently verified receipt and exact dependency lineage. Do not auto-release uncertain reservations. If a worker cannot be proven dead or a backend cannot prove unload, leave the lease in blocked/recovering state and offer safe recovery, never double-load.

The interface must survive: Lu crash, NVP crash, model loader crash, host supervisor crash, forced process kill, SQLite WAL replay, incomplete artifact publication, power cut at every transition, resource-pressure stop, and repeated restart. Resume the correct job after each; never drop creator decisions or fabricate a completed movie.

## Interface sketch (not API commitment)

- `request_model_handoff(task_id, desired_model_capabilities, estimated_ram_vram, deadline_policy)`
- `checkpoint_and_quiesce_lu(handoff_id, generation)`
- `verify_release_and_acquire_lease(handoff_id, generation, device_budgets)`
- `launch_nvp_model_and_job(lease, source_revision, job_id, approval)`
- `checkpoint_or_commit_nvp_output(job_id, manifest_sha, lineage)`
- `verify_nvp_release_and_restore_lu(handoff_id, generation)`
- `rehydrate_lu_task(checkpoint_id, validated_nvp_results)`

Names are conceptual only; no Lu pre-v1.0 ABI or direct DLC interface should be introduced.

## Acceptance gates (after Lu v1.0)

1. Constrained home PC where two models cannot simultaneously fit: swap each way without OS freeze, while preserving an unrelated active desktop workload.
2. Successive NVP specialized model swaps with at least one NVP production job and real validated FilmIndex output.
3. Crash/fault/power interruption injection after each journal state, including during unload, loader admission and output commit.
4. Exact persisted Lu task/permission/queued-turn reconstruction, no duplicate irreversible tool calls, no lost source or production revision.
5. Verify actual GPU/RAM headroom and absence of overlap, monitor host responsiveness and retain unknown cleanup reservations.
6. Verify no permission escalation, stale lease reuse or fake completed jobs; demonstrate restart after interruption with independently checked output.
7. Run across Windows and Linux with backend-specific caveats. Bitwise KV-cache restoration is not required; context continuity and durable workflow correctness are.

**Design principle:** model residency is replaceable and transient; durable work, creator intent, context and artifact lineage are authoritative.
