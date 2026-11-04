# NVP-STACK-02C3B1 — Trusted-host priority admission

**Acceptance:** CI run 41775842472 passed 3/3 jobs on code revision ca79b39b1cd19a8f6ecb4c999f6af046a84a8e4d (Linux 9 scheduler + 10 governor; Windows 9 + 10; React 2 and successful Vite build). This is a bounded scheduler primitive, not full production integration. Based on the accepted STACK-02C3 resource governor. This is NOT an automatic film production dispatcher and does NOT claim managed AI model loading.

## Design contract

The existing FULL-sync SQLite task ledger now supports a native trusted-producer queue. A producer calls TaskLedger.enqueue(AdmissionRequest, owner_key, lane) and gets QUEUED with no resource reservation and no process launch, even if the PC currently has plenty of memory.

A trusted producer calls claim_next(owner_key). Under one BEGIN IMMEDIATE write transaction, the ledger selects the next task in priority order and applies the same conservative OS-measured RAM/VRAM admission used for native Blender. Priority is interactive > standard > background; tasks in one priority lane retain FIFO order. It either atomically claims one ACTIVE reservation or returns the highest-ranked task as QUEUED with a real memory-blocking reason. A lower priority task cannot bypass a blocked higher priority task **within that producer's queue**.

TaskLedger.cancel_queued(task_id, owner_key) cancels only QUEUED work never claimed or started. An ACTIVE task cannot be cancelled by this shortcut: its OS-contained supervisor must verify cleanup before TaskLedger.finish releases the durable reservation. If the host crashes after admission, the reservation remains held and must be reconciled. No browser route exposes claim, enqueue, or cancellation authority.

The public read-only /api/system/activity includes queue_lane on scheduled tasks. The React panel shows the priority lane while preserving measured-or-indeterminate progress and OS memory headroom reporting.

## Verification

The new test_resource_scheduler.py exercises empty reservation at enqueue, priority and FIFO, head-of-line blocking, wrong-owner refusal, cancelled queue, active cancellation refusal, invalid lanes and duplicate IDs, fail-closed reservations, public snapshot fidelity and real two-process competition.

CI on Ubuntu and Windows runs the new tests plus the existing resource governor regression suite. A frontend job runs the existing resource activity interactions and builds the Vite UI. Acceptance requires checks to complete successfully on the exact branch commit.

## Boundaries and follow-on work

This is producer-local priority ordering, **not** a shared cross-engine automatic dispatcher. It has no OS-level authority to run Blender by itself. The caller still needs immutable, authorized task specifications and a native worker to perform a claimed job, and should refuse unrecognized task IDs. A global dispatcher must resolve multi-producer fairness, changing priorities, starvation, accepted-operation persistence, restart reconciliation and verified cancellation.

Next STACK-02C3B gate: explicit opt-in LM Studio v1 model management with sufficient RAM/VRAM estimates, instance provenance, no external-model eviction, and measured provider progress; integrate native Blender and encoding through the scheduler without bypassing containment. Current LM Studio external model requests stay observation-only. Hardware GPU pressure and a commercial one-installer bundle remain separate gates.

References:
- Existing engineering gate: NVP_STACK02C3_RESOURCE_GOVERNOR_PROGRESS_AND_PC_SAFETY.md
- LM Studio v1 API: https://lmstudio.ai/docs/developer/rest
- Model load: https://lmstudio.ai/docs/developer/rest/load
- Model unload: https://lmstudio.ai/docs/developer/rest/unload
