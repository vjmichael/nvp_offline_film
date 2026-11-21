# AUDIO-01J — Approved Picture + Final Audio → Audiovisual Master

## Goal and current implementation

Integrates a **verified B14 silent technical picture** with a **separately
creator-approved AUDIO-01I PCM24 final audio delivery**, preserving the exact
24-fps / 48-kHz sample clock (2,000 stereo samples per video frame).

This is a **native implementation candidate awaiting Windows/Linux acceptance**.
A successfully written ProRes MOV, queued CI job, or FilmIndex object is NOT
independent production verification.

## Source authorization

1. `nvp_audio01j_picture_lock.py` adds an immutable, human-approved picture
   lock. The source B14 technical candidate is NOT silently converted to an
   approved picture. The creator's lock explicitly names the B14 SHA, profile,
   frame count and immutable revision, after full B14 source verification.
2. `NativeAudio01JHost.approve_picture` invokes trusted creator policy,
   reserves the one-use creator event in durable SQLite, and publishes the
   picture lock into FilmIndex. A crash may consume an event without publishing;
   no event is reused automatically.
3. At AV scheduling, the trusted host invokes AUDIO-01I's
   `verify_delivery` (current creator decision, original approved audio bytes,
   native workflow and decoded technical proof), then validates the locked
   picture against its original B14 SHA. Both sources must be exactly aligned
   at 24 frames/s and 48,000 stereo samples/s.
4. A **separate explicit human event** authorizes the exact final AV ID,
   picture/audio document digests, final destination and duration. The event is
   durably consumed before the export task is queued; the worker cannot create
   its own approval.

## Worker and media

`backend/nvp_audio01j_native_host.py` integrates `ApprovedTaskBindings`,
`TaskLedger`, admission accounting, native resource watchdog, Win32 Job Object
and Linux OS-tree worker containment. Plans bind the Python/worker/FFmpeg/
FFprobe binaries by SHA and the complete immutable task spec. The worker
itself rechecks the ACTIVE authorized task and native grant in SQLite before
executing.

`backend/nvp_audio01j_final_av.py` uses FFmpeg with `-c:v copy` and
`pcm_s24le` in a MOV container, without padding/truncating mismatched
media. Both decoded streams are independently compared to the approved
source media: full pixel-plane SHA for the locked video and full PCM24 byte
SHA for the final audio. FFprobe verifies the exact video frame count, 24 fps,
48-kHz two-channel audio codec, and both stream durations within one audio
sample tick. The result is a new staged directory containing:

- `final_picture_sound.mov`
- `final_av_manifest.json`

After fsync and atomic same-filesystem directory promotion, the **worker**
registers only an unapproved `presentation` candidate revision. The trusted
host must first reap the worker, durably record its stop, independently decode
the candidate, inspect the worker's receipt and verify current creator audio
approval. Only then does the host register the terminal `master` revision,
with immutable FilmIndex dependency edges to the candidate, picture lock and
final audio delivery. `dcp_delivered` remains **false**. No DCP, surround
mix or distribution package is implied.

## Native completion and recovery

The host never equates worker-reported success with independent acceptance.
After reaping the native worker and writing a durable OS-stop witness, it
verifies the FilmIndex record, content-addressed movie, manifest and decoded
source/media identity. `verify_published` also requires a committed creator
approval event and a successful, stopped, unique native job.

`recover_completed` may reconcile only verified stopped workers with exact
immutable output, a matching worker receipt, and unchanged current AUDIO-01I
approval. It never performs a second render over a partially published MOV.
Unknown OS-stop state leaves the ACTIVE resource reservation held.

## Real native acceptance

`tests/test_audio01j_native_final_av.py` exercises genuine FFmpeg 24-frame
ProRes and two-stem PCM mixed/automated via AUDIO-01H, approved via
AUDIO-01I, and finally muxed by the contained AUDIO-01J worker. It checks
decoded picture and PCM24 identity, source hashes, approval events, restart
verification and nonce reuse denial. The *upstream B14 source-linear conform*
is substituted only for this synthetic ProRes fixture: it does **not** prove
complete unmocked B14 scene-linear filmmaking.

`tests/test_audio01j_final_av_crash_matrix.py` and
`tests/test_audio01j_picture_lock_crash_matrix.py` inject real abrupt
`os._exit(97)` at 20 named persistence boundaries; coverage tests require
each checkpoint to appear once and have a subprocess test. The opt-in fault
switches are inert in production.

`.github/workflows/nvp-audio01j-final-av.yml` requires Windows 2025 and
Ubuntu 24.04 with Python 3.11/3.13, real FFmpeg/FFprobe, and Win32 pywin32
Job Object bindings.

## Remaining production acceptance (OPEN)

- **Exact-head native CI jobs** must genuinely execute and pass; no passing
  AUDIO-01J Windows/Linux native run is asserted in this document.
- The release-critical premature master publication gap has been closed:
  workers only create `unapproved_synchronized_av_candidate` with
  `final_master=False` and `director_approved=False`. The trusted host
  alone publishes a `master` record after durable OS-stop evidence and
  independent decoded proof. The host-only master registration itself has
  a separate crash-injection checkpoint. Consumers still MUST use
  `NativeAudio01JHost.verify_published`, which confirms completed creator
  event, native grant and FilmIndex media custody.
- Actual Win32 non-cooperative worker-tree termination and crash/power-loss
  recovery require dedicated machine acceptance, including Windows parent
  directory durability and race-proof source-path custody.
- B14 end-to-end **unmocked** picture-source replay and studio UI-origin
  human authorization remain separate required gates.
- Strict delegated Linux cgroup-v2 remains explicitly **deferred**.
- No conforming DCP, IMF, ADM/BWF, surround/Atmos or final distribution
  packaging has been implemented here.


## Local native FFmpeg command-level smoke (Debian FFmpeg 7.1.5)

An independently generated 24-frame 128×72 ProRes MOV and one-second
48-kHz stereo PCM24 WAV were muxed using the same `-c:v copy` and
`-c:a pcm_s24le` operations. FFprobe measured **24 video frames at
24/1 fps**, and **one PCM24 audio stream at 48,000 Hz, two channels**,
with both durations exactly one second. Separate decoded PCM24 streams
had identical SHA-256 digests (288,000 bytes = 48,000 × 2 × 3); separate
decoded YUV422P10 video planes compared bit-for-bit (884,736 bytes).
Both local command-level checks passed.

This verifies command-level FFmpeg behavior in the local Linux runtime
only. It **does not** establish execution of the complete GitHub
FilmIndex/creator/contained-worker integration test or Windows acceptance.
