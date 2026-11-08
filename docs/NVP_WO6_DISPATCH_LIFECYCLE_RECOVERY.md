# WO6 — Exact native dispatcher lifecycle, cancellation and recovery

**Date:** 2026-11-07 (America/Phoenix).
**Implementation:** `nvp/wo6-exact-dispatch-recovery-20261107` stacked on WO5 PR #97.
**Acceptance:** OPEN pending actual exact-head native execution and installed Windows evidence.

## Root cause: desktop notice and durable claimed task could disagree

The native director desktop previously wrote `queued["task_id"]` into one host-owned
in-memory operation-family dispatch queue, but its consumer invoked
`host.run_next(timeout_seconds=240)`. The underlying approved binding
chose the *current scheduler head* for that worker family, without verifying
it was the ID from the popped desktop notice. Under a cancellation, reordered
priority, competing scheduler or multiple GUI notices, this could execute
a different still-queued task than the notice that initiated dispatch. An
accurate source and sealed spec are necessary but not sufficient to prove
the correct consent/dispatch correlation.

## Implemented fix

- Desktop dispatch now passes **`expected_task_id=trigger`** through the
  first-party Take, director shot, and data decision hosts into the existing
  creator policy binding and SQLite resource scheduler.
- The binding tests that the **actual current priority head** matches the
  expected ID before preflight and rechecks the sealed approval; the scheduler
  verifies the exact match **inside `BEGIN IMMEDIATE` before reserving RAM
  or transitioning QUEUED→ACTIVE**. Any race returns `NOT_CLAIMED`,
  `admitted=False`. It does not run another task, bypass priority, invent
  process execution or silently admit canceled work.
- All existing non-desktop host `run_next()` and generic resource-ledger
  `claim_next()` users retain their original default priority-driven API;
  this is a narrow additional exact-task guard, not a new queue subsystem.
- Durable cancellation still uses the original `WO6DurableRecovery` cancel
  transaction and worker-side SQLite admission: a queued canceled notice
  cannot indirectly admit a different task. ACTIVE worker cancellation,
  OS process-tree stop and post-commit receipt reconciliation are handled
  by their existing native host/ledger contracts, not a fake in-memory undo.
- Close drops unstarted ephemeral notices; QUEUED durable SQLite tasks are
  **not automatically replayed after a restart**. The creator may inspect
  them and explicitly cancel. No silent reauthorization or automatic retry
  of an immutable FilmIndex source mutation.

## Regression groups

- `tests/test_resource_scheduler.py`: refused out-of-order priority notice
  with **zero memory reservation**, explicit correct-head admission, stale
  canceled notice not accidentally claiming another task; original FIFO,
  resource pressure, two-process single-winner claims retained.
- Same suite: genuine `ApprovedTaskBindings` preflight verifies the sealed
  creator-approved spec remains bound to the expected task at admission.
- `tests/test_nvp_wo6_desktop_bridge.py`: actual queued task ID passed to
  host worker; original bounded queue and shutdown tests updated for exact
  notice argument; task received before close versus dropped afterward.
  Reopens a **real TaskLedger SQLite file** in a fresh desktop bridge and
  verifies a QUEUED task is not automatically executed and can be canceled
  only after a new host-owned OS confirmation.
- `tests/test_nvp_wo6_native_take_action.py`,
  `tests/test_nvp_wo6_native_shot_action.py`,
  `tests/test_nvp_wo6_native_data_action.py`: existing true source-bound,
  separately contained original writes, human/native grants and receipts
  remain mandatory.
- `tests/test_nvp_wo6_recovery.py` and
  `tests/test_nvp_wo6_kernel_attestation.py`: durable cancellation,
  crash-after-source-commit reconciliation, live Windows named Job Object,
  and kernel proof of stopped descendants remain distinct evidence gates.

Dedicated native matrix:
`.github/workflows/nvp-wo6-exact-dispatch-recovery.yml` runs Windows
2025 and Ubuntu 24.04, Python 3.11 and 3.13, genuine `usd-core==26.11`,
and Windows pywin32 Job Object support.

## Acceptance and honest limitations

**OPEN:** exact-head four-cell native results, OS process-tree termination
after a real hard host death, installed Windows NVP.exe creator click-to-task
and verified restart/recovery, physical UI task status under resource pressure,
genuine film/sound scene editing, finished-film acceptance and SMPTE Bv2.1.

A queued-but-not-claimed task is **not** a scheduled retry and does not
inherit new-session permission. The user needs to decide whether to cancel
or resubmit a fresh authorized action. No content-addressed Take/DCP or
original source is rewritten by this safety repair. GitHub CI queueing or
source submission is not accepted as execution evidence.
