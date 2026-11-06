# NVP-AUDIO-01A — Exact edited-picture PCM synchronization

**Status:** first native worker-side implementation; current-head CI acceptance pending. Not a movie master, human voice synthesis, sound-mixing engine or native-authorized audio worker.

## Why audio must have its own immutable clock

NVP's Digital Take and performance tracks exist independently of the camera. At 24 fps and 48,000 Hz, exactly **2,000 source audio samples per picture frame**. This contract uses integer mappings, not successive floating-point seconds, and resolves actual B13 editorial frame maps including trims, repetitions and reorders. The result preserves each source frame's exact audio samples, without inventing a speech waveform or silently resynthesizing dialogue.

`backend/nvp_audio01_picture_follow.py`:
- Reads an actual, stereo, 16-bit PCM 48 kHz WAV with a measured sample count matching original source picture duration.
- Independently checks exact B13 edit frame identity and original B12 delivery digest via `_source_rows`.
- Generates a new output WAV by selecting exactly 2,000 source samples for each conformed edited picture frame. It checks the resulting number of samples and copies input/out media into FilmIndex's immutable indexed media.
- Writes a deterministic manifest with source and output SHA-256, edit/delivery/take references and exact frame map, and records a new immutable `audio` revision with dependencies.
- Reopens and independently verifies edit, media hashes, WAV metadata, samples and per-frame source-range equality after restart.
- Flags audio discontinuities (cuts/repeats) as `needs_audio_transition_review` instead of claiming seamless speech and mixer-approved edits.

`tests/test_audio01_picture_follow.py`: true WAV repeated and reordered frame samples, independent verify after reopening FilmIndex, missing source duration, tampering, malformed edited mappings, no output overwrite.

## Clear limits

- This **picture-follow audio conform** is a technical first step. It is deliberately not a J-cut/L-cut editor; audio need not follow picture cuts in a creative edit. The next layer must separately edit audio clips/handles using an independent sample-addressed edit decision map, with overlaps, fades, room tone and isolated dialogue tracks.
- Cannot guarantee click-free hard edits, preserve uninterrupted mid-dialogue performance across independent takes or generate speech/phonemes. Those are explicit next acceptance gates.
- Source WAV must be a real recorded/generated input; no empty placeholder audio is interpreted as meaningful content. Mono, 24-bit/32-bit float, multichannel, ambisonics and production mastering formats are future adapters.
- Per-stage limits (480 edited frames) bound the current fixture, not film length. Implement source/media chunk streaming and audio windows before FILM-01 production length.
- This is still a worker-side algorithm with no creator-grant native scheduling, process containment or OS resource reservation. Do not expose it directly to the AI crew role system, web endpoints or untrusted paths.
- The existing film-master candidate is still silent until a director-approved audio track is separately conformed and muxed; this increment does not change the film's published sound/master flags.
- Audio timebase and metadata survive camera-only shot changes; a new performance/line timing must receive a new audio/performance revision and invalidate only dependent conform/master artifacts.

## Next development gates

1. Verify AUDIO-01A Windows/Linux new-head regression tests.
2. Introduce separate audio edit ranges and J/L-cut overlap decisions, preserve uninterrupted off-screen lines and reject invalid sample offsets.
3. Build a durable dialogue/event timeline with speaker IDs, external WAV/TTS identity and phoneme alignments (actual waveform measured before lips/jaw/tongue performance).
4. Add per-track mixing with peak and loudness QA; mux approved audio into a decoded/verified ProRes 422 HQ technical movie.
5. Extend bounded full-film streaming for 720–1,440 frames and long-duration films; restore/reverify audio chunks after interruption.
