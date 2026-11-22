# NVP Digital Film Package, Take, Presentation and Editing Contract

**Document ID:** NVP-DATA-SPEC-001  
**Revision:** 0.1 — November 3, 2026  
**Status:** Proposed engineering baseline [B/D]. **Not implemented and not accepted by code tests.**  
**Decision:** [Data-First Filmmaking ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md)  
**System authority:** [NVP MASTER DESIGN](NVP_MASTER_DESIGN.md)

> **DATA-TIME-01 creator amendment (2026-11-05):** This November 3 document initially described a Digital Take in terms of *frame/sample time domain* and illustrative `duration_frames`/FPS. Those fields are now **presentation/export metadata, not the fundamental authored timeline**. The authoritative world/performance/take source uses an exact time-addressed stream of semantic events and sparse curves, with immutable FilmIndex revision/hash references; specific picture/audio samples are derived at a selected delivery/backend boundary. Historic manifests retain their original format and interpretation; migrate them explicitly, never retroactively reinterpret previously approved frames. [Read the governing temporal ledger design](NVP_DATA_TIME01_EVENTS_NOT_FRAMES.md). Implementation and whole-pipeline migration remain open to native acceptance.

## Purpose

NVP should store the **information from which film can be captured and produced**, not treat any generated video clip as the authoritative scene. A living Film World produces immutable Take Packages. Each take produces multiple derived Presentation Packages. An editor selects presentation/audio versions into a finished 2D movie. Every source and derivative remains indexed together and can be traced, branched and partially regenerated.

## Identity and directed relationships

| Record | Stable identity | Revision rule | Required references |
| --- | --- | --- | --- |
| FilmProject | project_id | New accepted world/edit revisions | Creator scope, format, source root |
| WorldRevision | world_revision_id | Immutable after approval | Scenes, script, identities, assets, style, world facts |
| SceneRevision | scene_id + scene_revision | Immutable accepted scene state | World, objects, props, actors, anchors and constraints |
| AssetRevision | asset_id + content_sha256 | Immutable source bytes | Source geometry, proxy/high LOD representations, rig, licenses |
| ActorIdentity | actor_id | Persistent identity, versioned look/voice | Rig, appearance, voice references and permissions |
| StyleProfileRevision | style_id + revision | Immutable accepted style | Lighting/color/material/cadence/art-direction references |
| PerformanceRevision | performance_id + revision | Immutable approved timed motion | Actor ID, rig, pose/gaze/gesture, emotion, dialogue, contacts |
| DigitalTake | take_id + capture_sha256 | **Immutable** frozen record | Scene/world revision, shot/time, actors, camera, audio, source approvals |
| ProductionJob | job_id | Append-only state and effect receipts | Source take, target presentation/scope, backend and resources |
| PresentationRevision | presentation_id + revision | Immutable after completed approval | Source take, render/voice jobs, style, generated media, QC |
| EditorialRevision | edit_id + revision | Immutable approved timeline revision | Presentation shot ranges, sync, audio, transitions |
| FilmMaster | master_id + media_sha256 | Immutable mastered output | Exact edit revision, audio mix, encoder/version, output receipt |

An internal typed index must prevent dangling references, wrong-project dependencies, ambiguous “latest” lookups inside frozen packages and unapproved generated content becoming source truth.

### Relation graph

    FILM WORLD (editable, versioned)
       |-- screenplay, story/canon
       |-- scenes, anchors, physical assets, actor identities, styles
       |-- performances, cameras, lights, sound
       +--> frozen scene+performance+capture revision
                    |
              DIGITAL TAKE 04
                 |       |
          render job    voice/sound job
                 |       |
                 +---+---+
                     |
                 PRESENTATION A  (conventional photo-noir)
                 PRESENTATION B  (AI-enhanced photo-noir)
                 PRESENTATION C  (anime)
                       |
                EDITORIAL TIMELINE
                       |
                  FINAL 2D FILM
               (video + mixed audio)

A take does not need to copy all scene/asset source bytes. It **must** freeze a manifest of exact, resolved, durable immutable references and record which assets are unavailable. A source manifest that points only to “current actor” or a mutable file path is not acceptable as an approved capture.

