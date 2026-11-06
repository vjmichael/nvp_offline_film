# NVP AUDIO-01E.3B — Native worker admission, containment and actual termination

**Branch:** `nvp/stack02c3b14-picture-conform-20261104`
**Status:** Implementation and real-process regression tests committed. **Windows/Linux acceptance pending** on the exact head; no claim of verified success before CI.

## Scope and integration actually implemented

AUDIO-01E.3B connects NVP's audio chunk renderer to the **existing B14 native host pattern**, rather than introducing a separate process or security architecture:

- `backend/nvp_audio01e3_native_host.py` — native-only approval, immutable source/spec binding, `ApprovedTaskBindings` and `TaskLedger` queue/admission, `launch_contained`, `wait_guarded`, process cleanup, independently replayed chunks, journal state, durable OS-stop receipt and guarded recovery.
- `tools/nvp_audio_native_worker.py` — a real child process that reads a host-sealed input plan, validates original source SHA-256s, renders through AUDIO-01D and emits an unapproved completion receipt only after sample-by-sample verification.
- `backend/nvp_audio01e3_native_journal.py` — persistent SQLite progress/transitions (fixed to explicitly close DB connections on Windows).
- `backend/nvp_audio01e2_orphan_recovery.py` — one-chunk source replay and explicit orphan reconciliation.
- `tests/test_audio_native_os_termination.py` — real-process acceptance, not mock worker controls.
- `.github/workflows/nvp-audio-native-termination.yml` — dedicated Python 3.11 Linux and Windows native termination matrix; also included in the B14 Python contract jobs so PR checks are visible.

## Production-path execution

1. Trusted desktop creator-policy callback approves a source-bound, exact-sample audio job. The host records the source SHA, immutable plan, approved creator reference, output scope, Python executable hash and worker script hash.
2. Existing `ApprovedTaskBindings` queues the job in NVP's `TaskLedger`; this does **not** launch it. Actual RAM admission reserves a budget transactionally.
3. Before launch, the same native approval policy, sealed bytes, pinned worker hash, pinned Python hash, and source-bound journal state are checked again. Revoked or mutated inputs fail closed.
4. `launch_contained` starts the worker with the same B14 OS containment backend: on Windows a memory-limited kill-on-close Job Object, and on ordinary Linux a parent-death-guarded process group with RLIMIT_AS. The latter is **not** a cgroup-v2 descendant-proof guarantee.
5. `wait_guarded` monitors live task memory pressure and wall-clock timeout. If the owned process exceeds allowed conditions, the supervisor kills that process tree, waits and closes it.
6. Successful child exit is not enough to pass: the host independently replays the complete AUDIO-01D source/chunk chain and validates the worker completion receipt before marking the journal `completed` and releasing the ledger reservation.
7. On failure after verified OS cleanup, the host records a durable stop receipt, moves the audio journal to `recovery_required`, and finishes the ledger reservation as `INTERRUPTED`. If process cleanup is uncertain, the ledger reservation remains held.
8. `recover_stopped` requires interrupted ledger state **and** a durable owned-worker stop receipt. Only then can the existing AUDIO-01E.2 source-replay reconciler advance to `reconciled`. Merely creating a new host instance never proves an abandoned OS process is gone.

## Real process tests

The test launches actual native Python worker processes, writes real 48 kHz PCM, and does not substitute a fake process class.

- **Normal completion:** task admitted, real child generates chunks, independent replay passes, journal and TaskLedger finish successfully.
- **Actual force termination:** a CI-only child option holds after the first real completed chunk. Test calls the existing `terminate_tree()` OS primitive; observes worker stopped, the journal `recovery_required`, and the reservation `INTERRUPTED`. A new NativeAudioHost instance uses the persisted stop receipt to reconcile the audio after restart.
- **Resource watchdog:** live worker holds after a real chunk; measured-pressure sampler reports critical RAM; `wait_guarded` terminates the actual contained child and triggers durable interrupted state.
- The CI-only hold option is rejected unless `NVP_NATIVE_TERMINATION_TEST=1`; it does not appear in the production sealed input plan.

## Remaining production/security gaps

- The normal Linux process-group path has weaker post-parent-death descendant guarantees than delegated cgroup-v2 mode. Strong descendant containment requires verified cgroup support and OS-specific tests.
- The approved host currently handles first-attempt execution and post-kill **reconciliation**. Re-running a `reconciled` audio job under a *new* reserved/admitted worker attempt is not yet wired; never directly bypass the TaskLedger to finish recovery.
- The native host is currently invoked as a trusted Python API. Desktop UI command mapping, trusted creator-event persistence/revocation integration and safe no-follow file descriptors require their own acceptance.
- Per-job output-root lease/fencing across separate native host instances, checkpoint directory fsync and crash-injection at every database/filesystem boundary are not fully implemented.
- A recovered chunk set is **unapproved technical audio**, not a human-approved mix, master, full-length picture conform or mux.
- The pinned worker file hash and OS process-control logic depend on the host keeping the source checkout and native runtime protected from untrusted writes.

**Closeout rule:** Only claim native worker termination **verified** after the exact branch-head Windows and Linux CI runs show actual success, with the worker process actually started and killed in each platform's job logs.
