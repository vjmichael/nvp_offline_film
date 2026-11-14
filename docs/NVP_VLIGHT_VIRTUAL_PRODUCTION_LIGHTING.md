# NVP virtual-production lighting — dependency and design work order

Status: DESIGN / CANDIDATE EVALUATION, not a renderer acceptance. Logged 2026-11-08.
Scope: procedural/artist-directed *3D virtual film set lighting* (not a flat brightness/color-grading control). This work should not hold up WO6-07E synchronized source review.

## Candidate stack and commercial-use licensing research

1. **OpenUSD UsdLux**: preferred *authoritative scene representation*, already present in NVP's native scene stack. Light primitives include DistantLight, SphereLight, RectLight, DiskLight, CylinderLight, DomeLight, plus light shaping and shadows APIs. USD can hold time-sampled intensity, radiance/color, exposure, cone/focus and transforms. It is NOT itself a physically correct renderer. Upstream project currently publishes the **Tomorrow Open Source Technology License 1.0 (TOSL)** (a permissive license with trademark difference from Apache 2.0), not simply Apache 2.0. Do not conflate Pixar USD samples/assets (which may have a separate noncommercial EULA) with the engine library license.
   Documentation: https://openusd.org/release/user_guides/render_user_guide.html
   Upstream license: https://github.com/PixarAnimationStudios/OpenUSD/blob/dev/LICENSE.txt
2. **LuxCoreRender / LuxCore API**: candidate for physically based transport / independent path-traced lighting and final render parity. Upstream says **Apache-2.0**, including commercial embedding, with native C++/Python API. Evaluate actual USD/MaterialX/OpenPBR translation, precision, visibility, performance, GPU behavior, and transitive binary notices before using. It is NOT automatically compatible with NVP's existing shader/material pipeline.
   Official: https://luxcorerender.org/free/
   Source and license: https://github.com/LuxCoreRender/LuxCore
3. **Blender Cycles engine**: upstream identifies standalone **Cycles** engine as Apache-2.0, though **Blender application itself is GPL-2.0-or-later**. If considering direct engine integration, audit the exact standalone repo, dependencies and linking rather than assuming bundling full Blender is permissive. Blender may also be used as an explicitly separate external tool, but not silently redistributed with different license conditions.
   Licensing: https://www.blender.org/about/license/
   Cycles source: https://github.com/blender/cycles
4. **OpenShadingLanguage** (BSD-3-Clause) and **OpenColorIO** (BSD-3-Clause) are supporting shader/film-color technologies, not complete lighting engines. Relevant only if chosen renderer supports them. OpenColorIO requires separate managed view transforms/LUT quality and theater calibration.
   https://github.com/AcademySoftwareFoundation/OpenShadingLanguage
   https://github.com/AcademySoftwareFoundation/OpenColorIO

All above licenses generally permit use in commercial software, conditional on complying with terms; this is a preliminary upstream survey, not redistribution/legal sign-off. Pull exact release license/NOTICE and SBOM for each eventual bundled artifact, including third parties, and check SPDX/installer payload and trademark/asset restrictions.

## Desired virtual lighting system

**V-LIGHT-01 — Lighting as production data:** Native per-scene, per-shot USD light rigs (key, fill, back/rim, practical, ambient/dome, emissive mesh, gobo/cookie). Time-sampled positions/rotations, exposure/intensity, color temperature, physical dimensions/spread, shadows, bounce/GI, HDRI, linking and attenuation; realistic stage units and ACES/OCIO-managed color. Camera exposure, aperture, ISO/white balance must be distinguished from changing light energy. Existing NVP authoring should remain non-destructive; every light parameter keyed by exact original OpenUSD source SHA and Film Time.

**V-LIGHT-02 — Mechanics and photometric realism:** Compare UsdLux authoring against the actual renderer; validate physically plausible falloff, power, light color/temperature, area softness, IES fixtures if supported, shadow occlusion, reflections, roughness interactions, specular highlights, volumetric fog/smoke, motion blur effects and multi-bounce GI. Require reference light probes and 2–3 independently measurable scenes (Cornell-style box, human closeup with key/fill/rim and moving practical light). NO fabricated renderer parity.

**V-LIGHT-03 — Director lighting UI/AI:** Simple virtual grips and practical studio presets, interactive key/fill/back placement, live light parameter preview and lockable light-rig revisions. AI can suggest setups but cannot author or alter a scene without the director's independent values, exact source-impact review and two native OS approvals. Save original scene separately from lighting overrides and shot-local opinions.

**V-LIGHT-04 — Renderer bridge decision:** First evaluate native OpenUSD/UsdLux + current Hydra/Storm and MaterialX for preview; use permissively licensed LuxCore or standalone Cycles as independent path-traced renderer option if viable. Compare genuine ray-traced pixels, direct/indirect energy, soft shadows and material color versus source-managed reference. Document unsupported USD constructs and translation loss. A bespoke NVP **v-lighting** engine is a fallback only if existing commercially usable integration cannot provide required production quality or licensing compliance.

**V-LIGHT-05 — Acceptance:** Native Windows/Linux, real renderer image evidence and scene fixtures; calibrated OCIO/ACES reference, finite and valid units, motion continuity, measured 30s/30m memory and frame latency, installed NVP interaction, transitive SPDX/NOTICE and legal license review. Production final quality/feature-film scope remains a separate gate.

