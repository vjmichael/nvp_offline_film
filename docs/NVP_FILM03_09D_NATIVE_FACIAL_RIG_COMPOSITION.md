# FILM03-09D — Native USD facial rig and independent mouth animation

**Status:** 09D-1 original rig readback and native derived facial-overlay source code implemented. Exact-head Windows/Linux tests are OPEN. Neither real speech phoneme recognition nor believable rendered lip-sync has been proven.

## Director's acting intent

Facial expression follows the voice emotional state by default, unless the director explicitly chooses otherwise. Human actors and nonhuman object actors can intentionally smile over sad speech, frown over happy speech, or perform without a mouth. Mouth articulation, face emotion, and body acting are separately controlled.

## Actual original rig acceptance

The new backend/nvp_film03_facial_rig_compositor.py reopens the exact frozen original OpenUSD Take and source scene through FilmIndex. It inspects genuine UsdGeom.Mesh, UsdSkel.Skeleton, UsdSkel.Animation and UsdSkel.BlendShape binding/source point-offset geometry. Existing shape targets must have nonzero offsets. A shape named "MouthOpen" without actual movement is refused. An actor without a rig must not be presented as synchronized; no surrogate mesh or fabricated face is created.

An explicit semantic map binds canonical 09C phoneme-visemes to actual original facial shapes. An independent expression map binds the director's happy/sad/etc. track to actual original shapes. In this first compositor a face-expression shape and a mouth shape cannot overlap **even when their shape names differ but their real USD offsets deform the same mesh vertices**. A corrective rig is necessary before combining those targets. Shape support is independently reopened from the immutable source scene so a supplied mapping cannot spoof the original mesh. Original facial animation outside explicitly controlled targets and all original joint/body keyframes remain untouched.

## Derived native animation

Native UsdSkel.Animation keyframes are authored into a separate anonymous Sdf layer, with the original complete blend-shape ordering. NVP uses 48-kHz audio sample positions and 147000 exact Film Time ticks per sample. Simple short-duration crossfades between neighboring phonemes provide testable transitions, not a final coarticulation quality claim. Director expression overrides are preserved and existing conflicting expression targets are explicitly neutralized when selected.

The derived layer is independently composed with the original USD source; the frozen Take, scene mesh and original audio are not overwritten. A stored 09C native-alignment candidate may produce a separate unapproved FilmIndex facial candidate with typed original source links. Source integrity and precise ActorID/VoiceID linkage are checked again.

## Tests

Native tests publish a real USD skinned actor with nonzero MouthClosed, MouthOpen, Sad, Smile and inert-zero deformation targets. They inspect actual USD shape sources, freeze a genuine source Take, author a separate USD facial animation layer, reopen its keyframes, prove sad-to-happy director keyframes remain independent, and reject unrigged actors, absent shapes, zero-offset shapes, overlapping mouth/emotion mappings, wrong original Take, bad timing and unverified acoustic sources.

The phoneme timings used in these source/rig tests are structural fixtures. **They are not actual spoken dialogue or proof the acoustic model has run.** A test for the native USD data path is distinct from an actual Blender/Cycles rendered moving face.

## Open acceptance

- 09D-1: Source-locked native rig geometry, shape mapping and real USD facial-overlay authoring: **code implemented; Windows/Linux CI pending**.
- 09D-2: Execute actual reviewed 09C acoustic model on human-performed dialogue; review actual mouth target semantics and use the FINAL selected TTS/converted audio: **OPEN**.
- 09D-3: Host-supervised Blender/UsdSkel animation and real visual mouth-shape inspection, corrective rigs, coarticulation and actual source-versus-rendered timing: **OPEN**.
- 09E: Installed NVP director reviews the synchronized final voice, face (matching by default) and intentionally contrasting variants; authentic sound+render and restart/retake persistence: **OPEN**.

This work adds no performer legal/consent/rights administration or additional non-filmmaking subsystem. Existing Blender host and original USD data path are reused.
