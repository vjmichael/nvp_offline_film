# Color grading in NVP — A beginner's guide

**Audience:** Filmmakers who have never graded a film.  
**Current implementation:** NVP-GRADE-UI-01 adds an **Essentials grading tab** with global exposure/contrast/saturation/RGB balance, look presets, undo/redo, a real source-derived before/after preview, and immutable draft-look saving. It requires a complete, 24fps Cycles HALF OpenEXR presentation. NVP-GRADE-UI-02A adds **real per-shot lift/gamma/gain controls** and a measured RGB/luminance histogram, waveform and vectorscope. Calibrated reference monitors, advanced color curves, tracked masks, and final creative or mastering approval remain future work.

## 1. What does color grading do?

A film's colors help tell its story. **Color correction** brings shots to a consistent, natural baseline (correct brightness and unwanted color casts). **Color grading** changes the emotional look (warmth, coolness, saturation, cinematic contrast). They're related but not interchangeable. Neither process substitutes for good lights, textures or performances.

Consider two takes of the same room:

- The first has daylight streaming through the windows. A warmer treatment may reinforce comfort or nostalgia.
- The second is a suspense scene. Cool shadows and restrained saturation may reinforce uncertainty.
- Both changes should be revisable without touching the approved source performance.

NVP's immutable **Digital Take** is the source record. The Blender/Cycles **OpenEXR** frames hold scene-linear half-float image values. A **grading recipe** holds your creative color choices. The **color-managed presentation** renders that recipe into a defined viewing space. A **mastering candidate** is a high-quality video derivative, not a replacement for any of those originals.

## 2. The most useful beginner controls

| Control | What it does | When to start |
| --- | --- | --- |
| Exposure (stops) | Brightens or darkens the whole scene. +1 stop doubles linear exposure before tone mapping. | Fix a scene that feels overall too dark or bright |
| Contrast | Separates or compresses dark and bright tones around a midtone pivot. | Use sparingly after exposure |
| Saturation | Changes intensity of the colors; 0 gives neutral gray. | Correct an over-vibrant or dull look |
| Red/green/blue gain | Shifts the balance of the color channels in the scene-linear working image. | Compensate for a slight warm/cool creative cast |
| Lift/gamma/gain wheels | Separately adjust shadows, midtones and highlights. | **Planned** in the graphical grading workspace |
| Curves | Precisely reshape brightness, color or saturation ranges. | **Planned** |
| LUTs | Transform or stylize colors through an importable lookup table. | **Planned**, with metadata and profile validation |
| Scopes | Waveform, histogram, RGB parade and vectorscope show signal levels rather than trusting an uncalibrated monitor. | **Planned**, core professional workflow |
| Masks/secondaries | Change only a face, sky, shirt or selected hue, ideally with tracked motion. | **Planned** |
| Keyframes/shot match | Animate a grade over time and make adjacent camera angles consistent. | **Planned** |

**Already implemented in COLOR-01B2's versioned engine recipe**: exposure (−4 to +4 stops), contrast (0.5–2), saturation (0–2), and individual red/green/blue gain (0.7–1.3). A single **global** recipe applies to a whole short 24fps test sequence. This is not yet a user-facing grading GUI.

## 3. The right order to grade

1. **Keep the originals.** The Film World, approved Digital Take and indexed scene-linear EXR frames should never be edited in place.
2. **Identify the working color space.** This first mastering gate uses creator-declared scene-linear Rec.709 primaries. Real camera or CG primaries must ultimately come from independently verified metadata and/or calibrated chart targets. If you don't know the input space, do not guess and certify a master.
3. **Match exposure and neutrality.** Make white/gray objects plausible and ensure the scene isn't unintentionally too dark or bright.
4. **Adjust contrast.** Preserve important highlights and shadow details.
5. **Set a look.** Apply warmth, coolness and saturation gradually. Compare a few versions.
6. **Check clips and scopes.** In the current backend, the SDR clipping audit and 10-bit legal-code scan are available. Professional visual scopes are not yet implemented in the GUI.
7. **Compare shots in sequence.** A nice-looking isolated frame can still flicker or clash with the next shot.
8. **Encode a review/master candidate.** The COLOR-01B2 backend targets ACES 2's Rec.1886/Rec.709 SDR output view, then explicitly converts to limited-range BT.709-matrix YUV 4:2:2 10-bit MOV.
9. **Reopen and verify.** NVP checks the frozen source, grade recipe, exact frame count, video codec/profile, color tags, legal sample range and decoded difference from the graded reference.
10. **Approve intentionally.** A technical success does not equal creative signoff or a calibrated theatrical master.

