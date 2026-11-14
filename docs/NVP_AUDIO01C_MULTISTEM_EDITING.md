# NVP AUDIO-01C — Independent dialogue, ambience, SFX and music stems

**Status:** Implemented as a bounded, worker-side multi-source audio *preview*; exact-head native CI acceptance pending. **Not an approved professional mix, mastered soundtrack, final MOV, theatrical delivery, audio synthesis or model-driven sound design.**

## Scope

AUDIO-01A maps a single original dialogue WAV directly to B13 picture frames. AUDIO-01B separates one source's sound timing from picture timing, allowing J/L edits and fades. AUDIO-01C adds multiple independent **source WAV files** for dialogue, ambience, SFX and music. Each stem has its own source length, clip address, gain envelope, source SHA, indexed isolated WAV output and separate FilmIndex provenance. All outputs retain the exact B13 timeline frame count but the audio edits do **not** need to follow the picture source frame map.

Implementation: `backend/nvp_audio01c_multistem.py`; acceptance fixtures `tests/test_audio01c_multistem.py`. Exposed functions:

- `validate_stem_plan(plan, sources, output_frames)`
- `create_multistem_preview(capture, project_id, edit_id, revision, sources, plan, destination, audio_id)`
- `verify_multistem_preview(capture, project_id, audio_id, destination)`

## Source and edit plan contract

The `sources` mapping binds a unique portable `stem_id` to an independently authorized PCM WAV path. Every WAV must be actual signed PCM16 **48kHz stereo**; lengths may differ from each other and from picture duration. The format is pinned to this profile for the first controlled implementation. Every clip uses **integer per-channel sample indices** (not floating seconds):

```json
{
  "stems": [
    {
      "stem_id": "dialogue_a",
      "kind": "dialogue",
      "clips": [{"out_start": 0, "out_end": 4500, "source_start": 0, "fade_in": 0, "fade_out": 500, "gain_milli": 1000}]
    },
    {
      "stem_id": "roomtone",
      "kind": "ambience",
      "clips": [{"out_start": 0, "out_end": 8000, "source_start": 12000, "fade_in": 0, "fade_out": 0, "gain_milli": 1000}]
    },
    {
      "stem_id": "door",
      "kind": "sfx",
      "clips": [{"out_start": 1800, "out_end": 3800, "source_start": 0, "fade_in": 300, "fade_out": 0, "gain_milli": 1000}]
    },
    {
      "stem_id": "score",
      "kind": "music",
      "clips": [{"out_start": 2000, "out_end": 8000, "source_start": 0, "fade_in": 0, "fade_out": 0, "gain_milli": 500}]
    }
  ]
}
```

A clip's `out_start` is inclusive and `out_end` exclusive. `source_start` points into that stem's original frozen WAV. Fades apply integer thousandth linear envelopes; `gain_milli` is from 0 to 1000. Multiple clips may overlap and sum. Silence is preserved wherever no sample clip is assigned. Requested samples must exist in the exact source file.

Bounds: 1–8 stems; 1–128 total clips; no more than eight simultaneous clips; output 1–480 frames at 24fps; source WAV up to 30 minutes per stem; working memory uses 1,024-sample streaming blocks rather than loading the entire WAV. This is a **short-fixture acceptance gate**, not yet full-feature scalable film length.

## Render and clipping policy

The worker opens sources read-only. It renders one separate PCM16 WAV per stem, plus a composite `multistem_preview.wav`. Intermediate gain multiplication uses integer arithmetic and symmetric nearest-integer rounding. If any isolated stem or composite result would exceed the PCM16 range, the worker **fails** rather than silently clipping. There is no final-film loudness standard, true-peak detection, dithering, resampling or limiter yet.

The output WAVs and manifest are placed under a previously absent caller-selected destination (host authorization required). Original sources are rehashed after rendering to detect changes. Each source and result is independently indexed with SHA-256, and an immutable `audio` FilmIndex revision records the B13 edit, B12 delivery, original take, sample map, per-stem type, source duration, clips, SHA and output file. Verification reopens the project, validates each source/result from FilmIndex and **recomputes the entire output PCM in blocks** against each stem and composite WAV.

Output status is `unapproved_multistem_audio_preview`. Director approval, picture lock, final mix and final mastering are all explicitly false.

## Security and lifecycle boundaries

This is a worker-side calculation, not an end-to-end authorized native sound tool. The native host still must enforce permissions for every source and destination, parent path/symlink containment against races, resource bounds, separate OS worker containment, cancellation, cleanup, failure recovery, and crash-safe multi-file staging. Indexed outputs are not published as a FilmIndex revision if the worker throws before final registration; failed staging directories may remain for trusted cleanup.

No AI role grants authority: it may propose exact-stem edits for review only. Explicit user/director approvals precede authorization and execution.

## Windows/Linux acceptance

CI must compile the implementation and run `tests/test_audio01c_multistem.py` on both platforms alongside B14/AUDIO-01A/AUDIO-01B. Tests must demonstrate:

- Four independently sourced WAV stems and a mixed preview, with independently known sample values at multiple film positions.
- Different WAV durations; output exact 48kHz/24fps sample counts and separate picture/audio timing.
- Original sources remain byte-identical; indexed outputs survive DB reopen and pass deterministic sample replay.
- Reject invalid clip source bounds, unsupported categories, gain overflow, output overwrite, altered isolated stems, forged manifests, and PCM clipping without FilmIndex publication.
- Preserve B14 real Blender picture-edit conform acceptance.

## Remaining work

AUDIO-01D should add scalable full-length clip scheduling, incremental block/chunk receipts, native host-supervised cancellation/recovery and cross-platform secure staging. Then add broadcast/theatrical loudness and true-peak measurements, stem-bus controls, mixing automation, optional 24-bit/float exports, sound designer review, approved audio master and verified picture+sound mux. Nothing in AUDIO-01C should be described as a completed professional soundtrack.

Reference: `docs/NVP_AUDIO01B_DIALOGUE_J_L_EDITS.md`. NVP Acting Research is a separate branch and does not block this media pipeline.
