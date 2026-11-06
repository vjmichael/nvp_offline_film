# NVP DATA-TIME-01 — Authoritative event timeline, frame-independent film data

**Creator decision (2026-11-05):** NVP's canonical film timeline is not a list of video frames. It is an indexed, revisioned, time-addressable world of actions, dialogue, actor performances, camera movements, lights, props, sound, causal state changes and their provenance. Freeze 2D pictures *only when a presentation backend needs images, previews or delivery frames*. Approved Digital Takes remain frozen and versioned source data; derived picture and audio outputs never become a replacement for that authority.

**Implementation status:** First typed temporal-event ledger, FilmIndex revision dependencies, sparse event queries and bounded derived presentation-time plans committed. Existing frame-based media import/editor and B14 conform are still separate legacy/media adapters; migration and full Digital Take integration remain OPEN.

## Why this is important

- One authored action can be reused for a 24fps cinema presentation, a 60fps preview, or a different artistic interpretation without rewriting its source time.
- An actor moving a hand at 01:42:18 is one timed performance action, not thousands of rows of frame images. Sparse keyed animation and continuous world trajectories are evaluated at requested times.
- Changes can invalidate a specific actor, property, time interval and downstream render/audio work. Unrelated scenes need not be touched.
- A film can exceed three hours while its active metadata work remains small. File storage and VRAM consumption depend on *the current work window*, not the whole feature.
- FilmIndex source IDs and immutable revision document digests remain authoritative. A camera-move event references the exact camera revision and approved take; never just a drive path or a mutable current revision.
- AI assistance can eventually use typed actions, timelines, source references and retrieved intervals. This does not authorize the deferred AI layer or grant a model direct media access.

## Three distinct clocks

1. **Authoring/event time:** NVP v1 uses signed 64-bit integer ticks at exactly 7,056,000,000 ticks/second. This clock represents an exact rational domain for common 44.1/48/96/192 kHz audio grids and 24000/1001, 30000/1001, 24/25/30/60fps sample grids. More exotic rates must be converted with explicit, documented rounding or a future rational-time type; never silently truncate. A three-hour film remains well within the signed 64-bit range.
2. **Source-media time:** Imported camera recordings are already sampled streams with source PTS/keyframe indexes. NVP's separate SQLite/FFmpeg media adapter maps original presentation timestamps onto event-time scopes. Source camera footage and audio samples *cannot be made unsampled after recording*. The source frame index is a tool for reading those assets; it is not the ontology of the film.
3. **Presentation/export time:** A worker requests a bounded authored time window, an output cadence/clock, exact source revisions and style, then evaluates world state and actions to render image/audio samples. An output time grid is derived from the frozen source and never retroactively modifies it. Keyframe interpolation/retiming/actor motion evaluation remains an explicit engine capability gate.

For example, an action at authoring tick 7,056,000,000 is at exactly one second. It is not inherently frame 24, frame 60 or audio sample 44,100. Those are *projection choices*. The number of rendered frames is a property of a presentation job.

## Implemented typed event contract

The native `TemporalLedger` stores immutable, project-scoped authored revisions in SQLite. An event has `event_id`, `event_kind`, `subject_id`, `start_tick`, `end_tick`, exact `source_id`, `source_revision`, source FilmIndex document SHA-256, and a small typed JSON payload. Instantaneous events use `start_tick=end_tick`; sustained actions are half-open intervals `[start_tick,end_tick)`. Event kinds cover action, gesture, expression, dialogue, camera, lighting, prop, world, sound, music, cut and annotations.

A `temporal` FilmIndex revision stores the aggregate event count, timebase, duration and SHA-256 of the ordered sparse event manifest. A trusted transaction-time guard checks the exact referenced revisions and commits all indexed event rows with FilmIndex in **one SQLite transaction**. An interrupted or conflicting publication cannot create a falsely authoritative timeline. Source impact lookup now includes the normalized temporal event dependency index without stuffing tens of thousands of edges into the 128-edge FilmIndex JSON limit.

`events_at(...tick)` retrieves active events and instantaneous triggers. `events_in(...start_tick,end_tick)` pages bounded intervals using time indexes; metadata-only and no frame expansion. `verify` streams all event rows and rechecks the manifest and referenced FilmIndex source digests before authoritative final publication.

`TemporalProjection.prepare` projects a bounded time window onto a requested presentation cadence (24 or 60fps, for example), returning only sample times and the relevant exact source events. **It does not render frames, infer intermediate motion, approve an action or publish a master.**

## Data still to build