## 4. Understand the most confusing terminology

**8-bit vs. 10-bit vs. 16-bit HALF.** Bit depth expresses image sample precision. A 16-bit HALF OpenEXR is floating point and can store values greater than 1.0. A 10-bit ProRes/DNxHR frame uses 10-bit integer YUV samples, typically with 4:2:2 chroma resolution. Putting an 8-bit image into a 10-bit file does not regenerate lost detail.

**Scene-linear vs. display-referred.** A linear value of 2.0 is twice the scene radiance of 1.0; it is *not* a valid display code to clip naively. A display transform tone maps scene values into a viewing target. NVP uses a pinned **OpenColorIO / ACES 2** display/view transform; the source remains unchanged.

**ACES 2 vs. Rec.709 vs. Rec.1886.** ACES 2 supplies color transforms and view rendering. Rec.709 specifies SDR HD color primaries and common signal metadata. Rec.1886 describes an SDR reference display electro-optical transfer. NVP explicitly distinguishes the chosen display/view from the resulting MOV's color tags, matrix and legal range.

**ProRes vs. DNxHR.** Both are editing-friendly mezzanine video codec families. NVP-COLOR-01B2 uses **ProRes 422 HQ** or **DNxHR HQX**, 10-bit 4:2:2 QuickTime MOV at the supported test raster. Both are lossy; decoder pixels will not be mathematically identical to the pre-encoding RGB values.

**A DCP isn't just a MOV.** Theater projection needs its own JPEG2000/MXF, picture/sound/CPL/PKL package, approved audio, color transform into cinema XYZ, independent verification and ideally a real cinema-server ingest test. None of those arise automatically from a Rec.709 video file.

## 5. Five beginner exercises to learn grading

1. Start with a neutral recipe. Raise exposure by +0.25 stop. Compare the mood with the original.
2. Reset exposure. Reduce saturation to 0.70, then to 0.0; observe the difference between muted color and black and white.
3. Reset. Try a subtle warm balance, e.g. red gain 1.03 and blue gain 0.97. This is an **RGB creative balance**, not a physically calibrated white-balance Kelvin setting.
4. Restore a neutral grade, then increase contrast gently (e.g. 1.08). Watch for shadow/highlight clipping.
5. Save a second derivative with a new unique ID. Check that both can be reopened and still reference the **same** original Digital Take and EXRs.

These exercises are guidelines, not universal aesthetics. Do not make a scene dark merely because it's supposed to be cinematic.

## 6. Common mistakes to avoid

- **Relying only on appearance on your laptop.** Without proper calibration, perceived color may change across monitors. Use reference scopes and a verified output transform.
- **Accidentally processing an SDR file as linear EXR.** This double-transforms color and distorts highlights.
- **Letting a LUT silently change color spaces.** All LUTs need declared input/output spaces and validation.
- **Confusing gamma, exposure and contrast.** Exposure is a scene-linear multiplicative adjustment. Contrast changes tone separation; gamma typically targets midtone response. Their tools are not synonyms.
- **Crushing blacks or clipping highlights** for a dramatic look without noticing what data was lost.
- **Converting transparency to RGB without compositing.** NVP's current mastering gate refuses non-opaque sources rather than silently discarding alpha.
- **Assuming metadata proves calibration.** Correct BT.709 tags and zero illegal samples help, but are not a colorimeter reference, creative grade approval or a cinema certification.

