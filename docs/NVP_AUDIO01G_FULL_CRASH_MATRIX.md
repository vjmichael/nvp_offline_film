# AUDIO-01G — Full 21-boundary native mux crash-injection matrix

**Branch:** `nvp/stack02c3b14-picture-conform-20261104`
**Acceptance:** Source and independent CI execution are separate. The implementation and tests are committed; exact-head Windows/Linux CI is pending. **Strict delegated Linux cgroup-v2 stays deferred and OPEN**, not silently accepted.

## Test design: actual abrupt exits, not exception-only unit tests

`backend/nvp_audio01g_fault_matrix.py` defines **21 distinct after-effect crash points**. A test process with both explicit `NVP_AUDIO01G_FAULT_TEST=enabled` and the matching `NVP_AUDIO01G_CRASH_AFTER` exits by `os._exit(93)`. No Python finally, SQLite connection destructor, or worker cleanup can fabricate recovery success.

The source-level injection is inert without BOTH explicitly set test environment variables. These controls are for isolated native test hosts, never creator-authored AI plans.

### Filesystem and FilmIndex checkpoints — 9 real-media subprocess cases

`tests/test_audio01g_fs_crash_matrix.py` creates actual ProRes 24fps video and PCM16 48kHz sound; invokes the production AUDIO-01F mux using actual FFmpeg and FilmIndex, with only the earlier B14/AUDIO-01E *upstream proof callbacks* substituted to isolate publication. Every subprocess exits abruptly at a named gate. Reopened FilmIndex and the filesystem are audited independently:

| Boundary after effect | Expected durable observation |
|---|---|
| `stage_directory_created` | Stage exists; final destination and presentation absent |
| `mov_bytes_written` | Stage contains mux result; final presentation absent |
| `mov_independently_verified` | Decoded media was checked, still unpromoted |
| `filmindex_media_ingested` | Content-addressed media may exist, but no presentation revision |
| `manifest_file_fsynced` | Manifest staged, no public output |
| `movie_file_fsynced` | Both files flushed, no public output |
| `staging_directory_promoted` | Final directory exists, FilmIndex presentation absent |
| `destination_parent_fsynced` | Final directory exists; presentation registration still absent |
| `filmindex_presentation_registered` | Genuine unapproved immutable presentation exists; native worker receipt/host completion not implied |

The actual original picture and WAV bytes must never change; a prior staging directory must not be overwritten on retry. The FilmIndex media asset copy can precede the presentation revision; an unreferenced media asset is **not** published as a finished review.

### SQLite and process lifecycle checkpoints — 12 distinct subprocess cases

`tests/test_audio01g_sqlite_crash_matrix.py` runs the *actual* `NativeAudio01FHost` staging/TaskLedger admission for five boundary cases with real project revisions and still-valid creator approval:

- `approved_grant_sqlite`
- `intent_prepared_sqlite`
- `task_queued_sqlite`
- `task_claimed_sqlite`
- `intent_running_sqlite`

For the seven completion checkpoints, the test intentionally creates a **synthetic completed-worker fixture** that exercises durable SQLite transitions and real file fsync but **does not claim to prove the real OS worker was terminated**. This avoids silently treating a fake worker as a passing Windows Job Object acceptance test:

- `worker_receipt_fsynced`
- `native_worker_reaped`
- `os_stop_witness_sqlite`
- `grant_result_sqlite`
- `intent_verified_sqlite`
- `ledger_succeeded_sqlite`
- `intent_committed_sqlite`

Each child abruptly exits at its named point. The parent reopens the database, verifies exact persisted state and resource reservation, and distinguishes intermediate ACTIVE from terminal SUCCEEDED. A coverage assertion proves **every declared fault gate has exactly one matrix case**.

### Recovery correctness checks

`tests/test_audio01g_recovery_commit_matrix.py` validates:
1. Missing trusted OS stop witness refuses inspection and cannot clear ACTIVE.
2. Incomplete media is quarantined; TaskLedger remains ACTIVE and reserved.
3. An independently verified complete result can finalize once without rerendering.
4. Crash after TaskLedger success but before intent `committed` can reconcile the journal from the same immutable SHA and existing result.
5. Conflicting verified SHA is rejected without releasing the original reservation.

The production native mux host persists a worker-stop witness **only after closing a genuinely reaped owned OS handle**. It cannot reconstruct that evidence from a crashed host with no durable stop record. That uncertainty is a safe **OPEN** gate, not automatic takeover.

