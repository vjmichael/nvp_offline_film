# INDEX-TIME-09 — Continuous Non-destructive Film Time Playback with Sound

**November 6, 2026 · Implementation committed, native full-app/installed Windows acceptance not yet proven.**

## Audience and goal

NVP's captured footage is external, hashed, versioned source-of-truth.
An editorial assembly contains immutable *references* to original camera
frames/PTS and exact Film Time positions; a change to that arrangement
never writes into the recorded picture or sound. The slate describes
production metadata, not the source player. Playback observes an edit.

The prior INDEX-TIME-08 player showed up to 96 individually audited PNG
frames, stepping from one source PTS window to another. That is excellent
for precise inspection but **not** long uninterrupted playback with sound.

INDEX-TIME-09 adds **Watch your assembly with sound** in the Indexed
Footage desktop editor. A creator chooses a starting position, confirms
one trusted OS review dialog and NVP creates a bounded, temporary,
unapproved H.264/AAC MP4 from the **current exact FilmIndex edit
revision**. The HTML video element uses the file's single multiplexed
picture/audio clock, not independent JavaScript audio timers. Once the
derivative is verified and loaded, it plays continuously for up to
**20 minutes** or the end of its bounded section. A later section may be
prepared from the resulting Film Time position. A complete feature film
is not preloaded into original-media RAM.

**Camera sound supported now:** first embedded source audio stream, with
48 kHz stereo normalization. A clip with no source audio contributes
silence. An intentional editorial gap contributes both black frames and
silence. Existing separately indexed soundtrack/dialogue/multistem
AUDIO-01 production conform remains separate. This is not yet
multitrack audio mixing or an accepted final Dolby/DCP asset.

## Exact source to preview mapping

- The native trusted planner verifies the current FilmIndex original
  source SHA/revision, project, media volume, stamp, full saved edit
  manifest, source PTS in/out, and exact authored Film Time duration.
- A requested start within a held VFR frame is snapped to that actual
  source frame PTS, not nominal frame rate. A requested start in a gap
  preserves the black/silent interval. The maximum planned review
  interval is 20 minutes; at most 48 source/gap pieces and 32 unique
  recordings. The source data never gets rewritten or copied as input.
- Inside an authorized OS-contained worker, FFmpeg reads those exact
  original PTS intervals, selects and resamples picture into **24fps
  REVIEW ONLY**, resamples corresponding embedded audio to **48kHz
  stereo**, and pads each segment to the same exact count of 2000
  audio samples per 24fps video frame. The concatenated video and sound
  share one MP4 media clock; gaps are intentionally black and silent.
- The native verifier requires a genuine H.264+AAC video/audio pair,
  exactly the planned output-frame count, 48kHz stereo sound, independently
  measured stream durations and audio/video drift **not exceeding 50 ms**.
  The proxy's 24fps conversion and AAC encoder priming are not a claim
  of VFR frame-exact final-media conform.
- Audio and video come from the original recording's actual input
  streams. If a camera recording has no embedded sound, NVP does not
  invent a dialogue/music track. Adding independent editorial sound
  tracks will use the existing Audio workspace and its revisioned
  source identity in a later wave.

## Native trust and memory

The installed desktop, not JavaScript or a model, owns file access,
real user approval, and arbitrary executable selection. The trusted
window authorizes exactly a project/edit/revision/SHA, starting Film
Time, bounded source/input media paths, native tool digests and output
scope. The operation uses `ApprovedTaskBindings`, `TaskLedger`,
existing native resource admission, and `launch_contained` /
`wait_guarded` for Windows Job Object/Linux process containment.

A SHA-pinned native `nvp_av_proxy_worker.py` executes as a separate
worker process, or inside installed frozen
`NVP.exe --trusted-av-proxy-worker`. Worker checks pinned tool hashes,
the exact original media PTS plan and source stamps before and after
decoding. Partial or changed output is never claimed as accepted.
Task journaling, exit/kill verification, and reservation clearing must
precede success. Failure and unproven recovery never return pixels.

A completed derivative must be at most **160 MiB**. The worker writes
a canonical SHA256 receipt and the host independently validates stream
types, timing and full file bytes. Browser access is not an HTTP media
path: an opaque, per-window review ticket permits at most 1 MiB binary
chunks over `pywebview.api`. Every chunk is SHA-checked again in the
browser and the complete assembled temporary Blob is compared against
the native media SHA. HTML5 `video` loads only the verified private
Blob URL. Closing, scrubbing to another source, cancellation or a
new immutable edit invalidates the ticket and temporary output.
Temporary proxy files are deletable; original capture files and
historical FilmIndex/source indexes are not.

## Verification

Native tests `tests/test_nvp_index_time09_av_proxy.py` create real
long-GOP/VFR camera material with a sine-tone embedded audio stream,
a separate video without audio, and a significant intentional gap.
They test actual source identity and PTS plans, picture+sound mux,
48kHz stereo, independent FFprobe stream drift, nonzero source audio,
native user denial, foreign origin, altered camera bytes, contained
worker admission, SHA-checked bounded delivery and disposal without
changing original media. Frontend tests verify native approval,
single media-element clock, exact BigInt film-time cut jumps, independent
chunk and complete-media SHA checks, stale approval cancellation and
continued review sections.

**Independent media-layer experiment:** The implementation's filtergraph
was tested separately from GitHub in an available Linux runtime with
real native FFmpeg. It produced 72 H.264 frames across two source
segments and a black gap, 48 kHz AAC sound and 3.000-second audio versus
2.958333-second reported video stream duration (one 24fps frame apart),
and nonzero decoded audio from an actual synthesized 440 Hz source.
That experiment validated the filtergraph/codec path but is NOT full
NVP integration, installed Windows or native job-guardian acceptance.

`.github/workflows/nvp-index-time09-native-av.yml` requires actual
Windows 2025/Linux 24.04 Python 3.11/3.13 with pinned native FFmpeg/
FFprobe, real image/sound and Linux/Windows containment plus
React/Vitest. `--smoke-source` additionally requires a real installed
NSIS Windows `NVP.exe` to use its bundled SHA-pinned AV worker,
publish a verified H.264/AAC proxy, prove ≤50ms drift and leave the
source SHA intact. `--smoke-window` verifies that the real WebView2
original-film editor mounts sound-review controls. No claim of actual
installed acceptance before those jobs and independent physical test.

## Further work needed for full production

- Incremental prebuffering and seamless *arbitrarily long* feature-film
  playback beyond the current bounded 20-minute section (without
  rebuilding the whole proxy); multitrack external dialogue/music,
  fades, independent source audio/scene timing, and soundtrack mixing.
- Frame-accurate VFR native video preview without 24fps review
  resampling; exact audio-sample correspondence with final conform,
  proper handling of variable source audio offsets, more than the
  first embedded source audio stream, waveform thumbnails and
  audio-level/mute controls.
- Full independent physical Windows NSIS interaction, Linux-native
  installed app verification, adverse crash/kill/restart cleanup and
  FFmpeg/H.264/AAC redistribution/license review before public release.

**Safety/product decision:** The edit can always be rearranged or restored
as a *new* version. Playback and any downstream proxy observe a frozen
source and a selected immutable assembly revision. No source rewrite,
overwriting camera audio, or hidden capture destruction is permitted.
