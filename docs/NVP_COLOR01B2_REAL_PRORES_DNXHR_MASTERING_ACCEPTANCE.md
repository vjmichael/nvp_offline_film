# NVP-COLOR-01B2 — Actual Scene-linear OpenEXR to graded ProRes/DNxHR acceptance

**November 3, 2026 · engineering acceptance.**

**Evidence state:** **FULL NATIVE TECHNICAL ACCEPTANCE PASSED** in [GitHub Actions 41751400245](https://github.com/vjmichael/nvp_offline_film/actions/runs/41751400245): all **5/5 jobs green** (Linux codecs/grade tests, Windows contracts, React grading-guide build, official Blender/Cycles-to-two-master native acceptance, and pinned OCIO wheel diagnostics). An independent Linux local replay of the original 16 Cycles EXRs also passed both 10-bit codecs and FilmIndex source regrade. This is a **technical mastering candidate**, not a director-approved, color-calibrated, broadcast-certified or theatrical master.

## Full source-to-output graph

`Film World → frozen Digital Take → Blender/Cycles full sequence (16 genuine HALF RGBA EXRs) → global grading recipe → pinned OpenColorIO ACES 2 display/view transform → 16-bit RGB intermediate → BT.709-matrix legal-range YUV 4:2:2 → ProRes 422 HQ or DNxHR HQX QuickTime MOV → independent FFprobe/FFmpeg audit → FilmIndex immutable presentation → restart and repeat grade/decoder audit.`

**IMPORTANT:** NVP does *not* promote the old 8-bit PNG-to-10bit MOV path as calibrated professional source. All graded movies in this gate require **contiguous, full-frame**, independently decoded HALF OpenEXR from a frozen Digital Take. Sparse keyframes/legacy PNGs fail preflight.

## Color recipe

- OCIO runtime: `PyOpenColorIO==2.5.2`.
- Pinned builtin ACES config: `cg-config-v4.0.0_aces-v2.0_ocio-v2.5`, serialized hash from the original accepted COLOR-01B: `24ec81841048fc5db160a7bad882263246183385c5d49d0e86e11464917ead15`.
- Source: explicitly **creator-declared** `Linear Rec.709 (sRGB)` scene-linear primaries, not measured independently against a color chart. Fail closed without this declaration.
- Display/view: `Rec.1886 Rec.709 - Display`, `ACES 2.0 - SDR 100 nits (Rec.709)`.
- Global grading recipe: `exposure_stops` (−4..4), `contrast` (0.5..2), `saturation` (0..2), `red_gain`, `green_gain`, `blue_gain` (0.7..1.3), with finite/typed bounds and an immutable FilmIndex receipt. **No UI wheels, tracked masks, curves, per-shot keyframes, certified Kelvin balancing or creative sign-off yet.**
- Transform operates in source-linear float space, *before* ACES display/view, and is non-destructive. Actual output is 10-bit **integer YUV 4:2:2**; the pre-encoding source/reference buffer is 16-bit RGB, not a 16-bit QuickTime master.
- Explicit BT.709 RGB→YCbCr matrix, Rec.709 metadata, limited TV code range, 24fps and codec IDs.
- ProRes may not expose `color_range=tv` in FFprobe even when correct tagged primaries/transfer/matrix are present; therefore the **complete decoded 10-bit video** is scanned against the appropriate Y/Cb/Cr legal ranges. DNxHR explicitly reports `color_range=tv`.

## Real integration obstacle and correction

The first genuine native CI run reached actual 16-frame Cycles EXR source, but rejected OpenColorIO's Rec.1886 `CPUProcessor.applyRGBA` result because it had drifted original alpha 1.0 to approximately 1.0000116. The source image's EXR alpha was **exactly 1.0** and all scene RGB channels finite, with maximum source radiance around 17.375. A full-resolution independent `gbrapf32le` decode confirmed this.

COLOR-01B2 now applies **`applyRGB` to an independent contiguous *copy* of RGB**, preserving original opaque alpha and source arrays, and checks finite values and opacity before processing. It refuses *actual* transparency or nonfinite data; the fix does **not** relax permissible alpha error or fabricate successful decode. Unit tests assert that the source remains unchanged, even with mocked failing processors.

## Actual full native-source local replay — PASSED

Input: unchanged NVP FilmIndex `film.sqlite3` and original 16 full-frame 256×144 genuine HALF OpenEXRs recovered from the failing first native CI acceptance artifact (run [41750511932](https://github.com/vjmichael/nvp_offline_film/actions/runs/41750511932)). This artifact is real source data from Blender, not a synthetic gradient video. The frozen take and EXR source were reopened and SHA-verified before conversion.

| Property | ProRes 422 HQ | DNxHR HQX |
| --- | --- | --- |
| Frame count, FPS | 16, 24fps | 16, 24fps |
| Raster | 256×144 | 256×144 |
| Pixel codec profile | `prores/HQ, apch` | `dnxhd/DNXHR HQX, AVdh` |
| Grading | Neutral global | +0.15 exposure, 1.05 saturation, 1.03 red gain, 0.97 blue gain |
| Decoded code range failures | **0** | **0** |
| Mean absolute difference from independently generated reference (10-bit codes) | **0.694** | **0.380** |
| 99th percentile error | **10** | **4** |
| Maximum observed difference | **35** | **15** |
| MOV SHA-256 | `a73d5d63d383c26ea42a5c82aa908791b5df1121f1e346477d5a0859fee304b7` | `fd75dc643d36de98684ee084cd54673c4f876ad83e60e96af12bcea2107428fe` |
| Result | Real encode, full YUV10 decode and FilmIndex reopen passed | Real encode, full YUV10 decode and FilmIndex reopen passed |

The FilmIndex database was copied to a separate local working directory before the replay; the original failed-CI artifact was not overwritten. Each movie was registered as an immutable, versioned derivative with direct dependencies on its source EXR presentation and original Digital Take. The full decoder and grading reference were independently regenerated on reopen.

**Limitations:** This is a 16-frame, 256×144 technical result. Encoding itself is **lossy**. No independent display colorimeter, calibrated color chips, broadcaster signal validation, director approval, continuous longer film conform, sound mastering, DCI XYZ pipeline or physical theater ingest has been established.

## Independent first-party GitHub acceptance (fully rechecked) — PASSED

GitHub Actions [run 41751400245](https://github.com/vjmichael/nvp_offline_film/actions/runs/41751400245) executed the **real native fixture from scratch**: 16-frame original approved Digital Take, real Cycles HALF OpenEXR rendering, two separate ACES 2 Rec.1886 color grades, real ProRes and DNxHR QuickTime encoding, independent complete FFmpeg YUV10 sample decode, reference comparison and brand-new FilmIndex source/grade replay. This was **not** a merely mocked or synthetic-gradient end-to-end workflow.

- Native artifact: `nvp-color01b2-real-prores-dnxhr-evidence` (ID `13285153967`), a ZIP whose **91 members** passed ZIP integrity testing. The two actual MOV bytes were independently SHA-256 rehashed and matched the in-database acceptance report.
- Original approved 16-frame take SHA-256: `d52f6c351c7cebc4579daa57359093dc1f469cf20b645b2a65e8dc212b5b0831`.
- Original 16 HALF EXR FilmIndex revision SHA-256: `bac195ae68b435f35cc6839ee214a5a64e36282dbea92acaba157d6e21fd4b2f`.
- **ProRes 422 HQ**: 16 frames, 256×144, 24fps, 10bit 4:2:2, `apch`; SHA-256 `5883c02774dbbd7ebade035e455ce1113a0f411a503c03ea2819181f254acae0`; metadata `color_primaries=bt709, color_transfer=bt709, color_space=bt709`; legal sample failures **0**; mean reference error **0.693616 10-bit codes**, p99 **10**, maximum **35**.
- **DNxHR HQX**: same length, rate and raster, `AVdh` and `color_range=tv`; SHA-256 `b94e6ae0641ec4d776037193b89c4d16432ad230f9a050dd5a46b27800b8c490`; metadata BT.709 primaries/transfer/matrix verified; legal sample failures **0**; mean reference error **0.380380 10-bit codes**, p99 **4**, max **15**.
- Both videos independently decoded **1,179,648 10-bit samples**, covering all 16 complete YUV422 frames, then matched a separately regenerated pre-encoding graded RGB→YCbCr reference within the measured lossy-codec tolerances.
- The native fixture reopened both master candidates in a fresh `Studio`/FilmIndex, regenerated the grade from the original EXRs, rejected corrupted indexed MOV bytes, restored the original bytes and reopened again. An unrelated project's attempted read was rejected. The original take revision stayed unchanged.
- Linux, Windows, native Blender, React grading-guide and wheel diagnostics CI jobs all **passed**. This does **not** certify theatrical XYZ or calibrated creative approval.

**Important nuance:** ProRes's FFprobe output omitted `color_range` despite its correct BT.709 tags. The decoder's **complete YUV code range** was independently scanned and passed; the metadata omission is explicitly recorded, not invented as a positive tag.

## Tests and user education

- `backend/nvp_color_mastering.py` enforces exact OCIO policy, bounded grading recipe, complete source EXR sequence, 10-bit codec metadata and YUV code-level audit, and versioned FilmIndex/independent re-decode.
- `tests/test_color_mastering.py` uses actual local FFmpeg for both ProRes and DNxHR, plus adversarial invalid-grade/codec/alpha/NaN and missing-approval cases.
- `tools/nvp_color01b2_fixture.py` creates a **fresh native frozen 16-frame take**, renders the entire sequence with Blender/Cycles HALF OpenEXR, then grades/encodes it twice and checks FilmIndex reboot and corruption refusal.
- `.github/workflows/nvp-color01b2-mastering.yml` runs Linux, Windows and native Blender validation plus React UI production build.
- [Beginner-friendly Color Grading Guide](NVP_COLOR_GRADING_BEGINNERS_GUIDE.md) available as documentation and via the **Help · Color grading** tab in NVP.
- [Full Grading Workspace Design](NVP_COLOR_GRADING_WORKSPACE_DESIGN.md): staged novice-to-professional UI, scopes, wheels, curves, masks, keyframes, LUTs, shot matching, AI-suggested reversible grades, and authority controls.

## Next engineering gates

1. Real Blender render config audit for *measured* working primaries, not just creator declaration.
2. Native full-frame >48 shot/chunked source/mastering, larger tested raster, cancellation and bounded-memory worker orchestration.
3. Distinguish deliberate picture-locked creative grade approval, measured signal/caption/audio QC, and editorial compatibility.
4. Implement grading interface + waveform/vectorscope and masks/curves/keys, using the versioned grading data model.
5. Separately test DCI XYZ output with independent cinema 12-bit picture, sound and theater ingest.

**The original Film World and frozen Digital Take always remain authoritative.**
