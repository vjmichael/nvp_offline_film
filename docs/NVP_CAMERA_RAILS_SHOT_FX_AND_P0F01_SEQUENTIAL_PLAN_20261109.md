# NVP task-group order — F/G/H closeout, P0-F-01, and director camera rails / shot FX

**Decision:** 2026-11-09. **Status:** architecture register; CAM-FX-01–04 have authored source implementation, CAM-FX-05A has authored derived rail-camera USD staging and native regression source, and **no CAM-FX-05 Cycles moving-shot native acceptance is yet verified**.
**Authoritative:** `docs/NVP_DATA_ALL_TASK_LEDGER.md`, `docs/NVP_MASTER_DESIGN.md`, `docs/NVP_USD_FILM_WORLD_FULL_INTEGRATION_MASTERPLAN.md`.

## 2026-11-09 — actual native results and current engineering handoff

- 02M-F/G/H grouped run [42650335958](https://github.com/vjmichael/nvp_offline_film/actions/runs/42650335958) **completed 6/6 FAILED**, revealing strict USD prim-token regex overescape, a missing source fixture, undefined JS edit identity, and too-early debounced preview assertion. Those defects were repaired on the active CAM branch, but repaired native results have not been collected.
- P0-F-01 installed/model group [42664870777](https://github.com/vjmichael/nvp_offline_film/actions/runs/42664870777) **completed 4/4 FAILED**, revealing WO6 shutdown Python indentation, a missing React fixture host cancellation method, and the deleted Q4_K_M GGUF filename at the current hosted model revision. Fixes preserve the OS-consent boundary; no GGUF, installer or production model proof is accepted yet.
- CAM-FX-05A: `backend/nvp_cam_fx05_verified_shot_source.py` composes a genuinely approved CAM-FX-02 rail into an independently reopened, disposable derived 02M-H/01E USD snapshot at the *original* binding tick. The separate virtual camera is baked for rendering only; source 01D camera fields, actor mesh/poses and original PCM remain unchanged. The paired `tests/test_nvp_cam_fx05_staged_rail_source.py` covers two approved rail revisions, eight technique contracts and hostile admission. These are staged native source tests, **not executed real Blender frames**.
- CAM-FX-05B next: first-party separately verified rail-aware Blender/Cycles worker, exact fresh OS grant, dual worker receipt/readback, measurable difference in actual camera-rendered pixels, shot continuity over original Film Time, and installed view/artist direction. Only after that can 01Q/01S/01T consume the rail in selected-view film. Do not run small CI jobs for each edit; the grouped gate follows the completed implementation batch. 02M-H render gate [42671262108](https://github.com/vjmichael/nvp_offline_film/actions/runs/42671262108) was queued when checked.

## 0. Current acceptance: USD-FILM-02M-F/G/H

- Single **task-group** run: https://github.com/vjmichael/nvp_offline_film/actions/runs/42650335958 at exact SHA `389960c6a53cbf7c3842e5cfd972ff2d9a45f01a`.
- Target: Linux/Windows Python 3.11/3.13 native pxr/SQLite + installed-host bridge method tests, and Linux Vite/React build and DOM tests. Disclose source-only, fake-provider and simulated-OS gates as such.
- At last inspection, **six jobs were queued**; no OS job log existed to inspect. A queued job is neither passed nor failed. Do not change the CI-watched staging head or spawn parallel duplicate runs while these six remain queued.
- Once real logs are available: identify specific failing job/step, repair only observed defects on a new bounded iteration, then run **one replacement grouped batch** at the repaired exact head. Cancel earlier group run only if provably superseded. Attach OS job/artifact IDs, source SHA, suite/test counts and failure fixes to the ledger.
- Exit condition for native gate: all scoped group jobs completed successfully and real source reopen, model-attempt recovery and immutable shot binding checks pass. This does **not** satisfy physical installed WebView2 or genuine model GGUF acceptance.

## 1. P0-F-01 — original OpenUSD world editor, installed workflow [next group]

Finish the existing `ModularWorldDirector` and `TrustedDesktopWO5/WO6Bridge` rather than building a separate editor:

1. Real installed Windows catalog -> director proposal -> original USD source preview -> diff -> hide/place/remove -> undo/discard -> reopen, including two independent app processes and user-owned SQLite project continuity.
2. Actual installed local GGUF provider list -> bounded director intent -> untrusted strict JSON -> source validation -> persisted model receipt/draft; handle provider timeout, malformed result, source revision changes, app stop and restart. Provider self-report is **not** proof of model weights.
3. Keep GUI interactive during generation; host-owned bounded status and cancellation, no browser model URL, worker command or native approval. Use explicit OS confirmation for exact district publish. Prove denial, stale SHA, double-click, torn-save and interrupted publish reconciliation.
4. Physical NSIS install/relaunch/reinstall/uninstall with retained film sources, offline React assets and pywebview native dialogs. Distinguish GitHub-hosted test VM from owner-tested physical Windows machine.
5. Acceptance group once: Windows native source/React UI and installed executable smoke; Linux native parity; actual user-driven WebView2 interactions where runner cannot provide trustworthy physical evidence. Save installer SHA, log and reproducible defects. Gate only at end.

**Do not expand P0-F-01 into a renderer, Blender mini-app, general text-to-3D generator or unrelated tools.**

## 2. CAM-FX — director-modifiable *digital camera rails* and advanced shot technique language [new work groups]

### CAM-FX-01: canonical shot rail + camera technique source

- A **digital rail** is an immutable, bounded, revisioned **virtual 3D trajectory**, *not* a physically modeled track. Its source links to one exact `FilmIndex` project, frozen original 01E world Take / ActorID performance, 01D or 01M camera source and 01Q source-time shot/edit interval. Shared original Take time is integer **Film Time ticks**, not independent repeated performances or frame-as-authority.
- Rail assets have stable ID/revision/SHA, camera rig identity, reference-space (world or a pin-locked original source anchor), units/meters/Z-up, source clock interval, strict ordered control nodes, tangent/interpolation type, per-node ease/hold, boundary conditions, view orientation target/roll and lens/focus keyframes. Preserve origin/rebase transforms. Strictly bound node count/coordinate/speed/acceleration to avoid memory blowups and nonfinite matrices. Do not silently move the actor to fit a shot.
- Camera rails do **not** alter underlying world/ActorID USD source geometry, performance curves or original PCM. A user can change a shot/rail without reshooting or rewriting the frozen source.
- Basic native interpolation: stationary/linear/cubic Hermite or Catmull–Rom (choose and document exact parameterization), with deterministic evaluation at exact original Film Time. Choose arc-length or explicit timing mode for velocity/acceleration control. Native orientation can be look-at with up-vector/roll safeguard or explicit quaternion curve with bounded easing; prevent gimbal flip and NaNs.
- Lens/exposure controls: physical focal length, sensor/aperture, filmback, focus distance/target, f-stop/DOF, controlled zoom and rack focus. Render-dependent effects such as motion blur, anamorphic/distortion, chromatic aberration and handheld shake are **separate** reviewed profiles and should not be claimed from source-only USD transforms.

### CAM-FX-02: author and reopen stronger OpenUSD director layer

- Use first-party `UsdGeom.Camera`, `UsdGeom.Xform` and `UsdGeom.Xformable` time-sampled transform/Lens attributes as appropriate, authored ONLY on a distinct director-owned stronger shot/preview layer. Compose source camera + rail path + director shot opinions; bake exact-time rig matrices into time samples for the actual Blender/Cycles view. Avoid editing authoritative 01D/01E source layers or actor Takes.
- Native readback must reproduce the expected camera matrix, lens and focus at samples and intermediate ticks, with repeatable SHA and explicit layer-authority provenance.
- Camera rigs are **non-colliding** unless the director opts into a separate clearance constraint. Test collision/visibility rays against actual approved district 3D walls/openings. Preserve director override for intentional occlusion with an explicit warning rather than silently overriding creative intent.
- Director edits create new immutable rail/shot revisions with undo/diff/discard; stale revisions and unapproved source mutations fail closed. Any control points moved by mouse/keyboard must validate against first-party native scene coordinates.

### CAM-FX-03: director UI, previews and source/film-time integration

- Timeline-aware rail gizmos: display path, handles, tangents, easing/hold zones, keyframes, target/framing guides, safe areas, horizon/roll, optical metadata and camera presets. Keyboard/numeric editing, insert/move/delete/retime nodes, undo/redo, before/after, inactive rails, and source-time scrub.
- Low-fi readback uses actual source-pinned USD scene; hi-fi renders ONLY selected frames/shot viewpoints under the existing 01Q/01S/01T worker/resource budgets. GUI must not load an entire long film world to adjust one path.
- Shot techniques (typed built-in library, **not claimed implemented**):
  - Framings: establishing/extreme-wide/wide/full/medium/medium-close/close/extreme-close, insert/detail, two-shot/group, profile, over-the-shoulder, POV/reaction.
  - Rail moves: dolly in/out, push/pull, truck/track lateral, pedestal up/down, crane/jib/boom, arc/orbit, reveal/occlusion pass, follow/lead, tilt, pan and combined compound trajectories.
  - Lens/time/feel: zoom in/out, **dolly zoom**, rack focus, focus track, whip pan/tilt (preview/admission bounds), Dutch roll, controlled handheld/sway, snap/punch-in, timed hold and ease, slow/fast move at same underlying performance time.
  - Filmmaker can create arbitrary custom rail/shot technique by combining bounded motion, lens, focus and framing, not only picking a stock style.
- Do not conflate a static technique tag with passing native shot geometry validation. Depth of field, blur, occlusion, perspective continuity and shot rhythm need render/view evidence.

### CAM-FX-04: AI suggestion vs human direction

- AI may propose one typed technique preset, control points/timing/lens/focus and target **from verified native source scene context**, never arbitrary USD paths, shell code, scripts or model endpoint.
- AI recommendations remain unapproved reversible drafts; first-party host recomputes constraints, exact ActorID/camera/source SHA and camera/subject visibility. Director can change any control point/shot/lens, compare revisions and explicitly approve the exact final source proposal with the native OS dialog. No inferred grant from a model completion.
- Default AI suggestions may include multiple cinematic styles and narrative framing rationale, but must expose user-editable numeric shot parameters and allow rejecting every suggestion.

### CAM-FX-05: source and render acceptance

- Native Linux/Windows exact-head tests: at least static, dolly, arc, crane, pan+tilt, OTS, rack-focus and dolly-zoom rail variants sampled at several exact time ticks and between nodes. Test malformed controls, time rebase, rapid easing, target disappearance, project isolation, actor preservation, stale edit, crash and restart.
- Prove two distinct user-edited rail revisions produce distinct **real** camera trajectories over **identical** immutable ActorID/PCM source (zero rewrites).
- Independently reopen actual USD layer and Blender/Cycles output for moving camera, subject framing, realistic blur/DOF and wall/window occlusion; verify source/camera/rail hashes, timestamp continuity, bounded resources and render dispatch authorization. Physical Windows camera-gizmo use required separately.
- Package a real 10–30s multiphase camera movement in a selected-view editorial film, require human shot-quality review, but do not force nine redundant full-length camera rolls.

## 3. Sequential order of execution

| Order | Work group | Gate before next dependency |
|---|---|---|
| 0 | F/G/H exact-head OS acceptance | Complete real jobs; fix observed failures with one replacement group batch when needed |
| 1 | **P0-F-01** installed world editor / model-to-draft / NSIS | Verified installed source-edit, recovery and real model; no auto-grant |
| 2 | 02M-H to real 01D/01E shot frame quality | Genuine world/actor/camera projected occlusion and source-synced Cycles pixels |
| 3 | CAM-FX-01 + CAM-FX-02 | Native deterministic rail and stronger USD layer/ActorID source integrity |
| 4 | CAM-FX-03 + CAM-FX-04 | Installed director controls, typed AI suggestions and explicit approval |
| 5 | CAM-FX-05 + 01Q/01S/01T | Native rail render plus one genuinely finished 720-frame/30-second selected-view picture/48k PCM film |
| 6 | 02M/D/E world richness + FILM03 actors, expressive voice and body | Verified source and human-reviewed original performances |
| 7 | DA/DATA audio+editing, WO2–WO5 color/cinema finishing | Technical original-source decode, color/sound and DCP parity |
| 8 | HSURF-00 photoreal human surface program | After essential USD-FILM family as already directed |
| 9 | Sustained long-form+30-min film/feature and Lu workspace later | Separate system and filmmaker acceptance |

Acceptance runs should remain **one group-end batch**, not per commit; no fictional acceptance from queued CI, model-produced metadata or source-only geometry.

## CAM-FX 01–04 consolidated native reconciliation (2026-11-09)

Camera branches `nvp/cam-fx01-02-typed-rails-usd-layers-20261109`, `nvp/cam-fx03-04-gizmos-guidance-drafts-ai-20261109` and `nvp/cam-fx05b-protected-rail-cycles-20261109` are **already ancestors** of the passing 02M-H foundation (`120cc1c6aed737e006755e7ed9af3a6a484da2fd`); no cherry-pick or parallel code fork is needed. The successful 02M-H exact native Blender+Windows group is [42732782191](https://github.com/vjmichael/nvp_offline_film/actions/runs/42732782191). The old CAM-FX-03/04 run [42704474887](https://github.com/vjmichael/nvp_offline_film/actions/runs/42704474887) predates those repairs and failed on an unclosed parenthesis in `backend/nvp_cam_fx05_verified_shot_source.py` (fixed in the foundation), stale jsdom pointer-event fields, immediate clicks before async camera-bank selection, and a source queue Conform button incorrectly expected before it could legally exist. Tests were corrected to deliver a stable pointer ID, wait for source-ready controls, and assert conform is absent until a durable approved queue exists. No native source, permission boundary, film-tick identity or director approval was weakened. Windows installed acceptance is ported from passing P0-F-01 and 02M-H: verified NSIS x86 compiler, bounded process stages, two independent installed app launches and SQLite source recovery, actual native WebView2 3D gizmo/durable/AI method controls, exact SHA-preserving uninstall and always-upload diagnostic artifacts. The installed GUI explicitly returns to the real Direct the data tab before source camera-control assertions, as proved necessary by 02M-H. One exact-head grouped native CAM-FX-01–04 gate remains to be executed; no pass is claimed in advance.

## CAM-FX-01/04 first exact native group failures and sourced repairs

First task-group run [42736149486](https://github.com/vjmichael/nvp_offline_film/actions/runs/42736149486), exact SHA `ebb002064816c05d350cdca984e05d0d3e90b0b3`, **failed** across six jobs: Python source fixture native guidance used FilmIndex's letter-leading object-ID grammar for exact StoryBible UUID ActorIDs, rejecting legitimate 32-hex IDs beginning with a digit. The same test referenced nonexistent nested fixture `self.source.shots` rather than authoritative original `self.source.source.ids` IDs. The Windows/Linux failures confirm these are genuine, not CI compiler errors. Correct using the already-accepted 02M-H `_story_actor_id` source validator without broadening FilmIndex object identifiers; preserve exact actor PCM source identity. Four of five React files passed, 22/24 test cases; two CAM-FX advanced tests failed because the `createSourceDraft` helper clicked the camera preset before the asynchronous selected camera had enabled it. The other test sites awaited source readiness, but this helper did not. Wait for the real button to enable before clicking; no UI bypass or fake model approval. Rerun one full grouped CAM-FX 01–04 gate at the next final source SHA, with actual Windows NSIS/WebView2/source recovery outcome. CAM-FX-05 real Cycles remains OPEN until its own grouped render acceptance.

## CAM-FX group second native acceptance triage (2026-11-09)

The second [grouped run 42736695954](https://github.com/vjmichael/nvp_offline_film/actions/runs/42736695954), SHA `5ff640fe25b8950cfcfecd607365bc1782d1d3e1`, confirmed one code integration error: the imported `_story_actor_id` helper was not exported by the actual 02M-H world Take module on this branch. Restore the proven strict lowercase 32-hex StoryBible validator inline in CAM-FX-03 guidance; continue verifying membership in the immutable original actor source. React improved to 23/24 tests, with only a stale test text expectation: UI now correctly says `Native source-verified local model suggestion saved as editable UNAPPROVED rail version`, not the older `Local model suggestion ...` wording. Update the assertion; do not treat source-verified model suggestions as approval. Recheck complete grouped native and installed evidence after the current runner finishes.

## CAM-FX native third group — corrected source-object identity

On exact-head [group #42736974706](https://github.com/vjmichael/nvp_offline_film/actions/runs/42736974706), SHA `30033c469a6bd16d9aab626f4dc773cddd03d08b`, React 24/24 passed. Python native guidance correctly admitted exact historical 32-hex ActorID and verified 02M-H approved district geometry; its final original-hash assertion failed because the corrected nested fixture lookup used `OriginalTwoShotWorldTakeSource.ids` (IDs of newly COMPOSED 01E world Takes) against `original_take_shas` from the frozen original SCENE Takes. Verified `OriginalTwoShotWorldTakeSource.shots` contains their actual `take_id` keys; this is the authoritative object list for those two previously recorded source hashes. Match original scene take IDs and hashes, preserving strict equality, not rewriting any source. This completes the source fixture reconciliation. Wait for full current grouped conclusion before triggering an updated exact-head native gate.

## Verified CAM-FX-02 native OpenUSD missing-prim guard

Fourth exact-head [group #42737538489](https://github.com/vjmichael/nvp_offline_film/actions/runs/42737538489), source SHA `f25b5f26994a4753228be049ddcf159caccf1459`, passed React 24/24. Python native CAM-FX-03 real ActorID/source/PCM suite now traverses real authored geometry correctly. A later CAM-FX-01/02 native source test found the previously hidden OpenUSD C++ runtime error `RuntimeError: Accessed invalid null prim` at `backend/nvp_cam_fx02_usd_camera_layer.py:228`, `stage.GetPrimAtPath(CAMERA_ROOT).IsDefined()`. When the original world does not author the stronger director rig namespace, USD returns an invalid prim. Check prim truthiness **before** querying IsDefined, while still raising if a genuinely authored namespace exists. No new camera, actor, original Take or PCM authority is introduced. Rerun the complete Windows/Linux actor, rail and installed source group at final SHA, and verify real OpenUSD session-layer camera readback.

## CAM-FX-05 staging USD null-prim diagnostic (2026-11-09)

Fifth exact-head [group #42738066959](https://github.com/vjmichael/nvp_offline_film/actions/runs/42738066959), tested SHA `1fd25530a234fa1b6813626687f4a13239d386e5`, passed React and progressed beyond the repaired CAM-FX-02 null-prim guard. Windows/Linux staged CAM-FX-05 test then demonstrated `RuntimeError: Accessed invalid null prim` in `backend/nvp_cam_fx05_verified_shot_source.py:115`: `src.GetPrimAtPath("/World/NVPDirectorRails").IsDefined()`. The original source world intentionally omits the stronger director rig namespace. Guard null prim truthiness before `IsDefined()`, retaining collision rejection for genuinely authored source rig. This does not alter film actor/camera/PCM or grant worker authority. The separate real Cycles acceptance remains OPEN.
