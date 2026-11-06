> **Superseding decision (2026-11-06):** FFmpeg is NOT used by NVP, including imported conventional media, audio render, final 2D presentation or export. Any references below to FFmpeg as optional conversion/export are withdrawn. Seek independent non-FFmpeg library implementations. [DA-00–DA-07 ledger](NVP_DATA_ALL_TASK_LEDGER.md).\n\n# NVP-SOUND-01 — Native spatial sound through the digital film world

**Creator correction: November 6, 2026. Architecture direction accepted [C];
library evaluation, code integration and independent E2E acceptance OPEN [B/D].**

## Decision: the 3D world remains the sound source of truth

**NVP must not treat a recorded WAV/BWF, a pre-mixed stem, a decoded PCM
stream, an MP3, or a transient audio export as the authoritative record of
the sound that occurred during a 3D filming session.** The immutable
Digital Take Package freezes the original **scene/performance/sound-source
data**, including causal sound events, sound-producing object and actor
identities, exact Film Time events, geometry/acoustic material revisions,
transform/trajectory curves, references to source dialogue/voice/sound
assets, virtual listener/microphone options, and asset provenance.

OpenUSD is the spatial scene and media-description interchange/authoring
layer; UsdMediaSpatialAudio primitives attach referenced audio sources
to scene objects, define spatial versus nonspatial playback, media
references, gain, start/end time and loop mode. NVP keeps additional
typed source semantics, acoustic material properties, event causality,
source identity and precise Film Time in the shared temporal ledger.
OpenUSD SpatialAudio alone does not generate waveforms for footsteps or
voices, model wall occlusion or reverberation, or encode causal meaning.

A physical sound signal may still exist! Voice recordings, authored
SFX, procedurally synthesized source signals and imported media are
immutable source **assets referenced by the scene**, not a finished
soundtrack or a replacement for the 3D take. A purely semantic event
requires either a source signal or an explicitly specified synthesis
generator to become audible; a sound cue alone does not manufacture audio.

## Runtime chain — evaluation, not flattened media decoding

    Immutable Digital Take + sound asset references
       -> exact-time event/curve/scene evaluator
       -> OpenUSD scene emitter/listener and geometry resolver
       -> source signal reader, voice/procedural generator (as needed)
       -> acoustic simulation: motion, distance, occlusion, reflections
       -> streaming mixer/audio device (bounded PCM buffers)
       -> interactive, disposable preview from current 3D listener

Audio is computed on demand for a requested time window. The listener
or microphone can move; a door can open; an emitter can change location.
Such changes produce a *different audible result* without modifying a
previously approved Digital Take. Preview samples and optional caches
are derived, disposable products, not frozen source authority.

**Implementation preference to benchmark, not final library approval:**
- **miniaudio:** cross-platform device output, sample streaming, node-graph
  routing/mixing, source decoder and basic positioning.
- **Steam Audio:** optional high-fidelity geometry-dependent HRTF,
  obstruction, propagation, reflections and reverb. Evaluate the real SDK,
  performance, third-party license notices, reproducibility and ability
  to render through a virtual microphone. Its Apache-2.0 repository
  licensing must be handled as a bundled dependency.
- **OpenAL Soft:** alternative integrated 3D audio engine and HRTF/EFX
  route, with different LGPL deployment obligations. Compare rather
  than unnecessarily stack redundant mixers.
- **libsndfile:** optional conventional WAV/BWF/sample-accurate asset
  reader/writer and interchange adapter. It is not a scene-audio engine.

**BWF is OPTIONAL:** useful for importing or exporting an isolated
recording, a virtual microphone print, sound stem or delivery interchange;
not a required capture container, serialized Digital Take format or
creator-imposed source intermediate. A user can import MP3 music and SFX
as unchanged referenced assets. Conversion to temporary PCM buffers for
actual audio-device playback is an internal evaluation operation, not
a persistent flattened project soundtrack.

## Flattening boundary: final 2D presentation

Only when producing a **selected, final flattened 2D presentation**
does NVP evaluate the saved scene for chosen camera/time, choose a
listener/virtual microphone and soundtrack deliverable, and render a
definite 2D picture stream plus synchronized mastered audio. Different
selected viewpoints/acoustic mixes can be made from the *same frozen
3D capture*. Conventional audio/video encoding and muxing, including
FFmpeg, belongs **after** the authored scene has been evaluated.
A user-requested quick preview can create temporary output buffers,
but such media is not the Digital Take, a new source of truth, or a final
approved 2D film.

Existing INDEX-TIME-09/10 temporary H.264/AAC review proxies are a
**separate legacy/imported-footage presentation adapter**. They are
not evidence that NVP's intended data-native 3D sound subsystem is
implemented. Preserve their existing regression and physical-acceptance
gates until explicitly migrated; do not silently remove working import
support or call native 3D sound integration completed.

## AI-facing NVP contract

Expose typed queries:
- `sound_sources_at(film_tick, scene_revision)`: emitter, event ID,
  positions and authoritative associated sound/voice asset revisions.
- `acoustics_at(start_tick, end_tick, listener_id)`: scene/geometry/
  material dependencies and evaluated acoustic parameters with
  provenance, not a claim that an audio sample proves their causes.
- `audition(start_tick, end_tick, listener_id, mix_options)`: bounded
  creator-authorized native preview, with optional comparison receipts;
  no source writes, independent worker cancellation, native resource
  limits and clear preview/non-master status.
- `render_final_presentation(presentation_revision, view_and_audio_spec)`:
  explicitly creator-approved flattened output with exact dependency
  digests and delivery-format receipt.

All names above describe **design contracts, not implemented APIs**.
A model never gains direct filesystem/source access by merely discovering
a sound query. Native creator consent and the project's immutable
revision guard remain necessary.

## Acceptance gates still open

1. A USD scene containing a moving sound emitter, material/geometry
   obstruction and moving virtual listener must be queryable at arbitrary
   Film Time through the existing exact event ledger.
2. Playback/scrubbing both directions re-evaluates the scene instead of
   requiring a previously bounced BWF or complete soundtrack.
3. Real direct sound/occlusion/reflection behavior is independently
   validated across Windows/Linux in a bounded real process, including
   restart, cancellation and sound-device failure.
4. Two different virtual microphone positions yield distinct expected
   sound renderings from the **same immutable Digital Take SHA**.
5. Explicit final-presentation approval produces synchronized 2D
   picture/audio delivery artifacts; reopening the 3D source yields
   unchanged event, object and asset digests.

**No complete implementation or runtime acceptance is claimed here.**
