# FILM01-DONUT-R2 — Three performing objects, real depth, missing secondary light

**Reviewed:** 2026-11-08. **Status:** authored on standalone stacked branch; final-head
native Windows/Linux/GitHub artifacts OPEN. Base: FILM01-DONUT PR #109.

## Director's correct scene construction

The experimental short should not merely show a single static donut. **Three
objects are actors**, each with an original source motion curve in OpenUSD:

1. **Donut (the protagonist):** an actual 504-vertex / 1,008-triangle source
   torus with inner hole radius 0.63m and Z-axis hole, 3s bobbing motion.
2. **Box (supporting actor):** a green, roughness/metallic authored 0.8m
   original USD cube, travelling from stage left to right at source
   Z=-2.2m, **behind** the donut and camera-facing torus plane.
3. **Sphere (supporting actor):** a blue 0.6m USD sphere, moving on the
   donut's central Z-axis from Z=-4m behind to Z=+2.2m in front.
   Its 0.30m radius gives at least **0.33m geometric radial clearance**
   inside the genuine 0.63m toroidal hole, including during the
   donut's simple vertical bob. Motion is original time-sampled
   object performance, not composited 2D cutouts.

All three have `semantic_role="actor"` and must retain this even
though they have no faces, humanoid skeleton or conventional dialogue.
Original source scene, timed events, mesh SHA and frozen Take are
authoritative. A box and sphere are not "special effects": they are
participants in the shot.

## Actual native visibility behavior being demanded

The first-party OpenUSD/native triangle projection uses an actual
per-pixel Z buffer. `NativeSceneLinearRaster.render(...,
visibility_probe=True)` now **optionally** attaches a bounded,
depth-tested original prim-ID map during the same triangle draw
path. It records visible pixels per original USD actor and the
actual front-most source actor at the image center (rather than
guessing from RGB or the scene object list).

At 0s, the **sphere** should be visible through the open center
while the box is still left of frame center. At 1s, the **box**
should be visible through the torus hole because it passes in
front of the sphere (but behind the donut ring). At 2s, the
**sphere** should be visible through the hole again, having moved
forward while the box passed right. Tests enforce this exact
source-proven sequence:

| Frame @ 24fps | Box state | Sphere state | Center pixel must belong to |
|---|---|---|---|
| 0 | Left, behind ring | Behind box's depth plane | `/World/SphereActor` |
| 24 | Center, behind ring | Still farther behind | `/World/BoxActor` |
| 48 | Right, behind ring | Inside/opening crossing plane | `/World/SphereActor` |

Additional source-based guards check box Z remains behind the
donut, sphere XY remains exactly on the hole axis, radial
clearance, verified triangle pixel count, no source mutation,
unique per-frame PNG hashes and actual frozen Take revision.

The original **30-second FILM01 third shot** now also authors
`CrossingBox` and `PassingSphere` as two additional USD
object-actors. The donut engineer pauses near the beacon while
the box moves behind it and the sphere passes through its hole
around film seconds **26–27**, synchronized with the original
26.0–26.5s chirp event. The new source actions and time samples
exist in the *same locked scene/event history*; first two
shots keep the ensemble off-frame.

## Shadow and reflection complexity — honest answer

**Actual native depth occlusion is not ray-traced shadows or material
reflections.** The current NVP CPU microfacet raster can shade
source surfaces under local original and virtual light, but has
no implemented inter-object cast-shadow ray testing and no
secondary camera/specular reflection ray for another actor.
An image that merely shows the donut in front of a cube does
NOT prove its shadow falls on that cube or that a curved donut
reflects the green box.

New independent `tools/nvp_film01_donut_light_path_reference.py`
calculates Moller-Trumbore **rays through the actual source USD
torus triangles**, using the original source KeyLight and crossing
box at 1s. It measures box surface points that should be cast
in shadow from the donut, and points that should remain illuminated.
It separately tests ideal camera specular-reflection directions
from camera-visible torus facets and counts rays that hit the
green cube behind. These are **secondary-light reference expectations**,
not claimed rendered effects.

Native tests insist the actual scene produces **both shadowed
and unshadowed box samples** and at least one physically plausible
torus-to-box reflection ray. They also insist the current renderer
honestly reports `real_light_ray_traced_shadows_computed=False`
and `real_interobject_reflections_computed=False`. Accepting
depth occlusion is an independent gate; implementing honest
ray-traced/hybrid shadows and reflections is the next renderer
work group, not something a gold fill or USD sphere-light
metadata magically provides.

## Actual viewable proof

`tools/nvp_film01_donut_three_actor_motion.py` reopens the SAME
original frozen Take and produces:
- Six source-derived 640×360 PNGs at frames 0,12,24,36,48,60
  and a **3×2 contact sheet** showing the crossing and passage.
- With `--full-72`, all 72 genuine original
  640×360 OpenUSD frame PNGs at 24fps for three seconds and a
  real source-derived 3s **animated GIF**, not a generated
  placeholder animation or still-image video.
- SHA/pose/depth visibility receipts for each actual frame, and
  the independent geometric **shadow/reflection reference** JSON.
  Audio is not claimed in this short animation (GIF has no sound).
  The original full 30-second AV movie/PCM remains a separate
  native pipeline with the newly added actors.

CI `.github/workflows/nvp-film01-donut-three-actor-occlusion.yml`
runs real native OpenUSD/NumPy/Pillow Windows/Linux tests for
the actor scene, depth pixel identities, cast-shadow/reflection
reference, existing four-look shader and new original 30s
choreography; independently renders all 72 actual original
USD frames on Ubuntu, opens GIF and source images, and **only
after passing** uploads
`nvp-real-donut-box-behind-sphere-through-hole-3second-motion`.

No completed GIF, PNG, AVI, external installed player viewing, shader
cast shadows, genuine object reflections, human artistic approval or
DCI cinema-compliant 2K master is asserted until independently observed.
The reference probe and original screenshot comparisons should guide
the next shader development order: correct actor occlusion -> true
source shadows -> reflections/roughness response -> visual quality,
animation, audio and 2K output.
