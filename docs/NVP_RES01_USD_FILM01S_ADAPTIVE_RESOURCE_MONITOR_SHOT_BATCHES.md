# NVP RES-01 / USD-FILM-01S — Adaptive Resource Monitor and Director Camera Batching

**Director decision: Nov 8, 2026.** NVP owns its resource budgeting; when
operated by Lu it reports ONLY its own managed process usage and bounded
queue state. Lu may display/work with that information but must not gain
implicit permission to launch, cancel or reschedule NVP render workers.
One scene performance is captured once and is visualized from arbitrary
virtual camera viewpoints. Low-fi and hi-fi are two render paths from
that same authoritative data.

## Existing foundation reused

- `backend/nvp_resource_guard.py` already reads current Windows/Linux
  available physical RAM, Linux memory-pressure PSI, selected GPU driver
  budgets, and makes conservative task-admission decisions with headroom.
- `backend/nvp_resource_ledger.py` already records queued/active work
  and RAM/VRAM reservations. The installed director UI already contains
  `ResourceActivityPanel`.
- `BlenderWorkerSupervisor` already launches first-party reviewed,
  pinned Blender workers under OS containment, journal, timeout, explicit
  cancellation and memory ceilings. No mini-app/alternative process
  supervisor is created.

## RES-01 — NVP-owned process measurements

- `backend/nvp_resource_process_monitor.py` adds psutil-backed measured
  NVP *host* process and trusted child Blender worker/visible-descendant
  CPU time, sampled CPU percent (one core=100%), RSS MiB,
  peak observed RSS and observed IO bytes. Worker PID and creation time
  must match the trusted launch; registration rejects unrelated OS PIDs.
  Existing worker supervisor automatically registers after OS launch,
  polls every ~1.5s and retains the last known samples after exit.
- A shared per-process NVP monitor enables the existing local
  `GET /api/system/activity` route and sidebar `Computer & production
  activity` to display **NVP-owned usage** next to the existing whole-PC
  telemetry and resource reservations. Neither monitor reads external
  LM Studio/server worker process usage as if NVP owned it.
- Read-only versioned `nvp.resources.owned_process_report.v1` and
  `nvp.film01s.lu_read_only_resource_and_batch_report.v1` data carry
  measured host/worker RAM, CPU time/percent, IO, unknown/unavailable
  distinctions, hardware budget scope, and shot queue progress. They
  deliberately contain no executable paths, tool permission tokens or
  renderer launch/cancellation method. NVP's trusted native broker
  remains the only owner of worker execution authority.
- **Honesty limitations:** psutil descendant walks are observations,
  NOT proof that an escaped grandchild terminated. RSS sums can count
  shared memory more than once. On Windows DXGI the budget is process
  scoped, not globally free VRAM. GPU VRAM per NVP process/worker stays
  **unknown**, never guessed at zero or computed by subtracting system
  free VRAM. Other NVP worker types need further explicit registration;
  Blender integration is the first native path.

## 01S — automatic and user-set shot batching

- `backend/nvp_usd_film01s_adaptive_batch.py`: typed `Shot` with
  original camera ID and source frame in/out, `BatchPreferences` with
  **Auto or 1–64 shots per batch**, optional 1–32 maximum concurrent
  worker cap, CPU/GPU preference and conservative per-worker RAM/VRAM
  reservations. Original performance SHA is bound to a plan.
- **Auto batch size** uses measured RAM availability/headroom and usable
  CPU cores; RAM pressure and unknown RAM block dispatch. User-selected
  group size remains exactly what the director requested (except a
  naturally smaller last group), regardless of parallel worker count.
  Example: a low-power PC may batch 12 shots together yet safely run
  just ONE render worker at a time. A high-end PC may admit several
  workers and select larger Auto groups.
- Each dispatch re-checks current hardware/resource headroom. Existing
  NVP supervisor and its system activity ledger own memory admission;
  batching never overrides the protected worker's independent safety
  checks. GPU scheduling requires BOTH a measured compatible device
  budget AND a separately reviewed/verified Blender/Cycles GPU backend
  identity. No assumption that llama.cpp Vulkan or LM Studio GPU support
  implies a Blender-supported GPU renderer. Limited DXGI budgets force
  conservative concurrency.
- A single plan can include MANY **low-fi exploration viewpoints** but
  only a small selected subset of **hi-fi final shots**. Separate stage
  batches avoid rendering all camera views at final quality.
- `DurableShotBatchQueue` persists source-immutable plan SHA, stage,
  shot identity, chosen batch number, current status, attempt and
  independently verified output receipt SHA in SQLite WAL/FULL. It
  requires explicit director admission for the plan, new exact
  per-shot authorization for each worker claim, and an independent
  renderer-result verifier before SUCCESS. Crash recovery marks RUNNING
  as INTERRUPTED; a new attempt ID requires independent prior OS worker
  custody proof. Old approved source/permission is not reused.
- `NVPAdaptiveShotService` joins NVP hardware autodetection, durable
  shot planning and the existing native supervisor's owned-process
  report. Suggestions do not launch processes; starting real source
  Blender jobs remains in NVP's reviewed broker.

## UI and local planning endpoint

- Existing `ResourceActivityPanel` shows NVP host/Blender worker CPU/RAM
  separately from globally measured system use and separately managed AI.
- Director tab **21 · Batch camera shots** has interactive choices:
  viewpoint count, final selected shot count, Auto/manual shots per batch,
  Auto/user max simultaneous workers and CPU/GPU preference. It calls
  source-independent, read-only
  `POST /api/system/shot-batch-estimate` and reports predicted preview
  and final batch groups, measured resource safe concurrency, queued
  waits, and explicit limitations.
- **This browser form is estimation only**, not a rendered or queued
  source performance. No FilmIndex Take SHA is fabricated and no browser
  input grants native process authority. Binding the installed director
  source selection/EDL to the durable queue and NVP's reviewed native
  per-shot renderer is a separate 01Q/01R acceptance gate.

## Real tests and outstanding gates

- Python tests use deterministic synthetic LOW/HIGH PC hardware
  snapshots and a real, short-lived NVP-owned Python child. They check
  resource constraints, GPU unknown/limited, manual 12-shot group with
  only one safe worker, auto-scaling CPU/RAM, selected low-fi vs hi-fi,
  per-shot consent, SQLite reopen, crashed-job interruption and source
  report privacy/authority scope.
- Windows 2025 / Ubuntu 24.04 Python 3.11/3.13 resource test matrix,
  plus director UI tests of Auto/manual grouping and owned-worker
  display. Native CI results are OPEN until run and inspected.
- Remaining: physical installed NVP acceptance with actual Blender
  child process measurements under load, Windows Job Object/Linux
  descendant custody, GPU backend/device verification and per-worker
  GPU attribution where supported, real time-varying hardware stress
  and adaptive reduction. Live native 01Q selected-shot broker binding,
  designer UI persistent queue/edit controls, and Lu-side read-only
  connector acceptance remain OPEN. No full scene render or Lu
  controlling NVP is asserted from these tests.
