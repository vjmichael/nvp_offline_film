# NVP-GRADE-UI-02A — Authentic Shot-level Grade and RGB48 Software Scopes

**Engineering state: TECHNICALLY ACCEPTED (2026-11-03)** against an actual 16-frame frozen Cycles/OpenEXR film. Four CI lanes succeeded. This does **not** approve a creative grade, certify a monitor, or export a new final movie master.

## Why this stage exists

COLOR-01B2 and GRADE-UI-01 proved legitimate scene-linear OpenEXR imagery, real color-managed previews and versioned **global** draft looks. GRADE-UI-02A adds the first truly shot-local grading operation: filmmaker controls can affect an authored shot independently of its neighbors, and histogram/waveform/vectorscope readings derive from the **same post-ACES RGB48 bytes as its preview**.

## User experience

- **Shot strip:** NVP reads the exact ordered `frame` and `shot_id` values from frozen, content-addressed FilmIndex EXR presentation. Adjacent frames with the same ID form a shot span. Missing/duplicated frames, discontiguous repeated shot IDs and unexpected shot IDs fail closed.
- **Per-shot color adjustments:** Three independent RGB channel groups for **lift**, **gamma**, and **gain** (9 bounded sliders and numeric inputs), separately authored for each shot. Each operation happens in full-float scene-linear data **before** the pinned ACES 2 Rec.1886/Rec.709 display view. Lift is an additive offset, gamma a pivoted power adjustment about linear .18, gain a multiplicative adjustment. These are documented creative controls, **not** ASC-CDL-certified mathematics, camera white balance, or an independent color-calibration device.
- **Live numeric scopes:** 64-bin RGB/luma histogram, 64×64 pixel-column vs luma waveform, 64×64 BT.709-referred chroma vectorscope, exact sample counts and the SHA-256 of the measured RGB48 sample buffer. All reflect *post-ACES display-referred* output values. Software scopes are **not** calibrated SDI hardware or an approved video legal-range analyzer.
- **Non-destructive history:** Advanced look documents use `nvp.color.grade.shot_wheels.v1` with a typed global recipe and a shot-ID keyed map of LGG controls. The immutable FilmIndex edit is bound to both the exact source EXR revision and the original Digital Take, plus SHA of the source shot timeline. Versioned revisions and optimistic concurrency prohibit stale overwrites; neither a save nor a preview provides director approval.
- **Bounded previews:** Independent real EXR decode, creator-declared source primaries, pinned ACES/OCIO view and RGB48 decode with 2 simultaneous preview workers maximum. One preview request calculates its PNG and all scopes from the **same** RGB48 buffer; rapid browser edits cancel earlier requests.

## Provenance chain

`Digital Film World → Frozen Digital Take → Cycles HALF scene-linear EXR source (FilmIndex) → Shot-anchored draft edit v1 → Pinned OCIO/ACES 2 Rec.1886 display-referred RGB48 → preview PNG + numeric scopes`.

Shot boundaries come from the original frame source, not browser UI guesses. The preview has no authority to rewrite the take, source EXR sequence or already indexed ProRes/DNxHR/DCP package.

## Native evidence

[GitHub Actions run 41755784496](https://github.com/vjmichael/nvp_offline_film/actions/runs/41755784496) finished **4/4 green**: Linux Python contracts **24 tests**, Windows Python contracts **13 tests**, React/Vitest **6 interactions** and production build, and a genuine Blender 5.2.3 16-frame Cycles/OpenEXR/OCIO FilmIndex replay with two authored shots.

**Observed source:**

| Item | Measured |
| --- | --- |
| Full frame sequence | 16 frames, 24fps, 256×144 half-float Cycles EXR |
| Shot 1 | Frames 1–8, `SH_f1f228babbc546a7ae88574c13d1ee43` |
| Shot 2 | Frames 9–16, `SH_3aee4d8822d14366b73ffa07e16172ce` |
| Original EXR presentation SHA-256 | `02ba1506e9f59d79a355dbf6203b83a8316dacf39649072bc3f77b805720c9dc` |
| Frozen Digital Take revision SHA-256 | `c1047672eb9a8f1e7258f938c82e171891ce7a8422d3e86d777d2125146abc3d` |
| Shot timeline SHA-256 | `de10284741c11999a8b5043c9752874a493f42c2accb4c5d00c30fdcbb9a3c14` |
| First saved advanced look revision | `10027cfb9722207e4fabe3ba724bcdab8812242a5ec41e82a4f9871bc718fbe1` |
| Second saved advanced look revision | `ddb5061e437f4b125559425a1580f2a6cc16d6e7e9479e81a1d3c06e3ee02375` |

**Pixel proof:** A real neutral and modified PNG was generated for each of the two shots. SHA-256 differed for both before/after pairs; shot 1's PNG stayed **byte-identical** when a modification was applied *only to shot 2*. The three scopes each accounted for all **36,864 decoded pixels** per tested frame. Independent post-run ZIP inspection showed each PNG has 256×144 pixels. Per-channel mean absolute 8-bit preview differences were shot 1 ~[2.735, 0.020, 3.691], shot 2 ~[4.124, 0.009, 2.421] (RGB; the artistic intent is not graded/approved).

**Tamper and restart proof:** A new Studio/FilmIndex instance reopened both exact shot-look revisions. Attempts to commit a stale grade revision, access through a different film project, or reopen a corrupted content-addressed edit record were all refused. Restoring the authentic record recovered cleanly. The original source EXR and Digital Take revision hashes remained unchanged.

**Native artifacts:** `nvp-grade-ui02a-native-two-shot-evidence` in the GitHub run includes the original frozen-source acceptance chain, four image previews, the actual FilmIndex database and a JSON report. The curated compact evidence ZIP contains those four PNGs, the report, and a SHA-256 manifest.

## Actual files

- `backend/nvp_grade_advanced.py` — source shot-span reconstruction, bounded per-shot LGG math, actual post-ACES RGB48 scopes, immutable edit history, real PNG preview
- `backend/nvp_api.py` — project-scoped shot timeline, ephemeral advanced preview/scopes, and unapproved draft edit version/reopen APIs
- `frontend/src/ColorAdvancedPanel.jsx` + CSS — interactive shotstrip, numeric LGG controls, software scope displays and advanced draft saving
- `frontend/src/ColorGradingPanel.jsx` — embeds advanced section beneath existing Essentials and shares global grade/frame
- `tests/test_grade_advanced.py` — scope mass conservation, exact RGB48 hash, math bounds, shot isolation, forged/tampered history
- `frontend/src/ColorAdvancedPanel.test.jsx` — actual browser event tests: shot navigation, LGG controls, undo/redo, source declaration and measured scopes
- `tools/nvp_grade_ui02a_fixture.py` — authentic 16-frame, two-shot native full pipeline and restart acceptance
- `.github/workflows/nvp-grade-ui02a.yml` — four acceptance jobs

## Not yet delivered

A complete professional grading console still requires usable trackball-style wheels, editable tone and hue curves, LUT/ASC-CDL interchange, reference-shot matching, calibrated scopes and monitor output, masks, tracking, per-frame parameter keyframes, multi-clip conform, grade-to-MOV publication with explicit creative approval, and measured Rec.709/DCP quality targets. This 02A step establishes **real shot control and scopes**, not those later 02B/03 and COLOR-MASTER-01 gates.
