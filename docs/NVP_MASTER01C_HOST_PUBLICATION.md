# NVP-MASTER-01C — Host-owned, two-phase technical film publication

**Date:** 2026-11-05  
**State:** Implemented and locally verified at a bounded 30–60 seconds on Debian; Windows and delegated Linux OS whole-tree crash acceptance remain open. This is **not** AI-generated acting, creator picture-lock, a professional feature, or final film approval.  
**Previous gate:** [MASTER-01B native supervisor](NVP_MASTER01B_NATIVE_SUPERVISED_REVIEW.md); [MASTER-01A AV assembly](NVP_MASTER01A_LONGFORM_TECHNICAL_REVIEW.md).

## Reason for the design change

MASTER-01B brought the existing technical AV renderer under verified creator-scoped admission, OS containment, an exclusive host lease, cancellation and durable stop receipts. But its legacy worker could still publish an *unapproved* FilmIndex presentation before the native host independently examined the result. If the worker crashed at the index/receipt boundary, recovery had to distinguish a published-but-unconfirmed result.

MASTER-01C adds an opt-in **host-staged publication mode** to the existing trusted native host. The same serializer, creator-action verifier, task ledger, worker lease, resource watchdog, protected command launcher and FilmIndex are reused. No new privileged AI layer, database of competing film objects, generic shell executor or added model manager is introduced.

## New state contract

1. **Authorize and enqueue.** The native host binds the exact creator action to the project, review ID, ordered reel object IDs/revisions, source document and media SHA-256, precise frame count, RAM budget, time deadline, selected publication mode and pinned FFmpeg/FFprobe hashes. The seal also binds Python/worker/MASTER-01A/MASTER-01C module hashes; stale code revisions fail closed.
2. **Prepare in OS containment.** `tools/nvp_master01b_native_worker.py` runs with `publication_mode=host_staged`, calls `backend/nvp_master01c_two_phase.py::prepare_unpublished` and creates a new project-owned staging directory containing `prepared.mov`, `prepared.json` and a durable worker receipt. **It does not call FilmIndex media registration or revision publication.**
3. **Verify original media.** The worker probes real ProRes HQ/PCM24 streams, proves 24fps and 48kHz AV clocks, verifies source/review packet timestamps, compares all compressed picture packets and decoded PCM samples, rehashes original SHA-indexed source media, and writes an fsynced canonical manifest. Prepared output has an enforced size ceiling.
4. **Record OS stop.** Only after the contained native worker has stopped does the host persist a stop witness in the existing TaskLedger journal. If there is no trustworthy stop witness after a crash, the reservation remains held and work must not be blindly retried.
5. **Host-owned publication.** The trusted host independently re-reads the sealed preparation, re-probes original media, checks identical source-revision bindings and receipt hashes, honors controlled cancellation before publication, and uses `FilmIndex.put_media_file` followed by `register_revision` for one **unapproved** presentation. The existing FilmIndex governs immutable objects and dependency edges.
6. **Verify and complete.** After FilmIndex publication, the host independently reopens and checks the exact source-associated movie before marking the task `SUCCEEDED` and releasing reserved resources. Its output is `VERIFIED_TECHNICAL_REVIEW_UNAPPROVED`, never an approved final master or DCP.

## Crash boundary policy

| Crash location | Expected behavior |
| --- | --- |
| Before native worker launch | No effect, queued or safely failed; no invented completion |
| During staging/FFmpeg work | No FilmIndex review publication; protect original sources; preserve evidence for recovery |
| Worker stopped, before host publication | Recover from the exact immutable stage and existing approval binding; do not rerun FFmpeg |
| After media blob stored, before FilmIndex revision commit | Content-addressed blob may exist; later host publication is idempotent, with no duplicate revision |
| After FilmIndex revision commit, before TaskLedger success | Reopen the exact existing revision, verify source/packet/audio evidence, finalize the same task; no duplicate movie |
| Stage media/manifest altered | Reject before publication; do not claim verified output |
| Creator cancels after worker stop but before host commit | No FilmIndex publication, task cancelled and resource reservation reconciled after stop |
| Missing post-stop witness on crash/restart | `STALE_UNVERIFIED`, reservation retained; external OS reaping evidence required |

A native worker result does not grant permission. The host retains the creator-check and post-stop publication boundary. Unknown outcomes are not retried as if they were side-effect-free.

## Implemented files

- `backend/nvp_master01c_two_phase.py` — independent preparation/verification and idempotent FilmIndex commit functions.
- `backend/nvp_master01b_native_host.py` — new opt-in `publication_mode='host_staged'` and trusted host commit/reconciliation; default legacy `worker_publishes` remains for compatibility.
- `tools/nvp_master01b_native_worker.py` — preparation-only branch and exact source-bound receipt; existing legacy branch preserved.
- `backend/nvp_longform_review.py` — accepts explicit pinned FFmpeg for independent reopen.
- `backend/nvp_resource_supervisor.py` — optional host-owned cancellation predicate, no invented progress.
- `tests/test_nvp_master01c_two_phase.py`, `tests/test_nvp_master01c_native_host.py` — native media/approval/recovery tests.

## Local validation

Environment: Debian Linux, Python 3.13.5, native FFmpeg/FFprobe 7.1.5. Results recorded in the engineering-state ledger and source tests.

- **5/5** MASTER-01C two-phase unit/native staging tests: unpublished original, content integrity refusal, interrupted blob storage, simulated postcommit crash, source tampering.
- **6/6** MASTER-01C OS-contained native host tests: unapproved 30s and 60s host publication, actual process hard crash before publication with exact-stage recovery, actual process hard crash after commit with no duplicate revision, tampered stage refusal, postworker cancellation before commit.
- **9/9** legacy MASTER-01B host tests continue passing following the new mode addition.
- **7/7** previous MASTER-01A native long-form tests and **30/30** related FilmIndex/scheduler/supervisor/lease tests pass independently.

**57 tests across these suites**, executed in bounded groups to respect the development container's command timeout. These results do not substitute for actual Windows Job Object installed-app tests, delegated Linux whole-tree cgroup acceptance, or a coherent AI-generated short film.

## Known limitations and next implementation

- `commit_prepared` is an **internal trusted-host operation**, not a public endpoint or model-facing action. A caller that embeds arbitrary Python code in the native NVP process already has application authority; Lu per-user-turn authorization remains a later host integration responsibility.
- `host_staged` is opt-in while earlier MASTER-01B `worker_publishes` code exists. For new film work the host-staged path is the preferred candidate; retire legacy only after migration and target-OS native acceptance. Previously queued old plans may require explicit restaging if their pinned code or schema changed; do not silently replay them.
- A crash between output creation and the durable worker-stop witness cannot automatically free reservations without verified OS cleanup. Strict Linux cgroup-v2 mode requires actual delegation; the non-strict Linux demonstration does not prove orphan-free grandchildren after an uncontrolled crash. Windows Job Object tests remain queued/unverified.
- Current accepted reels are procedural color and sine-tone tests. The next meaningful film gate, **MASTER-01D**, must feed this path with actual creator-approved Digital Takes/presentations and authored performances, synchronized real dialogue/music/ambience, source-aware multi-shot edit choices, then validate generated 30–60-second cinematic content. Human review and approval of the film are independent from technical publication.
- No NSIS/Windows installer work should restart unless the creator explicitly requests it.