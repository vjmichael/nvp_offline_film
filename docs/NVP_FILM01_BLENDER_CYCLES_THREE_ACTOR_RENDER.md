# FILM01-BLENDER — Real supervised Blender/Cycles donut-box-sphere director screening

**2026-11-08 — baseline native real Blender accepted; directed retake pending native acceptance.**

This restores NVP's approved STACK-002 architecture: **Blender is the
external 3D production renderer**; first-party CPU OpenUSD raster is a
low-quality source/debug preview and must not be mistaken for Blender
or a roadmap for writing a new path tracer. The 2026-11-03
`NVP_ADR_STACK02_BLENDER_WORKER_USD_DEFERRED.md` decision remains the
production-reuse principle. The data-first OpenUSD authoring stack
developed later is an additional source representation; whether a
standalone USD installation belongs in the eventual single installer
is still a separate product-level architecture reconciliation, not
a reason to discard Blender.

## Direction: three OBJECT actors perform one scene

- Actual **donut**: the existing NVP FilmIndex original
  `/World/DonutActor` semantic `actor` and its ORIGINAL 504-point,
  1008-triangle torus (inner hole 0.63m), now with smoothly interpolated
  Blender normals and a reflective copper/bronze Principled material.
- Actual **box**: original `/World/BoxActor` semantic actor with a
  rough, green .8m cube, moving left to right **BEHIND** the torus
  plane at Z=-2.2m.
- Actual **sphere**: original `/World/SphereActor` semantic actor with
  a glossy blue .6m sphere, moving along the torus's **open Z-axis
  hole** from behind to in front, .33m radial clearance.
- Original 3-second Take = EXACT 72 frames at 24 fps, with SHA-verified
  per-frame actor world positions read from **FrozenSceneAV.snapshot**
  at exact Film Time. A real `UsdGeom.Camera` and `UsdLux` source
  scene are reopened for custody. Blender material/light setups are
  derived/artist-directed and not implied to be an exact UsdLux
  photometric conversion or a source revision.
- NVP's original third shot of the separate 30-second film already
  authors this blocking scene at approximately film seconds 26–27
  with the sound cue; the 3-second Cycles test is a director's
  **visual diagnostic** before full-film finishing.

## Two strict halves: authoritative source versus GPL Blender

1. First-party NVP host
   `tools/nvp_film01_blender_cycles_acceptance.py` creates a disposable
   test project using **real existing OpenUSD/FrozenSceneAV**.
   It reopens original FilmIndex USD mesh asset, Take and scene
   document SHAs and reconstructs all 72 poses from original Film Time.
   The immutable, SHA-addressed JSON scene description is **production
   data**. No model may invent arbitrary Blender code.
2. Host stages `source.json`, exact checked-in trusted
   `tools/nvp_film01_blender_cycles_worker.py` as a *pinned file*,
   and an immutable `BlenderOperation`. It uses the established
   `BlenderWorkerSupervisor` plus `ApprovedBlenderDispatcher`,
   native resource ledger/OS process containment and durable journaling.
   The CI approval checker is a test-only host callback matching the
   source Take and exact worker spec; a real production creator click
   and final redistribution approval remain separate gates. Neither
   web/LLM input nor a project filename can supply executable Python.
3. Independently licensed **external Blender 5.2.3/Cycles** is
   downloaded from official Blender distribution and **must match the
   upstream SHA-256 file**. It is executed as an external, pinned,
   version-checked process, not imported as a proprietary NVP library.
   The bpy worker adapter must be separately licensed/reviewed as GPL-
   compatible; the exact Blender binary, Python adapter, upstream
   notices/source obligations and installer redistribution remain
   on NVP's legal inventory for pre-release review.
4. The Blender worker constructs actual native geometry, per-frame
   original actor animation, Cycles CPU 8spp, 6 indirect light
   bounces, 4 glossy bounces, source-geometry smooth normals, a real
   Principled reflective donut, large key area light, a matte
   shadow-receiving backing plane and real artist silver/gold/fixed
   3pm alternative light fixtures. It renders **72 independent actual
   original Cycles 640x360 PNG frames**, with exact original frame
   indexes/source Take SHA recorded. It also renders **four separate
   actual Cycles stills** at the same source time, plus saves one
   original derived Blender `.blend` project.
5. The NVP supervisor requires exact declared media outputs (Blender
   scene, JSON audit, all four PNG looks) and durable worker success.
   The NVP host **independently** opens ALL 72 source PNGs with Pillow,
   verifies frame count/dimensions/each original image SHA, actual
   four-look pixel differences, original immutable Take, script and
   Blender binary SHA and persistent worker success. It creates a
   3x2 six-moment contact PNG, 2x2 real four-light look contact PNG,
   3-second frame-index-annotated animated GIF and source/audit JSON.
   The annotations are added ONLY to review GIF copies, never to
   original Cycles PNGs or source FilmIndex data.

## Evidence to download when native GitHub runs actually pass

Dedicated workflow `.github/workflows/nvp-film01-real-blender-cycles-donut.yml`:
- Windows2025/Linux Ubuntu24.04 Python3.11 source custody, native
  frozen Take/actor roles, original 72 pose/tick integrity, SHA-pinned
  fixed trusted script/BlenderOperation staging and existing native
  worker cancellation/journal safety tests.
- Ubuntu24.04 *genuine official Blender 5.2.3* installation validated
  against its published SHA-256. Real 72-frame Cycles batch through
  NVP's worker supervisor, bounded local resource ledger, original
  FilmIndex scene and independent png/GIF/artifact verification.