## 7. User experience we intend to build

NVP's dedicated grading workspace should offer beginner/advanced/professional workspaces rather than hiding controls. A preview monitor with before/after wipe, timeline/shot gallery, editable curves and color wheels, keyed local adjustments, scopes and LUT browser should all be synchronized to **versioned grading recipes**. Every action should support Undo/Redo, grade versions, copy/paste grade, reset, and a clear warning when a source or output-space assumption isn't proven.

AI assistance can propose a look or match a reference, but the **director/editor retains final creative authority**. Every AI-generated grading change should be inspectable and reversible. NVP will not silently alter the approved source or export an unapproved grade.

## 8. Mastering checklist

- [ ] Original Digital Take is frozen and recorded in FilmIndex.
- [ ] Source images are genuine scene-linear HALF EXRs (not up-converted 8-bit proxies).
- [ ] Working primaries and OCIO version/display/view are confirmed.
- [ ] Grade settings and intentional approvals are recorded and reversible.
- [ ] Source sequence is complete: no missing, duplicated or reordered frames.
- [ ] Rec.1886/Rec.709 SDR transform has an independent clipping audit.
- [ ] Video has correct codec, 24fps, raster, bit depth, and color-space tags.
- [ ] Decoded picture samples remain in legal 10-bit YUV ranges, and lossy deviation is measured.
- [ ] A fresh project reopen verifies FilmIndex and regenerated graded reference.
- [ ] Sound, calibrated monitor, creative approval, picture lock and deliverable-specific certification are handled separately.

This guide will be expanded with screenshots, interactive examples and contextual help as the grading UI is implemented.


## 8. Using the NVP Essentials grading tab

1. Open your NVP film and select **15 · Grade color**.
2. Choose an existing **full-frame, frozen Cycles OpenEXR** source. If the source list is empty, render/verify a complete EXR take first; you cannot grade an 8-bit proxy as a true scene-linear source.
3. Move the **Before / After** slider. The two images come from the *same* pinned ACES output transform; only the grading recipe changes. Your browser display is not a calibrated reference monitor.
4. Adjust exposure in small increments (e.g. +0.2), then test contrast, saturation and RGB balance. Every slider also has a numerical field; try presets and **Undo/Redo**. To return to the source look, choose **Neutral**.
5. To save your current look, enter a stable Look ID (e.g. `look_mara_day`), tick the **source primaries declaration** only if it is accurate for your source, and choose **Save draft look**. Subsequent saves to the same ID create numbered, immutable revisions. The original Digital Take and OpenEXR frames do not change.
6. Load saved looks by clicking them. Older revisions can be inspected without rewriting newer ones; save an older variant under a new Look ID if you want to branch. Draft looks are **not** director approvals and are not automatically exported as final ProRes or DCP masters.

**Troubleshooting:** A busy-message means the preview worker guard is limiting expensive EXR decodes. Invalid clipping values are refused rather than hidden. If the browser preview looks different from your editing suite, do not compensate by guessing at color: use a calibrated monitoring workflow for final approval.


## 9. Advanced shot grading: lift, gamma, gain and scopes

The **Shot grading & professional scopes** section appears under the same Grade Color tab, after the Essentials settings. Select one of the numbered shot cards. NVP finds its actual frame range from the frozen Digital Take's EXR presentation. Changing shot 2's color balance does **not** change shot 1's original image or its saved grade.

**Lift, gamma and gain** are three related sets of RGB adjustments:

- **Lift** shifts the dark/near-black tonal values. Try a tiny lift such as +0.006 in blue to cool darker details, then reset. Overuse destroys dark tonal separation.
- **Gamma** reshapes middle-gray contrast around a fixed scene-linear pivot. A neutral value of 1 changes nothing. This is artistic grading, not the display's transfer-function gamma.
- **Gain** scales color channels; a small red gain above 1 with a blue gain below 1 produces a warm balance. This is not a calibrated white-balance thermometer.

