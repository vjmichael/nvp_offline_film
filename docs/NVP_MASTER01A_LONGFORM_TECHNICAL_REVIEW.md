# NVP-MASTER-01A — Bounded multi-reel 30–60-second technical review

**Date:** 2026-11-05  
**Status:** Implemented native technical preview assembly and test fixture; **not AI-generated film, creator-approved picture lock, final-master publication, feature film, model integration or installed desktop acceptance**.  
**Source owner:** `backend/nvp_longform_review.py`; developer CLI in `tools/nvp_longform_review.py`; native tests in `tests/test_nvp_longform_review.py`.

## Motivation

NVP already has working shorter-shot and shorter-reel production machinery. Several finished-media components deliberately enforce per-stage bounds (for example 240 frames for PIPE-01B's initial full-motion renderer and 480 frames for AUDIO-01J). A 30–60-second short at 24 fps needs **720–1,440 contiguous frames**. Raising caps across every existing worker without independent RAM, filesystem, cancellation and crash/recovery tests would endanger existing acceptance. **Assemble multiple bounded reels instead**.

This first stage accepts already-indexed ProRes 422 HQ + stereo PCM24 MOV segments at 24fps, verifies each independently, concatenates exact media streams using native FFmpeg, independently probes the output, verifies continuous video/audio packet timestamps and its 48-kHz audio sample clock, and publishes one immutable, source-linked `presentation` review. It does **not** recode media, invent/forge footage, approximate missing audio, silently change raster sizes, mutate frozen takes, or claim creator approval.

## Data contract

1. The existing production system produces an exact source `presentation` or `master` object with a stored `movie_sha256`/`rendered_mov_sha256`, correct `frames`/`frame_count` and the immutable media file under the same project's FilmIndex.
2. `index_technical_reel(...)` converts the proven source to a short *technical* `presentation` reel, recording a dependency on the producer's exact revision and document SHA. It refuses nonvideo objects, sources without indexed bytes, nonexistent revisions, codec/raster/sample-clock mismatch or reels over 480 frames.
3. `assemble_review(...)` accepts 2–12 ordered `{object_id, revision}` pairs. It never accepts file paths from the model. Every reel is required to be a source-indexed technical reel; names and revisions are validated through the project-scoped FilmIndex.
4. Native `ffprobe` requires one ProRes HQ 10-bit 4:2:2 video stream (tag `apch`, 24fps) and one stereo 48-kHz PCM24 audio stream. Source raster sizes must match; audio samples must equal 2,000 per frame. The total must be 720–1,440 frames inclusive.
5. Native FFmpeg concatenates ordered streams without re-encoding in a temporary directory under the project's FilmIndex store. The output must pass the same exact AV probe, including gap-free packet timing. Every source compressed ProRes frame packet SHA and every decoded PCM24 stereo audio sample is compared with the concatenated output, and the input files are rehashed after native work. The media is atomically stored by SHA; FilmIndex registers a new immutable revision with typed dependencies on **every source reel**.
6. `reopen_review(...)` re-verifies exact original source revisions, document hashes, source media, final media, dimensions, video count, and audio samples from a fresh Studio/FilmIndex instance. A corrupted or missing source or output refuses.
7. `creator_approved_final_master` and `dcp_delivered` are **always false**. This preview is not a creator-authorized final 30–60-second film or DCP.

**Important current limitation:** FFmpeg stream-copy concat presupposes all reels have compatible codec/extradata, frame sizes and clocks. The code checks codec/raster, every video packet payload, decoded PCM samples and gap-free per-stream timestamps; future production acceptance must still validate perceptual picture/sound transitions and real source-model worker integration. Audio and picture are technical fixtures in the test; acting, voice generation, lip sync, camera continuity and narrative quality are separate acceptance gates. The normal application native-worker authorization, OS containment, cancellation and crash journal must wrap this operation before it is exposed as a model-driven or GUI production command.

## Technical validation

```bash
PYTHONPATH=.:tests python -m unittest tests.test_nvp_longform_review -v
PYTHONPATH=.:tests python -m unittest tests.test_nvp_longform_review tests.test_production_end_to_end tests.test_full_motion tests.test_film_index -q
```

Native 2026-11-05 Debian evidence: **30 related tests passed**, including 7 new long-form cases using actual FFmpeg/FFprobe: 36 seconds (864 frames), the 60-second ceiling (1,440 frames), restart/rehash, exact compressed-video and decoded-PCM byte equality, contiguous packet timestamps, injected packet-gap refusal, content tampering, source corruption, incompatible raster, short duration and forged reference rejection. Some test methods combine multiple negative assertions. A separate broader suite including the older AUDIO-01J native integration test exceeded the execution time limit in this container; it is **not claimed passed**. No physical Windows acceptance or actual model-generated footage was tested.

## Developer-level CLI

This CLI performs work as its invoking human/developer; it is not an NVP model tool or evidence of trusted creator authorization. It takes exact FilmIndex reel identities, never arbitrary media paths:

```bash
python -m tools.nvp_longform_review \
  --studio-db /path/to/studio.sqlite3 \
  --project-id YOUR_32_HEX_PROJECT_ID \
  --review-id preview001 \
  --reel reel01:1 --reel reel02:1 --reel reel03:1 \
  --report /existing-folder/preview-proof.json
```

The report contains the verified, content-addressed MOV path. It does not grant approval or rewrite existing outputs. Reel import is an internal trusted Python call `index_technical_reel(index, project_id, reel_id, producer_id, producer_revision)` following genuine existing media registration.

## Next gates toward actual generated film

- **MASTER-01B:** Integrate the assembly into the supervised native production host, with authenticated creator intent, worker termination, journal checkpoints, staging recovery and verified ordering/reel clocks.
- **MASTER-01C:** Bind actual approved NVP digital takes, performance, cameras and production audio to reel inputs. Reopen a real multi-shot world, not generated test patterns.
- **PIPE-01C:** Authorize and integrate selectable licensed/local AI video, performance and voice generation workers with a deterministic, source-bound adapter; verify actual outputs and consistency.
- **MASTER-01D:** Persist an editable timeline for reel joins and source-bounded revision impact; prove regenerate-only-changed-shots behavior.
- **FILM-01:** Produce, inspect and export a continuous 30–60-second creator-approved film with consistent actors, acting, dialogue, framing, real synchronized sound, quality review and independent replay after restart.

Keep all feature-length claims **open** until longer-scoped, resource-bounded, recoverable native production has passed.