- **ONLY on full actual job success**, upload:
  `nvp-FILM01-REAL-BLENDER-CYCLES-donut-box-sphere-3s`, containing
  the real source-derived 72 PNGs, genuine saved Blender scene,
  3-second GIF, six key stills/contact, four Cycles lighting
  stills/contact and SHA/worker/output receipts.
- If a native worker fails, upload a **SEPARATE explicitly labeled
  diagnostic log** and do not claim the director's film exists.
- No local environment lacking Blender, no queued GitHub run, no
  first-party CPU-proxy render and no illustrative image count as
  NVP's verified Cycles pictures.

## Independent native Blender reopen (distinct process)

The test **must not trust the original render worker alone**. A new
first-party GPL-labeled separate-process adapter
`tools/nvp_film01_cycles_reopen_audit.py` is run from the Ubuntu
acceptance job **after** the original supervised Blender process has
closed and its `.blend` has passed worker SHA checks. The *second*
genuine pinned Blender binary opens `source_derived_Blender_Cycles_scene.blend`,
rechecks 1008 smooth torus faces, 3 real object-actor roles, source
Take SHA, saved frame range/camera/key/shadow receiver, Cycles
CPU/diffuse/glossy-bounce settings and original USD positions at
frames 0/12/24/36/48/60/71. It writes an independent
`independent_saved_Blender_reopen.json`, checked against the source
frame/audit manifest before any director artifact is published.
This is **CI-only independent re-open acceptance**, not production
Blender worker bypass or native Windows installed approval.

## Acceptance and known open issues

The user's immediate goal is to **WATCH and judge** actual Cycles
picture. The program can verify that Cycles used a real path-traced
render engine with cast-shadow/indirect/specular bounces enabled and
distinct silver/gold/sun PNG results. It MUST NOT claim the actual
green cube is visibly reflected in a specific donut facet or that
cast shadows are artistically adequate until someone inspects the
native images or a source-targeted pixel reference comparison proves
it. (The original CPU-raster shadow/reference test remains a
useful geometric oracle for future comparisons, not production
rendering.)

After picture acceptance, required outstanding gates include
actual physically installed Windows Blender worker with Job Objects;
durable source-linked scene/take release and per-look creator approval;
film 30-second true Cycles renders and mastered original soundtrack;
camera editing and actor performances; calibrated OCIO/ACES HDR,
2K 12-bit XYZ/JPEG2000/MXF and DCI DCP; and redistribution/legal
license review. A 640x360 8-sample Cycles GIF is NOT DCI/theatrical
master, and the source project's original PCM is not in GIF (GIF is
silent; full 30-second AV finishing is separate).

## FILM01 baseline render actually inspected — 2026-11-08

- Exact baseline source/Cycles head: `0d24a3891a146a0199262d5f3cbe47243c3e9429`.
- [Native Windows/Linux/Cycles success](https://github.com/vjmichael/nvp_offline_film/actions/runs/42490015508), artifact ID `13621138323` (`nvp-FILM01-REAL-BLENDER-CYCLES-donut-box-sphere-3s`). The CI reported all three native jobs successful, including separate saved .blend reopen and all 72 PNG/GIF tests.
- Actual downloaded six-shot contact and four-look sheet were opened and visually inspected; not concept imagery. **Observed** ring smooth and hole real, blue sphere travels inside hole in depth, green cube is visible through hole at ~1 second; glossy tan/beige-looking material is insufficiently copper-like; broad/diffuse backdrop shadow distracts from action; sphere's approach spends too long behind box, then comes forward quickly. Silver and gold treatments generate visibly distinct white/cool/warm highlights; no claim yet of visually legible green-box reflections on a named facet.
- The baseline package is retained immutable for side-by-side comparison; no baseline pixels have been modified. Rendering acceptance does **not** confer physical fidelity, creator release, legal distribution, Windows installed-app acceptance or theatrical color approval.

## Director retake 01 — authored revision awaiting native re-render

- `tools/nvp_film01_donut_light_probe.py` now permits explicitly selected `performance="director_retake_01"`. The staged Cycles acceptance generates this as **a distinct frozen FilmIndex/OpenUSD Take** with different SHA; baseline generator remains the default so old checks remain reproducible.
- Source-authored sphere approach: at 1.0s z=-2.8m (baseline -3.7), 1.5s z=-0.45m (baseline -1), 2.0s z=0.7m (baseline 0.1), 2.5s z=1.7m (baseline 1.45). Same .30m sphere radius, real torus hole clearance, unchanged actor roles, unchanged topology; position snapshots continue to come from frozen USD, not invented Blender animation.
- Observed tan ring motivates derived Blender shader change to a darker copper base `(0.42,0.205,0.092)`, metallic `0.86`, roughness `0.22`; key area reduced from 1.8m to 1.15m to control diffuse shadow edges, light 800W at (3.2,3.4,5.5), plus cool 125W area rim and restrained world ambient. These are **artist-directed lighting/material overrides**, not silent edits to the authoritative original USD source material.
- The independent second Blender open now asserts the saved Principled metallic/roughness, new rim presence/energy and key radius. The source regression asserts that retake SHA differs from the baseline and confirms changed 24/36/48-frame frozen sphere positions.
- Do not call retake accepted until its actual pinned native Windows/Linux source tests, separate real Blender 72-frame render, second Blender reopen, full PNG/GIF and audits complete; thereafter compare original vs new contact sheets and note remaining artistic quality gaps. For production a creator must explicitly approve the retake, not rely on CI's test-only authorization.
