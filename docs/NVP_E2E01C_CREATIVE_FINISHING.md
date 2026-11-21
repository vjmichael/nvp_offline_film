# NVP-E2E-01C — Creative Finishing Integration

**Status:** Native finishing handoff implemented; Windows/Linux contract CI
pending. NOT a completed end-to-end film or independent cinema acceptance.

## Production sequence and authoritative owners

This gate does not build a second audio mixer or film exporter. It links
existing native host decisions:

1. **Editorial/color:** B13 source-bound edited timeline -> B14 technical
   picture conform -> verified edited technical MOV. Color/source integrity
   remains under the existing B14 and picture-candidate verifiers.
2. **Creator picture approval:** `NativeAudio01JHost.approve_picture` spends
   an exact creator-event authorization and indexes an immutable picture
   lock. `validate_picture_lock` rejects a merely technical or unapproved
   picture candidate.
3. **Audio mastering:** `NativeAudio01IHost.stage`, `run_next`, and
   `deliver` maintain independent candidate production and director mix
   approval. The final PCM24 WAV delivery is revalidated through the native
   host; an unapproved mastering candidate is never sufficient.
4. **NVP-E2E-01C finishing coordinator:** `NativeFinishingHandoff.register`
   anchors the immutable picture-lock SHA and approved audio-delivery SHA
   in the *same* SQLite TaskLedger used by the native mastering/AV hosts.
   Output directories and exact FilmIndex identities are sealed before
   a new native final-AV stage is requested.
5. **Synchronized final movie:** `stage_final_av` uses the existing
   `NativeAudio01JHost.stage` creator-authorized native mux job. The
   `run_final_av` helper invokes only the J-host contained worker and
   rejects unrelated job completions. The coordinator checks
   `TaskLedger.state=SUCCEEDED`, released RAM reservation and independent
   `NativeAudio01JHost.verify_published` before marking AV verified.
   FilmIndex must show the exact picture-lock and audio-delivery IDs.
6. **Approved mezzanine distribution:** A *separate* creator event passes
   to `NativeAudio01KHost.publish`; only the native K-host's complete
   copy, publication witness and SHA verification promote the technical
   distribution to `DISTRIBUTION_VERIFIED`.
7. **Restart:** `reopen` rechecks existing host proofs. A stopped,
   completed AV may be accepted without rerendering; an ACTIVE, missing,
   unverified or unknown worker remains pending. Crashes between host
   stage and coordinator receipt are marked `AV_STAGING_UNCERTAIN`, not
   auto-replayed. Likewise incomplete K publication stays
   `DISTRIBUTION_UNCERTAIN` until native verification succeeds.

The coordinator never marks `dcp_delivered=True`. Mezzanine distribution
is NOT a cinema DCP and does not imply projector acceptance.

## Committed artifacts

- `backend/nvp_e2e01c_finishing.py` — durable handoff with actual native
  J/I/K host interface checks and FilmIndex-source custody.
- `tests/test_nvp_e2e01c_finishing.py` — concrete SQLite/restart
  tests for creator-approval identity, worker completion, duplicate
  rejection, post-crash uncertainty, altered approval, mismatch/false
  success and published mezzanine verification.
- `.github/workflows/nvp-e2e01c-finishing.yml` — Windows 2025 and
  Ubuntu 24.04; Python 3.11 and 3.13.

The contract suite patches actual native FFmpeg/worker outputs. It is a
durability and authorization boundary test, **not** a genuine media
mastering, color science, executable containment or cinema validation
result.

## Still open before closing E2E-01C

- [ ] Exact-head Windows/Linux four-cell CI passes.
- [ ] Source-bound B12 -> B13 -> B14 -> edited technical ProRes output
  with authentic scene-linear/graded picture and trusted worker execution.
- [ ] Real approved AUDIO-01H mix -> native AUDIO-01I mastered PCM24
  candidate -> separately director-approved audio delivery.
- [ ] Actual `NativeAudio01JHost.approve_picture` with creator event
  -> native contained mux -> verified 24fps picture and 48kHz PCM24
  sample count/duration/track-map, using same approved project.
- [ ] Real K native approved mezzanine distribution, restart, SHA review
  and FilmIndex dependency integrity.
- [ ] Termination/watchdog, Windows Job Object and Linux process tree
  kill evidence, disk-full, shutdown and creator-event failure injection.
- [ ] Reconcile crash window between native J/K staged publication and
  coordinator receipt via source-grant lookup; currently manual review
  required. No automatic retry is safe without the durable repair path.
- [ ] E2E-01D full-workflow fault injection and E2E-01E installed-app GUI
  smoke remain separate.
- [ ] AUDIO-01K.3 independent DcpDoctor QC and actual projector ingestion
  remain open; this coordinator must not claim theatrical delivery.

**Acceptance classification:** implementation committed, validation open.
Draft PR #45 remains unmerged pending verified machine execution.
