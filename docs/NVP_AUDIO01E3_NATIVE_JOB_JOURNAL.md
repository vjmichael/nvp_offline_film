# NVP AUDIO-01E.3 — Native audio job journal and recovery admission

> **Tracking notice (2026-11-13/14):** This is a historical/technical reference, **not an active task ledger or backlog**. The sole current NVP task journal, priorities, statuses, acceptance gates and branch/PR dispositions are maintained in [NVP_DATA_ALL_TASK_LEDGER.md](NVP_DATA_ALL_TASK_LEDGER.md), through draft convergence [PR #161](https://github.com/vjmichael/nvp_offline_film/pull/161). Older branch/PR claims below are source snapshots; preserve technical evidence but do not use them to decide current task priority.


**Status:** First host-side contract committed; exact-head Windows/Linux CI pending. This gate does **not** yet launch an audio worker inside Windows Job Objects or Linux process groups, and it does not independently prove trusted OS process-tree termination. Those functions exist elsewhere in NVP's B14 native host architecture and must be explicitly connected in the next increment.

## Existing NVP infrastructure

The NVP production branch already has:
- `backend/nvp_b14_native_conform.py` — trusted creator-policy authorization, `ApprovedTaskBindings`, `TaskLedger`, `launch_contained`, `wait_guarded`, source-specific receipts.
- `backend/nvp_resource_supervisor.py` — resource-pressure and timeout watchdog for *owned* OS-contained workers.
- `backend/nvp_audio01d_chunked_recovery.py` — deterministic, receipt-bound audio chunks and cooperative pause/cancel.
- `backend/nvp_audio01e2_orphan_recovery.py` — source-replayed orphan reconciliation, refusing malformed/unknown artifacts.

This increment adds the missing **audio-specific durable lifecycle ledger**, not a second native process supervisor.

## AUDIO-01E.3 code

- `backend/nvp_audio01e3_native_journal.py`
- `tests/test_audio01e3_native_journal.py`
- CI: `.github/workflows/nvp-stack02c3b14-conform.yml`

`AudioJobJournal(database)` stores one SQLite job record and append-only state transitions. Job admission requires a **trusted caller-supplied** `verify_creator_action(creator_event, exact_scope)` returning literal `True`, binds SHA-256 hashes of each source WAV, the sample-exact edit plan, output directory and bounded duration, and uses immutable canonical JSON and SHA-256 spec digests.

Journal state transitions are serialized by SQLite `BEGIN IMMEDIATE` with generation compare-and-swap and monotonic sample progression. Allowed transitions are explicit: approved → running / recovery-required / failed; running → recovery-required / completed / failed; recovery-required → reconciled / failed; reconciled → running / completed / recovery-required / failed. Completed and failed jobs are terminal.

`recover(job_id, attest_stopped=trusted_host_callback)` requires the job in `recovery_required`. It refuses to reconcile unless the trusted host attests the worker is stopped and that it has exclusive control over the staging area. It rechecks source SHA-256, calls `reconcile_next_chunk`, then audits the checkpoint and commits a `reconciled` journal transition. A callback returning anything other than literal `True` fails closed.

This is **not** proof of the host attestations. Callers outside the trusted native host could trivially provide a permissive callback, so only native integration with the actual OS-owned worker handles is acceptable for a security/containment claim.

## Test cases

- Creator refusal cannot create an approved job.
- Duplicate job IDs fail rather than overwrite records.
- Illegal and stale generation transitions fail.
- On restart, pending reconciliation is refused without a worker-stop attestation.
- One legitimate orphan from a multi-stem render is source-replayed and adopted, then standard chunk rendering continues without rewriting earlier chunks.
- Original source changes reject recovery.
- Events persist in SQLite in transition order.

## Remaining work / acceptance before calling AUDIO-01E.3 complete

1. Use real `ApprovedTaskBindings`, `TaskLedger` and the repository's `launch_contained` worker to create the AUDIO worker entrypoint and *host-held* creator approval. Never accept an AI/browser callback as authority.
2. Prove host retains identity/ownership of actual worker OS handles; abort/wait/reap the whole worker tree before any E.2 reconciliation, including resource pressure and host crash.
3. Add exclusive single-job lease/lock (including stale lease fencing), safe path admission, no-follow creation and directory-fsync at every durable transition.
4. Only mark `completed` after independent chunk replay and FilmIndex/WAV verification. The generic journal `transition` API alone is not an acceptance authority.
5. Run real process kill and injected crash tests at chunk body, receipt swap, `.new`, WAV assembly and FilmIndex commit stages on Windows and Linux.
6. Publish a signed or externally trusted result witness only after the complete chain is actually tested. No fabricated status based on a test file existing.

AUDIO-01F remains the independent full-film picture/timebase binding gate. Model-proposed audio edits never authorize native execution or creator approvals.
