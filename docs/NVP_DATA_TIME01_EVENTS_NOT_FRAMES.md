# NVP DATA-TIME-01 — Authoritative event timeline, frame-independent film data

**Creator decision (2026-11-05):** NVP's canonical film timeline is not a list of video frames. It is an indexed, revisioned, time-addressable world of actions, dialogue, actor performances, camera movements, lights, props, sound, causal state changes and their provenance. Freeze 2D pictures *only when a presentation backend needs images, previews or delivery frames*. Approved Digital Takes remain frozen and versioned source data; derived picture and audio outputs never become a replacement for that authority.

**Implementation status:** First typed temporal-event ledger, FilmIndex revision dependencies, sparse event queries and bounded derived presentation-time plans committed. Existing frame-based media import/editor and B14 conform are still separate legacy/media adapters; migration and full Digital Take integration remain OPEN.

## DATA-AV-01 native A/V source migration — 2026-11-06

The authoritative temporal event ledger and immutable OpenUSD Digital
Take now feed a native FFmpeg-free audio evaluation path, using
SHA-addressed original sound signals and bounded sample queries.
`backend/nvp_data_av_source.py`, `nvp_data_av_scene.py`,
`nvp_data_av_usd.py` and `nvp_data_av_desktop.py` supply recorded
source windows, in-memory `UsdMedia.SpatialAudio` bindings, dry
stereo listener mix and trusted on-demand audition. Captured sound
assets are not synonymous with the flattened soundtrack; neither a
WAV/BWF print nor a video frame sequence is the source of truth.

All previous FFmpeg/indexed-video native runtime references in this
document describe **optional conventional-media source adapters**
and historical proof gates, not the current Digital Take player.
The separate final 2D presentation may encode video/audio after
the frozen source has been evaluated. Detailed active work:
`docs/NVP_DATA_AV01_NATIVE_MIGRATION.md` and
`docs/NVP_SOUND01_NATIVE_SPATIAL_AUDIO.md`.
The new native 3D visual player, complete 3D acoustics and installed
long-form acceptance remain open.

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
