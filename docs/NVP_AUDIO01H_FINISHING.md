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
