# NVP AUDIO-01E — Verified WAV materialization and FilmIndex publication

**Status:** First production-integration increment committed; exact-head Windows/Linux CI not yet passed. **Scope is audio-only technical previews**, not final soundtrack, human approval, film-time picture sync, final master or deliverable MOV.

## Why this gate exists

AUDIO-01D stores and verifies frozen PCM chunks so a long stem-mixing job can pause and resume. AUDIO-01E turns a **complete, independently replayed** AUDIO-01D checkpoint into ordinary accessible audio files: one signed 48kHz/16-bit stereo WAV per stem and one stereo composite preview WAV. It records their source and media SHA-256 hashes as an immutable, project-scoped FilmIndex `audio` revision. An interrupted/partial chunk job cannot be published.

## Code and API

- `backend/nvp_audio01e_wav_publication.py`
- `tests/test_audio01e_wav_publication.py`
- `publish_chunked_wavs(capture, project_id, audio_id, plan, sources, total_samples, chunks_dir, output_dir)`
- `verify_published_wavs(capture, project_id, audio_id, plan, sources, total_samples, chunks_dir, output_dir)`

The publisher requires an absent destination under a host-authorized parent, a completed AUDIO-01D checkpoint, exact source hashes and unchanged sample-addressed plan, and full deterministic replay. The source PCM chunks are streamed in bounded chunks to ordinary WAVs without loading an entire soundtrack into memory. Each newly published WAV is independently indexed with `put_media_file` and stored with its SHA in the final immutable FilmIndex audio manifest.

A **separate 48kHz original source** is retained and indexed for every dialogue, ambience, effects or music stem. The verification function reopens FilmIndex and checks the checkpoint digest, per-stem source hashes, manifest equality, output WAV SHA/duration, media registration and **exact reassembled PCM against the original chunk files**.

## Status fields and honest limitations

The FilmIndex entry has `format=nvp.audio.materialized_multistem_preview.v1`, `status=unapproved_audio_only_pcm16_stems`, `picture_bound=false`, `picture_locked=false`, `director_approved=false`, `final_mix=false`, `final_master=false`.

Audio-only outputs have **no asserted film-picture timeline dependency**. B13/B14 remain 480-picture-frame acceptance fixtures; AUDIO-01D's longer audio capability cannot be called film-synced without a separately verified picture edit of the same exact timebase and duration. Audio-plus-picture conform and mux are subsequent work, not silently enabled by this step.

The current trusted worker must still be enclosed by native OS process containment, directory-fsync crash recovery, exclusive output locking and write race protection. The output folder is not automatically removed after a failure; trusted cleanup is required. Checkpoint SHA-256 hashes are integrity evidence assuming protected trusted storage; they are not an attacker-resistant signature scheme. Before a two-hour soundtrack can be publicly claimed, runtime/throughput, storage and failure-injection tests must be performed on actual Windows/Linux hosts.

## Acceptance tests added

- Two independently created WAV stem sources and actual AUDIO-01D chunk render.
- WAV files containing exact expected stereo samples (original voice, attenuated ambience and their real composite).
- Index registration and verification after new SQLite/FilmIndex object is opened.
- Refuse partial/incomplete chunk receipt publication and duplicate FilmIndex audio ID.
- Refuse changed original audio and tampered output WAV.
- Both Windows and Linux CI run the new test, alongside earlier audio A–D and real Blender picture conform.

## Next gates

1. **AUDIO-01E.2:** Native host-admitted and OS-contained worker with journaled intent, restart/cleanup and idempotent commit/recovery; test crash at every file/receipt/publication boundary.
2. **AUDIO-01F:** Bind full-duration editorial picture timeline and rational sample/frame clock (including J/L edits), prove exact frame/sound length, render audition mux and independently probe packet timestamps.
3. **AUDIO-02:** Film sound QC (integrated loudness, true peak, channel order, clipping, edit pops), controlled automation, review/approval, 24-bit/float deliverables and real final mastering profiles.
4. **AUDIO-03:** User-facing multitrack timeline and mixing interface with controlled edits, visible waveforms and buses.

Preserve immutable takes, creator approvals and model-independent native authorization. No model role may automatically approve a performance, change its source audio or claim a technically rendered soundtrack is a final master.
