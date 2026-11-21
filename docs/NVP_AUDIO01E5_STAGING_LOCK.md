# NVP AUDIO-01E.5 — Cross-process staging fence and host-crash safeguards

**Status:** New cross-process locking code and tests committed; exact-head Windows/Linux CI must pass before closeout.

NVP AUDIO-01E.4 retains an SQLite row mapping the authorized render attempt to its output directory. That row prevents two cooperating hosts from approving the same directory, but it does not by itself stop an already-running worker from writing while another host performs recovery. AUDIO-01E.5 adds an OS-managed, cross-process exclusive lock for each audio staging path.

## Implementation

- `backend/nvp_audio_native_staging_lock.py`: exclusive lock on a persistent sibling `.nvp-audio.lock` file (Linux `fcntl.flock(LOCK_EX|LOCK_NB)`; Windows `msvcrt.locking(LK_NBLCK)`). A lock-holder keeps its open file descriptor until the protected operation ends. The operating system releases the lock when its owning process dies; no PID heuristic or stale-lock-file deletion is used.
- `NativeAudioHost.run_next` acquires the staging lock before transitioning the job to `running` and retains it through native worker launch, OS termination/reaping, independent output verification, and journal/ledger finalization.
- `NativeAudioHost.recover_stopped` requires the previously persisted OS-stop receipt and interrupted ledger state, then acquires the same staging lock before invoking source-verified recovery.
- `tests/test_audio_native_staging_lock.py` exercises same-process contention, lock reuse and actual OS process death while holding a lock.
- The main B14 Windows/Linux workflow now explicitly runs `test_audio_native_os_termination.py` and the staging lock test on **both** platforms.

## Critical safety boundary

The lock is an admission fence **only for cooperating native hosts**, not a defense against an arbitrary process that ignores the lock or a filesystem actor with rights to replace source/output paths. The SQLite owner row and immutable source receipts remain necessary. Existing `staging` filesystem paths must be admitted by the trusted host; no-follow descriptor-relative file operations and full path race hardening are not supplied by this increment.

A host crash can release its OS lock automatically, but **that does not prove its worker descendants are all gone**. Therefore a restarted host may not release an `ACTIVE` TaskLedger reservation or reconcile the audio unless a durable, independently verified owned-worker stop receipt exists. On Windows kill-on-close Job Objects provide an owned handle lifecycle; on default Linux process groups do not guarantee containment if a descendant escapes the group. Strong cgroup-v2 descendant containment and external guardian reconciliation remain outstanding.

## Acceptance rules

1. One native host holds exclusive staging lock while the worker is running. A second host cannot run/reconcile the same audio staging directory.
2. Killing a real lock-holding subprocess releases only its OS lock, not the prior TaskLedger reservation or immutable receipts.
3. Native termination and resume tests must pass independently on both Windows and Linux.
4. The interrupted first attempt remains `INTERRUPTED`; a new authorized and admitted attempt can finish untouched PCM chunks after trusted reconciliation.
5. A missing genuine worker-stop witness, corrupted PCM, changed source or competing lease fails closed.

**Still open:** crash-injection during SQLite/filesystem boundary transitions, a persistent guardian able to attest OS descendants after host death, strict Linux cgroup containment, full feature-film picture/sound timebase binding, professional mix/master acceptance.
