# NVP AUDIO-01D — Durable chunked audio stem rendering and recovery

**Status:** Worker-side implementation committed; native Windows/Linux CI pending. This is an **audio-only, unapproved technical preview**, not a picture-locked final mix, mastered soundtrack, or commercially authorized media export.

## Objective

Advance the AUDIO-01C independent dialogue, ambience, SFX and music stem architecture beyond the B13 short-picture acceptance limit. Preserve sample-exact source timing and provenance across long-duration jobs, while supporting explicit cancellation, finite-memory rendering, restart, tamper detection and durable receipts.

Existing B13/B14 picture conform remains bounded by 480 frames at 24fps. AUDIO-01D **does not silently remove that limit**, and does not claim a feature-length film is now conformed. The worker accepts its own exact audio duration in samples; a later full-film index/timebase integration must bind it to an approved picture revision.

## Implemented source

- `backend/nvp_audio01d_chunked_recovery.py`
- `tests/test_audio01d_chunked_recovery.py`
- Linux and Windows gates in `.github/workflows/nvp-stack02c3b14-conform.yml`

### API

`run_chunked_preview(plan, sources, total_samples, directory, *, cancel=None, max_new_chunks=None)`

`verify_chunked_preview(plan, sources, total_samples, directory, *, replay=True)`

Inputs are a versioned caller-controlled plan with **1–8 categorized stems**, sample-addressed clips, independent read-only source stereo PCM16 48kHz WAVs, per-clip gain and optional fade envelopes. Duration bound is two hours at 48kHz; **sample addresses are integers**, not floating-point seconds. The current implementation permits at most 50,000 clips, eight simultaneously active source clips and 1,024-frame inner processing in the AUDIO-01C renderer; AUDIO-01D persists one-second PCM chunks. Render working memory is bounded by chunk size and active stem count rather than total film length.

The render worker produces a separate immutable PCM chunk for each stem plus a composite chunk. Each checkpoint entry records source/output offsets, PCM chunk file names, sizes and SHA-256 hashes. A run never replaces committed chunks; the next run verifies all committed receipts and all input source hashes and clip instructions before advancing. A terminal `complete` marker appears only after every chunk has been committed and audited.

### Cancellation and recovery behavior

A trusted host-supplied cancellation callback is checked **before** each new chunk. If it requests cancellation, the worker returns a resumable state with the last committed sample offset; no partial media is marked complete. A `max_new_chunks` parameter enables deterministic pause/resume acceptance. After a crash during output-file publication but before the receipt transaction, an orphan file may be left; the worker currently refuses it and requires trusted cleanup. The workflow does **not** yet guarantee automatic crash reconciliation or directory-fsync durability. Do not misrepresent cooperative cancellation as enforced OS worker termination.

Checkpoint replacement writes a new JSON file, flushes/fsyncs it, then atomically renames it over the previous checkpoint. The native host must establish a safe, authorized destination and ensure directory write access and OS containment. A malicious local actor with write permission could alter or replace checkpoint files; the current unkeyed SHA receipts detect accidental/cross-restart damage under the trusted-staging assumption but are not cryptographic authentication against an active adversary.

### Verification guarantees

Verification checks:

1. Exact read-only source WAV content hashes and source durations.
2. Stem IDs, kind and bounded sample-plan shape, edit instructions and clip overlap.
3. No missing or reordered durable receipts; each file matches its exact claimed size and SHA.
4. The sequence covers the requested number of output samples with no gap.
5. Optional complete deterministic sample-by-sample replay of isolated stems and composite PCM.
6. `final_mix=false`, `final_master=false`; never claim director approval or picture lock.

### Acceptance tests

The first native CI tests intentionally write real independent PCM WAVs of 30 seconds. They render **25 seconds of two concurrent stems**, pause after three chunks, resume to 25, compare original first-chunk bytes, replay all chunks after restart, reject source/plan mutation and chunk corruption, and verify clipping and illegal sample-address refusal.

The tests prove a bounded worker **can operate beyond the prior picture fixture**, not that two-hour throughput, resource isolation, live host cancellation or professional audio delivery have been accepted. Those must be measured separately.

## Explicitly deferred to AUDIO-01E / native integration

- Durable **effect journal** integrated with NVP's native worker manager, OS process containment and crash reconciliation of pre-receipt chunks.
- FilmIndex media-file publication of complete WAV stems and master, assembling chunked output without holding it in RAM, and authoritative full-length picture/timecode linkage.
- Efficient interval lookup for very large clip counts; the current renderer scans each clip per chunk, which may be slow for heavily edited feature films.
- Streaming output to preview playback/GUI, audio envelope/loudness plots, professional gain automation and interactive editorial timeline.
- Sample rate/channel/layout conversion, 24-bit/float exports, true-peak and LUFS analysis, sound designer approvals, approved soundtrack master, movie mux, delivery.
- Native authorization of arbitrary audio paths, no-follow file descriptors, guard against filesystem race attacks, resource admission, cancellation kill escalation and recovery supervisor.

## Architectural non-negotiables

NVP remains the filmmaker-controlled workspace; AI crew models can propose sound edits but do not own native tool permissions or approve mixes. Source WAVs and frozen takes remain immutable. Rendering is deterministic where defined; impossible, clipping, unsafe, or unsupported operations are reported, not silently repaired. The separate NVP Acting Research branch is unaffected.
