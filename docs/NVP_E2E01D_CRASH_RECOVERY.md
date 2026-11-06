# NVP-E2E-01D — Whole-Workflow Crash and Recovery Acceptance

**Gate: OPEN.** Coordinator durability repairs and hard-kill test matrix are
committed, but native worker kill/recovery, actual filmmaking workflow,
Windows/Linux CI and director-approved full-export acceptance are still open.

## Purpose

An installed standalone NVP alpha must survive a power loss, abrupt process
termination, worker crash or interrupted disk/SQLite transaction without:
- claiming a successfully rendered, creator-approved or DCP-delivered film
  when the native process never stopped or independent verification failed;
- silently releasing ACTIVE RAM reservations without a verified OS-stop
  witness;
- reissuing the same approved work or spending a creator event twice;
- overwriting original frozen takes, picture edits, PCM24 masters or output;
- accepting a false FilmIndex revision, wrong source package, or altered
  media checksum on application restart.

These controls must remain independent of Lu or any model runtime.

## Repairs delivered in E2E-01D

The E2E-01B chain previously persisted a B13 import ticket *after* calling
`NativeB13ImportHost.stage_and_approve`; the same hazard existed during
`NativeB14ConformHost.stage_and_approve`. A hard crash in either interval
could orphan a queued native worker and permit the duplicate submission to
be attempted after restart.

The chain now writes an SQLite handoff before either external native call:
- `IMPORT_STAGING_UNCERTAIN` before B13 staging, with a unique placeholder
  task key under a per-presentation unique constraint.
- `CONFORM_STAGING_UNCERTAIN` before B14 staging, after the exact B13
  immutable edit SHA has been verified.
- On a matching host ticket, an atomic state transition commits the actual
  worker task ID. A missing/incorrect host result leaves the state uncertain
  and does not automatically release resources or retry.
- `reopen` surfaces a native-reconciliation requirement for uncertain work.
  It does not guess which OS worker ran or succeeded.

The E2E-01C finishing coordinator already records
`AV_STAGING_UNCERTAIN` before AUDIO-01J staging and
`DISTRIBUTION_UNCERTAIN` before AUDIO-01K publication. The K-stage can be
reconciled only from the original K-host's verified publication receipt.

## Crash matrix (committed; CI execution pending)

`tests/test_nvp_e2e01d_process_crash.py` launches an **independent Python
process** and invokes `os._exit(93)` at these points:

| Crash boundary | Durable state required on restart |
|---|---|
| B13 stage after durable intent, before host returns | IMPORT_STAGING_UNCERTAIN, placeholder ID, no automatic retry |
| B14 stage after verified edit, before host returns | CONFORM_STAGING_UNCERTAIN, exact edit identity intact |
| AUDIO-01J final AV stage after durable intent | AV_STAGING_UNCERTAIN, no invented native AV job |
| AUDIO-01K mezzanine publication after AV verification | DISTRIBUTION_UNCERTAIN, approved AV identity preserved |
| TaskLedger admission after active RAM reservation | ACTIVE with reserved=1 and original RAM budget retained after process death |

The parent inspects SQLite **after the child is gone** and refuses any
fabricated `SUCCEEDED` task or final master. It also instantiates fresh
Studio, FilmIndex, TaskLedger and original native B13/B14 or I/J/K hosts,
reopens the coordinator, and verifies the uncertain state still requires
native reconciliation. A separate ledger instance reopens the live RAM
reservation to ensure it is not silently freed.

`tests/test_nvp_e2e01b_native_handoff.py` also covers staging exceptions,
exact edited revision, duplicate submission rejection, and explicit
unverified-output states. `tests/test_nvp_e2e01c_finishing.py` covers
AV publication, creator approval identity, failed verification, no
double-spend/replay, and uncertain distribution custody.

**Evidence limitation:** The hard-kill subprocesses run genuine SQLite and
real host-object setup, but downstream native stage functions are patched
to inject the death. They DO NOT prove that real FFmpeg/Blender/JPEG2000
children, Windows Job Objects, or Linux process trees were terminated.
Actual native host OS failure acceptance is a separate remaining gate.

## CI

`.github/workflows/nvp-e2e01d-recovery.yml`

- Windows Server 2025 × Python 3.11 and 3.13.
- Ubuntu 24.04 × Python 3.11 and 3.13.
- Must run the real process-death suite and E2E-01B/01C regression suites.
- A compile-only result or a queued/skipped job does not count as accepted.
- This workflow uses PR or explicit dispatch, not duplicate simultaneous
  push and PR triggers, to limit queued runner congestion.

