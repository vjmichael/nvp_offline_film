# NVP-COLOR-01B — Pinned ACES 2 Color-managed SDR Mastering Intermediate

**Status as of 2026-11-03:** Native technical **16-bit SDR review sequence** conversion **PASSED both GitHub Linux CI jobs** after transparent-input/forged-view hardening; independently verified against a real frozen Digital Take. **NOT** a calibrated, director-approved, video-format or theatrical master. Cross-platform acceptance also passed: [GitHub run 41748075195](https://github.com/vjmichael/nvp_offline_film/actions/runs/41748075195) reported **3/3 jobs passed** — Linux Python, Windows Python and authentic native Linux Blender/Cycles/EXR/OCIO.

## Intent, authority and identity

NVP stores a frozen, source-authoritative Digital Take and a verified Cycles OpenEXR presentation. The next derivative is **display-referred image data** produced by a specific, versioned OpenColorIO view transform. Nothing edits the original take, camera, lighting, or EXR source hashes.

A 16-bit container does **not** make an image high-fidelity by itself: the source must have been rendered into scene-linear half-float EXR, actually decoded to full-float RGBA, and *then* color managed. The resulting SDR PNG sequence is a first mastering **intermediate / review output**, not final film mastering.

## Pinned transform recipe

| Parameter | Declared and checked |
| --- | --- |
| OpenColorIO library | `PyOpenColorIO 2.5.2` exact |
| Configuration | `ocio://cg-config-v4.0.0_aces-v2.0_ocio-v2.5` (loaded as the equivalent built-in config name) |
| Config serialized SHA-256 | `24ec81841048fc5db160a7bad882263246183385c5d49d0e86e11464917ead15` in the native CI acceptance |
| Input source encoding | Blender scene-linear EXR, 16-bit HALF RGBA, ZIP |
| Source gamut / working primaries | `Linear Rec.709 (sRGB)`, **creator-declared assumption**, not independently colorimetrically measured |
| Explicit transform | OCIO `DisplayViewTransform` with looks not bypassed, data processing enabled |
| Display target | `sRGB - Display` |
| ACES view | `ACES 2.0 - SDR 100 nits (Rec.709)` |
| Output | 16-bit integer RGB PNG image sequence; full exact RGB48le decoded readback |
| Output status | `unreviewed_color_managed_sdr_candidate` |
| FilmIndex format | `nvp.presentation.color.ocio_sdr.v1` |

**Important:** OpenColorIO's ACES v2 configurations distinguish a *color space* from a *display/view transform*. Only the latter bakes the ACES Output Transform for review. Do not simply convert the input via `ColorSpaceTransform` and label it a Rec.709 master. This target intentionally uses an **sRGB display encoding**, not broadcast Rec.709 transfer with a different monitoring EOTF. It must **not** be tagged as broadcast-legal BT.709 ProRes without a separate dedicated output policy and signal-range audit.

NVP explicitly verifies the installed OCIO library version, the precise builtin config and source/display/view names, a SHA-256 of its serialized config, and the OCIO processor cache ID. Environment-supplied `OCIO` or `ocio://default` cannot silently replace the named config.

## Frame conversion and independent evidence

1. Reopen the original frozen take and Cycles EXR presentation using FilmIndex and enforce source SHA and source frame order.
2. Independently decode each actual EXR using FFmpeg `gbrapf32le` to **full 32-bit float**. Retain alpha and HDR radiance values greater than 1.0. Reject nonfinite values, dimensions/count mismatches, missing source, wrong EXR pixel type, or unapproved gamut identity.
3. Apply the *pinned OCIO ACES 2 display/view* to float32 RGBA. Reject any unexpected alpha change, and reject transparent source in this opaque RGB workflow unless a future explicit compositing policy is implemented.
4. Audit every out-of-range channel **before** output quantization. Reject jobs clipping more than 2% of all color channels; the max permitted threshold is hard bounded. Record count/fraction even for zero clipping.
5. Round after view processing to 16-bit RGB, encode a PNG, and **independently** decode its RGB48le bytes with FFmpeg to prove exact correspondence. Preserve the exact decoded RGB48le SHA-256.
6. Index each PNG by content SHA; commit a new immutable FilmIndex `presentation` with **direct edges to both** its source EXR presentation and original Digital Take. Reopen in another `Studio` and optionally independently re-decode all output PNGs.
7. Refuse any change of OCIO version/config/view/processor identity, stored file bytes, source frame order or hashes, take lineage, media precision, or cross-project identity.

This stage is limited to a maximum of **120** review frames, within a bounded 1920-pixel maximum dimension and independent decoder budgets. It cannot claim a feature-length conform.

## Native creator-file evidence

GitHub Actions [run 41747736864](https://github.com/vjmichael/nvp_offline_film/actions/runs/41747736864) passed **both Linux CI lanes** after hardening, including the **real Blender native lane**: it rendered actual Cycles/EXR source from a frozen Digital Take, created **four 128×72 color-managed 16-bit PNGs**, and proved exact 16-bit independent FFmpeg readback, restart recovery, restored corruption refusal, FilmIndex source integrity and cross-project isolation. The Python lane of that early run failed **one test wording assertion** (it expected the phrase 'nonfinite' rather than the actual explicit 'NaN/Infinity' refusal), not an uncorrected color transform. A follow-on Linux run has since **passed** the corrected wording check and all targeted legacy regressions.

### Observed image and HDR reference metrics

- Source EXR presentation revision SHA-256: `16b67b3e9ce34291b4384696e914560a318989bcfbd9b6ff045614b2ae7a3363`.
- Graded SDR review FilmIndex SHA-256 (final native hardening run): `78c68396d3f1fa0682f3177f4d6060b2ab8718e32364e8d840f412085195dc22`.
- Native input HDR diagnostic sample RGB: `(2.25, 0.370361328125, 0.05859375)`.
- OCIO-transformed display float RGB: approximately `(0.983328879, 0.52537, 0.319996983)`; quantized RGB16: `(64442, 34430, 20971)`.
- Measured clipping for **all four actual rendered 128×72 frames**: **0 channels**; source and RGB16 output SHA-256s retained individually in `color01b_report.json`.
- Original Digital Take SHA-256 unchanged; fresh `Studio` reopens and re-decodes each graded PNG successfully. Corrupted PNG detected; restored original accepted. A separately published forged FilmIndex review claiming the `Raw` view instead of the declared ACES 2 view was also **refused** despite valid underlying image hashes.

The test fixture sets the source-primaries confirmation flag for a **technical test**, not a real director's creative or calibration signoff. Both Linux and Windows pinned OCIO/test lanes passed **27/27 targeted Python regressions** each (5 OCIO, 4 EXR, 8 presentation, 10 full-motion); a separate native Linux job passed true Cycles rendering and 16-bit FilmIndex readback. [Cross-platform CI](https://github.com/vjmichael/nvp_offline_film/actions/runs/41748075195). Actual movie mastering remains gated.

## Explicit open work

- Calibrate source and output primaries against independently known color targets; record **source image color space from the actual Blender project/OCIO configuration**, not just an external declared assumption.
- Move from four selected review frames to an independently verified contiguous full-frame EXR sequence; add shot-accurate conform and graded cut/EDL decisions.
- Implement a separately pinned **Rec.1886/Rec.709 broadcast output** with explicit YUV matrix, legal/full range, chroma subsampling, transfer and MOV `nclx` metadata. Verify tagged pixels and tolerances before ProRes/DNxHR production output.
- Implement actual **DCI XYZ** transform with cinema transfer and projection-side verification, rather than forwarding an SDR display PNG or trusting the DCP encoder implicitly.
- Add approved sound and visual QA; technical tests do not constitute any creative, theatrical or screening authorization.

No changes to Lu. NVP Film World and frozen source remain canonical; presentation mastering outputs are derivative and versioned.
