# NVP-INT-LU-01F-R1 — NVP-side durable IPC operation lifecycle

**Local NVP-only implementation candidate** (2026-11-21). Prepared from NVP draft PR #161 at exact SHA `7ece5eb6efec8007fed867bfcf86a59770f081a5`. This package has **not** been published to the PR branch. Lu Core source is untouched. No new branch/PR/CI workflow and no auto-merge.

## Deliverables

- `backend/nvp_lu_operation_journal.py`: pure Python 3.11+ SQLite journal with `WAL`, `synchronous=FULL`, `BEGIN IMMEDIATE`, explicit persistent schema version and bounded metadata. It never opens a Lu transport, starts a worker, invokes a capability, enrolls a secret or grants effects. Existing native Rust IPC remains fail-closed.
- `tests/test_nvp_int_lu_01f_r1.py`: 17 local focused tests with independent-process hard exit, concurrency, replay refusal, cancel-ack and terminal distinction, epoch isolation, revocation, and restart reconciliation. Test-only callbacks returning True are *not* real host authentication.
- Independent `storage_guard`, per-operation supervisor `authorize(action, scope)` and authenticated `verify_receipt` / `verify_ack` hooks. No test fallback is built into the journal. **Installed Windows production must use actual host-protected EFS/ACL/identity custody; this candidate does not prove that.**

## Bound identities and durable states

Each immutable operation is keyed by Lu's `OriginRefs` (workspace, conversation, original user turn, task, operation), typed NVP capability ID/version, effect class, canonical TypedValue input digest, ordered ObjectRef collection digest, deadline, *host-minted session ref* and *Lu Core epoch ref*. A canonical SHA-256 request digest is stored. Reusing an operation ID with changed turn, capability, effect, typed input, object references, deadline, session or epoch hard-fails. Duplicate identical `prepare()` returns an inert snapshot and NEVER dispatches or authorizes again.

States: `PREPARED` → `IN_FLIGHT` → `TERMINAL` (only externally verified `APPLIED`, `REFUSED`, `FAILED`, `CANCELLED`) or `UNCERTAIN`. A supervisor restart reclassifies all recorded in-flight operations to `UNCERTAIN`, with **no automatic redispatch**. A host `TERMINAL_STATE_UNCERTAIN` receipt preserves the ambiguous state; it never becomes a fictitious failure/success and may be reconciled to a genuine verified terminal later. A second conflicting terminal is refused. Existing terminal receipts cannot be overwritten. Original user-turn and epoch bindings remain durable across reconnection.

Cancellation and revocation set durable flags. A `CancelAcknowledged.signal_recorded` **only records host acknowledgment of a cancel signal**, not worker termination, effect rollback, or terminal cancellation. Revocation prevents fresh dispatch, but does not retroactively erase an already-applied effect. A verified `APPLIED` receipt after a cancel or revoke records the observed outcome honestly. Any reissued effect must use a **new user-authorized operation**, not replay an uncertain old one.

## Local tests and limits

Run from repository root after copying paths:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_nvp_int_lu_01f_r1.py' -v
python3 -m compileall -q backend/nvp_lu_operation_journal.py tests/test_nvp_int_lu_01f_r1.py
```

This is a **locally tested source candidate**, not a full exact-checkout regression or a compiled Windows installed runtime. Integration with NVP's existing FilmIndex/TaskLedger supervisor and Lu's true `Cancel`/`Reconcile`/`OperationEvent` Protobuf transport is **next**; the journal provides the persistent side but deliberately exposes no producer send. A source file can be present without claiming production readiness.

**Unfinished acceptance:** independent real Windows `CancelAcknowledged` and `ReconciledOperation` exchange, installed NVP-signer + Lu Core peer/credential broker, original-user-turn effect grants, supervisor/FilmIndex binding, true receipt attestation and immutable external custody, crash/power-loss testing on actual installed Windows, native Debian Rust (separate from Ubuntu), and CONV-12/WO3 full-cohort reconciliation.

## Repository publication discipline

Keep PR #161 on its existing `nvp/mainline-convergence-20261113` branch; do not publish these files until all original exact-head workflow runs have terminal dispositions. After review, stage a **single** non-forced successor containing this task and other qualified independent local work, and perform focused native acceptance without per-task stacked CI. Update only the canonical `docs/NVP_DATA_ALL_TASK_LEDGER.md` with accurately scoped status. Do not create a new branch, PR, duplicate task journal, or CI trigger.
