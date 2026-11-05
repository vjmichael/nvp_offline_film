# NVP-E2E-01B — Native Editorial Worker Integration

**Status: implemented bridge + native-host contract tests committed; exact
Windows/Linux CI and actual full-source B12 -> B13 -> B14 execution pending.**

## Architecture

NVP-E2E-01A's direct-FFmpeg technical editor does **not** grant permission
to treat arbitrary source clips as director-approved B13 NLE media.

Instead, E2E-01B connects the two **existing** authenticated native
production routes:

1. `NativeB13ImportHost`: receives approved OpenTimelineIO bytes over a
   trusted creator event, hashes the incoming edit, validates B12's original
   frozen media, and queues an exact source-bound operation in the durable
   SQLite TaskLedger. Its existing child worker is OS-contained and guarded
   against CPU/RAM pressure. It commits an immutable FilmIndex `edit`
   revision and independently re-verifies after completion.
2. `NativeEditorialChain`: persists the exact B13 imported
   `project_id`, `edit_id`, `revision`, document SHA, source package,
   intended B14 presentation ID, and native task IDs. The persistent chain
   lives inside the *same* resource-ledger SQLite database, not model
   memory or the desktop UI.
3. `NativeB14ConformHost`: may stage its worker **only after B13's
   independently verified native completion**. A second trusted creator
   authorization applies to the exact edit revision and output. The
   B14 worker uses the existing OS process containment and RAM watchdog
   to publish a source-bound, unapproved SDR16 picture conform.
4. Restart and recovery: reopening the coordinator checks real B13/B14
   task state, stored exact-source checksum, FilmIndex revision and
   independently verified host receipts. It cannot mark a queued,
   missing, interrupted, or unverified worker as successful. A previously
   published native result is reconciled without rerendering.
5. A cancelled B13 queued import is not a successful render, and never
   claims to have killed a live OS process. Resource cleanup and
   termination witnesses remain the responsibility of the native hosts.

No Lu integration, direct GUI automation, extra MCP transport or
second rendering daemon is introduced by this gate.

## Files

- `backend/nvp_e2e01b_native_editorial.py`: durable native editorial
  chain with `stage_edit`, `run_import`, `verify_import`,
  `stage_conform`, `run_conform`, `verify_conform`,
  `cancel_queued_import` and `reopen`.
- `tests/test_nvp_e2e01b_native_handoff.py`: SQLite restart, exact
  revision handoff, wrong job ID rejection, no duplicate conform stage,
  false final-master rejection and original native cancellation authority.
  Mocking at the already tested B13/B14 worker completion boundary is
  explicit; passing these tests **does not count as actual native render**.
- `.github/workflows/nvp-e2e01b-native.yml`: four-cell
  Ubuntu 24.04/Windows 2025 × Python 3.11/3.13. It runs the new handoff
  contracts alongside B13 OTIO/native authorization and B14 conform
  source-bound contract suites.

## Acceptance required before E2E-01B closes

- [ ] New four-cell CI passes on an exact head SHA.
- [ ] Reuse real original B12 FilmIndex frozen-take media; run a real
  native B13 OTIO import through the authorized OS-contained worker.
- [ ] Authorize and run B14 real native picture conform **on that same
  source revision**, with actual B13 package inputs.
- [ ] Restart *both* native hosts and Studio/FilmIndex; independently
  reverify the movie's exact frame/source lineage and no changed take.
- [ ] Demonstrate cancellation, child/grandchild termination and
  no RAM leaks on actual Windows Job Objects and Linux process trees.
- [ ] Demonstrate abrupt host/process crashes at all handoff boundaries
  without double staging, duplicate FilmIndex publication or false
  output approval. The coordinator currently lacks a full crash matrix.
- [ ] Resolve multihost concurrency races, particularly a process
  interruption between staging a B13/B14 job and persisting the chain
  receipt; the result must remain safely discoverable before production.
- [ ] Complete E2E-01C audio/color/final AV integration and installed
  desktop alpha acceptance separately.

**Release conclusion:** native-worker orchestration has been added, but
it is not an end-to-end native-render acceptance or finished desktop
filmmaking workflow. Keep draft PR #45 unmerged pending actual validation.
