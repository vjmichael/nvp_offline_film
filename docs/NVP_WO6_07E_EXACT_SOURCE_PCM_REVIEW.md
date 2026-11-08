# WO6-07E — Exact editorial Film Time + original recorded PCM director audition

Date: 2026-11-08. Branch: `nvp/wo6-07e-synchronized-director-preview-20261108`.
Stack: WO6-07D PR #102, earlier original-source and model review PRs #100–#101.
Implementation submitted. Native Windows/Linux, React and physical installed-app ACCEPTANCE OPEN until tests execute.

## Purpose and what is really delivered

This is the first *genuinely source-bound* director review of a newly committed
original digital-slate edit and the selected original/WO6-07D recorded sound
timeline at a chosen **24 fps output frame**. Existing FilmIndex/OpenUSD
scene, authored performance/shot sources, exact temporal events, PCM source
chunks and immutable editorial revisions remain authoritative. There is
no new renderer, native worker, model manager, database or approval pathway.

For the requested output frame (integer 0..259199) the host:
1. Reopens the exact `SlateSequenceAssembly` committed edit ID/revision/SHA;
   rejects changed SHA, non-slate edit, out-of-bounds duration and stale edit.
2. Uses `source_at` to map output Film Time to original source segment,
   source Take ID/SHA and source Film Time. Original performance and
   camera/actor/lighting USD transforms are reopened using
   `assemble_film_crew_context` with bounded real OpenUSD/USD schemas.
3. Selects the original frozen Take's event timeline by default. A separately
   chosen WO6-07D sound-cue timeline is permitted only when it proves the
   **complete original temporal event manifest** unchanged, exact duration
   and one additional original recorded-PCM sound cue with SHA/identity.
   The entire original history is audited up to a bounded 128 events.
   Source history beyond the admitted limit fails closed.
4. Maps the same original source Film Time to exact 48 kHz sample cursor
   (NVP tick base / 48 kHz). Reads at most **12 original 24fps frames
   (0.5 seconds, up to 24000 samples)**, stopping at the selected edit
   segment boundary, without crossing into the next Take. Original audio
   chunk reads stay <=8192 samples and verify each original PCM SHA.
   At most four overlapping original sound/music/dialogue source events
   are admitted, with explicit finite gain. Mixing is a bounded
   `int16` summation/clamp ONLY for source audition, **not a final mix**.
   An absent or exhausted source is reported, never invented.
5. Serializes a real mono 48 kHz WAV from verified original PCM into a
   bounded `data:audio/wav;base64` payload and separately records
   source ID/SHA, sample interval, active semantic events, verified
   USD actor/camera/light transforms, exact frame/time projection,
   resulting WAV SHA and source-review SHA. No file is written to the
   creator's original source, no native worker or model executes.

## React / WebView2 director review

The existing `WO6CreatorActionsPanel` now includes
`WO6DirectorSourceReview` with a bounded original-commit catalog,
exact source edit selection, optional original/one-cue audio timeline,
zero-based 24fps frame choice, frame stepping, audited original actor/
camera/light world coordinates and **user-clicked** WAV audio controls.
Changing the edit, timeline or frame discards stale audio immediately.
WAV playback never autostarts. Missing native WebView2 IPC does not
fall back to generic browser/LLM execution.

This interface presents verified original SOURCE data **beside
sample-accurate original sound**. It is **not** synchronized rendered
picture-and-sound MOV/MXF playback: no raster frame exists in this
source-level packet; no sustained A/V clock, output picture pixels,
motion interpolation/cross-cut resampling or reference-managed color
accuracy is yet established. Native source poses are not pictures.
The window contains at most 0.5s of PCM; click to listen to one excerpt.
The display does not claim the creator watched a whole reel or approved
a film. The one-frame edit/source mapping is exact, but the playback
does not pretend to be continuous 24fps.

## Gates/tests

- `tests/test_nvp_wo6_07e_source_review.py` genuinely creates a frozen
  OpenUSD Take + indexed PCM original and commits a two-segment original
  slate cut + derived one-cue sound timeline via existing contained
  native workers. The new reviewer then proves output 24fps frame #24
  maps to second segment, exact 1s original source tick, correct original
  Take SHA, actual WAV sample bytes and file SHA, half-second native
  audio sampling and unchanged original PCM/Take. It proves original
  source without added sound remains silent and wrong hashes/out of
  range/protocol partial keys are rejected.
- `frontend/src/WO6DirectorSourceReview.test.jsx` checks actual React
  native request binding, user-initiated audio without autoplay,
  no browser-native writer actions, source edit invalidation, bounds
  refusal and missing installed native bridge.
- `.github/workflows/nvp-wo6-07e-exact-source-pcm-review.yml`:
  Windows 2025 / Ubuntu 24.04 × Python3.11/3.13 with real OpenUSD 26.11,
  original WO6-07D authoring regression and true native edit PCM review,
  plus React build and Vitest.

## Next real requirements, not false conclusions

- **WO6-07E continued/07F**: actual live multi-frame visual OpenUSD
  rendered picture + continuous 24fps A/V clock, derivative
  editorial cuts and per-reel multi-stem sound; independent
  real device and visible installed NVP.exe acceptance, including
  cancellation/seek across edits, audio glitches/dropout evidence.
- Real picture from USD/Hydra/MaterialX or a different approved
  renderer. Lighting mechanics (V-LIGHT) now separately tracked; see
  `docs/NVP_VLIGHT_VIRTUAL_PRODUCTION_LIGHTING.md`. UsdLux describes
  lights but is not itself global illumination.
- Audio master mix decision and QC, color transform and independent
  render parity; sustained original 30 minute film viewing/hearing;
  60–90m and 3h performance; SMPTE Bv2.1 theater ingest,
  license/NOTICE/signature review remain OPEN.

The read-only source reviewer never grants native or creative consent;
earlier two-confirmation WO6 authoring remains independent, and a
cached WAV URI is not an approval or future playback attestation.
