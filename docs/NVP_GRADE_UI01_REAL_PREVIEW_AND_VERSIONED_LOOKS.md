# NVP-GRADE-UI-01 — Essentials grading workspace: implementation and acceptance

**Scope:** Functional global grading UI; immutable, unapproved grade recipes; real scene-linear source-derived preview; version history and recovery. **Not** director-approved creative grading, calibrated browser viewing, automatic ProRes export, cinema DCP mastering or an Advanced/Professional grading suite.

## Product workflow

The filmmaker selects a full 24fps Cycles HALF RGBA OpenEXR presentation previously indexed from a frozen Digital Take. The software reopens source and take revision hashes, then derives both previews through the *same pinned OCIO 2.5.2 / ACES 2 Rec.1886/Rec.709 view* used by COLOR-01B2. Before uses a neutral recipe; After uses the working grade. The filmmaker can drag a before/after wipe; adjust exposure, contrast, saturation and red/green/blue gains via sliders and precise numeric fields; choose Neutral, Warm, Cool, Soft daylight or Low-key drama presets; undo, redo and reset. All effects operate on the **source EXR**, not on an 8-bit proxy or post-quantized MOV.

The Save Draft action requires an explicit *creator declaration* that the EXR is linear Rec.709 source primaries (this is **not** a colorimeter measurement). It writes a `kind=edit` immutable FilmIndex record with a typed `nvp.color.grade.global.v1` recipe and direct dependencies on both the exact source presentation and frozen take. Saving the same Look ID with a fresh expected revision preserves prior versions; stale writes fail transactionally. Historical grade versions can be reopened and compared. Neither saving nor preview automatically modifies the Digital Take, EXRs, playback, approved grades, masters or a theatrical package.

**Production limits:** The current native mastering path is at most 48 contiguous 24fps EXR frames at up to 1024x576; this first panel makes *actual source image* previews only, sampled at the original source frame indices. It does **not** yet render a grade across an entire movie from the GUI, publish an approved grade or allow keyframed shot-specific edits. The browser's RGB PNG output is an uncalibrated *approximate* Rec.1886 view representation; a calibrated Rec.709 grading monitor is required for image approval. An FFmpeg preview has a process timeout, bounded PNG size and server-wide two-concurrent-preview limit; multiple rapid requests cannot spawn unbounded workers.

## Software interfaces

| File | Responsibility |
| --- | --- |
| `frontend/src/ColorGradingPanel.jsx` | Essentials UI; real before/after source pixels; controls/presets; undo/redo; versioned draft save/load; source declaration |
| `frontend/src/ColorGradingPanel.css` | Responsive monitor, split wipe and accessible controls |
| `frontend/src/App.jsx` | Tab 15 connects grading workspace to the existing NVP film; Help tab connects the learner |
| `frontend/src/ColorGradingGuide.jsx` | In-app lessons and feature-status guidance |
| `backend/nvp_grade_workspace.py` | Validated source discovery, immutable FilmIndex edit history and bounded actual OCIO previews |
| `backend/nvp_api.py` | Project-scoped source/grade/history API and read-only actual PNG preview endpoint |
| `tests/test_grade_workspace.py` | Concurrency, versioning, identity/refusal, FastAPI validation and neutral preview tests |
| `tools/nvp_grade_ui01_fixture.py` | Real 16-frame Blender/EXR/OCIO previews and independent FilmIndex restart/tamper tests |
| `.github/workflows/nvp-grade-ui01.yml` | Linux, Windows, React and native Blender acceptance |

### API

- `GET /api/projects/{project_id}/color-grading/sources` — only validated full-frame HALF EXR sources
- `GET /api/projects/{project_id}/color-grading/sources/{source_id}/preview?frame=1&mode=before|after&…` — actual color-managed PNG; `Cache-Control: no-store, private`; return 409 if busy/clipped or source is invalid. **Read-only**.
- `GET /api/projects/{project_id}/color-grading/grades?source_id=…` — current draft looks.
- `POST /api/projects/{project_id}/color-grading/grades` — immutable edit commit, creator source declaration, optimistic expected revision.
- `GET /api/projects/{project_id}/color-grading/grades/{grade_id}[?revision=N]` — validate current or historical grade.
- `GET /api/projects/{project_id}/color-grading/grades/{grade_id}/history` — exact revision chain.

The API is local-only in the current NVP server, and this gate does not grant model-initiated edit authorization, run uncontrolled exports or accept paths from the browser.

## Acceptance and launch states

**Initial CI:** [run 41753193134](https://github.com/vjmichael/nvp_offline_film/actions/runs/41753193134) reported passing Linux (20 targeted tests), Windows (10 targeted tests), and React production build; the separate actual Blender/Cycles/native FilmIndex gate was still running at first documentation. The subsequent concurrency guard, guidance, and test updates are committed on this branch and need verification on the latest SHA. Do not mistake an earlier green run for newer commit acceptance. A fully verified native result must be added before closing.

**Security and product limits:** Opaque source required. Invalid or changed EXR/MOV/grade bytes refused. Source primaries remain creator-declared, not measured. No calibrated viewer, auto-grade claim, director approval, color wheels, LUTs, scopes, masks, tracking or final DCP export in this gate.

**Next:** `NVP-GRADE-UI-02` (actual wheels/curves, per-shot timeline, waveform/vectorscope, LUT management and reference comparison) followed by `NVP-COLOR-MASTER-01` (measured color targets, calibrated Rec.709 output and precise metadata/roundtrip signal audit). Keep the World and frozen Digital Take canonical.