1. **State and curves:** Define reproducible world-state snapshots plus sparse vector/quaternion/camera/rig/audio parameter curves, interpolation rules, temporal overlap and deterministic event evaluation order. One event payload is not a substitute for motion trajectories.
2. **Capture migration:** Freeze this authored event timeline into actual Digital Take Packages, alongside scene assets, camera/performance/audio source revisions, consent and approvals. Existing frame-scoped packages remain compatible until a governed migration is accepted.
3. **Media adaptation:** Map external camera PTS to authored time with explicit synchronization, source offsets, discontinuities and VFR policy. Preserve the original media frame index and real file provenance.
4. **Production:** Have the native renderer/AI presentation adapters request a time interval and evaluable world state, not an arbitrary frame stack. Sampling pictures is a derived step; engine-specific window overlap and determinism still apply.
5. **Invalidation and recovery:** Use exact time intervals and typed dependency edges to schedule the smallest correct safe regeneration unit; recover interrupted derived work without altering source events.
6. **UI:** Provide a human-first action timeline with event markers, scene/actions search, actors and dialogue tracks, timecode display, and editable visual curves. The human may choose to display frames/timecodes, but data authority remains time/event-based.

Do not conflate "film events are not frames" with "no frames exist": imported footage, lo-fi viewports, generated video models, renderers and final DCP contain pictures. The requirement is to postpone sampling/materialization until it serves a specific operation.

## Benchmark boundary

BENCH-01 compares **only the source-video frame-access adapter** (NVP SQLite/FFmpeg versus FFMS2 C API), not NVP's authored temporal event representation. FFMS2 cannot represent actor intentions, script actions, world state or persistent camera motion; it is a video-index/decode library.

See `docs/NVP_BENCH01_OWNED_INDEX_VS_FFMS2.md`. FFMS2 is allowed as an isolated benchmark dependency, not part of the NVP installer. Comparisons require measured CI artifacts and cannot be claimed until real native results have passed.

## Audio clarification — data-first sound access (2026-11-06)

**Creator correction:** The authoritative NVP editor/playback model is
time-addressed **data**, not an array of rendered video frames, and the same
applies to authored sound. The authoritative data are semantic sound/dialogue/
music events, sparse automation curves, exact time spans, source media identities
and revisions. The native read/mix/render boundary may evaluate samples from
immutable recorded media at a requested Film Time. PCM samples are *derived or
recorded media data*, not a replacement for the production source graph.

**Audio access format recommendation, not yet an implementation mandate:**
- For sample-exact native read/mix/scrub/reverse, use bounded **PCM** windows;
  a 48-kHz uncompressed WAV (or BWF for exchange/time-reference metadata)
  supports direct sample-block offset calculation and reverse sample reading
  without whole-file decoding. For long continuous exports use RF64/BW64
  when a classic RIFF-WAV size cap would be exceeded.
- **FLAC** with seek points is suitable for lossless, space-saving source
  storage; seeking and reversing require local compressed-block decoding to
  PCM. It is not a byte-for-byte direct sample address like PCM.
- MP3, AAC and Ogg Opus are valid input/output formats, not preferred
  authoritative editing intermediates. Seek accuracy depends on container
  indices, decoder priming/pre-roll and packet dependencies. Never infer
  exact source audio sample positions from compressed byte offsets alone.
- Imported originals (WAV, FLAC, MP3, Opus, AAC, etc.) remain hashed and
  unmodified. NVP should build a versioned, disposable index and decode
  **only the needed window** to a bounded PCM ring buffer. The sample-rate
  conversion between 7,056,000,000-tick Film Time and each source sample
  clock must be exact-rational or have an explicit rounding rule, including
  source start offsets/encoder delay.
- Seek backward = choose an earlier Film Time and read there. Audible
  **reverse playback** additionally requires ordering decoded PCM samples
  backward and correct channel/transition treatment; playback direction
  is an editor instruction, not a file-format property.
- The current INDEX-TIME-09/10 H.264/AAC temporary review proxies are
  **derived presentation adapters**, not the canonical Film Time model
  nor proof of an accepted direct-data audio engine. Avoid describing
  authoring or playback navigation as frame-driven. Video codec picture
  samples remain an internal rendering/decoding implementation detail.

**Acceptance required later:** sample-exact random seek in both directions,
bounded scratch/RAM, continuous clock alignment across multi-source clips,
dialogue/music stems, gaps, cancellation/restart, and unchanged original
source hashes. Existing CODEC/FFprobe checks alone do not prove these.

