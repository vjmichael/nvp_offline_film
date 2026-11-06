# NVP AUDIO-01G / AUDIO-02 — Native mux crash recovery and sound finishing

## Status

First implementation committed on `nvp/stack02c3b14-picture-conform-20261104`; real Windows acceptance **pending**. Linux delegated cgroup-v2 remains **deferred/open**. No film or mix is designated final theatrical master.

## AUDIO-01G: transactional technical-review publication

`backend/nvp_audio01g_mux_intent.py` writes a durable SQLite mux intent before native TaskLedger queue admission. The state machine is `prepared → running → verified → committed` with `quarantined` when incomplete output is observed. Each transition requires the expected previous state in a BEGIN IMMEDIATE transaction; stale updates fail.

`backend/nvp_audio01f_picture_sound.py` now writes the FFmpeg MOV and canonical manifest in a **sibling staging directory on the same filesystem**, then independently decodes video and PCM, fsyncs the completed media and manifest, atomically renames staging to the destination, and only afterward publishes the immutable FilmIndex presentation revision. Partial output never appears at the final destination. On POSIX, the parent directory is fsynced after promotion. On Windows, FlushFileBuffers on files is performed, but no general power-loss atomicity claim is made for directory metadata.

`backend/nvp_audio01g_mux_recovery.py` can inspect the original sealed plan and verify completed media + exact worker receipt after the **trusted native host attests the owning worker process tree is stopped**. It quarantines missing or corrupted media and keeps the ACTIVE TaskLedger reservation held; when fully verified, an explicitly requested trusted recovery can persist the exact result digest and complete the reservation without rerunning FFmpeg.

The native host does not infer OS process death from an absent PID or an unlocked file. The OS-stop attestation is an explicit caller-supplied trusted boundary; this increment does **not** yet persist a Windows Job Object stop witness across a fully crashed host, so automatic host-crash finalization is not claimed. The committed regular exception path now holds rather than automatically releases a possibly recoverable ACTIVE reservation.

**Important:** This is staged filesystem publication followed by immutable FilmIndex commit, not one global atomic transaction across SQLite + filesystem. If the process crashes after directory promotion but before FilmIndex commit, an orphan final directory remains non-published and must be quarantined and inspected. Do not silently overwrite it.

## AUDIO-02A: sample-domain track automation

`backend/nvp_audio02a_automation.py` applies exact, bounded linear gain keyframes to PCM16 stereo at 48kHz in small blocks. Position is integer samples; gains are integer thousandths of unity. It preserves the source file, exclusive-creates a derived WAV, validates bounds, and reports the resulting PCM hash. It includes no phantom quality enhancement or implied human approval.

Current implementation covers **gain automation** (including keyframe ramps); pan, EQ, compression, reverb, dialogue ducking, fades across edits, noise restoration, multi-bus routing and nondestructive DAW timeline controls are later finishing increments.

## AUDIO-02B: objective loudness and true-peak analysis

`backend/nvp_audio02b_loudness_qc.py` invokes real FFmpeg's loudnorm measurement pass, parses integrated LUFS (`input_i`), true peak dBTP (`input_tp`), loudness range (`input_lra`) and relative gating threshold. It does **not** normalize or alter the WAV. The initial review policy defaults to -16 LUFS ±2 LU and true-peak ceiling -1 dBTP; this is an initial NVP technical-review policy, **not** a universal cinema or broadcast delivery standard. Output QC fails if outside limits and cannot be relabeled as mastering.

## AUDIO-02C: final mix creator decision

`backend/nvp_audio02c_mix_approval.py` requires a passing measured report, SHA-256 match to the exact WAV, and a **fresh remeasurement** before invoking a trusted native creator-approval callback. If the creator approves, an immutable FilmIndex audio revision binds the exact prior audio revision, mix SHA and QC measurement. The result is `creator_approved_final_mix_not_master`: `final_mix=True`, `director_approved=True`, `final_master=False`. Human authorization does not silently approve the picture, final video master, DCP or delivery.

