# USD-FILM-01G — Film-first three-shot native acceptance

## Director's correction (2026-11-08)

NVP is a motion picture production environment, not a 3D-model turntable.
A technically valid donut, box and sphere render is insufficient unless
the **original ActorID performances play across an edited sequence**.
The visual acceptance unit is one 30-second short, not individual PNGs.

## Three distinct angles, with actual cuts

| Cut | Source timeline | Camera | Cinematic purpose | Actor blocking |
|---|---|---|---|---|
| 1 — Establishing | 00:00–00:10 | Original wide master | Introduce staging and shared spatial geography | Donut/Engineer, CrossingBox, PassingSphere, ServiceCraft all geographically readable |
| 2 — Action | 00:10–00:20 | Different three-quarter side angle | Show depth and movement | Box passes **behind** donut while sphere approaches and passes through its real opening |
| 3 — Detail/reaction | 00:20–00:30 | Third distinct close angle | Deliver a readable dramatic payoff | Sphere clears opening, box's position and light/shadow/reflection reveal the encounter's result |

These are intended compositions, not claims that the current source Takes
already contain the exact blocking or camera geometry. Actual native source
cameras, evaluated original actor meshes, and film ticks must prove them.

FilmIndex world, frozen Digital Takes, original ActorIDs, VoiceIDs, dialogue,
authoritative 48k PCM and original film-time remain authoritative. The camera
and performance may differ across shots but must preserve spatial continuity,
screen direction, trajectory and sound continuity at each cut. No source actor
is silently replaced with a Blender proxy.

## Native acceptance requirements

1. Director approves one original source world, three shot camera plans and
   three immutable world Takes. Each of the three originals must have a
   different camera prim and camera-shot SHA. Preserve original source hashes.
2. Blender/Cycles evaluates all actual **240 frames per shot** at their exact
   original film ticks (24 fps). Geometry, shadows, specular response and
   occlusion must change with performance. A still repeated 240 times fails.
3. Native per-frame receipts identify the specific world SHA, Take SHA,
   camera SHA/prim, exact film tick and PNG SHA. No guessed authenticity.
4. Conform cuts in order to **720 decoded frames / 30 seconds**. Independently
   decode the assembled video with FFprobe. Original audio event streams are
   synchronized to the film clock, mixed and separately checked for 48k PCM
   duration/essence when an audio master is claimed.
5. Inspect a contact sheet across **all three** shots, film playback across
   cut boundaries (frames 239→240 and 479→480), original ActorID spatial
   continuity and legible composition. Screen direction, box depth,
   sphere-through-hole topology, animated lighting, shadows, reflections,
   camera grammar and sound edits require human review.
6. Accept only after Windows/Linux exact-head native runs, generated
   playable film and JSON audits have been inspected. Synthetic or mocked
   acceptance tests only validate their contracts and remain separately labeled.

## Implemented vs still open

- **Implemented:** strict three-shot film conform contract, camera/source
  identities, exact tick and per-frame receipt verification, sequential edit
  with FFmpeg/FFprobe, 30s original PCM16 mux gate, refusal tests and OS CI.
- **Open:** connecting the USD-FILM-01F two-still Blender handoff to
  720 genuine per-frame 01E world-Take renders with distinct source cameras;
  production-quality movement, continuity, score/performance/sound mixing;
  actual native film artifact inspection and director approval.
- **Open:** USD-FILM MaterialX/render parity and photoreal actor work.
  HUMAN-SURFACE HSURF-00 remains deferred until USD-FILM family gates.

The strict conform module is an acceptance boundary, not evidence that those
native frames are already rendered.
