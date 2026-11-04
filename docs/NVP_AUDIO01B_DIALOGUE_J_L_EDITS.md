# NVP AUDIO-01B — Source-accurate dialogue J/L editorial previews

**Status:** Implemented as a bounded worker-side PCM edit and independent FilmIndex verifier; CI verification pending on exact head. **Not** an approved professional dialogue mix, audio master, or native-host authorization system.

## Purpose

AUDIO-01A follows edited picture frames by copying exactly 2,000 source audio samples per 24fps frame at 48,000Hz. AUDIO-01B allows an editor to change *audio timing independently* of picture cuts: lead dialogue in a J-cut, hold outgoing dialogue over the next picture in an L-cut, create overlapping audio transitions, apply exact-sample fades and gains, or leave intentional silence. It does **not** manufacture new dialogue or silently declare discontinuity repair complete.

## Implementation

- `backend/nvp_audio01b_dialogue_edit.py`: `validate_audio_plan`, `render_audio_samples`, `create_dialogue_preview`, `verify_dialogue_preview`.
- `tests/test_audio01b_dialogue_edit.py`: 24fps/48kHz synthetic source fixtures, independently aligned samples, measurable fades, immutable index verification after reopen, refusal to overwrite, WAV tamper and invalid-address rejection.
- Same B13 edit and B12 delivery lineage as AUDIO-01A; content-addressed source and output WAV indexed as `audio/wav`.
- Output preview remains `unapproved_dialogue_edit_preview`, with `final_mix=false`, `final_master=false`, `director_approved=false`, and `picture_locked=false`.

## Contract: exact sample edit plan

The input is a strictly validated JSON-like dict:

```json
{
  "clips": [
    {
      "out_start": 0,
      "out_end": 2250,
      "source_start": 0,
      "fade_in": 0,
      "fade_out": 500,
      "gain_milli": 1000
    },
    {
      "out_start": 1750,
      "out_end": 7750,
      "source_start": 0,
      "fade_in": 500,
      "fade_out": 0,
      "gain_milli": 1000
    }
  ]
}
```

Every position is an integer **per-channel audio sample**, not a frame index or floating-point time. The output duration is anchored to the exact B13 picture-edit frame count (2000 samples per 24fps frame). The audio plan may *depart* from the picture source-frame map by design. `out_start` is inclusive; `out_end` is exclusive; `source_start` is the sample address into a frozen original PCM WAV. Gains are nonnegative integer thousandths, 0..1000. Audio preview is 48kHz, signed little-endian PCM16 stereo. At most 480 frames, 128 bounded clips and eight overlapping active clips; excessive or out-of-range plans are rejected.

A fade envelope starts at zero on the first fade-in sample or ends at zero on the final fade-out sample. Two simultaneous fades combine with a conservative minimum envelope per clip; integer gain and symmetric rounding are applied before signed 16-bit saturation. The resulting output is deterministic under the same source and plan; as with any PCM16 mix, high-level overlapping sources may clip, and **clipping detection, loudness normalization, professional dialogue cleanup, and spectral processing are not yet supplied**.

## Data integrity and safety

The native host must provide authenticated, authorized input/output paths and OS containment. The worker refuses existing output directories and symlink paths at the checked boundary, then indexes frozen source WAV and generated preview WAV by SHA-256. A frozen FilmIndex audio revision carries exact B13 edit, B12 delivery and original take dependencies and the independently authored sample plan.

`verify_dialogue_preview` rechecks indexed original media, output bytes, the stored plan, the B13/B12 picture lineage, exact output sample count, and *deterministically recomputes* PCM from the source and plan to reject tampering.

This is **not** a final authorization/security boundary: an outer native tool host still must perform sandbox path admission, race-safe file creation, worker lifecycle management, cancellation and cleanup.

## Deliberate exclusions

- No invented speech, music, foley, ambience, mastering, DCP, loudness certification, real-time preview UI, or soundtrack approval.
- No per-track independent WAV stems yet. AUDIO-01B uses one original stereo WAV source and bounded clips into an output preview. Multi-stem mixing will require separate time/clip and asset lineage.
- No automatic prevention of audible pops at clip boundaries when no fade is specified; the user may specify a fade explicitly.
- No blanket claim that all J/L transitions sound appropriate. Technical timing and creative acceptance are separate gates.

## Acceptance and next work

1. Compile, run `test_audio01_picture_follow.py` and `test_audio01b_dialogue_edit.py` in Linux and Windows native GitHub jobs.
2. Preserve B14 real Blender picture conform acceptance.
3. For each AUDIO-01B preview, validate source media/sample timebase, independent sound edit, sample count, exact replay after restart and no original changes.
4. Follow with AUDIO-01C: independently sourced dialogue/ambience/music stems, verified clip boundaries and scalable streaming, audibility/clipping tests, then host-authorized final mix and mux. Do not call AUDIO-01B a professional finished master.

The proposed human-controlled AI film-crew editor can suggest an AUDIO-01B plan, but such proposals never constitute director approval or native tool authorization.
