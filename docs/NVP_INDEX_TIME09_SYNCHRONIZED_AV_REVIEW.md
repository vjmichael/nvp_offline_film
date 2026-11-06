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

A completed derivative must be at most **160 MiB**. The worker
writes a canonical SHA256 receipt and the host independently validates
streams, timing and complete proxy file bytes. The browser does **NOT**
receive the entire MP4 via `pywebview.api` or construct a whole-file
JavaScript Blob: after a native `get_synchronized_av_stream` verifies
the exact revision/ticket, it receives only a relative media URL under
the local 127.0.0.1 NVP application origin. The read-only FastAPI
`/api/native-av-review/{ticket}/media` endpoint requires the active
native window, an unpredictable private ticket, same-origin requests,
a current source/edit/PTS binding, independently audited MP4 SHA and
unchanged file/source stamps. Only **HTTP 206 byte ranges up to 1 MiB**
are returned per request. WebView2 can request initial, random-seek or
suffix MP4 ranges while retaining the video on NVP's private disk
rather than pinning an entire 20-minute MP4 inside JavaScript RAM.

The native H.264/AAC media element still chooses its own decoded-frame
and compressed-data buffering: **the 256 MiB preview RAM budget is a
design target, not a proven hard memory limit yet**. NVP should aim for
3–5 seconds buffered ahead, 1–2 decoded seconds, ~1 second behind, and
~0.25–0.5 seconds audio buffer, adapting resolution/queue depth under
pressure. Even with 20-minute review sections, neither source movies
nor all original frames are decoded into RAM. Closing, scrubbing,
cancelling, replacing or superseding an edit revokes the ephemeral
ticket and deletes temporary derivative files only; captured media,
index, source hash and editorial revisions remain untouched.

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


## Off-GitHub native acceptance procedure

`tools/nvp_index_time09_independent_acceptance.py` is now included as a
reproducible engineering QA harness for Windows and Linux *outside* a
GitHub Actions runner. It runs real original VFR picture+sound/native
worker tests, source edit preservation and original-PTS frame inspection
from disposable local fixtures, then emits a SHA-grounded JSON evidence
report, with a strict pass/fail exit code and no remote build services.
On a physical Windows system with an **already installed** NSIS
`NVP.exe`, its optional `--installed-exe` option also invokes the
packaged executable's native original-import/source, synced A/V worker
and real WebView2 UI smoke commands; it does not build or install NSIS
on the test computer. Actual human audio perception, mouse input and
in-app physical clickthrough still require a separate manual
acceptance record. No developer CLI is exposed to filmmakers.


## SYSTEM-READY-01 — Automatic prerequisite discovery and safe installation

The NVP desktop now has a **System readiness & packages** screen
accessible even before opening a project. It inspects bundled or
already-installed FFmpeg/FFprobe, the Windows WebView2 runtime (with both
per-user and machine-wide registry views), Debian/Linux GTK/WebKit2
library availability and cache free disk space. Inventory is read-only.

On **Windows**, NVP's NSIS single installer already includes its Python
interpreter, original-frame and A/V worker scripts, and real SHA-pinned
FFmpeg/FFprobe executables. No Python/pip or FFmpeg install is required
from the filmmaker. At packaging time the trusted Windows release workflow
downloads Microsoft's Evergreen WebView2 bootstrapper from Microsoft's
link, requires a valid Microsoft Authenticode signature, and embeds it.
NSIS checks the actual installed WebView2 registry and asks permission to
run the bundled Microsoft installer **only if WebView2 is absent**; it
verifies the registry again and refuses a falsely successful setup.
Offline users without WebView2 require a separate signed offline
standalone runtime variant in a future installer; this bootstrapper needs
internet access when invoked.

On **Linux**, a read-only scan identifies GTK/WebKit and FFmpeg gaps.
If a supported apt+polkit environment is present, the user can choose
a fixed allowed repair in the GUI. NVP then requests a second native
confirmation and the OS's own privilege authorization before
`apt-get install` of the exact, hardcoded official repository packages.
An unknown distro/manager shows an actionable limitation rather than
guessing a package name, running arbitrary shell commands or installing
software without permission. The OS package manager's own failure or
refusal is reported as failure. This is NOT a promise that every Linux
distro is fully packaged or independently accepted.

Native package detection and fixed installation policy are implemented
in `backend/nvp_system_packages.py`, with pywebview bridge methods
`system_package_inventory` and `repair_system_package`, the main
`frontend/src/SystemReadinessPanel.jsx`, and independent mocked
approval/install tests. All film footage remains unmodified.
