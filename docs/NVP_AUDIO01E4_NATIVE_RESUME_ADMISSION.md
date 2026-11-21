# NVP AUDIO-01E.4 — Fresh native worker admission after recovered audio chunks

**Status:** Implementation and real-process regression tests committed. **Cross-platform acceptance pending exact-head CI.**

## Goal

AUDIO-01E.3 proved the NVP audio worker can be admitted under the same creator-authorization, TaskLedger memory reservation, OS-containment, and resource-watchdog infrastructure as the B14 picture pipeline. AUDIO-01E.2 can safely reconcile a source-verifiable interrupted chunk after the original worker was stopped. The missing connection was *resuming the remaining work under a newly authorized OS-contained worker attempt*, rather than executing audio processing directly inside an unadmitted recovery callback.

## Changes

`NativeAudioHost.stage_and_approve(..., resume_from=prior_job_id)` implements a fresh audio job, new approval check, and new `ApprovedTaskBindings` admission. Before staging, the trusted host requires:

- Prior audio journal state is exactly `reconciled`; prior TaskLedger reservation is `INTERRUPTED`.
- A persisted `audio_native_os_stop_receipts` record for the prior worker (reaped after the native OS termination).
- Exact unchanged source WAV paths, SHA-256 hashes, original clip plan, total duration, and staging path.
- A real in-progress source-verified PCM checkpoint, with no sample regression.
- A database-backed exclusive `audio_native_staging_leases` entry still owned by the *previous* attempt.

The staging lease transfer is serialized with SQLite `BEGIN IMMEDIATE`: compare-and-swap from the previous job to the newly authorized job. No second approval may take that directory after the first successful transfer. The new worker receives an immutable, independently sealed plan and must pass the existing approval recheck before reservation and launch.

The new attempt is launched with `launch_contained` and watched by `wait_guarded`; its child resumes existing AUDIO-01D chunks rather than overwriting them. Completion still requires independent deterministic PCM replay and the exact worker receipt. Previous interrupted job history and stop evidence remain persistent.

The fresh attempt is distinct from the prior attempt: two job IDs, independently recorded task states and receipts. No direct bypass of TaskLedger, resource admission, or native host approval is permitted for rendering the remainder.

## Added real process regression

`tests/test_audio_native_os_termination.py::test_reconciled_job_requires_new_authorized_native_attempt`:

1. Admit and launch a genuine OS-contained audio worker.
2. Wait for the first real 48kHz PCM chunk to be committed.
3. Terminate the actual worker process tree, observe `INTERRUPTED`.
4. Instantiate a new trusted native host against the same ledger and journal.
5. Recover the surviving sample checkpoint using the durable stop receipt and source replay.
6. Stage an entirely new, approved and resource-admitted audio worker attempt using `resume_from`.
7. Prove a competing second resume is refused by the directory lease.
8. Run the new worker to completion; verify original chunk bytes remain unchanged, the resumed job is `SUCCEEDED`, and the original job remains `INTERRUPTED`.

This is **real contained process execution**, not mocked worker control, but its Windows and Linux acceptance must be read from the exact current CI head. CI code existence alone does not constitute proof.

## Boundaries

The lease prevents competing **cooperating NVP host attempts**, not malicious filesystem actors or arbitrary processes ignoring the ledger. Host-crash orphan recovery still requires external OS stop attestation before releasing stale ACTIVE reservations; no process-name guess is accepted. SQLite and filesystem admission are not one atomic transaction, so failed staging can leave an unqueued journal record and must be reconciled by a future host cleanup gate.

Linux ordinary process-group containment does not guarantee descendant control if a malicious child escapes the process group; strict delegated cgroup testing remains open. Directory-fsync, no-follow path handles and OS-backed cross-process lock fencing remain future hardening. Sound remains an unapproved, audio-only technical preview—not a professional mixed/mastered film soundtrack or a verified picture+sound mux.

## Closeout

Do not mark this gate passed until exact-head Windows and Linux jobs each show actual worker termination, recovered re-admission, completed source-verified PCM replay, and previous chunk byte stability. The NVP Acting Research branch remains independent.
