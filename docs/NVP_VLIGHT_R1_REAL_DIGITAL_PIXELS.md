# V-LIGHT-R1 — Real digital gold-fill and impossible fixed-sun OpenUSD pixels

**Date:** 2026-11-08. **Branch:** `nvp/vlight-digital-preview-raster-20261108`.
**Stack:** FILM01 PR #106, its actual full 720-frame native AVI deliverable.
**State:** Code committed; exact-head Windows/Linux native tests and both
full 720-frame preview artifacts unverified until runners complete.

## The creator's digital-first correction is implemented in PIXELS

NVP does not require physical bounce-card geometry, indirect path tracing
or actual sun astronomical time to achieve these two lighting choices.
The direct artist lighting schema in `backend/nvp_virtual_light_fx.py`
already evaluates a typed chosen color, magnitude, target prim, Film Time
and frozen free-running clock phase when captured.

**New:**
- `backend/nvp_virtual_light_raster_adapter.py` validates all original FX
  settings at the requested exact Film Time and resolves the target prim
  against actual frozen source USD objects (or reserved
  `/World/Scene` for an intentionally scene-global artistic sun).
  Every decision carries its original SHA; duplicate effects,
  missing actors and uncaptured free-running clocks fail closed.
  The adapter outputs a bounded per-prim linear-RGB contribution list,
  not a new emitter mesh, shell/plugin or source mutation.
- `backend/nvp_native_scene_linear_raster.py` consumes those per-prim
  contributions at actual source triangle shading. The existing
  GGX/Schlick direct neutral UsdLux source remains unchanged when
  `virtual_fx=None`. Nonphysical silver/gold fills directly add
  directional or broad color to the selected object's source-linear
  pixels, including textured surfaces. A fixed "Summer 3PM" sun
  adds artist-selected warm directional contribution to actual USD
  surface normals; its azimuth/elevation remain independent of the
  scene's story time.
- `backend/nvp_wo6_07f_rendered_av.py` threads an OPTIONAL
  `virtual_fx` list through genuine source-pinned 3D picture
  rendering. It publishes exact original frame/Take/PNG SHA,
  `virtual_fx_actually_applied_to_pixels`, source FX SHA and count.
  The source WAV and 2,000 original PCM samples per frame remain
  unchanged by lighting.
- `tools/nvp_film01_original_30s.py` offers
  `--apply-virtual-fx` to produce the *same original 30-second
  short's* genuinely rendered PNG/AVI with visible gold engineer fill
  and locked scene sun. The source report separately distinguishes
  **FX design intent** (not proof of rendering) from the final actual
  frame receipt (proof shader was invoked). Source Takes/PCM/edits are
  never overwritten. The user can compare the baseline AVI and
  FX-enabled AVI side by side, with contact sheets from actual
  frames. Both remain 640×360 CPU-preview artistic output.
- `tests/test_nvp_virtual_light_raster.py` requests real original
  OpenUSD/USD camera/sphere/actor 3D pixels and source PCM and compares
  baseline vs virtual gold and fixed-sun picture hashes. It checks
  a real warm pixel delta with gold without any physical reflector,
  exactly identical native WAV/source SHA, no Take mutation, and
  denial of absent target, duplicated IDs and unrecorded live clocks.
  It also creates a genuine six-frame test archive with artist FX
  applied to actual emitted pictures.

## Full 30-second visual comparison

Dedicated workflow `.github/workflows/nvp-vlight-digital-preview-render.yml`
uses native Windows 2025 / Ubuntu 24.04 to test actual actor
pixel differences, pure FX timing and original source custody.
Its separate Linux job attempts a full **720-frame** actual native USD
raster + original **1,440,000 PCM sample** render, with
`--apply-virtual-fx`, then produces:

- **AVI** `nvp-relay30-vlight-playable-640x360-mjpeg-pcm.avi`
  — real original 24fps MJPEG video and interleaved 48kHz source WAV,
  with the virtual gold/sun contributions included as source-rendered
  pixel changes.
- **PNG/WAV ZIP** with original per-frame source SHA and explicit
  virtual-FX shader applied metadata.
- **Actual 3×3 frame contact sheet** and independent RIFF/JPEG/PCM
  readback receipt.

These outputs are uploaded only when real native runner evidence
exists; a queued workflow is not a download. The baseline AVI from
FILM01 PR #106 remains a separate visual/control artifact for judging
the effect.

## Crucial limitations

- This is an actual **virtual artist lighting approximation** in a
  first-party CPU **linear Rec.709 uncalibrated preview**. It intentionally
  violates physical light transport and does not represent global
  illumination, realistic silver/gold material reflectance, Hydra/
  MaterialX photometric quality, source-managed ACES or cinema XYZ12.
  It is a tool for artist-controlled fiction.
- The effect config in a disposable film-test project is a SHA-checked
  **preview-sidecar**. Full FilmIndex-native effect revisions, creator
  approvals, light object attachment/snap/locking, per-actor face
  segmentation, actual free-run capture UI, film-grade compositing
  and native packaged export approval remain open.
- A raw effect may alter picture but not mastered sound or original
  USD. Tests prove source frame changes and deterministic
  data routing, not that the shot is visually convincing.
  Human review of actual AVI and native installed Windows playback
  is mandatory, and the 2K DCI finishing/physical theater gates
  are unchanged.