## Execution and limitations

Dedicated workflow: `.github/workflows/nvp-audio01g-crash-matrix.yml` on Windows 2025 and Ubuntu 24.04, Python 3.11 and real FFmpeg. The unit tests do **not** infer success from a skip: the explicit dedicated workflow installs FFmpeg and runs the cases.

The 21-point suite verifies observable crash boundaries and safe DB/filesystem states, **not full proof of power-loss durability**. `os._exit` is process loss, not removal of host power, SSD write-cache failure, kernel panic or torn-sector corruption. The Windows Job Object native worker and watchdog remain a separate required actual process termination gate.

For final AUDIO-01G production closeout, the outstanding real native job test must kill the *actual* contained worker at each relevant stage, persist/restart under a trusted OS stop guardian, and either safely reconcile fully verifiable already-published film or preserve unverified output for operator review. **No directory with a missing FilmIndex revision is promoted into an authorized final production artifact.**

The separate Linux delegated-cgroup guardian remains intentionally deferred per the user's direction. No strict Linux guardian acceptance is claimed.

## Window-specific hardening and coverage assertion

The nine real-ProRes filesystem crash cases now launch their subprocess through NVP's actual `launch_contained` Windows Job Object adapter. The OS-owned process tree includes the Python crash worker and FFmpeg descendants, and the test closes the native process handle after the abrupt exit. This adds real Windows process-containment exercise at each filesystem point (it does not simulate host-level power loss).

`test_all_declared_crash_points_have_subprocess_cases` proves the 9+5+7 test classification is a one-to-one match with the 21 declared gates. `test_every_fault_point_is_in_actual_production_code` additionally scans the live worker/host/mux source to ensure **every declared gate is actually instrumented exactly once**, preventing a false-green test that names a checkpoint never executed.

The completion-side seven cases use synthetic worker completion to isolate SQLite durability; a true 21-way OS-worker-termination matrix is NOT claimed. It remains a separate native-host E2E acceptance task, alongside a power-loss durability test on appropriate hardware.

## AUDIO-01G next gate: genuine native late-stage worker / OS stop evidence

`tests/test_audio01g_native_late_crash_matrix.py` adds seven **real worker** late-crash executions using `NativeAudio01FHost.run_next`, NVP's actual `launch_contained` process supervisor (Windows Job Object on the Windows runner), FFmpeg-rendered 24-frame ProRes/48-kHz PCM technical media, source-immutable FilmIndex publication, and an actual child process exiting at the receipt boundary. The isolated test fixture worker is `tests/fixtures/nvp_audio01g_native_real_mux_worker.py`.

The test replaces only the expensive **upstream** B14 picture and AUDIO-01E WAV proof callbacks with known test fixture results. The real resulting MOV is independently FFprobed and its decoded audio is hashed against the input WAV. Thus this is evidence of contained real media execution and native recovery-state logic, **not a claim that the upstream B14/01E sources were fully verified inside this specific test**.

It exercises:
- `worker_receipt_fsynced`: actual child exits 93; host reaps it, persists OS stop, quarantines the reservation rather than publishing completion
- `native_worker_reaped`: host crashes after close but before durable stop witness; recovery must fail closed
- `os_stop_witness_sqlite`: source/FilmIndex complete, stop witness persisted, ACTIVE reservation remains
- `grant_result_sqlite`, `intent_verified_sqlite`: result digest and journal evolve without releasing ACTIVE prematurely
- `ledger_succeeded_sqlite`, `intent_committed_sqlite`: successful reservation release and exact post-crash journal reconciliation without rerendering

A host subprocess exits abruptly with `os._exit(93)` at each host milestone; the worker-receipt case has a real worker exit 93 and a host-side caught failure that exits 95 for unambiguous forensic attribution. A restart opens the same SQLite files and checks original picture/sound bytes, source decoded samples, worker-stop witness presence, TaskLedger reservation, journal state and independent immutable FilmIndex result. This test also checks that missing OS stop evidence blocks reconciliation.

This closes the gap **in test scope** between synthetic SQLite-only completion fixtures and true native worker execution. It still does not simulate an external host power-off, nor does it prove that a different desktop process can safely take ownership of a crashed Job Object without a surviving guardian. Linux strict delegated cgroup-v2 remains OPEN / DEFERRED.

AUDIO-01G is not production-accepted until exact-head Windows CI logs demonstrate that the native real-worker matrix passes and the full unmocked Blender source tests pass independently.
