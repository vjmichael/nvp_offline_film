# NVP-GRADE-UI-02B1 — Source-linear tone curves and reference-shot advice

**Status: technically accepted on native Linux and cross-platform tests (2026-11-03).**\n\n**Scope:** First part of GRADE-UI-02B. Real bounded HDR scene-linear EV tone curves, one immutable curve plan per shot, source-image preview and reference-shot exposure *advice*. No calibrated monitor, colorimetric matching, arbitrary control-point curves, 3D LUT imports or final approved film master yet.

## Why this is different from fake “curves”

The controls operate on actual independently verified Blender Cycles **16-bit HALF scene-linear OpenEXR** values *before* the pinned OpenColorIO ACES output transform. This is not an 8-bit brightness filter placed over a MOV. The existing immutable Digital Take and source EXR frames remain authoritative.

Each curve stores five precisely defined knots at **-8, -4, 0, +4, +8 exposure stops relative to 18% scene-linear gray**. The first/last points remain fixed; the three middle points have numerical **EV offsets** limited to ±1.5 stops. Points are finite, ordered and required to preserve monotonic luminance response. Input luminance is derived from linear Rec.709 RGB coefficients; each color channel is multiplied by the same bounded exposure factor. Black stays black, alpha stays unchanged and valid scene-linear HDR radiance greater than 1.0 is not clipped by the curve stage.

The pipeline order is **global look → per-shot RGB lift/gamma/gain → per-shot EV tone curve → pinned ACES 2 Rec.1886/Rec.709 display view → independent RGB48 sampling/scopes + uncalibrated PNG review preview**.

## Reference-shot advice

A filmmaker chooses an actual source reference frame and a target frame. NVP decodes the authentic source frames and measures the same post-ACES RGB48 software scope luma from each. It computes a bounded ±0.75-stop **starting suggestion** using the ratio of the *mean display luma values*. Black/near-black reference frames are refused. The suggestion carries the source hash, frame IDs, original means, clamp disclosure and per-image SHA values.

**Important:** This is a heuristic, **not** accurate color matching, exposure meter calibration or camera-linear photometry. A display-luma ratio cannot by itself establish a colorimetrically correct linear-exposure change. It **does not modify the grade automatically**. The UI provides a separate explicit action for the filmmaker to apply the suggestion to the selected shot's mid-gray tone-curve knot.

## Version history and protections

New `nvp.color.grade.shot_curves.v1` FilmIndex `kind=edit` records pin their exact EXR presentation revision and originating Digital Take, with the frozen original shot timeline SHA-256 and a canonical typed curve plan. Each saved look is an unapproved draft. Optimistic concurrency refuses stale expected revisions and restores older ones for independent inspection; edits cannot change source identity. The rendering path is subject to the same at-most-two concurrent preview limit and bounded FFmpeg processing as the prior accepted grading workspace.

Actual project-scoped FastAPI routes:
- `POST /api/projects/{project_id}/color-grading/curves/preview`
- `POST /api/projects/{project_id}/color-grading/curves/reference-suggestion`
- `POST /api/projects/{project_id}/color-grading/curves/grades`
- `GET /api/projects/{project_id}/color-grading/curves/grades/{grade_id}?revision=N`

The UI includes a five-point curve plot, three editable EV offsets, numeric inputs, undo/redo/reset, source-accurate preview, explicit reference advice and separate consent-gated curve-draft save/load. Nothing here grants AI permission to alter a filmmaker's approved grade.

## Verification

The first native Linux acceptance chain ran the genuine Blender/Cycles 16-frame two-shot frozen EXR fixture. It generated different curve previews for shot 1 with a modified curve, proved that shot 2 was **byte-identical** when only shot 1 was changed, and independently checked that the RGB/luma histogram, waveform and vectorscope each accounted for the complete 256×144 frame pixels. It verified an inspectable source-reference suggestion without new FilmIndex edits, saved and reopened two curve revisions, refused a stale write, refused a corrupted document and cross-project lookup, and rechecked that the original source EXRs and frozen Digital Take were unchanged.

**Native acceptance passed:** [GitHub run 41757833085](https://github.com/vjmichael/nvp_offline_film/actions/runs/41757833085) passed **4/4 jobs**: 31 Linux regressions, 20 Windows regressions, the production React build and 9 real Vitest/DOM tests, plus native Blender/Cycles two-shot EXR→curve→ACES preview, reference advice and FilmIndex restart/denial acceptance. Initial UI-test selectors were corrected because the advanced and curve editors have distinct consent checkboxes. No backend gate was weakened.

**Independent artifact audit:** Four real 256×144 PNGs were extracted, decoded and SHA-256 matched to `grade_ui02b1_report.json`. **Shot 1 changed** (neutral `120191812c21058a96e160d09396d0349bddb62b08b83959414511bf134a0b58`; graded `61c999375701d3f6c9eaebeea93ede625097fd450ff070653a878bafa4b43698`). **Shot 2 remained byte-identical** under a Shot-1-only curve (both `941d49b4b85bb4af61e73ae000c3fc0dac478acd6d525ee0d824974d47461622`). Every scope counted 36,864 pixels. Original EXR revision `5ca58558f75a0884cc2a1fe71c02eb1305373b4319888a2819181f254acae0` and frozen Digital Take `1c98ee15828fab57535402f56f2d8660a1e47cb2498253fceb0251a374de8e37` were unchanged. Two immutable curve edits independently reopened, with deliberate corrupted edits, stale writes and other-project lookups refused.

A reference comparison of frames 1 and 9 suggested **−0.054122 stops**, derived from mean display-luma 0.449036 vs 0.432503, explicitly *advisory only* with no change saved. This is not calibrated exposure matching.

## Remaining GRADE-UI-02B work

- **02B2:** vetted OpenColorIO `.cube` / ASC CDL / common LUT workflows with explicit input/output-space contracts and content-addressed LUT assets; use OCIO's standard FileTransform rather than reinventing interpolation or trusting an arbitrary LUT filename.
- Editable arbitrary-knot tone and hue curves, direct-manipulation trackballs, reference color charts, real shot matching and a user-approved look-copy workflow.
- Actual director approval, grade-to-MOV export handoff, independent calibrated mastering monitor and cinematic DCP transforms remain separately gated.

**References:** [OpenColorIO LUT formats](https://opencolorio.readthedocs.io/en/v2.4.2/guides/using_ocio/using_ocio.html) · [Parent GRADE-UI-02A native acceptance](NVP_GRADE_UI02A_SHOT_COLOR_SCOPES_ACCEPTANCE.md).
