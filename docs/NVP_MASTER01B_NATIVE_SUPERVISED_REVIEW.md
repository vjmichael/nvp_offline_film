# NVP-MASTER-01B — Native supervised 30–60-second film review

**Date:** 2026-11-05  
**Status:** Implemented bounded host/worker foundation; local Linux native acceptance passed. **Not a creator-approved or AI-generated film, and not a completed Windows acceptance.**

**Design authority:** [NVP MASTER DESIGN](NVP_MASTER_DESIGN.md), [MASTER-01A real technical review](NVP_MASTER01A_LONGFORM_TECHNICAL_REVIEW.md), [Data-first ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md).

## Why this gate exists

MASTER-01A proved exact media assembly from several already-indexed ProRes/PCM24 reels but still invoked FFmpeg from a developer Python process without the production host's admission, cancellation, resource monitoring or OS custody. MASTER-01B connects that existing assembler to NVP's *existing* trusted-native machinery rather than creating a competing queue, subprocess framework or film database.

## Implementation

- `backend/nvp_master01b_native_host.py`: trusted `NativeMasterReviewHost`. Requires an existing `FilmIndex`, `TaskLedger`, native creator-action verifier and application-owned workspace. The host validates exactly 2–12 bounded same-project source reel IDs/revisions, their FilmIndex documents and SHA-addressed genuine AV media. It binds producer revisions, source hashes, frame totals, requested new review ID, pinned FFmpeg/FFprobe/Python/worker/module hashes and resource limits to a sealed task plan. It rejects approval-event reuse and duplicate targets.
- `backend/nvp_approved_tasks.py` / `backend/nvp_resource_ledger.py`: existing host policy callback is rechecked by `ApprovedTaskBindings` at admission, with queue vs active states and conservative RAM reservation.
- `backend/nvp_worker_host_lease.py`: an exclusive kernel lock protects one host executing or reconciling the native journal. The lock is not itself a worker-tree cleanup witness.
- `backend/nvp_worker_containment.py`: existing Windows Job Object or Linux OS child custody launches a pinned absolute Python worker. Strict delegated Linux cgroup-v2 custody may be explicitly required where real delegation exists; non-strict Linux is **development-only** and does not claim a whole-tree OS guarantee after an uncontrolled host crash.
- `backend/nvp_resource_supervisor.py`: existing `wait_guarded` watchdog gains an optional trusted-host-only cancellation predicate. Cancellation stops the owned tree. Progress is never fabricated from elapsed time.
- `tools/nvp_master01b_native_worker.py`: reads the sealed local plan, calls the original MASTER-01A source-indexed assembler, reopens the resulting **unapproved** review and fsyncs a narrow worker receipt. It cannot approve a final master, publish a DCP or decide human policy.
- After the worker stops, the native host fsyncs a SQLite stop witness and reopens the FilmIndex/media **independently** before marking the ledger `SUCCEEDED`. It cross-checks the exact source refs, source-binding digest, frame count, media SHA and worker receipt. This uses the original immutable FilmIndex graph; it is not a parallel authoritative production database.

**Allowed output:** `VERIFIED_TECHNICAL_REVIEW_UNAPPROVED`; always `creator_approved_final_master=False` and `dcp_delivered=False`.

## Crash, cancellation and replay rules

- **Denied or revoked before admission:** no native worker starts. Queued tasks are cancelable without reserving memory.
- **Controlled in-process cancellation:** the host signals the watchdog; the contained worker group is terminated, the stop is recorded, and the job ends `CANCELLED`. No blind retry and no promotion of an unapproved result.
- **Crash after a verified stop witness but before ledger completion:** a fresh host takes the kernel lease, independently reopens the recorded exact movie and receipt, and finalizes the *same* task without running FFmpeg again. Idempotent reconciliation does not create a second FilmIndex revision.
- **No trustworthy worker-stop witness after restart:** return `STALE_UNVERIFIED`, retain the resource reservation and do not retry or infer that descendants were reaped. This requires a future OS-backed recovery path before normal service can safely reclaim the task.
- **Corrupt or missing receipt and verified stopped worker:** treat as interrupted or failed, never as a successful creator-approved movie. External side effects remain unapproved.

### Limitations and deferred gates

1. The host is a native-only Python API and has not been exposed as an unguarded FastAPI or AI model tool. A real human-turn/creator verification callback remains mandatory. Approvals to *assemble technical reviews* are not film release approvals.
2. MASTER-01A's output publication still occurs **inside the contained worker**; a host crash between film index publication and receipt may leave a source-indexed, unapproved orphan. Recovery does not blindly replay. Future MASTER-01C should make publication a host-mediated two-phase commit and add a postcrash source-reconciliation reconciliation path.
3. Strict Linux whole-process-tree recovery needs actual delegated cgroup-v2. Default non-strict Linux direct-child custody does not guarantee grandchildren are dead after a hard host crash without a stop witness. Windows Job Object completion has not yet been accepted on actual Windows.
4. Tests consume genuine FFmpeg ProRes/HQ and PCM24 **procedural color/sine reels**, not AI actors, voices or cinematic content. Prove real frozen-take, acting, dialogue and 3D presentation coherence separately.
5. This does not authorize reusing the original developer CLI as an AI tool, publishing a creator-approved film, or removing per-reel duration/resource bounds.

## Measured local acceptance (2026-11-05)

Environment: Debian Linux, Python 3.13.5, system FFmpeg/FFprobe 7.1.5, real temporary SQLite FilmIndex and native subprocesses.

Run:

```bash
python -m unittest tests.test_nvp_master01b_native \
  tests.test_nvp_longform_review tests.test_film_index \
  tests.test_resource_scheduler tests.test_resource_supervisor \
  tests.test_worker_host_lease -q
```

**46 tests passed; zero errors.** The new MASTER-01B suite contributes nine tests, including a real 720-frame (30-second) contained AV worker, true separate-host-process hard exit after post-stop witness and cold-start recovery without duplicate publication, queued creator denial/replay, exact plan tamper refusal, initial stale-reservation refusal, source media corruption refusal, controlled active cancellation and rejection of unrelated native binaries. MASTER-01A's earlier genuine 864/1440-frame tests remain part of the combined run.

Windows and the full authored-film pipeline remain independent acceptance gates. The first full cinematic short still requires genuine performances, voices, coherent visuals, mixed sound, selective revision, human approval and real physical installed-app acceptance later.

## Next gate — NVP-MASTER-01C

Move the unapproved FilmIndex publication out of the worker into a creator-authorized, host-owned two-phase staging/commit path, with crash tests at every filesystem/SQLite transition. Connect sources from actual NVP frozen Digital Takes, B14 editorial conform and approved picture/sound workers, not procedural clips. Build a real 30–60-second coherent story scene using consistent actors and audio, then inspect and approve the finished movie. Continue keeping NSIS packaging paused per creator direction.