## Digital Take Package minimum

The capture is **not the low-fi viewport image**. It is approved, timed production state sufficient to reconstitute the scene and to direct downstream render/voice models.

- Project/film, scene, source WorldRevision, creator approval and asset/character/rights digests.
- Frame/sample time domain: rational FPS, duration, frame origin/inclusive policy, audio sample rate, synchronizing source timebase.
- Shot/camera: stable shot ID, sensor/lens/focus/exposure data, precise transform/track, cut and motion timecodes, camera/occlusion exceptions.
- Cast: actor IDs, representation/rig maps, per-frame or keyed motion, expressions, gaze, gestures, contacts, props, clothing, continuity state and approvals.
- Dialogue/sound: approved script/line IDs, speaker ID, recorded or intended vocal performance, microphone context, timing/sample references, silence and room ambience.
- Environment: scene transforms, light/prop/collider state and any timed world events relevant to capture.
- Style binding: approved style profile/version and references, with explicit style variants permitted for finishing.
- Provenance: content digest, track digests, upstream revision manifest, approvals and exceptions, status of missing/incomplete capture input.

Capture is **immutable after commit**. A new gesture, camera, wardrobe or line creates a new version or branch of the relevant upstream data and a new capture/derived package where required. The original remains reviewable.

### Illustrative manifest (not a deployed schema)

    schema: nvp.digital_take.v0.1
    film_id: film_001
    scene_id: scene_012
    scene_revision: 9
    world_revision: 24
    take_id: take_004
    capture_sha256: [actual SHA256 after canonical serialization]
    duration_frames: 120
    time: {fps_numerator: 24, fps_denominator: 1, first_frame: 1, audio_hz: 48000}
    approved_references:
      scene_manifest_sha: [immutable digest]
      character_01_asset_sha: [immutable digest]
      style_profile_id: style_noir@3
      performance_01_sha: [immutable digest]
      camera_track_sha: [immutable digest]
      dialogue_timing_sha: [immutable digest]
    active_shots: [shot_02]
    approval: {status: approved, receipt_sha256: [actual receipt]}

Square-bracket fields here are **explanatory placeholders**, not valid checksums. The exact canonical JSON/Protobuf serialization, exchange format, digital-signature options and host IPC codec will be decided in a tested schema implementation. Never mislabel this design sketch as executable or validated.

## How the digital script is produced

The Digital Take is vendor-independent. A **Presentation Compiler** makes a selected backend-specific job plan from approved take data, not by asking a video model to infer the scene from a loose prompt.

**Video backend inputs when supported:** reference images / character identity, scene stills, camera paths, timecoded pose tracks, depth/normal maps, object-ID masks, lighting/style guidance, approved motion, actor dialogue/audio and planned shot durations.

**Voice backend inputs when supported:** script line/phoneme details, character voice reference with rights and consent, vocal intention, emotion, accent/language, timing, reference recording and per-line revision.

**Conventional renderer inputs:** exact Blender/other 3D scene source, detailed asset LOD, materials, lights, animation, camera and frame timing.

The adapter MUST declare real capabilities (camera trajectory, depth/pose masks, reference identity, speech-to-speech, voice cloning, conditioning length, interpolation, token/chunk limits, frame resolution, hardware constraints). If a requested critical input cannot be enforced, the UI MUST say so and refuse or ask for a reviewed approximation. A text prompt alone cannot guarantee camera, spatial or identity preservation.

**Rendering mode labels:**

1. Source-directed deterministic render: source camera/pose/geometry are directly evaluated with conventional engines.
2. Conditioning-guided AI: model consumes supported control passes; model output may deviate and needs independent review.
3. Open creative generation: user intentionally authorizes visual invention, not a source-accurate continuity claim.

Persist job version, model/checkpoint or provider ID, installed digest if available, config, seed, control digests, output frame/video/audio hashes, timings, warnings, QC results and approval. **Do not promise bit-identical regeneration for nondeterministic systems**; preserve traceable inputs and actual produced outputs.

## Presentation package

