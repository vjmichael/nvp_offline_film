# NVP Windows native audio acceptance — Linux strict-cgroup deferred

## Scope decision — 2026-11-04

The strict Linux delegated cgroup-v2 host-crash/descendant gate remains **OPEN / DEFERRED** because the available container exposes a read-only `/sys/fs/cgroup` mount. No local kernel delegation is claimed, and no skipped hosted-runner test may be counted as genuine strict Linux acceptance.

The Linux cgroup guardian code and its optional dedicated self-hosted workflow stay intact for later verification. Do **not** downgrade strict Linux production mode silently just to pass CI.

## Current Windows focus

AUDIO-01E Windows native host uses the existing suspended-process, assign-before-resume Job Object launcher and `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Tests now cover:

- Actual native audio worker normal completion, force-kill after a real PCM chunk, watchdog-triggered termination, durable worker-stop receipt and a fresh authorized TaskLedger attempt to resume unchanged samples.
- Real independent grandchild launched into a separate Windows process group: kill the owning Job Object, verify the grandchild's Windows process handle signals termination.
- Last-host-handle close while worker/grandchild are alive: verify Windows Job Object kill-on-close terminates the descendant.
- Real AUDIO-01F ProRes/PCM16 mux executed inside the existing contained launcher, independent audio decode verification, and force-kill of the live contained mux worker after writing a real technical-review MOV.

Tests are in `tests/test_audio_windows_job_object_descendants.py`, `tests/test_audio_native_os_termination.py` and `tests/test_audio01f_windows_contained_mux.py`. A dedicated fast CI matrix is in `.github/workflows/nvp-audio-windows-job-object.yml`.

## CI failure diagnosed and repaired

The original audio native host wrote grants, approval outbox, stop receipts and acknowledgments inside `TaskLedger._db` connections whose connection wrapper uses SQLite `isolation_level=None`. Several explicit `BEGIN IMMEDIATE` transactions were not followed by `db.commit()`. Closing the connection rolled back the writes; on the next step the host reported `Unrecognized legacy admission; quarantine only` even for a newly staged job. Host transaction commits are now explicit. Crash fixture inserts were corrected to persist before restart, so they actually test durable state rather than uncommitted state.

The previously completed Linux job `126846440306` failed because the missing test-fixture commit made `audit_incomplete_admissions()` return zero rows. The Windows job `126846440524` failed before native worker launch because of the missing grant/outbox commit.

## Evidence criteria before closeout

Do not declare success from code or a queued workflow. Require an **exact latest commit SHA** Windows job that reports every real worker test, process handle assertion, approval/outbox recovery, and contained FFmpeg mux as passed. Check the job's actual logs and no unexpected skipped tests.

AUDIO-01F currently offers a technically verified 24 fps / 48 kHz review mux, bounded by the existing B14 480-frame picture gate. Its integrated user-authorized, TaskLedger-admitted production mux is a separate engineering gate; current contained FFmpeg test does not constitute full creator authorization of arbitrary real projects.

## Next engineering work

- Resolve exact-head Windows CI regressions and retest.
- Integrate AUDIO-01F mux as a separately approved and resource-supervised native task, without expanding the trusted surface for arbitrary commands or filesystem paths.
- Production-length picture conform and professional loudness/true-peak audio QC.
- Revisit strict delegated Linux cgroup-v2 evidence only when a writable delegated host or explicitly configured self-hosted runner exists.

## Windows post-exit verification recovery correction

The native audio host now records `worker_reaped=True` before discarding a closed Windows PROCESS/Job Object handle. If the independent PCM verifier fails *after* successful worker exit, the error path no longer invokes `poll()` on a released Windows PROCESS handle. It persists an OS-stop witness only after a genuinely reaped worker, transitions the journal to recovery-required, and leaves the TaskLedger record `INTERRUPTED` rather than falsely completing it.

A real-worker regression test `test_verified_worker_exit_then_host_verifier_failure_is_recoverable` injects the host-side verification failure after the child has genuinely exited. Its Windows acceptance remains pending the exact current CI run.

**Deferred unchanged:** Linux cgroup-v2 delegated host-crash acceptance stays OPEN and is not part of Windows closeout.
