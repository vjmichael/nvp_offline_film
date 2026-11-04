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

**Final cross-platform gate:** [GitHub run 41753886773](https://github.com/vjmichael/nvp_offline_film/actions/runs/41753886773) passed **4/4 jobs** for the combined branch changes: Linux **21** Python tests; Windows **11** Python tests; production React build plus **3** real jsdom/Vitest interaction tests; actual native Blender/Cycles → half-float EXR → OCIO before/after preview → FilmIndex graded draft history/corruption/restart acceptance. The earlier native fixture incorrectly selected the creator project by presentation title; the corrected fixture locates the unique frozen EXR object by FilmIndex identity. The [earlier failed native run 41753193134](https://github.com/vjmichael/nvp_offline_film/actions/runs/41753193134) is retained as evidence of the detected fixture issue, not disguised as success.

### Measured native evidence

- Actual full-frame EXR source ID: `exr_source_16f`, 16 frames, 24fps, 256×144 (Cycles HALF OpenEXR).
- Indexed EXR presentation revision SHA-256: `7d89cc75fcd20ad2e124fa58ad6d279191b13df26391403fd7e7c711f1b06bb5`.
- Frozen source Digital Take revision SHA-256: `406e203efb4cb4951f8e61d99bf46d934559d28376e3b85d4651527aecbd3aee`.
- Same frame 1, pinned OCIO, neutral preview: PNG SHA-256 `02ab657599bdc1e24f05dc2660fa1ffca30e825ae15254f0f248d37fc3ec2447`.
- Same frame 1, saved warming grade (exposure +0.15, red 1.03, blue 0.97): PNG SHA-256 `2ec9e6458de319c4765946500d7c1e66cdf61ab2875f19d1a9d18d9e4f556f20`. The output images differ because the underlying OCIO-processed pixels differ.
- First FilmIndex grade edit SHA-256: `f08ad02b8584ad9ec3603fbe25ab865122ba4422fa830c83a775f120096a2b23`. Revision 2: `388bdaf8ac474aca2d03ffa4e9990f781c1c8b91f8c01bae41869e47524a1c7e`.
- A brand-new `Studio` reopened *both immutable grade versions* and their original take/source dependencies. Stale client write → refused; deliberately corrupted stored grade → refused; another project ID → refused; restoring the original bytes → successful reopen.
- Actual native acceptance artifact is stored as `nvp-grade-ui01-real-blender-preview-evidence` in [GitHub run 41753886773](https://github.com/vjmichael/nvp_offline_film/actions/runs/41753886773). Browser snapshots remain **uncalibrated reference previews**, and both grade revisions remain **draft, not director-approved**.


**Security and product limits:** Opaque source required. Invalid or changed EXR/MOV/grade bytes refused. Source primaries remain creator-declared, not measured. No calibrated viewer, auto-grade claim, director approval, color wheels, LUTs, scopes, masks, tracking or final DCP export in this gate.

**Next:** `NVP-GRADE-UI-02` (actual wheels/curves, per-shot timeline, waveform/vectorscope, LUT management and reference comparison) followed by `NVP-COLOR-MASTER-01` (measured color targets, calibrated Rec.709 output and precise metadata/roundtrip signal audit). Keep the World and frozen Digital Take canonical.
