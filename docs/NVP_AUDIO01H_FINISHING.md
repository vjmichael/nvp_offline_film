# AUDIO-01H — Professional audio finishing: bounded automation core

Development began while AUDIO-01G's Windows/Linux native mux crash acceptance remains queued. **Implementation is not production acceptance.**

## Landed

- `backend/nvp_audio01h_automation.py`: pure PCM16 stereo gain automation for the existing 24fps/48kHz picture clock.
- Canonical control points are strictly increasing sample indices with explicit first and last sample, within +/-24 dB and finite values.
- Per-sample interpolation is in dB; each sample is converted to linear amplitude during processing.
- Input bytes are never mutated, exact PCM sample count is mandatory and clipping raises a hard error; neither automatic normalization nor a secret limiter is permissible.
- A sample-peak function is present explicitly **not** marketed as true-peak.
- `tests/test_audio01h_automation.py`: unity identity, changed gain, endpoint identity, clipping, invalid envelopes, exact clock and sample-peak labeling.
- `.github/workflows/nvp-audio01h-automation.yml`: Windows/Linux Python 3.11/3.13 test matrix.

## Explicitly NOT landed / not yet accepted

1. Native authenticated worker use, resource admission, Job Object containment, crash-safe output publication and FilmIndex dependency custody for the new automation engine.
2. FFmpeg/native BS.1770 integrated LUFS with LRA and oversampled true-peak (dBTP). Sample-peak (dBFS) is NOT interchangeable.
3. Creator-approved mix decisions or reversible approval/rejection events. `final_mix`, `final_master`, `director_approved` remain false until a separate authorization design and real acceptance.
4. Full real-media multitrack automation with source-stem replay and picture synchronism.
5. Exact-head CI results; do not equate a successful repository push with passing native Windows tests.

## Next engineering order

AUDIO-01H.1: standards-aware FFmpeg ebur128/loudnorm inspection with explicit independent evidence on the decoded technical WAV and no publication; verify true peak, loudness and measurement failures.

AUDIO-01H.2: author immutable per-stem automated revisions in FilmIndex through existing native host authorization, containment and staging. Preserve original source stems and never auto-overwrite.

AUDIO-01H.3: guarded final mix review and explicit creator acceptance, with revocation/revision semantics; keep actual mastering and delivery separate.

AUDIO-01G strict Linux delegated cgroup-v2 remains open/deferred. Do not block AUDIO-01H engineering on the pending CI runs.


## Implemented since initial core commit (AUDIO-01H.1–.3 candidate)

- AUDIO-01H.1: `nvp_audio01h_loudness.py` executes real FFmpeg `loudnorm` EBU R128 analysis, returns integrated LUFS, LRA and oversampled dBTP evidence with unchanged source SHA verification. This **does not normalize** or promise broadcast compliance. Silent/unmeasurable input fails closed.
- AUDIO-01H.2: `nvp_audio01h_stem_revision.py` reads immutable 48kHz PCM16 source WAV, requires an exact externally provided per-operation authorization callback, applies sample envelope, creates absent-only WAV, indexes media and source dependency in FilmIndex as an unapproved audio revision. Explicit `stem_id=None` selects only the published `mix_preview.wav` composite.
- AUDIO-01H.3: `nvp_audio01h_mix_decision.py` independently remeasures the exact indexed output WAV, requires explicit authenticated creator callback, and records immutable ACCEPT, REJECT or REVOKE revisions. **Only an automated composite**, never an individual stem, may be accepted as a final mix. A final mix review is **not** authorization for final master or DCP. Creator-event replay prevention must be implemented in the native host.
- New unit and native-FFmpeg tests are included in the dedicated 4-cell Windows/Linux Python 3.11/3.13 workflow.

## Acceptance boundaries still OPEN

The pure authoring API does not itself provide native process containment or durable approved-task grants. Before production use, the authenticated NVP host must connect the AUDIO-01H operations to the existing `ApprovedTaskBindings`, TaskLedger, native Job Object supervisor and crash recovery. Callback authorization injected by an arbitrary caller is **not a security boundary**. The existing AUDIO-01G native mux crash CI is still a separate gate.

The 01H.2 staging currently uses absent-only destination creation and immutable FilmIndex media indexing; an interruption may leave an unregistered WAV. It does NOT yet have a dedicated durable journal, OS-stop witness or recovery reconciler. Never characterize it as transactional crash-complete publication.

AUDIO-01H.3 creator review is an immutable decision record, not yet a complete UI-facing approval workflow. Native event authentication, anti-replay, source-pinned final delivery and media standard target policy remain open.


## AUDIO-01H native integration and E2E candidate (current head)