A presentation can contain:
- Final or draft video segments / frame sequences for explicitly named shots and time ranges.
- Separate audio stems, spoken dialogue, timing/alignment, music and effects with usage rights.
- Render passes and control assets, including RGB, depth, normals, object/actor ID masks, poses, timecode and references.
- Style/model/engine settings, provider metadata, input snapshots, seed and exact source take hash.
- QA: identity/wardrobe/prop continuity, lipsync, correct camera path, video/frame sync and creator review status.
- Output digests, immutable receipts and any declared known drift or incompatibility.

**One take -> multiple presentations**, each preserving its own run context and visual style. The director can process an approved older take through a newly installed compatible model without refilming; full re-creation may be blocked by unavailable model assets or rights. Any AI-invented prop is presentation-only until explicitly authored into the world via a reviewed source edit.

## A single index and dependency graph

The logical storage implementation should separate small transactional metadata from heavyweight immutable blobs:

    projects(project_id, active_world_revision, settings_revision)
    source_objects(project_id, object_id, object_type)
    source_revisions(project_id, object_id, revision_id, manifest_sha, approval)
    asset_blobs(project_id, asset_id, revision_sha, blob_sha, license_scope)
    takes(project_id, take_id, capture_sha, scene_id, scene_revision, approval)
    presentations(project_id, presentation_id, take_id, job_id, style_rev, approval)
    timeline_revisions(project_id, edit_id, revision_id, timeline_sha)
    masters(project_id, master_id, edit_id, edit_revision, media_sha)
    lineage_edges(project_id, src_type, src_id, dst_type, dst_id, edge_kind, scope)
    jobs(project_id, job_id, status, input_sha, worker_lease, output_scope, result_sha)
    immutable_blobs(content_sha, bytes, storage_locator, verified)

Use **SQLite** for indexed references/transactions, a content-addressed store for large 3D and media files, versioned manifests and portable project archives with verified dependencies. Blobs may be shared/deduplicated, not copied per take. Model weights and source footage cannot be assumed redistributable merely because the project references them.

Useful typed edges: WORLD_OF_SCENE, CAPTURE_FROM_SCENE, ACTOR_IN_TAKE, PERFORMANCE_IN_TAKE, SHOT_CAMERA_TRACK, AUDIO_DERIVED_FROM_LINE, PRESENTATION_OF_TAKE, MODEL_JOB_FOR_PRESENTATION, EDIT_USES_PRESENTATION, MASTER_OF_EDIT.

A current source revision must not retroactively alter earlier lineage; frozen manifests bind to exact revision IDs and hashes. The editor must follow both **forward** and **backward** provenance links.

## Targeted revision, regeneration and review

On each requested change:

1. Determine the **authoritative layer** modified: world, take, presentation, edit or final master.
2. Create a new source revision, never overwrite an approved take. Identify changes to source geometry, actor look, prop position, motion, camera, lighting, dialogue, voice, style or model.
3. Traverse typed dependency edges using actor/shot/frame/audio interval scopes. Mark only dependent derivative versions *stale relative to the new source*; preserve historical approvals for their original inputs.
4. Compute **minimum correct regeneration groups**, accounting for backend temporal windows, required transition handles, lip sync and downstream composite/edit scope. Show costs and compatibility.
5. Queue model/renderer jobs against exact hashed inputs, with permission, provenance, measured RAM/VRAM budget, cancellation and restart receipts.
6. Independently check outputs where possible, compare with source and previous accepted presentation, then ask for director acceptance.
7. Save a new approved presentation/timeline revision and, when requested, export a newly mastered 2D film.

**Illustrative edits:**

| Change | Regenerate | Preserve |
| --- | --- | --- |
| Incorrect actor face in Shot 2 | Shot 2 visual presentation and affected control/reference passes | Source performance and unrelated shots/audio |
| Wrong emotional delivery in dialogue Line 98 | Voice line, alignment, dependent lip/visual and audio segments | World, camera, unrelated lines |
| New camera angle | Camera branch, camera-dependent passes, resulting presentation | Source performance and old camera/take |
| New actor gesture | Performance revision/new take + dependent visuals | Old take, set, unaffected captures |
| New visual style | New presentation from existing approved take | Original take and old style presentations |
| Move a prop | Updated source scene and precisely dependent captures/presentations | Other independent assets/scenes |

