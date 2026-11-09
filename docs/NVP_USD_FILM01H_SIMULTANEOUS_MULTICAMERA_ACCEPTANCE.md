# USD-FILM-01H — Synchronized multicamera filmmaking acceptance

## Director's instruction

The three cameras film the **same original 30-second performance**.
Unlike the preceding three-shot-only rendering test, all three cameras
must cover every source frame. The editing decision is independent of the
performance. NVP can then cut between wide, side and detail at any original
Film Time without making actors repeat the event.

This is *time-synchronized multicamera coverage*, not necessarily three
Blender GPU processes simultaneously. Renderer workers may serialize
camera views for resource safety and still preserve exact timing.

## Authoritative source/performance design

- One original persistent USD world SHA.
- One original actor-performance identity independent of camera (a
  **new shared performance source adapter is required** because current 01E
  world Digital Takes bind camera shots to frozen Takes).
- Three different original UsdGeom.Camera prims and camera-shot SHAs.
- Each camera evaluates original ticks i * 7,056,000,000 / 24,
  i=0..719. No altered actor state or rerun on angle change.
- Each native Cycles frame receipt must bind the world SHA, shared
  performance SHA, camera shot SHA/prim, original exact tick, PNG SHA,
  and a source-evaluated canonical ActorID state digest. A difference
  between angles at any tick fails closed.
- The original 48k PCM sources are captured **once for the performance**,
  not three separate soundtracks. Preserve their original event ticks.

## Render and edit targets

- All-camera source coverage: 3 x 720 = **2160 distinct rendered pictures**.
- Establishing: wide camera frames 0..239.
- Action: side camera frames 240..479. Read geometry / occlusion for box
  behind donut and sphere through donut hole.
- Reaction/detail: detail camera frames 480..719.
- Final picture: exactly 720 decodable frames at 24fps / 30 seconds.
- Retain the three original camera rolls to allow editorial re-cuts and
  continuity review. A three-view synchronized comparison/contact sheet
  is an additional visual acceptance artifact.
- Native visual inspection must verify same positions, actions, timings,
  lighting behavior, reflections, believable camera framing and screen
  direction across cut boundaries. Recurring geometry / source actor
  hashes are a necessary but insufficient visual quality test.

## Implementation status and open gates

Implemented on 01F branch:
`backend/nvp_usd_film01h_multicam.py` and
`tests/test_nvp_usd_film01h_multicam.py`, plus Windows/Linux contract CI.
The verifier checks all 2160 source receipts and requires identical
per-tick actor-state hashes; editor selects three 240-frame windows from
full-length camera rolls and can invoke the existing native FFmpeg/FFprobe
picture conform worker to produce a silent workprint.

**Not yet implemented/accepted:** real 01E source-independent shared actor
performance adapter; approved Blender worker automatically rendering all
2160 source-evaluated native camera frames with authoritative actor-state
digests; sound mix; actual native moving-image artifact; human picture and
performance review. Unit test fixtures intentionally contain synthetic
non-image payloads and claimed-positive receipts strictly to exercise
the validator; they are NOT Blender production evidence and no native
film acceptance may be based on these synthetic tests.

The existing 01F two-frame proof and 01G three-shot conform do not satisfy
this multicamera film acceptance without these missing native steps.
HSURF-00 stays after USD-FILM family completion.
