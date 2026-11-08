# FILM01-DONUT — An object can act; a real torus tests cinematic lighting

**Date:** 2026-11-08. **Branch:** `nvp/film01-donut-actor-lighting-20261108`.
**Base:** FILM01-R2 PR #108. **Acceptance:** code and dedicated native CI
authored, not declared passing until actual final-head Windows/Linux jobs
and generated source pictures are inspected. The pre-existing 720+720
short-film job was queued as of this task.

## Design decision

**An actor is a performing object with a source Film Time history.**
An actor need not be biological, anthropomorphic, voiced or humanoid.
NVP's existing OpenUSD `semantic_role=actor` can attach to a genuine
cube, sphere or mesh. A **donut actor** can move, pause, wobble, choose
an intention, be filmed from authored cameras and carry original sound
events while remaining visibly an ordinary toroidal object.

The director selected a donut to test lighting. This is an unusually
useful test: the open hole, continuously curved outer and inner
surfaces, bright face and narrow highlights show whether the
rasterizer/renderer is computing geometry, material response,
directional fill, occlusion and continuity. A uniform sphere or cube
can hide many such errors.

## Original source, not decorative overlay

- New `backend/nvp_film01_donut_actor.py` creates a finite,
  deterministic, wrap-closed torus in the original **XY plane, up Z**,
  36 major segments ×14 minor segments = **504 real XYZ points and
  1,008 outward-wound triangles**, with face-varying USD UV data.
  Major radius 0.95m, tube radius 0.32m, inner *open* hole radius
  0.63m, outer radius 1.27m. Validates shape, finite dimensions,
  nondegenerate topology, triangle budget and stable geometry SHA.
- `tools/nvp_film01_original_30s.py` now uses an immutable
  `EngineerDonut` authored USD **mesh** bound to the original
  `/World/Engineer` **actor** path. It replaces only the old
  Engineer sphere proxy in the disposable test project's original
  three shots. The original 30s editorial story, frozen Takes,
  10s/10s/10s cut timing, original 48k PCM/chirp at 26s and
  object-actor semantic role are preserved. The donut gets a
  source-material roughness .31/metallic .10 and a small authored
  midpoint Z bob as acting performance. No model generates frames.
- All three source scene revisions and independent Takes have a
  genuine bound native USD triangle mesh, not an AI image, donut
  icon, flat texture or screen-space torus silhouette. Original
  object binding, geometry SHA and nonhuman actor role are
  included in source and rendered-frame receipts.

## Native four-look light proof (fast visual diagnostic)

New `tools/nvp_film01_donut_light_probe.py` authors ONE separate
**frozen source USD Take** with the torus mesh as `role=actor`,
a genuine native `UsdGeom.Camera`, a native `UsdLux.SphereLight`,
and an authored 3s original timeline/motion curve.

At exactly the SAME Film Time and original Take SHA it renders four
distinct authentic **640×360 native floating-point NVP picture
frames** and independently reopens their PNG display derivations:

1. **Neutral** — actual native SphereLight and USD rough/dielectric
   microfacet source material.
2. **Silver virtual fill** — direct, neutral/cool per-donut artist
   lighting contribution, without an actual physical reflector.
3. **Gold virtual fill** — intentionally warm per-donut contribution;
   test requires a measurable positive warm pixel difference.
4. **Locked summer-3PM sun** — one director-selected permanent
   virtual directional sun, not a real astronomical position.

The native lighting diagnostic checks an actual dark center hole
and illuminated curved annulus in the emitted 3D RGB image; at least
one genuine rasterized triangle, exact source/Take/mesh SHA, original
actor role and actual per-look pixel SHA; all three FX treatments
must differ from the neutral original image and gold must have the
expected warm-channel contribution. Reopening frozen Take after
renders must show NO source modification.

The first visual review artifact, if CI passes, is
`nvp-original-donut-actor-four-real-lighting-looks` containing
**four separately named genuine NVP-rendered PNGs**, a 2×2
side-by-side contact sheet
`donut_actor_real_NVP_4_lighting_looks.png`, and the source
geometry/image/lighting receipt JSON. No FFmpeg, Blender substitute,
image-gen output, placeholder screenshot or fake render is allowed.

## Native acceptance

`tests/test_nvp_film01_donut_lighting.py` verifies USD mesh
topology, outward/finite nondegenerate faces, UVs, stable SHA,
refusal of malformed torus, actual original USD scene
`semantic_role=actor`, frozen Take/camera/light and the same
real source image with four light treatments. Negative tests
refuse nonexistent scene prim lighting and uncaptured live clocks.

`.github/workflows/nvp-film01-donut-actor-lighting.yml`:
- Windows2025 and Ubuntu24.04 Python3.11 with real usd-core26.11,
  NumPy and Pillow; native torus+source PNG/lighting tests;
  existing original three-Take full-short source acceptance.
- Ubuntu separate genuine original four-frame renderer, validates
  actual PNG image SHA, visible dark hole and illuminated annulus,
  different picture receipt values, and uploads the **actual**
  contact image and four original PNGs **only on success**.
- Exact-head native results, actual still images, installed desktop
  playback and independent human review remain OPEN until observed.

## What a real review should reveal

| Test | What an actual image can reveal | Current technical limitation |
|---|---|---|
| Inner/outer ring | Is the hole really open; do curved surfaces resolve? | Flat face normals/tessellation may produce faceted highlights |
| Neutral key light | Does the highlight wrap naturally with ring geometry and roughness? | First-party CPU GGX is an uncalibrated local preview |
| Silver virtual fill | Is the neutral fill readable without bleaching the shape? | Direct per-prim artificial light, not real reflector GI |
| Gold virtual fill | Does the warm effect show up on the inner and outer ring? | No physically calibrated Kelvin/material or shadow transport |
| Fixed sun | Does the impossible directional look survive reproducibly? | Direction is art-directed; no accurate sun/sky model |
| Actor movement | Is the donut bob visible and intentional between cuts? | Transform-only animation; no deformation or dynamic squash |
| Export | Do actual pixels/PCM review well in a native player? | 640×360 MJPEG/PCM16 is not photoreal finished film or cinema DCP |

**No fictional success:** Merely creating the source or queued CI cannot
show the user whether NVP's shading is good. Once the four images
actually exist and are inspectable, the human director judges them.
A scene-linear CPU image with artificially colored fill is not proof
of full global illumination, soft shadowing, accurate indirect
bounce, Hydra parity, cinema 2K XYZ, or DCI compliance.
