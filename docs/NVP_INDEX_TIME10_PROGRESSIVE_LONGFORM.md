# INDEX-TIME-10 — Progressive Long-Form Assembly Playback

**November 6, 2026 · Initial production implementation on a stacked draft
branch; native Windows/Linux and physical installed-app acceptance pending.**

## Scope correction — native captured sound

Only sound **generated, performed or recorded during filming of a 3D
Digital Take** is in the proposed BWF captured-stem policy. Editor-imported
music/FX (MP3, etc.) are separate immutable media sources and do not
require recoding. The governing Digital Take is the typed event,
emitter/microphone-transform and source-revision graph. An optional
BWF microphone print is an indexed audio signal, not the authoritative
semantic 3D take. Real playback should evaluate source events and
generate needed acoustic PCM windows directly; FFmpeg is limited to
external media import, review/presentation and export boundaries.
See `NVP_DATA_TIME01_EVENTS_NOT_FRAMES.md#capture-sound-01--filmed-3d-scene-sound-versus-imported-soundtrack-2026-11-06`.

## Authority reminder — film data, not rendered samples

The creator reaffirmed that NVP's **authoritative playback/edit timeline**
is exact-time, data-first source events, spans and immutable references.
Any reference below to 24fps pictures, picture frame counts, video player
decoding or H.264/AAC sections describes a *temporary media adapter*,
not the film's source representation or the required primary editor
navigation model. INDEX-TIME-10 currently adapts authored source data
into review-only MP4 sections; its presence is not proof that a genuinely
sample-windowed, on-demand data-first player has been completed.

The audio-native direction is to map exact Film Time into sample-addressed
source read windows and feed a bounded PCM mixer/ring buffer. WAV/BWF
supports direct PCM sample offsets; FLAC with seek tables supports
lossless indexed seeks with bounded block decoding; MP3/AAC/Opus need
codec-aware indices, priming/pre-roll and local decoding. Existing input
originals remain untouched. See `NVP_DATA_TIME01_EVENTS_NOT_FRAMES.md`.
This is a design clarification, **not a claim of code acceptance**.

## Product contract

NVP must always edit **assemblies of immutable source references** and
must never cut, overwrite, transcode in place, or remaster the frozen camera
recordings or their original audio. A FilmIndex revision is the versioned
assembly's immutable provenance. All preview media is disposable and
strictly separate from approved film masters.

INDEX-TIME-09 renders an independently verified, muxed H.264+AAC
24fps/48kHz stereo *review-only* MP4 from one bounded A/V Film Time interval.
INDEX-TIME-10 adds an explicitly approved **progressive session**:
- One native OS consent authorizes review of one exact project/edit/revision/
  source-SHA beginning at the chosen Film Time, up to four hours or its end.
  The limit prevents an open-ended native authority. Another session
  requires new creator approval. Source changes, session expiry, stop or
  native host restart revoke the session.
- Each section is still planned at no more than 20 minutes, no more than
  48 source/gap pieces, 32 source recordings and 160 MiB temporary MP4.
  Output is built by the same SHA-pinned worker under the same resource
  supervisor, process containment, native worker consent binding and
  independent FFprobe+media SHA acceptance as INDEX-TIME-09.
- Only **current + one prepared next** may exist at once (two tickets,
  maximum 320 MiB preview files if both hit their 160 MiB cap). The
  supervisor has a single worker thread: no two 2-GiB encoders run in
  parallel. It can synthesize the next section while the first verified
  section plays from private disk, not while the first is still encoding.
- Intentional editorial black/silent gaps are actual Film Time.
  The planner now retains trailing gaps and can render a bounded
  **gap-only** section using native synthetic black picture + silence;
  it does not silently skip unfilmed time or fabricate recorded media.
  A deterministic test checks this exact planner and graph contract.
- The browser never chooses next Film Time, original source path, native
  executable, output directory or source frame. The trusted host derives
  the next requested start as the current **sealed plan's exact
  `actual_start_tick + review_duration_tick`** and independently replans
  the exact saved edit. Source frame PTS can snap the successor slightly
  backward; native advance requires no missing Film Time and the viewer
  seeks past overlapping held frames.