## Remaining production crash/restore acceptance

- [ ] Exact HEAD E2E-01D CI jobs pass all four matrix cells.
- [ ] Real AUDIO-01I mastering worker failures at every filesystem/SQLite
      checkpoint in `nvp_audio01i_fault_matrix.py`.
- [ ] Real AUDIO-01J worker interruption before and after mux staging,
      container stop, FilmIndex registration, publication and ledger finish.
- [ ] Real AUDIO-01K creator event/film copy/manifest/rename/index crash
      boundaries; repair and reopen from original host custody.
- [ ] Actual B13/B14 native worker termination and persisted job/host
      recovery. Include  Windows Job Object and Linux OS process-tree evidence.
- [ ] Native worker resource watchdog failures, partial output cleanup,
      concurrent creators, disk full, missing binaries, changed hashes,
      and destination symlink/ancestor substitution.
- [ ] No false creator approval and no FilmIndex revision without complete
      source custody throughout original B12→B13→B14→I→J→K chain.
- [ ] Explicit operator-driven native reconciliation for uncertain B13/B14/J
      staging; unique native-grant discovery and safe recovery without
      duplicate work are not yet implemented.
- [ ] Installed Windows NSIS app close/reopen and full project render.
- [ ] E2E-01E/01F desktop and theatrical acceptance remain separate.
- [ ] All downstream DCP-o-matic/DcpDoctor QC still required, and
      `dcp_delivered` must remain false until real cinema approval.

**Closeout decision: IMPLEMENTATION IN PROGRESS; NO NATIVE CRASH ACCEPTANCE YET.**


## 2026-11-04 native OS and film-wide hardening

New source tests and acceptance gates on the development branch:

- `tests/test_nvp_e2e01d_native_tree.py` uses the **real**
  `backend.nvp_worker_containment.launch_contained` API. On Windows it
  creates real Job Object worker and grandchild processes and verifies
  explicit termination and kill-on-close, including the case where the
  direct worker exits first. On Linux it exercises actual worker-group
  termination and checks that ordinary PDEATHSIG mode does not claim
  detached-child containment. If cgroup-v2 delegation exists, it runs a
  detached-session grandchild inside the real delegated worker cgroup and
  requires kernel `cgroup.kill` to terminate it. Without delegation that
  stronger test is explicitly skipped; the strict launch must fail closed.
  No fake cgroup is used.
- `tests/test_nvp_e2e01d_fault_boundaries.py` AST-checks every declared
  AUDIO-01I/J/K `crash_after` against actual native host, worker and
  filesystem side-effect callsites. Each checkpoint is exercised in an
  isolated Python child with an actual `os._exit`, verifying both the
  expected exit code and the required test-only opt-in. This validates
  injection plumbing; **it does not prove that a full mastering or DCP
  production operation recovered from that interruption**.
- `backend/nvp_e2e01c_finishing.py` now has a limited
  `reconcile_stopped_av_after_crash` path. When the coordinator missed an
  AUDIO-01J stage response, it searches original native J-host grants for
  one exact matching sealed plan and an OS-stopped, `SUCCEEDED`,
  nonreserved task. It requires native J-host creator/FilmIndex output
  verification and will not rerender, spend approval, free RAM or
  advance active/queued/ambiguous work. A lost *incomplete* J stage still
  needs native operator reconciliation.
- `tools/nvp_e2e01d_verify_approved_film.py` strictly reopens existing
  Studio/FilmIndex, picture lock, source-bound technical MOV, approved
  native AUDIO-01I audio, stopped native AUDIO-01J final AV, and the
  AUDIO-01K creator-published mezzanine. Source and final frame counts
  must agree, and `dcp_delivered` remains false. No synthetic approval
  or replacement source is supplied by the verifier.
- `.github/workflows/nvp-e2e01d-approved-film.yml` is a separate
  **manual, fail-closed** proof requiring actual Windows and Linux
  self-hosted NVP alpha machines with original absolute-path native
  custody, original runtime and creator-approved film fixture. Required
  GitHub variables are
  `NVP_E2E01D_APPROVED_FILM_MANIFEST_WIN`,
  `NVP_E2E01D_ORIGINAL_PYTHON_WIN`,
  `NVP_E2E01D_APPROVED_FILM_MANIFEST_LINUX`, and
  `NVP_E2E01D_ORIGINAL_PYTHON_LINUX`. Both machines must carry labels
  `nvp-alpha-custody` plus the platform label. This workflow does not
  claim a pass without provisioned machines and real film inputs.

