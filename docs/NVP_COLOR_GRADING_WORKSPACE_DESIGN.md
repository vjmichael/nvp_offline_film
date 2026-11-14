# NVP Color Grading Workspace — Product and Architecture Contract

**State:** Design target and delivery gates. Not a claim that the controls already appear in the NVP GUI.

## Product goal

A novice should be able to improve a shot using exposure, contrast, color balance and easy presets. A professional should have direct access to a full non-destructive grading system comparable in workflow categories to established nonlinear editors and color systems, without NVP hiding technical metadata or discarding source data.

### Three user-facing workspaces

**Essentials:** large source/render monitor, baseline grade/neutral reset, exposure, contrast, warmth, saturation, brightness comparison, four recommended preset starting points (neutral/warm/cool/low-key), Before/After and short explanatory tooltips. AI may *suggest* a grade but must not apply it without an explicit edit action.

**Advanced:** Lift/gamma/gain and log-style wheels, hue-vs-hue/hue-vs-sat/luma-vs-sat curves, channel mixer, RGB balance and hue vs luminance controls, color-match/reference still, image split/wipe comparisons, shot-strip grade copy/paste, node/stack order and version history.

**Professional:** EXR float/ACES-centric pipeline with working/output space selectors, supported camera input profiles, LUT/CDL management with provenance, secondary qualifiers, power windows/masks, tracking/rotoscoping, per-shot and per-clip keyframe interpolation, group grades, automatic shot matching with inspectable delta, color-managed viewer proof, gamut/clipping warnings, RGB parade, luma waveform, vectorscope, histogram, false color, scopes signal-range overlays, scene-linear readouts, HDR waveform and managed multi-monitor output where supported.

## Core data model and authority

1. **Canonical Digital Take** and Film World assets never change as a side effect of grading.
2. **Frame sources** are immutable, hashed EXR derivatives. Blender/Cycles must record the actual render primaries/OCIO config, not an invented label.
3. **Grade document** is a versioned structured recipe, referenced by immutable ID/revision, with editable node graph/ordered adjustments; its actual DIL/UI representation is not authoritative. The first 01B2 implementation records **global** exposure, contrast, saturation and RGB channel gains. Advanced controls remain open.
4. **Grading timeline** maps shot/clip/time coordinates to recipe versions, interpolated parameter curves and semantic masks; eventual conforms use exact frozen camera/frame/sample coordinates, never floating time guesses.
5. **Transform chain** must state (a) source pixel/primaries, (b) scene-linear creative operation, (c) ACES/OCIO view and display/output intent, (d) quantization/matrix/legal range, (e) codec/container. Each stage has a pinned version and hash.
6. **Master export** stores direct provenance edges to original take, rendered EXR source and grade recipe. Every version remains reopenable and independently measurable.
7. **Permissions and approval:** exposure to tools is not authority to commit a grade. Proposed AI grades have provenance and require user acceptance. Final creative grade, broadcaster QC, theater ingest and color-calibrated approval are separate checkboxes.

## UI interactions and quality

- **Non-destructive editing:** Undo/Redo, copy/paste grade, reset by group, disable/re-enable individual nodes, compare original/current/reference, alternate look versions, per-shot and group-level apply.
- **Presets:** distinguish user-saved looks (recipe) from LUT files (transform). Preview context includes the source/output space and gamut. Refuse invalid LUT sizes, unsupported gamut, missing metadata or unsafe paths.
- **Color controls:** numerical input plus slider, wheel or curve control; keyboard shortcuts and fine-step editing. Show linear vs display-referred numbers and explain what one stop means. Controls expose hard limits and warn when clipped.
- **Scopes:** calculate from decoded image data in the selected output space, not raw untransformed previews. Show legal-range thresholds when output is TV-limited. Document clipping and sampling.
- **Consistency:** grade decisions cannot vary based on the host's uncalibrated browser Canvas/CSS color. UI preview is helpful but does not replace media-file or monitor verification.
- **Accessibility:** high-contrast UI, keyboard navigation, readable labels and numeric alternatives to wheels/colored-only cues.
- **Education:** contextual `?` help links to [beginner's guide](NVP_COLOR_GRADING_BEGINNERS_GUIDE.md), an interactive test-shot tour, a plain-English glossary, expert readout toggle and per-export QC explanation.

## Delivery gates

| Gate | Functionality | State |
| --- | --- | --- |
| COLOR-01A | Half-float native EXR from frozen Digital Take | Native Linux accepted |
| COLOR-01B | Pinned ACES 2 source-to-16-bit SDR review PNG | Linux+Windows contract accepted |
| COLOR-01B2 | Full contiguous EXR → Rec.1886/Rec.709 view → tagged, legal 10-bit ProRes/DNxHR; source-bound recipe and independent film decode | Engineering in progress |
| COLOR-GRADE-UI-01 | Beginner exposure/contrast/saturation/RGB controls, presets, real OCIO before/after, undo/redo, versioned draft grade saves | **Accepted**: 4/4 CI jobs, real native EXR-to-preview and FilmIndex tamper/restart proof ([run 41753886773](https://github.com/vjmichael/nvp_offline_film/actions/runs/41753886773)); still uncalibrated/draft only |
| COLOR-GRADE-UI-02A | Actual per-shot lift/gamma/gain channel controls, frozen shotstrip, post-ACES histogram/waveform/vectorscope, immutable look history | **Accepted technically:** four CI jobs and native two-shot EXR verification in [run 41755784496](https://github.com/vjmichael/nvp_offline_film/actions/runs/41755784496); unapproved, uncalibrated |
| COLOR-GRADE-UI-02B1 | Actual source-linear 5-knot HDR EV tone curves, source-derived reference-shot exposure suggestion, immutable per-shot draft plans | **Accepted technically**: 4/4 CI jobs and real two-shot EXR/OCIO/FilmIndex replay ([run 41757833085](https://github.com/vjmichael/nvp_offline_film/actions/runs/41757833085)); no automatic grade application |
| COLOR-GRADE-UI-02B2 | Validated OCIO LUT/ASC-CDL import, arbitrary hue/luma curves, graphical trackballs, color-reference matching and controlled look interchange | Not implemented |
| COLOR-GRADE-UI-03 | Masks, tracking, per-frame keyframes, node stacks and HDR controls | Not implemented |
| COLOR-MASTER-01 | Measured color targets, monitor profile, true video/master QC, audio+editorial lock | Not implemented |
| CINEMA-XYZ-01 | Gamut/transfer to DCI XYZ with independent 12-bit/JPEG2000 and theater-ingest tests | Not implemented |

Each checkbox marked complete must have a testable acceptance artifact, not just functioning sliders or a successfully opened MOV.
