# USD-FILM-01M — Director-managed virtual cameras and shot-local occlusion

## Intent

NVP is a filmmaking system, not a game-camera simulator. The **3 angles ×
wide/medium/close-up = 9 camera** setup is a useful default preset for a
single performance, **not** a maximum or mandatory cinematographic grammar.

Director-created source camera banks may contain reverse angles, over-the-
shoulder, extreme long/far shots, overhead/top-down, low/upward viewpoints,
crane/dolly/tracking/aerial/drone views, closeups, inserts and any named
custom shot. Framing/setup labels are descriptive; actual lens, world pose,
movement and projection remain authoritative. Multiple cameras may observe
the exact SAME actor performance; render workers may serialize coverage
without changing source Film Time.

## Implementation [source committed; native CI acceptance OPEN]

- `DirectorCameraBank` is a versioned, FilmIndex-owned `presentation`
  referencing ONE existing immutable 01E world Digital Take/actor timeline.
- Source-preferred new rig can begin with one camera; a sequence of explicit,
  host-authorized typed `add`, `replace`, `remove` operations yields new
  immutable revisions. A camera removed from the latest rig remains in older
  revisions; original scene/Takes/actor performance are never deleted.
- A rig may contain 0 cameras while being edited; capture acceptance
  requires at least one. Current **per-rig resource admission cap is 96
  cameras** and 48 timed movement keys per camera, with explicit resource
  budgets. This is a safety/performability limit, not a 9-camera film limit.
  Future measured virtualization/partitioning may increase this cap.
- Typed camera controls: stable ID, arbitrary named setup and framing,
  world position in meters, native Euler direction, focal length in mm,
  focus distance, near/far clipping, original Film Time camera move keys,
  and up to 16 explicitly chosen primary-camera-ray occlusion exceptions.
- `open_source_views` authors `UsdGeom.Camera` prims **only into a
  disposable in-memory USD session layer** under a reserved director rig
  namespace. These prims are cameras, not meshes/rig props or physical
  colliders. No meshes, camera body, lens housing, gimbal, drone model or
  camera crew is included in the picture. Optional editor camera gizmos
  are separate viewport-only guides; never baked as rendered performers.
- Cinematic cameras have **no collision barrier**: they may sit inside,
  behind or cross walls/props at director's choice. This does NOT mean
  that a solid wall magically vanishes from the view.

## Camera-specific see-through blocking geometry

- Default shot: normal physically occluding walls/props.
- Optional director override: choose exact source geometry prim paths
  to make *primary camera rays only* ignore those particular objects
  for one camera's render. This keeps the world geometry and original
  material/transform references unchanged. Other cameras still see the
  wall; shadows, diffuse/glossy and transmission paths should remain
  enabled rather than deleting the object or mutating global USD visibility.
- A strict source-side validator checks that exclusions exist in the
  ORIGINAL USD world, contain genuine renderable geometry, and cannot
  hide an ActorID, camera or camera-containing subtree. Exclusions cannot
  be arbitrary strings supplied to an unreviewed Blender script.
- The first-party Blender `per_camera_primary_ray_exclusions` adapter
  resolves imported source hierarchy strictly, rejects ambiguous/missing
  geometry, applies `visible_camera=False` to approved mesh descendants
  and **restores** the previous visibility even if rendering throws.
- This behavior depends on Blender's Cycles camera-ray visibility feature.
  The real 5.2 import → wall mask → Cycles image must still be executed,
  independently inspected and accepted. Contract-only tests are not
  proof of actual image occlusion or shadow/reflection appearance.
- Camera-local ray visibility changes are editor/renderer derivations,
  not canonical source USD `visibility=invisible` opinions. The native
  original world and other camera source renders remain untouched.

## Tests and acceptance

- The existing one-original-performance Donut/Box/Sphere/Craft 01I fixture
  now also contains a source-authored environment prop `Wall`.
- Native pxr tests create a new one-camera bank, add reverse/OTS/low-angle
  and moving aerial cameras, place a virtual camera inside wall geometry,
  inspect native `UsdGeom.Camera` on the disposable stage, check the wall
  remains original visible geometry, remove one camera as a new revision,
  reopen FilmIndex and verify old camera revisions/actor SHA survive.
- Camera-ray unit tests check that wall mesh camera-ray visibility is off
  only during the selected shot, that its shadow/reflection/diffuse flags
  remain unchanged, that ActorID meshes are not altered, that exceptions
  revert on error and that ambiguous imported hierarchies fail closed.
- Native Windows/Linux Python 3.11/3.13 source jobs are wired and must
  pass on the exact head. No full nine-feed footage or 30s picture/audio
  acceptance is implied by this feature's source tests.

## Following required work

**USD-FILM-01N:** connect revisioned cameras and per-shot visibility
to real supervised native Blender/Cycles worker/frame outputs; verify
camera orientations, wall-exclusion image differences, unchanged
non-excluded cameras and their shadows/reflections. Add an editor camera
list, plus add/move/duplicate/remove/undo operations and exposure of
shot-specific visibility settings. Then continue full nine-roll 6,480
genuine pixels, 30-second edited picture + original audio, and USD-FILM
00–10 remaining independent native/visual gates.

Long-form film acceptance remains blocked until genuinely watched,
edited, moving-actor multi-camera output is achieved. HSURF-00 remains
after the USD-FILM family per creator priority.