A shot-specific repair does **not** automatically require rebuilding the entire film. But models may require a longer contiguous time span; the UI must show the truthful execution scope and run continuity checks at boundaries.

## Low-spec mode and optional Lu workload management

**Filming mode:** lightweight 3D proxies, cheap shading, simplified but declared colliders, cached draft voices, visible camera/actor/control timelines, no mandatory high-poly rendering or video model residence.

**Production mode:** load the selected high-fidelity assets and generation models for specific shots or audio segments; render offscreen; save outputs; free/reuse workers. Hi-fi sources remain in versioned persistent storage and are loaded when necessary.

**Optional Lu:** Film Workspace job scheduler, per-turn authorization, worker containment, resource budgets, backend discovery/load/unload, cancellation and recovery. NVP retains ownership of source data and model-specific semantic inputs. Speech diffusion, video diffusion and Blender may each need distinct execution workers; llama.cpp cannot execute arbitrary media models.

**Standalone:** NVP retains a capability-limited local production executor if Lu is absent. External/cloud AI providers remain opt-in, permission-scoped and subject to rights/privacy terms. Directing a movie must not require a cloud account.

## Editor user experience and final 2D film

The editor presents a film timeline and played-back finished footage, with click-through to source scene, capture and job provenance. It offers **Compare versions**, **Re-render this shot**, **Regenerate this line**, **Adjust camera**, **Retake gesture**, **Change style**, **Open in low-fi scene**, **Revert**, and **Approve presentation** with real scope previews. Some changes need only a new presentation; other changes need a branched capture.

The final master is a **flat encoded 2D movie with mixed sound** (or other chosen delivery profile), but its master receipt points backward to the approved edit, the exact presentation and audio versions, their take captures and the original film-world revision. The creator can reopen the project later and produce another edit or render without pretending the original video is editable 3D.

## Independent acceptance and roadmap

**Nothing in this spec is claimed as tested simply because it has been documented.**

| Milestone | Real acceptance |
| --- | --- |
| NVP-DATA-01 | Typed index and immutable blobs persist after restart, verify hashes, reject stale/cross-project references |
| NVP-CAPTURE-01 | Proxy room, two characters and moving camera captured into an independently reopenable, frame-accurate immutable take |
| NVP-PIPE-01 | Same take yields two versioned presentation variants; one via conventional 3D, another via selected compatible alternative, with declared capabilities |
| NVP-AUDIO-01 | Actor/line/voice continuity and approved timed vocal performance, with correct selective lip-sync/audio dependencies |
| NVP-EDIT-01 | One shot/line/prop edit reruns only the valid dependent scope, leaves unrelated artifact SHA values intact, and supports comparison/rollback |
| NVP-RECOVERY-01 | Kill/restart worker during production; intact approved original, recoverable job ledger and no false final-output claims |
| NVP-MASTER-01 | Actual decodable playable 2D film with sound, source-indexed timeline and independent reopen of full project |

**First vertical slice:** a *complete* modest-quality short film, from authoritative world data through real capture to presentation and final playable movie, is more valuable than optimizing advanced detailed foot anatomy before this entire contract exists. The already verified Blender source/audit work remains a foundation, not a substitute for this end-to-end test.

## Known open implementation decisions

- Canonical schema serialization/version migrations: JSON, Protobuf IPC and optional USD interchange, with no semantic loss.
- Exact frame/subframe/audio-sample time representation and shot transition handles.
- Immutable store/archive layout, garbage collection while preserving all referenced source versions.
- Real capability negotiation contracts for each video/voice backend and handling partially enforced constraints.
- Quality thresholds for identity preservation, temporal continuity, performance and audio sync.
- Measured Windows AMD and Linux/CPU admission and model worker residency, without CUDA lock-in.
- Formal rights/consent metadata, model/data export restrictions and optionally signed review decisions.

Decide these in implementation milestones with adversarial tests rather than embedding assumptions into unreviewed production code.