- `backend/nvp_audio01h_native_host.py` provides a trusted, per-operation host entrypoint using existing `ApprovedTaskBindings`, `AdmissionRequest`, `TaskLedger`, `launch_contained` and `wait_guarded`.
- `tools/nvp_audio01h_native_worker.py` executes only a canonical sealed automation plan. A worker cannot manufacture creator consent; its result must match independent FilmIndex verification before ledger completion.
- A durable stopped-worker flag is written only after the native process is reaped. `recover_completed` requires that witness, unchanged source digest, expected automation points, unchanged output bytes, worker receipt and FilmIndex. It never rerenders and cannot clear an uncertain ACTIVE reservation.
- `tools/nvp_audio01h_measure_worker.py` runs actual FFmpeg EBU R128 under the same native OS containment. The host independently checks the received evidence and rechecks exact creator permission before publishing a mix decision.
- Creator action IDs are reserved in SQLite **before** publication, preventing reuse after a crash; a lost event is fail-closed, not silently replayed.
- `tests/test_audio01h_native_e2e.py` creates a real indexed stereo/48kHz two-stem fixture (dialogue + music) and exact composite, runs approved contained sample automation, compares unchanged source hashes, checks FilmIndex, performs actual FFmpeg loudness inspection, rejects unauthorized decisions, records ACCEPT then REVOKE, and tests restart/no-rerender plus missing stop-witness denial.
- `.github/workflows/nvp-audio01h-automation.yml` now runs the above on Windows 2025/Ubuntu 24.04, Python 3.11/3.13 and installs Win32 Job Object bindings.

### Claims deliberately excluded

This E2E test starts from **real fixture WAV samples arranged into indexed AUDIO-01E-compatible stem records**. It does not independently execute the upstream AUDIO-01D chunk engine or authenticate an actual human UI event source. It covers the integrated AUDIO-01H native path, not all NVP production stages from a raw timeline.

The implementation is committed; **Windows/Linux CI execution remains unverified until exact-head successful jobs are observed.** A file creation or queued workflow is not a passed test. The strict Linux delegated-cgroup-v2 gate remains explicitly deferred. The native stop flag does not prove full host-power-loss durability or transferable ownership across two live supervisors. No mastered deliverable or DCP approval is emitted.

Final production closeout still requires real human-event-origin attestation, host interruption/crash injection of this new 01H worker and measurement worker, and proof against output replacement after read-before-publish races.


## AUDIO-01H.4 — Abrupt-exit and approval-custody hardening (candidate)

The 01H crash matrix now defines 14 independently named points in `backend/nvp_audio01h_fault_matrix.py` and triggers real `os._exit(94)` only if BOTH opt-in CI environment keys are present. These gates are inert for ordinary production operation and are never accepted from a user/model media plan.

The native host/worker now instrument:
- sealed plan fsync; grant and queue SQLite commits; admission to ACTIVE
- worker FilmIndex registration; worker receipt fsync; native handle reap
- durable stopped witness; independent output verification; TaskLedger SUCCESS; result SHA commit
- creator-event nonce reservation; FilmIndex creator-decision registration; nonce completion

`tests/test_audio01h_native_crash_matrix.py` executes nine actual host-abort points in subprocesses and reopens SQLite/FilmIndex, checking absent decisions, held ACTIVE reservations, refused recovery without stopped witness, and no-rerender reconciliation after verified stops. `tests/test_audio01h_worker_crash_matrix.py` exercises the two actual child-worker abort points and proves neither partial FilmIndex publication nor a worker receipt becomes a final approval. `tests/test_audio01h_creator_crash_matrix.py` exercises three creator-approval crash windows; once reserved, the same event nonce cannot be reused regardless of the crash point.

Security refinements:
- Creator authorization is checked before a nonce is reserved, avoiding unauthorized nonce exhaustion; original exact-scope approval remains independently checked before FilmIndex publication.
- A FilmIndex audio revision alone cannot be considered a final mix: the trusted host must find exactly one completed resource-ledger native producer with a matching result SHA, durable stopped witness, and sealed original composite plan.
- The full canonical native loudness report must agree with fresh measurement, not just selected LUFS/LRA/TP numbers.
- Symlink source-directory rejection takes place before resolution.
- The test suite additionally attempts to approve a manually produced, uncontained FilmIndex audio object and requires rejection.

**Remaining:** CI results are not yet available. AUDIO-01H native acceptance MUST fail if any Windows/Linux test fails, skips required native media, or cannot prove stopped-worker custody. Fault injection tests simulate process crashes, not power loss; Linux delegated cgroup-v2 remains deferred. Creator-event identity is delegated to the trusted host policy callback, not a complete UI-origin attestation implementation. FilmIndex publication's file/SQLite boundaries still need full storage-fault injection for physical power-failure guarantees.


### AUDIO-01H.4 native fault acceptance candidate

Code and tests now cover 14 explicit post-effect abrupt-exit gates across plan, grants, TaskLedger admission, worker FilmIndex publication, receipt, OS-stop witness, verified completion, and creator-event decisions. Tests assert all 14 production gates are unique and actually covered. Mandatory media tests cannot skip absent native FFmpeg.

The trusted host now requires a successful OS-reaped, immutable, digest-matched, resource-released native producer before accepting a final composite. A manually produced FilmIndex-only composite is explicitly denied. Approval event preflight is checked before replay-nonce reservation, and exact-scope creator authority is rechecked before publication. The native measurement worker verifies pinned FFmpeg executable bytes.

**This is not a passing acceptance claim.** Source and CI matrix are committed, but no exact-head successful Windows/Linux native logs have been observed. Remaining risks: OS grandchild termination and containment interruption tests; genuine UI event attestation; ancestor-path replacement races; upstream full AUDIO-01D-to-01E replay; power-loss durability. Delegated Linux cgroup-v2 remains deferred.