- After an independent source/codec/duration/SHA receipt, the window
  obtains a distinct opaque URL under the existing 127.0.0.1 bounded
  HTTP 206 media-range route. The next native media element requests only
  metadata while waiting. Original video is never placed in full-size
  browser buffers.
- At `ended` the frontend requests native `advance`; it is authorized
  only for the current ticket + exact session + single prepared successor,
  with both finished/reverified and no Film Time gap. The old ticket,
  already-finished worker outputs and corresponding disposable files are
  revoked. The single media element loads the approved next file and
  attempts to resume from the exact overlap offset. If the next proxy is
  not yet ready, **both picture and sound pause together** and resume
  only when a verified successor arrives. There is no silent skip.

## Memory and latency

This design consumes a maximum of two temporary media files, each at most
160 MiB, on **disk**, rather than putting two complete MP4s into JS RAM.
The HTTP route still returns at most 1 MiB per range. Only one FFmpeg
worker, with the existing 2 GiB worker resource admission, can encode
at a time. The player uses HTML media-element buffering. That buffering
is **not a formally enforced 256 MiB process cap**; actual Windows
WebView2 buffers, decoded frame residency, CPU/GPU behavior, fast-start
range playback, timeline seek latency and cache peak must be measured on
installed machines. Do not advertise hard memory compliance until then.

An independently rendered H.264/AAC file per section and a media-element
source switch may cause a short playback gap and AAC priming artifact.
**This is progressive ahead-of-playhead review, not yet an independently
verified sample-exact/gapless feature-film timeline.** Later migration to
a measured fMP4/MSE or native shared-clock segment engine may be needed
for seamless music/dialogue and true arbitrarily long playback. A
successful unit test does not establish perceptual continuity.

## Trust, cancellation and crash boundaries

Progressive begin/prepare-next/advance/stop methods exist only on the
trusted `NativeVideoDesktop` bridge. The 4-hour session token is random,
window-local and not reconstructible from SQLite. Each child operation
has its own task/approval ID, exact per-source media plan SHA, pinned
Python/worker/FFmpeg/FFprobe hashes, OS confinement and durable TaskLedger.
A stopped session revokes both tickets and queued worker approvals. Its
running worker is signaled for cancellation, and output cannot be served
while it is stopped. The worker supervisor must independently reap the
OS process tree before resources are released or scratch output discarded.

On a native-host restart, no progressive session is reconstituted.
Previously persisted grants are marked revoked. Queued stale tasks are
cancelled. An ACTIVE/OBSERVING task is not blindly marked successful or
released: it remains an explicit containment/recovery problem until the
OS has independently established worker termination. The new host
cannot return media bytes from an abandoned private ticket.

## Test and acceptance evidence

- `tests/test_nvp_index_time10_progressive.py`: host-derived exact next
  tick, unauthorized session/anchor refusal, one successor only, session
  limit, unverified-next refusal, no-gap advance, old ticket revocation,
  cancel both slots and fail-closed restart.
- `frontend/src/SynchronizedAssemblyReview.test.jsx`: progressive
  creator approval, next reviewed media ticket, handoff on `ended`,
  single new segment while originals remain intact, session stop, and
  absence of the progressive control on older native builds.
- Re-run `tests/test_nvp_index_time09_av_proxy.py` with **real FFmpeg**
  original long-GOP/VFR camera picture and tone, gap and silence, and
  `tests/test_nvp_index_time09_media_range.py` to preserve verified,
  bounded, origin-restricted media range security.
- Workflow `.github/workflows/nvp-index-time10-progressive.yml`
  explicitly targets Windows 2025 and Ubuntu 24.04 Python 3.11/3.13,
  bundled native picture/audio media tools and React/Vitest. The actual
  exact-head result must be inspected before marking native acceptance.

**Still open:** genuine two-section 20+ minute native footage playback
using a physical NVP application; external independent host-crash →
worker-tree cleanup → restart ledger reconciliation; Windows installed
NSIS interaction; Linux packaged app acceptance; measured start/seek
latency and RAM peak; guaranteed frame/sample-exact segment joins;
invisible transition timing under CPU and GPU pressure; multitrack
dialogue and music. Never replace these with a mocked assertion or a
green job on a different commit.