The ordinary hosted Windows/Linux matrix validates process termination
and crash-point wiring. The *full approved-film* matrix is a separate
machine/fixture-dependent acceptance and remains OPEN until it returns
actual successful native evidence. A technical DCP ZIP cannot substitute
for a complete creator-approved FilmIndex workspace. Original native
authorization and absolute file paths must match; simply copying an
archive to an arbitrary hosted runner would invalidate custody.

**Current decision:** Implementation and additional CI coverage committed;
real hosted matrix and original-machine film acceptance are not yet passed.


## Source-bound B13/B14 crash reconciliation (follow-up)

`NativeEditorialChain.reconcile_completed_stage` now handles the crash window
after the original B13 or B14 host finished but before its task ID reached
the coordinator:

1. Query the original native grant plus durable `TaskLedger` for a **unique**
   matching project, immutable original source, exact edit revision, source
   SHA, output identity, a stored result SHA, `SUCCEEDED`, and zero held
   resource reservation. B13 and B14 have different exact identity keys.
2. Reopen the original native B13/B14 host's
   `verify_completed(job)`, which requires its previously recorded
   trusted completion, native receipt and source-bound FilmIndex audit.
3. Independently compare the immutable FilmIndex revision SHA to the
   matching native grant.
4. Atomically bind the original job ID into the coordinator's prior
   `IMPORT_STAGING_UNCERTAIN`/`CONFORM_STAGING_UNCERTAIN` record.
5. Advance only after the established B13 or B14 verifier accepts the
   existing output. No new worker, creator event or RAM release occurs.

Two matching native grants fail closed as ambiguous. Missing/incomplete or
ACTIVE/QUEUED grants stay uncertain. The regression suite models the native
completion result at the existing trusted host boundary, but does exercise
actual TaskLedger SQLite grants and exact revision reconciliation; actual
worker crash/OS acceptance remains a separate matrix.

The AUDIO-01J equivalent recovers only one uniquely matched stopped,
`SUCCEEDED`, unreserved grant, a byte-exact original plan and creator/
FilmIndex publication. It does not recover an ACTIVE J worker or replay
an interrupted creator event.

## E2E-01D next gate — Real AUDIO-01K native media publication

`tests/test_nvp_e2e01d_real_k_publication.py` creates an actual short
FFmpeg ProRes/PCM24 movie and an actual SQLite FilmIndex source master.
It invokes production `publish_mezzanine` in a **separate process** with
real file copy, fsync, SHA-256, manifest/SHA256SUMS publication,
`os.replace` directory promotion and FilmIndex registration.

The child is terminated with `os._exit(98)` at each of the six
AUDIO-01K filesystem/SQLite boundaries:

1. `staging_directory_created`
2. `movie_bytes_fsynced`
3. `manifest_fsynced`
4. `checksums_fsynced`
5. `directory_promoted`
6. `filmindex_registered`

The parent independently reopens the original SQLite Studio/FilmIndex,
re-verifies unmodified source MOV bytes, and checks the exact distinction
between a staging directory, an externally visible promoted output and
a committed immutable FilmIndex record. The promotion-before-index crash
must **not** be reported as a completed distribution. Once indexed, the
real K verifier must re-validate the source movie/checksums/dependency.

**Scope limitation:** the synthetic creator-approval callback in this
specific K filesystem crash test is a labeled technical fixture. This
does not prove that a real creator authorized the film, nor is the test
allowed to substitute for `NativeAudio01KHost` creator-event or original
AUDIO-01J stopped-worker custody. The separate no-mocks,
self-hosted approved-film workflow remains the release gate.

`.github/workflows/nvp-e2e01d-recovery.yml` now installs actual
FFmpeg on Windows and Linux and runs this real K fsync/rename/FilmIndex
hard-kill matrix. All four native matrix cells must execute and pass;
none of them is considered accepted while queued.

## K native creator-event crash closeout expansion

The real media crash test also exercises the original
`NativeAudio01KHost.publish` creator-event transaction at both
`creator_event_reserved` and `creator_event_published`.
After an abrupt child-process exit, a new native host reopens the
resource ledger and verifies exactly one creator event. A reserved
event is never considered delivered; an event marked PUBLISHED must
match the immutable FilmIndex distribution document SHA and the real
promoted ProRes/PCM24 movie. Repeating the same creator event must
fail even if publication was interrupted. These are *actual native host
SQLite and copy operations*, but the fixture uses a clearly synthetic
trusted creator/AV-verification callback; release-level approval must
still use the no-mocks original-film acceptance gate.