Decision: **do not invent NVP v-lighting immediately**. Use UsdLux as authoritative lighting description, validate native preview, and prototype Apache-licensed renderer bridge(s) before deciding a custom subsystem. No candidate is bundled into this work order.


## Creator's simple V-LIGHT control specification (2026-11-08)

**UsdLux is already part of OpenUSD**, exposed in Python through
`from pxr import UsdLux` and used by NVP's existing native
`UsdLux.SphereLight` source schema. No separate UsdLux runtime, marketplace
plugin or independently installed lighting editor is required. The
existing OpenUSD library represents light *data*; the chosen render delegate
is still responsible for actual scattering/shadow/illumination.

**V-LIGHT-SIMPLE-01 (first useful artist UI):**
- **Place light:** Click Add Light, place a draggable/rotatable light gizmo
  anywhere in 3D space, select an established type: Sphere (omni),
  Distant (parallel directional), Disk/Rect (softbox/area), Cylinder
  (light strip), Dome (ambient/HDRI). Add beam/spot via
  `UsdLux.ShapingAPI` cone angle and cone softness; no fake new
  ray-type USD schema is needed.
- **Brightness and color:** intensity, exposure (stops), RGB/hex color
  and optional white-light temperature in **Kelvin** (e.g. 2700K warm,
  5600K daylight). These are separate controls. The color temperature
  path is enabled explicitly with LightAPI's enableColorTemperature;
  if RGB color is also selected, the renderer's combination behavior
  must be made clear. Do not equate Kelvin with brightness or assume
  photometric lumens equality across renderer types.
- **Soft or hard:** luminous emitter SIZE controls area-shadow softness;
  `ShapingAPI` cone softness controls beam-edge rolloff; shadow controls
  are separate, not interchangeable. The actual ray-traced renderer must
  visibly implement those meanings. Expose a simple Soft/Hard artist
  preset while preserving the underlying authored parameters.
- **Attachment:** Free Move, Snap To Object, Attach To Object,
  and Lock In Place. Use USD parent-child transforms or evaluated
  absolute matrices when baking a captured frame. **UsdLux does not
  itself implement a live constraint/locking system**, so NVP's
  first-party scene editor stores/re-evaluates the attachment target,
  offset, source SHA and lock state. Snapping and locking are NOT
  permissions for a model to alter source.
- **Pulse/flicker:** on/off, speed in Hz, amplitude, phase and optional
  simple wave shape (smooth pulse, sharp pulse, flicker later). A
  deterministic bounded function evaluates intensity at authoritative
  Film Time and is baked as time-sampled UsdLux intensity into an
  immutable derived light revision when the director approves.
  A separate monotonic light timer is permitted for live effects, but
  its phase or real event times must be captured/synced to Film Time
  before an immutable final render. Unrecorded live phase must never
  change the original finished picture unpredictably.
- **Edit and persist:** selecting a light presents its source identity
  and editable controls. Undo / Save Light Rig stores a new original-
  preserving authored revision, not an overwrite. Source-impact
  preview and both existing native OS approvals remain required.
  AI may suggest combinations but never automatically install lights.

**Scope decision:** implement this small everyday interaction *before*
photometric-accuracy extras such as IES, GI, participating media,
gobo light linking and theatrical calibration. These advanced lighting
mechanics remain V-LIGHT-02+ gates; do not let them make basic lights
difficult to place or adjust. For WO6-07F continuous rendered preview,
existing source **SphereLight** is supported by NVP's CPU scene-linear
raster as a *neutral scalar light* only; Kelvin/RGB, beam shaping,
emitter softness and calibrated multi-bounce radiance are NOT proven by
that preview. Those require an appropriate UsdLux-capable renderer.


## Creator clarification: independent FX timers, silver/gold bounce (2026-11-08)

- **Independent time is permitted:** Cop-car red/blue strobes, a flashlight flash, fireworks, flicker and lightning may run on their own monotonic oscillator during live authoring. NVP must offer *Capture/Sync*, recording clock origin/phase, triggers and exact offset to original Film Time. Timeline-synchronized mode is a separate switch. Final picture/audio rendering must replay the same recorded effect reproducibly rather than running a non-repeatable wall timer.
- **Silver Bounce / Gold Bounce:** Placeable, orientable passive 3D reflector boards, freely moved, snapped, attached or locked. Silver has a comparatively neutral reflectance and gold warms the actual reflected illumination. Size, roughness/matte versus specular response and positioning matter. These boards are **not** emitted light, not an exposure shortcut and not a post-processing tint. Real indirect light transport/BSDF in the chosen renderer must be demonstrated by independently measured scene comparisons. The current simple CPU preview cannot prove GI or true reflected color.
- **Priority:** Simple artist UI for practical lighting and FX comes before advanced IES/volumetric/cinema photometric calibration. Preserve original source scene, source SHA, Film Time and creator-native two-approval isolation.

Detailed work-order requirements: `docs/NVP_VLIGHT_FX_TIMERS_REFLECTORS.md`. This is a **design backlog**, not a claim of finished installed controls or physically accurate bounces.