All three have separately bounded **R/G/B numeric controls**. The present implementation uses precise sliders, not full physical-looking circular trackballs. All operations are non-destructive and occur **before** the pinned ACES display transform. Your **global Essentials** grade still applies to every shot; per-shot controls are layered on top.

### Why the scopes are useful

- **Histogram:** Count of image pixels at each brightness/color level. A spike pinned to the far right may indicate clipped highlights; a pile near zero may indicate crushed shadows.
- **Waveform:** How brightness is distributed across the picture, horizontally. Bright clouds appear high on the corresponding part of the graph; dark ground appears lower.
- **Vectorscope:** How saturated and tinted the colors are. Values near the center are less saturated; displaced clusters indicate strong chroma directions.

NVP's scopes are calculated from the actual **post-ACES 16-bit RGB preview pixels** and record their checksums. They are software diagnostics, not a calibrated physical monitor or a broadcast SDI legal-range verifier. They are updated when the preview is recomputed.

### Beginner practice

1. Choose **Shot 1**. Change its red Gain to 1.06 and blue Gain to 0.96. Compare the picture and scopes.
2. Choose **Shot 2**. It still has its own neutral lift/gamma/gain unless you change that shot separately.
3. Try a tiny blue Lift increase in Shot 2 (e.g. 0.01) and inspect the waveform and color vectorscope.
4. Click **Reset selected shot** and experiment again. Use **Undo shot edit** and **Redo shot edit** to compare variants.
5. Enter an advanced look ID, confirm the source-primaries declaration only when correct, then **Save advanced draft look**. The FilmIndex creates an immutable version. **Load saved advanced look** can retrieve it. Neither operation approves a final creative grade or encodes a new movie.

**Before filming a final master:** verify source primaries, calibrate the intended monitor, review all source frames, and explicitly approve the creative grade. Do not assume a pleasant-looking uncalibrated browser preview is a cinema or broadcast color standard.


## 10. Tone curves and comparing two shots (GRADE-UI-02B1)

The new **HDR tone curves & reference-shot advice** panel lives underneath the per-shot grading controls. Think of a *tone curve* as an instruction for how dark, middle, and bright parts of the image should change.

NVP's first editable curve is deliberately simple: it offers three adjustable points—**Shadows, Middle gray, Highlights**—with fixed deep-black and bright-white endpoints. Each point changes exposure in stops, rather than editing 8-bit brightness. A +1-stop mid-gray setting doubles the original scene-linear value at that pivot, before ACES makes a viewable SDR preview. Values beyond 1.0 remain available to the film pipeline; the curve itself does not chop them off.

### Try it

1. Select **Shot 1** in the original shot strip. In the curve panel, move **Middle gray** from 0 to +0.25 stops. Watch the real preview.
2. Increase **Shadows** by +0.1 stops, then inspect how the waveform shifts. Try **Undo curve**, **Redo curve**, and **Reset shot curve**.
3. Select **Shot 2** and observe that it has its own neutral tone curve. Editing Shot 1 does not automatically edit Shot 2.
4. To compare the shots, return to Shot 1 and set **Reference frame** to one inside Shot 2. Click **Compare reference without changing any image**. NVP measures the decoded image data and suggests an exposure starting point. The proposal is deliberately separate from the **Apply suggestion** button.
5. Save an unapproved curve draft under an ID only after accurately confirming the EXR's declared source primaries. **Load curve draft** reopens the saved version; the original Digital Take and image files remain unchanged.

**Important limitations:** Reference exposure advice is based on average *display-referred* brightness, so it is only a rough creative starting point, not calibrated color matching. A browser cannot replace a calibrated reference monitor. NVP will refuse malformed, nonfinite or out-of-range curves rather than silently corrupt the film.

### Coming next: LUTs

A **LUT (look-up table)** stores a predefined mapping between colors. Professional LUT handling requires knowing exactly what color space the LUT expects and what it produces. NVP will use the established OpenColorIO processing system and record the LUT's content hash and color-space contract. Until those safety checks are accepted, do not assume a random downloaded LUT is safe to apply to scene-linear imagery.
