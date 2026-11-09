# USD-FILM-01O / 01P — Complete Restart-Resumable Camera Rolls and Edited Film

## Blocker / filmmaking acceptance contract

One director-authorized original **30-second actor performance** must be
recorded from every selected camera in the original bank; 9-camera
standard is an optional preset, not a maximum. All views see the same
USD source state at the same original Film Time. Their geometries, camera
lens/direction, wall occlusion and actual native rendered pixels are
checked. The accepted nine-camera example requires **6,480 original
Blender/Cycles PNG frames** from **9×720 frames at 24fps**. Original
audio belongs to the shared performance, never independently replicated
per camera. A contiguous **720-frame edited 30-second movie** must be
assembled and independently decoded together with original 48k PCM.

## 01O — What is implemented in source

- `backend/nvp_usd_film01o_original_camera_roll_source.py` builds one
  source-verified immutable *derived* 720-frame native USD source
  stage from the original world Take plus an exact 01M camera bank
  revision. Evaluates all canonical source ActorIDs, transform/rig timed
  attributes and native cameras; creates real Blender-compatible
  24fps USD time samples and checks native pose parity at selected
  cut-boundary frames. Original FilmIndex Take and assets untouched.
- `tools/nvp_usd_film01o_blender_camera_chunk.py` is a fixed first-party
  native Blender 5.2 Cycles worker with eight original frames per
  bounded job. One USD import per chunk, source actor/camera transform
  parity at every frame, native lens checks and shot-local primary-ray
  wall masks. It emits eight real PNGs and a source-linked native audit
  only if Cycles actually rendered them; no pseudo/mock images.
- `backend/nvp_usd_film01o_recoverable_camera_roll_host.py` uses the
  existing pinned `BlenderWorkerSupervisor`: exact director
  authorization per new chunk attempt, verified source SHA, OS-contained
  worker, 600s deadline, 8GiB memory budget, SQLite job journal,
  cancellation, independent output/PNG/Film Time re-verification.
  Each roll is 90×8=720 source frames, each standard 9-camera setup
  requires **810 bounded jobs**. No single 6,480-frame unkillable process.
- Restart behavior: a prior `SUCCEEDED` job is independently verified
  (script/input SHA, journal and each output) and **reused**, never
  automatically re-rendered. A `RUNNING`, `INTERRUPTED`,
  `CANCELLED`, `TIMED_OUT` or `FAILED` job must not be replayed.
  New attempts use new unique job IDs, fresh director authorization and
  host-provided independent OS custody proof for previous attempts.
  The code does not equate SQLite reconciliation with terminating a
  detached native process. Any missing kernel/orphan protection blocks
  reissue. `progress`/one-step `run_next` report bounded continuation.
- A complete roll can only be gathered after all 90 source-specific
  chunks have succeeded and been independently reverified; every
  individual PNG/receipt is checked again, then persisted with source
  Take/ActorID/camera and original supervisor job references.

## 01P — What is implemented in source

- `backend/nvp_usd_film01p_source_multicam_film_conform.py` validates
  the exact original camera bank and **all its full 720-frame source
  rolls**, independently revalidates 90 completed native supervisor
  chunk jobs per camera, decodes each PNG and checks every source actor
  state/tick against the original 01O source manifest.
- Director EDL supports flexible camera selection (standard nine
  cameras or any 1–96 cameras). Each cut must preserve exact shared
  source time, no actor retake/reposition, no gap or overlap, and the
  720-frame resulting edited sequence is assembled with FFmpeg FFV1.
  FFprobe independently decodes all 720 pictures at 24fps.
- Original audio is read from verified 01E FilmIndex PCM event chunks,
  extracted and independently essence-verified via 01F original source
  WAV stem adapter. Audio events use original Film Time and authored
  timeline gains. One 30s mono 48k PCM16 technical mix is generated;
  its exact 1,440,000 PCM samples and original source identities are
  checked. After mux to an actual Matroska film, FFmpeg independently
  decodes the audio and compares its PCM SHA with the mix essence.
  No TTS, stock audio, AI performance or extra camera soundtracks.
- Output receipt carries all original camera-roll SHAs, director EDL,
  source performance Take/world SHAs, original source audio event
  provenance, source PCM essence and independently decoded film SHA.
  **Director creative approval and cinema quality remain FALSE.**
- Existing 01I test performance now includes one original 30-second
  48k PCM test recording and 01O/01P unit/native tests for real USD
  source, source WAV mix, arbitrary EDL, restart re-verification and
  permission refusal. Official Blender 5.2.3/native Windows/Linux
  CI workflow added to run 8 real Cycles frames, not 6,480.

## Acceptance status and next operations

**IMPLEMENTED, NOT YET NATIVE ACCEPTED.** Latest 01I/01L/01M/01N
native jobs were still queued/pending when inspected; there were no
finished Blender logs/media to diagnose. Source and workflow commits
never count as 01O/01P native pass or an actual short film.

Required to close:
1. Inspect actual exact-head 01I, 01L, 01M, 01N, 01O native OS job logs
   and original media. Repair concrete failures, then re-run exact SHA.
2. Inspect and independently verify 01O's real eight-frame smoke and
   restart replay/refusal tests before dispatching the full workload.
3. Execute and journal all selected native camera rolls in the actual
   host, across restarts; quantify real CPU/GPU, storage, throughput,
   camera-occluder and exposure behavior. Keep failures and
   unsupported orphan cleanup explicit.
4. Conform actual 720-frame edited film plus original 48k PCM through
   01P; inspect audio/picture media, every camera boundary, actor
   occlusions, staging, reflections, lighting, angles and cinema pacing.
5. Director confirms the produced film; only then close multicamera
   film acceptance and unblock longer-scene tests. Other USD-FILM
   00–10 source/visual/physics/MaterialX/quality gates stay separate.

Longer-form practical workflow should render only the scene's selected
camera coverage. Cameras can be unlimited in shot grammar; the current
per-bank 96-camera resource budget is reviewed separately.
