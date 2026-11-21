# FILM-01A — Bounded, restartable picture-frame batches

**Implementation:** `backend/nvp_frame_batches.py`, with `tests/test_nvp_frame_batches.py`.  
**Status:** Primitive committed and unit contracts written; the 30–60 second production pipeline is **not yet integrated or accepted**.

## Reason for this gate

The first complete short film requires 720–1,440 final frames at 24 fps. B12 currently limits original media to 120 frames, B13 and B14 conform to 480, and the B14 technical MOV uses a whole-clip temporary RGB48 file with a 1 GiB staging guard. Raising constants alone risks resource exhaustion and does not create safe streaming, recovery, or continuity behavior.

## Delivered primitive

- Plan contiguous, source-bound edit-frame windows in independently addressable batches of 1–96 frames.
- Preserve source-frame number, shot ID and original blob SHA across rearrangements and repetitions.
- Seal each batch plan against the exact source edit revision SHA and exact ordered frame map.
- Write each frame separately and fsync it. Publish a deterministic receipt only after its entire batch is materialized.
- Reopen an existing complete batch and independently hash **every** frame before reuse.
- Fail closed when a checkpoint is partially written, missing or modified. No automatic deletion, overwrite, duplicate execution or inferred success.
- Keep native host approval, actual FilmIndex indexed-source verification, resource admission, process containment and final publication in their existing trusted owners.

The helper's mock image bytes in its unit tests are not actual film frames. The tests exercise batch lineage and crash-safety contracts only; they cannot establish visual, color, audio or export quality. This helper does not independently detect a whole-project revision being superseded while it runs; the trusted host must recheck the exact FilmIndex source before admission and final publication.

## Next production work, ordered

1. **FILM-01B:** Route real FilmIndex B12/B13 mapped source rows through this batch processor, pin exact authorized edit, enforce PNG16 dimensions and source EXR/color lineage, and use native TaskLedger admission and worker containment.
2. **FILM-01C:** Replace fixture-only B12 120 and B13/B14 480-frame limits with bounded, source-verified multi-batch production policies; preserve a conservative small-fixture pathway until production acceptance.
3. **FILM-01D:** Convert the B14 scene-linear RGB48 technical MOV into streaming or bounded segment stages, including exact color conversion, segment boundary audit, timebase and deterministic conform.
4. **FILM-01E:** Connect actual synchronized 48kHz audio (2,000 samples per frame at 24 fps) and independently verify complete 30–60-second deliverables.
5. **FILM-01F:** Full creator-approved real short, at least three shots and two cuts, human visual review, post-restart reopen, source hashes, native containment and crash recovery.
6. Keep cinema/DCP and installed Windows alpha as independent release gates; neither is a prerequisite to developing the 30–60-second film engine.

**Do not classify the current stage as accepted NVP-FILM-01** until real native media and human creative acceptance pass. The AI Assistance Layer is paused by the creator until the core filmmaking system is complete.
