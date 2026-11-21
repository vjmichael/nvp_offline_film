# NVP-STACK-02C3B11 — Frozen Float32 EXR → ACES 2 SDR16 editorial image sequence

**NVP-only work. Lu/DLC Workspace interfacing remains deferred until after Lu v1.0.**

## The important decision: reuse, not duplicate

NVP already implements an official pinned ACES 2 SDR color review in `backend/nvp_color_ocio.py` (COLOR-01B), plus an independently tested 10-bit ProRes/DNxHR mastering candidate in `backend/nvp_color_mastering.py` (COLOR-01B2). Those older pipelines take an earlier, HALF precision B8-era EXR presentation. B9/B10 use a different **Float32, content-addressed, independently read-back complete sequence** from original frozen `DigitalCapture`/`FilmIndex` takes. B11 **does not create another OCIO math engine**: it bridges the modern Float32 source to the existing verified `color_policy()`, `decode_scene_linear_exr`, `apply_view`, and `_encode_png16` functions.

## Exactly what B11 records

1. `frozen_review_source(capture, project_id, exr_presentation_id)` calls B9's `verify_indexed_exr_sequence` to rehash **every** original 32-bit Float EXR, the original immutable Digital Take and all independent native float readback receipts. It reopens the captured 24fps shot sequence and requires a contiguous 1..N timeline with exactly one camera cut/shot for every frame. Current editable WorldState is not consulted.
2. A *separate* trusted native creator event (provided only by an installed NVP host) must consent to the exact source take and presentation SHA, original linear Rec.709 input declaration, full frame count, camera cut provenance, ACES 2 display/view configuration, RAM/disk budget and expected 16-bit RGB PNG output contract. An HTTP request, model output or browser-side boolean is not native consent. CI uses a fixture identity, not installed user-presence verification.
3. `NativeB11ReviewHost` binds this exact consent and operation to SQLite/`ApprovedTaskBindings` with NVP's measured physical memory headroom and a pinned native Python/worker source SHA. The job is queued without launching; the policy is checked again before/after memory admission and directly before `launch_contained`. The actual work runs as an OS-contained subprocess. On an unknown OS launcher cleanup, ACTIVE memory reservation is held for reconciliation, never silently freed. Revocation only cancels never-started work.
**B11A observed native alpha compatibility (measured, not guessed):** The first actual B9→SDR worker refused the source because B9's real native Blender Float32 frames carried alpha **0.99853515625** on all tested pixels, while COLOR-01B's final RGB view insists on exactly opaque alpha. B11 explicitly declares and pins `nvp.display_review.near_opaque_aa_alpha_v1` to creator consent and durable worker plans. It permits only an antialiasing-level alpha shortfall **≤0.003** (min alpha ≥0.997, max ≤1.000001), records per-frame observed alpha min/max and number of display-only normalized pixels, then sets only the **derived review buffer** alpha to 1.0 so the established OCIO SDR code can safely operate. Original Float32 RGB and alpha bytes are untouched. **Actual transparency** (e.g. alpha=0.96, 0.5 or 0) still fails closed; NVP does not guess whether the source is premultiplied or unassociated, and does not invent a matte without explicit director compositing. CI unit tests use the exact observed 0.998535 value and deny truly transparent frames. This is not a source-blend or production compositing solution.

4. Worker `tools/nvp_b11_review_worker.py` independently reopens the same FilmIndex source and verifies the pinned color policy. For each EXR frame, FFmpeg decodes actual 32-bit HDR RGBA data, COLOR-01B applies the **official OCIO ACES 2 SDR 100-nit sRGB DisplayViewTransform** in floating point, then writes a genuine **16-bit RGB PNG** with explicit clipping metrics, nearest-even quantization and FFmpeg round-trip byte-for-byte RGB48 verification. The original EXR is not converted in place.
5. Every verified PNG is content-addressed in the existing project-scoped FilmIndex. Only after **all N frames** finish and the frozen source revisions match again does the worker register a separate immutable `presentation` with original take revision-1 and Float32 EXR presentation revision-1 typed dependencies. The manifest includes exact source frame SHA, output PNG SHA, uncompressed RGB48 readback SHA, frozen shot/cut ID, FPS, original OCIO config SHA and processor cache ID.
6. The host verifies completion only after native OS shutdown and a second full FilmIndex reopen. `verify_sdr_review` independently rehashes and decodes every persisted PNG in a fresh review context, verifies actual PNG 16-bit RGB structure, all 24fps frame numbers and source/cut continuity, and requires the pinned OCIO policy unchanged. The original frozen Digital Take and scene-linear EXR remain disk-persistent and untouched.

## Practical editorial handoff

The result is a **complete numbered 16-bit sRGB SDR review-image sequence** plus its exact shot/cut timeline and saved color-management provenance, suitable as the foundation of an offline editor handoff. A later standard OpenTimelineIO/FCPXML/EDL exporter and the existing ProRes/DNxHR pipeline can consume a verified derived sequence. Neither must be claimed complete until actual export/round-trip acceptance exists. An ACEScg working-space EXR is not itself SDR; B11 *uses the display view*, not a mere ACEScg colorspace transform.

## Important limits

- **The 16-bit PNG review is display-referred** and not a high-bit-depth scene-linear master. That scene-referred master remains the **original B9 Float32 OpenEXR sequence**. Do not destroy or overwrite it.
- The current input primaries are explicitly **creator-declared** as standard scene-linear Rec.709; no physical camera/input OCIO characterization, calibrated monitor, ICC profile or custom Blender OCIO source attestation is claimed.
- A 120-frame complete review at 160×90 proves format, timing and persistence; it does **not** prove production-resolution image quality, motion realism, lens fidelity, a polished final film, or color grading by a human.
- No audio, lip-sync, sound mix, OTT/DCP export, picture lock, final ProRes master or approved display calibration is delivered by B11.
- This work is host-only. Installed NVP native user-presence UI, Linux whole-tree cgroups and Windows GPU VRAM measurements remain separate production acceptance gates.

## Automated evidence

Workflow `.github/workflows/nvp-stack02c3b11-sdr-editorial.yml` runs Windows and Linux native creator/source/tamper/expiry/revocation/low-RAM/unknown-process-cleanup regressions, B9 OpenEXR and B10 OCIO regressions, frontend build/tests. Linux also installs **real Blender, FFmpeg, OpenColorIO** and reruns B9's original 120-frame frozen take; a separately contained native review worker converts **every 120-frame Float32 source image** into 16-bit RGB PNG under the established ACES 2 SDR 100-nit sRGB view, then a fresh FilmIndex opens the exact frame and camera-cut archive.

**Review:** B11 stacked draft PR on B10; do not claim full acceptance before the final CI run is green.
