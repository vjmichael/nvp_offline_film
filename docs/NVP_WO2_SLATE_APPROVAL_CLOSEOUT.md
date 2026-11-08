# WO2 — Real SLATE native approval consistency and SQLite durability

**Status:** Implementation repair submitted, **ACCEPTANCE OPEN**, native OS results pending.
**Branch:** `nvp/wo2-slate-native-approval-consistency-20261107`.
**Review:** [PR #95](https://github.com/vjmichael/nvp_offline_film/pull/95) stacked on [WO1 PR #94](https://github.com/vjmichael/nvp_offline_film/pull/94).
**Native matrix:** `.github/workflows/nvp-wo2-slate-native-approval.yml`, Windows 2025 + Ubuntu 24.04, Python 3.11 + 3.13, pinned genuine OpenUSD 26.11. Keep WO1 independent gates open.

## Identified original failure cause

Historical SLATE-05/06 native tests reported `PermissionError: Creator approval missing, changed or revoked` during `ApprovedTaskBindings.enqueue`. This failure appeared on the positive *trusted* preview queue path.

Source audit identified the cause in `backend/nvp_slate_preview_cache.py`:

1. `SlatePreviewCache.reserve()` opens an SQLite connection with `isolation_level=None` (autocommit mode) and executes `BEGIN IMMEDIATE`.
2. It inserts an apparently `PENDING` cache row and returns a `PENDING` response.
3. The `_db()` contextmanager previously executed `yield db; db.close()` with **no `db.commit()`**; SQLite rolls back an open transaction on close.
4. The trusted creator approval check opens a separate SQLite connection and calls `cache._job(...)`; it finds **no actual PENDING reservation**, so the checker rejects the entire native task as missing/changed/revoked authorization.
5. The same missed transaction commit affected `accept_verified()`, `fail()`, and `evict()`, risking lost accepted-image cache states and failed cleanup.

I reproduced step 3 directly on local CPython sqlite3: an INSERT after `BEGIN IMMEDIATE`, followed by connection `close()` without `commit()`, resulted in **zero persisted rows**.

### Corrective code

- `SlatePreviewCache._db()` now commits only on successful scope exit when `db.in_transaction`, rolls back on **any** exception, and always closes the connection.
- Configure `busy_timeout` ahead of WAL initialization and do not reissue `PRAGMA journal_mode=WAL` on already-WAL databases; this avoids repeated journal-mode contention in concurrent host/native workers.
- In `NativeSlatePreviewHost`, a failed immutable approval binding now revokes orphaned SLATE-05/06 and pre-Take camera consent rows (audit retained), marks unregistered cache PENDING as FAILED and removes inert staging only when no durable TaskLedger task exists. Already-registered work retains staged inputs for crash recovery.
- Explicitly retain all source FilmIndex/Take SHA, exact worker/script/image identity, scene provenance, authorization expiry and original creator consent checks. No unauthorized retry or replay.

### Regression suites

- `tests/test_nvp_slate05_preview_native.py`: real trusted preview enqueue persists PENDING across a **new independent SQLite connection**, stable approved binding, deterministic denial cleanup, fault-injected transaction rollback, existing cache reuse and recovery.
- `tests/test_nvp_slate06_geometry_native.py`: strict source-native OpenUSD geometry approval; denied binding revokes without synthetic worker; pre-Take camera variant receives the same cleanup.
- Other native tests in the exact-head WO2 and WO1 matrices remain required. No FFmpeg or arbitrary browser/model-exposed native worker grants.

### Remaining acceptance and handoff

- Verify all 4 WO2 jobs run and pass at the final exact commit and all relevant SLATE-05/06 workflow gates are green; inspect real failure logs and repair any additional issues.
- Windows/LINUX native tests must show both **positive valid creator approval succeeds** and **negative invalid/revoked/mutated approval fails closed**; loss of pending cache or ledger records is not accepted.
- No installed-app or production-film acceptance is claimed by test fixture, nor is any earlier red run rewritten as a pass.
- Once proven, append run ID, tested SHA, and per-platform successes; only then mark WO2 acceptance **CLOSED**.
