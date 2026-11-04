# AUDIO-01I — Native PCM24 Mastering and Final Audio Delivery

## Scope

AUDIO-01I converts an explicitly accepted AUDIO-01H composite into a separately
indexed **unapproved** master candidate, then requires a **second exact creator
authorization** to publish an audio-only final master. It never claims to
deliver a picture master, DCP, M&E, or theatrical surround mix.

Files:
- `backend/nvp_audio01i_mastering.py`: profile selection, trusted current
  AUDIO-01H ACCEPTed source, real FFmpeg 48-kHz stereo PCM24 conversion,
  full decoded sample-count verification, ffprobe codec verification, and
  independently measured BS.1770/EBU R128 metrics.
- `tools/nvp_audio01i_native_worker.py`: sealed worker plan; no approval.
- `backend/nvp_audio01i_native_host.py`: ApprovedTaskBindings + TaskLedger,
  RAM admission, Linux/Windows OS containment, watchdog, native process-reap
  custody, FilmIndex verification, and no-rerender restart reconciliation.
- `tools/nvp_audio01i_inspect_worker.py`: independent PCM24 verification
  executes in a **second contained worker**, including pinned binary hashes.
- `tests/test_audio01i_native_master_delivery.py`: real two-stem WAV fixture
  -> approved AUDIO-01H mix -> contained native mastering -> independent
  sample/loudness proof -> separate creator-approved delivery -> restart audit.
- `.github/workflows/nvp-audio01i-native-delivery.yml`: native Windows 2025
  and Ubuntu 24.04, Python 3.11/3.13 matrix.

## Explicit profiles

`archive_pcm24_v1`: 48 kHz stereo PCM24 WAV conversion, no automatic
normalization or undisclosed limiter. 24-bit container precision does not
invent source dynamic range from the 16-bit preview.

`streaming_pcm24_v1`: FFmpeg loudnorm processing aimed at -16 LUFS integrated
with -1.5 dBTP true-peak ceiling (11 LU LRA requested). **This is an NVP
technical profile, not a universal streaming-platform compliance promise.**
Actual integrated LUFS, true peak, LRA, sample count, and bit depth are
independently measured and recorded; candidate is rejected if the decoded
sample clock changes or the true-peak ceiling is exceeded.

## Trust and publication

1. Read the *current* decision head and require ACCEPT + final_mix=True.
   REVOKE, REJECT, stale decision revision, wrong source hash, and missing
   content-addressed source WAV fail closed.
2. Require one matching completed AUDIO-01H native worker and one durably
   recorded creator-event publication from its ledger; a manually authored
   FilmIndex object alone is not enough.
3. Creator separately authorizes the exact candidate identity, profile,
   source digest, destination, and operation.
4. The protected AUDIO-01I worker produces and indexes an unapproved PCM24
   master candidate; the trusted host remeasures it in another contained
   process and checks the real worker receipt before releasing resources.
5. The creator separately approves the final delivery with a new event ID.
   The delivery event is durably consumed *before* publication to prevent
   approval replay after a crash.
6. The trusted host checks the original native candidate location, worker
   receipt, and FilmIndex content-addressed copy, then writes a sealed staging
   folder with `master.wav` and `manifest.json`; fsyncs; atomically renames
   the directory; and registers a final FilmIndex audio revision.
7. An interrupted staging directory or promoted-but-unregistered folder is
   not automatically treated as an approved final master. Retries never
   overwrite it. Review/reconcile must inspect it explicitly.

## Explicit limits and open acceptance

- This is **source code and a required native CI test suite**, not a verified
  Windows production release. The four-platform native acceptance must actually
  run and pass on an exact commit before closeout.
- Upstream test begins from an indexed fixture made of real dialogue/music WAV
  samples and a summed composite; it does not replay all AUDIO-01D generation
  or full picture-conform handoff in the same test.
- The human origin of `verify_creator_action` events must be supplied by
  NVP's trusted UI/authorization layer; a Python callback by itself does not
  constitute identity proof.
- The current bounded technical profile supports **48-kHz stereo PCM24 WAV**,
  not surround/Atmos, ADM/BWF metadata, CD mastering, broadcast network QC,
  platform-specific delivery packages, or a final video mux.
- Crash injection for all final-delivery filesystem and SQLite boundaries,
  real Windows non-cooperative child termination, and power-loss recovery
  remain distinct acceptance work. Linux delegated cgroup-v2 remains OPEN
  and explicitly deferred.