`verify_final_mix_approval` independently reopens the revision and validates dependency lineage, source WAV bytes and QC evidence.

## Tests and outstanding closeout

- `tests/test_audio01g_mux_recovery.py`: journal compare-and-swap, no recovery without stopped-worker evidence, partial-output quarantine retaining ACTIVE reservations.
- `tests/test_audio02_finishing.py`: deterministic PCM automation and untouched sources; real FFmpeg loudness analysis; creator refusal, positive approval, forged-QC remeasurement rejection and after-restart FilmIndex verification.
- `tests/test_audio01f_picture_sound.py`: existing real ProRes/PCM mux plus new interrupted staging preservation.
- `.github/workflows/nvp-audio-windows-job-object.yml`: Windows Job Object, actual mux, durable recovery and AUDIO-02 tests.

**Not complete:** Exact-head Windows CI pass, true injected SIGKILL/TerminateJobObject at every filesystem/SQLite publication boundary, persistent Windows host-crash guardian attestations, durable multi-bus mastering engine, feature-length picture, professional delivery-specific QC profiles and director acceptance UI.

**Deferred intentionally:** Linux strict delegated cgroup-v2 tree-termination acceptance remains OPEN; no tests are counted as passing it on read-only or undelegated hosts.

## Additional recovery and finishing hardening

- The native AUDIO-01F host now persists `native_audio01g_os_stops` only after it actually closes an owned, reaped process handle. `inspect_interrupted` and `finalize_interrupted` consult that durable witness themselves instead of letting arbitrary callers pass a permissive lambda. A full host crash before the witness commit is **not automatically recoverable**; that remains blocked rather than relying on PID guesses.
- `reconcile_post_commit_gap` closes a restart gap when FilmIndex and TaskLedger show an immutable verified successful mux but the AUDIO-01G journal stopped at `verified`. It rechecks original source media, worker receipt, result SHA, and the persistent OS-stop witness, then advances the journal without rerendering.
- AUDIO-02A now also offers `sum_automated_stems`: bounded, aligned PCM16 stereo 48kHz WAV summing from up to eight individually automated stems. Integer saturation is **not** a true-peak limiter. Derived mixes require subsequent AUDIO-02B measurement and explicit AUDIO-02C approval.
- AUDIO-02B validates target ranges and measures the creator-selected loudness/true-peak policy using actual FFmpeg.
- AUDIO-02C remeasures the exact WAV at approval time and rejects forged or stale QC dictionaries before accepting a native creator event.

Tests are committed, but **the corresponding Windows/Linux CI results are not yet verified**. Automated CI tests of source checks and transitions do not replace an end-to-end fault-injected Windows Job Object recovery test.

## Real native finishing acceptance fixture

`tests/test_audio02_finishing.py::test_real_ffmpeg_qc_then_creator_approval_after_restart` creates a genuine three-second 48kHz stereo PCM16 tone, measures its actual integrated loudness and true peak with FFmpeg, requires the measured technical review gate to pass, then commits a separate creator-authorized final-mix decision to FilmIndex and reopens SQLite to verify its immutable lineage. The test runs actual FFmpeg where installed; mock-based authorization tests are separate.

This is an acoustic measurement fixture for functional correctness, **not a professional mastering reference waveform** or an endorsement of a universal delivery loudness target. Finished audio quality and program-specific loudness standards require independent review.

## Windows task state

The current Windows Job Object workflow includes AUDIO-01G and AUDIO-02 tests, along with the earlier actual contained-worker termination and FFmpeg mux tests. The **latest SHA still has queued GitHub CI jobs**, so no cross-platform pass is asserted.

`NativeAudio01FHost` now stores `native_audio01g_os_stops` only after reaping its owned worker handle and refuses interrupted recovery without that persistent witness. The state-check test verifies persistence, not genuine OS execution; the real Windows Job Object acceptance jobs are required.

No complete automated host-crash takeover is asserted when the OS reaped handle was not observed and persisted before the crash. Such ACTIVE jobs remain held for native intervention. Strict delegated Linux cgroup-v2 acceptance remains OPEN / DEFERRED.
