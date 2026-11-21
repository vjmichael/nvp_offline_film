# NVP-PROD-01 — Persistent virtual studio, takes, dailies and editorial

**Status:** architectural contract and implementation roadmap. Existing scene/capture/FilmIndex functionality supplies partial foundations; this document does not claim that a complete GUI dailies system, high-fidelity actor performance, or unlimited render farm is implemented. Do not block ongoing B14 edited-video acceptance.

## Identity of NVP

NVP is a filmmaking production pipeline operating on an enduring 3D set, not a disconnected 3–10-second video-prompt clip factory. Authoritative scene state includes locations, spatial relationships, assets and props, actors, set dressing, lights and camera rigs; source revisions remain immutable for any already captured take. A screenplay is editable production intent, not an instruction that must overwrite historic takes.

## Distinct editorial objects

- **Scene/set revision:** 3D world state, cast and prop identities, material/lighting/environment state, coordinate systems and approved dependencies.
- **Script revision:** scene and character actions, dialogue, emotional beats, timing intentions and director's notes.
- **Performance revision:** what a given actor actually does, says and expresses along the common source clock, independent of camera framing.
- **Take:** an immutable production event binding exact script, scene, actor/performance, dialogue/audio and production settings at capture. The take gets a stable identity and production timestamps; subsequent creative changes create a new take or a deliberately new source revision, not a silent overwrite.
- **Camera coverage:** one or multiple camera interpretations of the same take. A new close-up, insert or reverse-angle must not reset dialogue or acting. If the performance changes, create a distinct take/performance revision.
- **Presentation:** render or editorial media derived from explicit take, camera and color/output revision. Renders may be regenerated at different fidelity without rewriting source.
- **Editorial decision:** source time ranges, transitions, chosen takes/angles, audio overlaps and director approvals, independent of media storage layout.

## Retakes and on-the-fly direction

A filmmaker can modify script lines, actor direction, facial/body delivery, camera, props or lighting. The revision planner must identify the difference between (a) camera-only re-coverage, (b) new performance/take, (c) scene/set revision requiring a new production source, and (d) new edit using existing takes. Preserve all old take revisions and their indexed results. Verify props and actor positions persist across any camera-only changes. When two takes are combined, editorial continuity is an explicit review of gaze, posture, breath, hand/prop positions, dialogue and matching action; no fraudulent continuity claim.

## Dailies: durable indexed production record

Provide a creator-friendly **daily folder** view grouped by local production date (with persisted production timezone), then project → scene → shot/coverage → take. Record immutable take ID, take number, capture UTC and displayed local date, script/scene/performance revision hashes, camera coverage IDs, timecode, render and audio media references, creator notes, quality/status flags, selected/circled take and independent verification status.

Suggested human-facing layout:
```
Dailies/
  2026-11-04/
    Scene_012/
      Take_001/
        take_manifest.json
        camera_A/
        camera_B/
        audio/
      Take_002/
        take_manifest.json
        camera_A/
        audio/
```
This is a **view/export convention**, not the authoritative identity. FilmIndex remains the immutable identity store. Never derive database identity from directory names, trust an unverified folder, or force creation of duplicate full-resolution media on disk for every camera. Use hashes and media references, with exported files only when requested or required by editing systems. Date is metadata; midnight/date changes may not move already indexed takes into a different day.

## Resource, crash and restart rules

Save take manifests, media/chunk receipts, approvals and revision dependencies durably; incomplete takes are distinctly labeled interrupted, not reused as approved productions. Native workers load only required scene/shots/frames, preserve temporal state at chunk boundaries and obey existing resource guard. Render retries never silently generate a different performance. Camera-only changes invalidate only camera-dependent renders; new take or revised source invalidates its own downstream artifacts, not earlier approved takes.

## Acceptance tests

1. Capture two performances of a single scripted scene; preserve Take 1 after changed line/direction and creation of Take 2.
2. Change from wide to close-up after capturing Take 1; freeze original actor/dialogue/performance identity and verify coverage is derived from the same source.
3. Change one prop or lighting revision for a new take, then reopen and prove previous take has unchanged set data.
4. Store multiple camera angles per take; edit shots from different takes and check matching action/continuity as necessary.
5. Reopen FilmIndex and dailies after interrupted render and process restart; verify statuses, media hashes and indexed dates.
6. Search and select take by date/scene/actor/notes without making the filesystem layout an untrusted source of truth.
7. Human review of performance quality, emotion, lips, neck/body and lighting remains separate from structural verification.

## Delivery sequence

Continue B14 edited professional picture and native resource/safety gates. Introduce AUDIO-01 timeline/sample synchronization and PERF-01 camera-independent acting, then durable DAILIES-01 index/UI and cross-take conform. These are production-engineering goals rather than a request to choose a new video generation model.
