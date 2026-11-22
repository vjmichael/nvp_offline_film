# NVP AUDIO-01E.6 — Strict descendant containment and crash-boundary checks

**State:** Code and failure-injection tests committed; native CI verification pending. This is NOT blanket production completion.

## 1. Linux parent-crash and descendant containment

NVP already implements delegated cgroup v2 worker containment in `backend/nvp_worker_linux_cgroup.py`, including the independent guardian, `cgroup.kill`, `memory.max`, `pids.max`, and kernel membership confirmation. Previously the AUDIO host used the weaker default Linux process-group mode.

`NativeAudioHost(..., strict_linux_tree=None)` now defaults to strict delegated cgroup-v2 protection on Linux. If the host has no verified delegated cgroup, launching the audio worker **fails closed** instead of silently substituting process groups. Windows continues to use the existing kill-on-close Job Object. `strict_linux_tree=False` remains available explicitly for the process-group regression tests but **does not satisfy the strict production guardian gate**.

`tests/test_audio_linux_strict_cgroup.py` checks failure without delegation and, on truly delegated Linux hosts, launches a genuine host subprocess and worker that creates a detached grandchild. It then simulates abrupt host death via `os._exit` and checks the real kernel cgroup is emptied by the guardian. A hosted CI runner without cgroup delegation will SKIP the real guardian test. That skip is **not a success** for strict descendant termination: the test must also run and pass in a controlled delegated systemd scope before this gate closes.

## 2. Crash during checkpoint replacement

`backend/nvp_audio_checkpoint_stage_recovery.py` adds source-verified `reconcile_checkpoint_stage`. It handles `checkpoint.json.new` only under a stopped-worker attestation and the same audio staging lock. It validates source hashes, the previous committed checkpoint, canonical staged JSON, immutable prior receipts, exact next chunk sample range, exact per-stem and composite PCM bytes and SHA-256 receipts. It permits precisely one next receipt or an independently consistent completion marker, then atomically replaces the checkpoint. Changed historical receipts, suspicious artifacts, missing PCM, symlinks and altered source audio fail closed; nothing is silently discarded.

`AudioJobJournal.recover` now reconciles a valid staged checkpoint before the existing orphan-chunk routine. It does not treat a mere `.new` presence as an approval to modify media.

`tests/test_audio_checkpoint_stage_recovery.py` injects genuine source-backed staged files, corruption, forged history, no-op absence and invalid attempts to rewrite terminal checkpoints. The normal renderer must subsequently resume and prove PCM replay.

**Limits:** This does not guarantee power-loss atomicity across all filesystems; directory fsync, safe descriptor-relative open/rename and independent publication attestation still need a dedicated durability pass. An existing complete checkpoint after interrupted final publication requires separate authorized completion reconciliation.

## 3. Crash between SQLite admission and queue publication

The audio journal, grant/lease row, and TaskLedger queued task are currently in separate transactions. A host crash can leave an approved journal and persisted grant that **never reached** `ApprovedTaskBindings.enqueue`.

`NativeAudioHost.audit_incomplete_admissions()` performs a read-only audit of this split-commit condition and reports `QUARANTINED_NEEDS_NATIVE_AUDIT`. It does not invent task entries, grant execution authority, release reservations or create false worker-stop witnesses. `recover_stopped` now fails explicitly if the TaskLedger row is missing. `tests/test_audio_admission_crash_gap.py` injects this precise condition and verifies it remains non-runnable.

**Remaining:** A transactional outbox or shared durable admission transaction is needed for automatic reconciliation across the SQLite boundary. Audit/quarantine is safer than guessing, but is not automatic crash recovery.

## Closeout gates

1. Windows Job Object actual-kill, watchdog, restart and new-worker resume tests pass at exact head.
2. Linux process-group tests pass, while the **strict guardian host-crash/escaped-descendant test separately passes in a genuinely delegated cgroup environment**.
3. Staged checkpoint and admission-gap fault injection pass on both systems.
4. Native host never releases stale ACTIVE reservations or treats skipped tests/partial media as verified final sound.
5. Only after all above and filesystem transactional durability can full AUDIO-01E crash/restart hardening be called production accepted.

AUDIO-01F (film picture/audio sync) remains separate; no output in this gate is a director-approved soundtrack or master.
