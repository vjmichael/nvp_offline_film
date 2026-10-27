# Neural Video Producer (NVP): World-Aware Film Studio Design

**Revision:** 2026-10-26 — design update based on the original NVP repository and the creator's current direction  
**Status:** Proposed architecture and migration plan; not an implementation claim  
**Source:** NVP repository, main branch, reviewed 2026-10-26  
**Priority:** Production-ready Lu Core remains the immediate priority. NVP/Film Studio development follows as a specialized Lu DLC Workspace.

> This design preserves the original NVP's core vision: serious, offline-first AI filmmaking with a production bible, persistent actors and locations, real virtual cameras, specialized film-crew roles, and Unreal Engine 5. It expands the design to make persistent 3D world state authoritative and to separate controllable filmmaking from probabilistic generative rendering. This document does not supersede the repository's proprietary license or establish that proposed features already work.

## 1. Purpose and problem statement

NVP is not intended to be a prompt-to-clip toy. The director must be able to realize a planned film rather than repeatedly accept the closest output a video generator happens to produce.

The original NVP README identifies problems with short disconnected AI clips, misattributed dialogue, changing character appearances, weak spatial understanding, objects being passed through, and the absence of a production-oriented scene/shot workflow. The existing repository responds with Unreal Engine 5, a Production Bible, specialized director/DP/acting/script/asset roles, and an offline, asynchronous production architecture.

The updated objective is **director-controlled, world-consistent filmmaking across an entire project**, where a scene has an enduring existence independent of the frames rendered from it. Characters, props, sets, actions, cameras, and story state persist between shots and can be rendered in photorealistic, anime, cartoon, clay, stop-motion, or other styles without changing the canonical identities.

### Success criteria

1. A named character stays the same character through multiple scenes, shots, takes, and visual styles.
2. A physically modeled obstacle remains an obstacle. Characters do not accidentally pass through a fence, wall, or prop.
3. Scene blocking, shot composition, eyelines, screen direction, camera axis, and dialogue attribution can be explicitly planned and validated.
4. The director can intentionally override cinematic or physical conventions for an artistic purpose; exceptions are explicit and recorded.
5. An unacceptable result can be repaired locally without destroying approved shots or resetting the whole project.
6. Every approved take can be traced to its assets, world-state version, camera, animation, style, model run, and human decisions.
7. Offline operation is the baseline; optional cloud services must be separately authorized.

## 2. Confirmed direction versus engineering proposals

### Creator's expressed requirements

- Persistent 3D characters, settings, and props are the basis of consistency; a realistic, cartoon, anime, clay, or stop-motion output should not require reinventing the actor's identity.
- Films are constructed from scripts, sluglines, scenes, characters, dialogue, shots, performances, cameras, and edits, not merely a sequence of independently prompted video clips.
- The system should understand practical cinematography and rules such as the 180-degree rule, without preventing deliberate artistic departures.
- Physically implausible behavior and identity morphing should be controlled, not accepted as an unavoidable generator artifact.
- NVP should use a real 3D production environment, originally Unreal Engine 5, with virtual camera and crew roles.
- Lu Core is the foundation and current development priority; the future AI Film Studio is a specialized, full-featured Lu DLC Workspace with its own production-oriented UI. Lu's vanilla GUI remains available.
- Core Extensions are optional Lu-native capabilities, not MCP servers. Workspace/CE tool ownership and the integration contract require further design.

### Recommendations in this revision, not yet ratified decisions

- Use an authoritative canonical world representation plus a 3D/physics engine, rather than asking a generative model to maintain the world's truth.
- Treat learned world models as optional predictors, not the source of canonical geometry or identity.
- Use a task/capability-based model registry and replaceable inference adapters rather than requiring a particular SSM, VLM, diffusion model, or vendor.
- Adopt versioned structured data contracts and an explicit validation/approval gate before AI-generated actions mutate the canonical scene.
- Build a small benchmark before committing to custom model training.

## 3. Key distinction: world representation, world model, renderer

**Canonical world representation:** Deterministic, persistent project data: identity IDs, assets, geometry, rigs, transforms, relationships, wardrobe, props, temporal continuity, camera setup, and approvals. This is the source of truth.

**Simulation:** Unreal Engine or another capable 3D runtime executes blocking, skeletal animation, collision, camera placement, lighting, and deterministic or controlled physical interactions. The simulation should enforce known geometry rather than depend on a video model's guesses.

**Learned world model (future research):** A neural predictor of likely actions, physical outcomes, or temporal developments, useful for complex interactions not captured by authored animation or physics. Predictions must be checked against canonical state and may not silently redefine it.

**Generative renderer:** An optional model or combination of models that transforms geometry-, pose-, camera-, and identity-conditioned frames into desired visual detail or style. Its outputs are candidate renders, not authoritative scene state.

**Validation and approval:** Rule-based checks, simulation checks, vision-based checks, and director review compare output against the planned shot. Failed renders are flagged for targeted repair or regeneration.

This is a hybrid production system, not necessarily a single gigantic neural network.

## 4. Proposed logical architecture

1. **Lu Core (shared platform, later integration):** Session identity, user authority, native tool permissions, extension lifecycle, general memory and model services, scheduling, logging. Film-specific production logic must not be hardwired into vanilla Lu.
2. **AI Film Studio Workspace (NVP successor):** A full specialized application UI: project browser, script breakdown, production bible, casting, asset library, 3D stage, director's monitor, camera/lighting controls, shot planner, timeline, dailies, editing, audio, render queue, and continuity review.
3. **NVP Production Domain Services:** Project/sequence/scene/shot/take management; script parser; production bible; casting and character representation registry; set/prop registry; wardrobe/state tracking; story timeline; optical rules; camera-axis and blocking planner; continuity engine; approval/versioning.
4. **3D Stage and UE5 Bridge:** Scene assembly, transforms, collision, rigs, animation, Control Rig/Sequencer, virtual cameras, lighting, structural render passes, and shot metadata. UE5 is a proposed primary implementation, not an exclusive data format.
5. **AI Film Crew:** Director/planner, script supervisor, DP, acting coach, asset assistant, editor, sound designer, and quality-control roles. A role is a task, instructions, tools, and authority boundary; it does not automatically require a separate large LLM.
6. **Model Runtime and Resource Scheduler:** Local-first, capability-addressed inference for vision, dialogue, animation, image/video, speech, music, and sound; model identity/version, hardware compatibility, memory budget, and provenance. Cloud adapters are optional and permission-gated.
7. **Output and Evaluation:** Deterministic preview render, optional conditioned generative pass, automated consistency checks, human approval, dailies, non-destructive edits, final master.

### Authority and data flow

Director instruction -> script/shot plan -> approved canonical scene changes -> UE5 stage/simulation -> structural render passes -> optional generative stylization and sound -> continuity checks -> director approval -> immutable/versioned take record.

AI suggestions and generated frames must not silently rewrite approved actor identities, locations, geometry, or story events. Changes to canonical world state require a validated, auditable command and the appropriate user or workflow authorization.

## 5. Production Bible and canonical data model

Retain the original Production Bible concept and evolve its JSON samples into versioned, validated records. Do not discard existing IDs or assume sample model files are present.

| Record | Canonical content | Relationship to existing NVP |
| --- | --- | --- |
| Project / Production | title, style profiles, asset roots, frame rate, delivery format, access rules | Project wizard and project manager prototypes |
| Sequence / Scene | script slugline, location, story time, participants, action, scene version | Scene/shot IDs in dashboard and temporal tracker |
| Shot / Take | planned blocking, lens, camera path, axis, edit intent, simulation and render provenance | DP engine, render manager, dailies/versioning |
| Character Identity | stable ID, name, physical traits, role, allowed likeness, voice identity | Casting ledger |
| Character Representation | mesh/rig/LOD, style-specific appearance, animation retarget mapping, identity reference | Extension to casting ledger and LoRA metadata |
| Character State | wardrobe, injuries, held objects, emotion/performance, scene time | Wardrobe states and temporal tracker |
| Set / Prop | persistent asset ID, geometry, collision, transform, ownership, material state | Environment registry and temporal prop states |
| Camera Package | sensor, lens constraints, camera pose/path, motion constraints, line-of-action metadata | Optical ruleset |
| Style Profile | rendering/animation/material rules and permissible deviations | Existing cinematic style and generative tokens |
| Continuity Event | action, timestamp, before/after state, reason, approver | Evolution of temporal tracker |
| Model Run | model/adapter/version, seed, inputs, settings, output hashes, licenses, device, QA results | New; required for reproducibility |
| Approval / Revision | approved take, rejected region, change request, parent revision | Evolution of dailies/branching |

Use stable opaque IDs and explicit references, not repeated free-text identity descriptions. Define units, coordinate systems, timecodes, serialization versions, migration behavior, and atomic update semantics. Protobuf may be suitable for Lu-native internal messaging; JSON remains appropriate for human-editable production bibles and external AI API boundaries. The exact Lu/Workspace interface is still a proposal.

### Character identity is not the same as a render mesh

One canonical character may have multiple approved representations: realistic body/face rig, anime rig, cartoon proportions, or a clay puppet. Each representation maps back to the same character identity and approved scene performance. A single mesh is not required to fit every artistic style.

### State changes must be explicit

A damaged coat remains damaged until a documented wardrobe or story event changes it. A prop transferred from one actor to another records an ownership/attachment event. A character cannot teleport between shots without a planned time or spatial transition. An approved exception is allowed, but must be intentional.

## 6. Filmmaking intelligence and cinematic constraints

Script ingestion should identify sluglines, scenes, named and background characters, dialogue speakers, action beats, props, and continuity dependencies. The parser proposes structured breakdowns; the director can edit them.

The shot planner should represent blocking and camera positions in 3D, then evaluate eyelines, screen direction, coverage, and line-of-action/180-degree continuity. The 180-degree rule is a default continuity constraint, **not an absolute prohibition**: an intentional axis crossing, motivated camera move, or other override can be approved.

The acting system should map script beats to timed actions, facial expression, skeletal pose, contact and interaction targets. Performance must be checked against the character's rig, nearby objects, and physical limits. Dialogue is explicitly attributed to a character/voice identity and synchronized to mouth/performance tracks.

The DP system should use real camera parameters, shot scale, focal length, sensor, focus, motion, lighting, and framing. The existing optical ruleset is a useful starting point; rules must be validated against the actual virtual camera.

## 7. Visual styles without identity drift

The canonical 3D scene and timeline remain stable while the render treatment changes. Styles can use different meshes, shaders, rigs, animation timing, and optional generative finishing.

- **Photorealistic:** physically based rendering and lighting; optional detail enhancement or 3D-conditioned video synthesis.
- **Anime:** cel shading, line work, stylized rigs and expressions, and optional frame-level refinement.
- **Cartoon/illustration:** non-photorealistic rendering, exaggerated motion, and painterly materials.
- **Clay:** sculpted surface appearance, tactile material imperfections, miniature-set presentation.
- **Stop-motion:** stepped frame timing, pose holds, intentionally irregular motion and texture; not simply a text prompt saying “stop motion.”

A project Style Profile records geometry/rig mappings, shader rules, frame cadence, acceptable motion, palettes, and constraints. Switching styles should be non-destructive and versioned. A render pass must never become the only surviving copy of the scene.

## 8. Generation, training, and evaluation strategy

### Preferred sequence

**A. Controlled baseline:** Produce a complete, short multi-shot scene using UE5 alone, with persistent actor, set, camera, collisions, and timeline. Confirm that this deterministic baseline is reproducible.

**B. Conditioned generation:** Test pretrained models using controlled input: reference identity assets, depth, segmentation/object IDs, pose, optical flow/motion vectors, camera trajectory, and seed. Validate what the selected model and inference backend actually support.

**C. Targeted fine-tuning:** Only if B fails measurable tests, experiment with a small adapter/LoRA or other efficient fine-tuning method on properly licensed, paired scene/render data. Fine-tuning should solve a named failure, not substitute for missing world state.

**D. Custom models/world-model research:** Consider only after benchmarking reveals gaps that cannot be addressed by simulation, authored animation, constrained generation, or adapters. Training a competitive general-purpose video foundation model from scratch is not a prerequisite.

### Data strategy

Synthetic scenes rendered by our own 3D stage are unusually valuable because geometry, camera poses, contact points, character IDs, segmentation, and intended actions are known. Use such paired data to train or test spatially conditioned generation and continuity checks.

Historical film footage can inform cinematography, editing, acting, and narrative patterns, but finished footage alone generally lacks ground-truth 3D stage data. Internet Archive availability is **not** proof of public-domain status or permission for model training. Require per-item provenance, rights verification, documented permitted uses, and exclusions for unclear rights, performers, voices, and music. Respect source access terms and rates.

### Benchmark: one actor, one fence, three shots

1. Stage an actor approaching a barbed-wire fence, stopping before collision, looking left, and turning away.
2. Film the same action in a wide shot, close-up, and reverse angle with a planned camera axis.
3. Repeat in realistic, anime, and clay/stop-motion treatments.
4. Verify actor identity, costume, fence geometry, object permanence, body/fence intersections, action order, eyeline, screen direction, and dialogue assignment.
5. Change only the character's facial expression in one approved shot; confirm other pixels/regions and other approved takes remain stable within defined tolerances.

Record first-pass director-instruction compliance, temporal identity stability, collision violations, shot-to-shot continuity, human repair minutes, rerender scope, latency, peak VRAM, and reproducibility. Set numerical acceptance thresholds **after** baseline measurements; do not invent them now.

## 9. Audio, voices, and editing

Character voices are persistent, versioned identities linked to approved reference performances and consent records. Dialogue generation must honor speaker attribution, timing, emotion, and lip synchronization. Environmental sound should follow the scene geometry and action timeline where practical. Music generation is a separate optional subsystem, not an excuse to entangle music weights with the core film world.

Editing should preserve scene/shot/take lineage, source timecodes, camera metadata, and revision history. The editor should be able to cut from approved takes and send a specific shot or region back for revision without redoing the production.

## 10. Hardware and deployment

NVP remains local/offline-first, with asynchronous jobs and potential multi-GPU/distributed execution. Treat resource planning as measured scheduling, not a guarantee that all models and UE5 fit in VRAM simultaneously.

The creator's current target includes an AMD Radeon AI PRO R9700 with 32 GB VRAM and 32 GB system RAM, with future hardware upgrades. The legacy README assumes NVIDIA CUDA and provides approximate memory figures; those figures are not verified benchmarks for this AMD configuration. Evaluate Windows/Linux driver support, ROCm compatibility, UE5 GPU rendering support, model kernels, mixed precision, offload, and process isolation before selecting the inference stack.

Prefer staged loading, one heavyweight generation task at a time initially, memory accounting, job cancellation, retries, checkpoints, and render queues. Cloud use is optional, disclosed, and explicitly authorized.

## 11. Security, provenance, and licensing

- Preserve the existing proprietary licensing text in the original README. This architecture revision does not change ownership, source access, distribution, or licensing.
- Validate file paths, upload names, asset references, project IDs, and command parameters. Use atomic writes and structured validation for canonical state.
- Separate viewing/observation from permission to mutate a scene, call a model, read private assets, or transmit data.
- Keep voice and likeness rights, source licenses, dataset provenance, model licenses, and generated-asset lineage in the production record.
- Maintain recoverable revisions and backups. A label such as “immutable snapshot” must be backed by actual storage semantics, not a mutable JSON list.
- Do not grant film-production AI agents unrestricted shell or UE5 command execution. Expose allowlisted native operations through an auditable capability boundary.

## 12. Read-only repository review: what exists versus what does not

The following observations are based on static inspection of the main branch on 2026-10-26. No build, runtime, Unreal scene, GPU model, or integration test was executed.

### Existing design/code assets worth retaining

- **Original project intent:** README.md and readme.md describe serious filmmaking, 3D scenes, AI crew roles, offline operation, asynchronous processing, and UE5.
- **Production Bible samples:** casting ledger, environment registry, optical ruleset, and temporal tracker contain useful identity, geometry, camera, wardrobe, and state fields.
- **Project/versioning prototypes:** backend/nvp_project_manager.py, nvp_render_manager.py, nvp_db.py, and nvp_version_control.py implement portions of project cloning, take folders, JSON records, and dailies.
- **DP and acting interfaces:** backend/nvp_dp_engine.py and nvp_acting_coach.py express the intended separation of optical and performance planning.
- **UE5 bridge concept:** frontend/nvp_ue5_bridge.py includes editor-world lookup and camera parameter application.
- **UI prototypes:** React project wizard, director dashboard, reconstruction panel, versioning panel, and a separate touchless-audio component.
- **Audio prototype:** backend/nvp_stt_service.py and the touchless WebSocket frontend show the intended STT/voice flow.

### Gaps and correctness risks to address before treating NVP as runnable

| Area | Static finding | Required follow-up |
| --- | --- | --- |
| Main API | backend/nvp_api.py imports VideoMambaDirectorPipeline, but backend/nvp_core.py does not define it; the API file also begins with an un-commented “Python” line | Make imports and startup valid; introduce an interface and test double before real model loading |
| UE5 dispatch | dispatch_to_ue5_bridge in nvp_api.py is a no-op; bridge acting-vector application currently logs intended action rather than executing animation | Define validated commands, transport, acknowledgments, and a working UE5 integration test |
| DP / acting | DP recording and optical inference are explicitly simulated; acting coach uses a timed placeholder rather than loaded model inference | Treat these as prototypes and implement/test incrementally |
| Project wizard | Integrity check is a mocked UI response, including claimed auto-injection of the bridge | Replace with actual read-only checks and user-authorized installation steps |
| Frontend wiring | src/App.js imports NvpReconstructedPanel but repository file is NvpReconstructionPanel.js; src dashboard/versioning components import ./nvp_config.json while the config is in frontend/; reconstruction panel expects availablePlates but App does not supply it | Resolve paths/props and verify a clean build |
| API contracts | Dashboard calls /api/engine/generate_scene; the reviewed backend API does not define that route; the versioning UI expects a get_daily_ledger route not present in the reviewed versioning module | Establish a versioned endpoint contract and contract tests |
| Launcher | Start_NVP.vbs and start_nvp.sh reference nvp_launcher.py, which is absent from the reviewed tree; launch_npv scripts contain placeholder paths and npm start despite Vite dev scripts | Consolidate and test startup scripts |
| GPU portability | STT/TTS code explicitly selects CUDA; the README assumes NVIDIA hardware | Add backend/device detection, CPU fallback, and measured AMD compatibility |
| Data consistency | JSON updates are direct file writes; scene clone uses shallow copy; version-control branching has a hard-coded example date/path | Add atomic updates, deep-copy semantics, safe path handling, proper indexing, and recovery |
| Documentation | README.md and readme.md overlap and differ only by case, which is troublesome on case-insensitive Windows filesystems | Retain legal README; consolidate non-legal technical guidance carefully in a later cleanup |
| Tests | No automated test suite or CI configuration was evident in the reviewed repository tree | Add unit, contract, smoke, and UE5 integration tests |

The existence of a UI control, class name, model path, or JSON field is not evidence that the full production workflow has been implemented. The legacy descriptions of an integrated SSM/VLM pipeline should be treated as architectural intentions until the missing runtime components are connected and tested.

## 13. Incremental delivery plan

**P0 — Preserve and stabilize (first, after Lu Core priorities permit):**
- Freeze a reproducible baseline and inventory dependencies and licenses.
- Make frontend/backend launchable with health checks and explicit “not connected” states rather than simulated success.
- Fix broken imports, paths, missing routes, and startup assumptions; add basic tests.
- Preserve the current Production Bible samples and map their fields to versioned schemas.

**P1 — Canonical 3D world and film grammar:**
- Implement stable character/set/prop identities and scene/shot/take hierarchy.
- Build a minimal script-to-scene breakdown and state-transition engine.
- Add an authoritative UE5 stage with collision and camera transforms.
- Implement basic continuity and 180-degree/eyeline validation with intentional overrides.

**P2 — Deterministic short-film pipeline:**
- Script -> staging -> animation/blocking -> multicamera coverage -> render -> dailies -> editing.
- Add versioned takes, approved revisions, reproducible renders, and targeted shot changes.
- Complete the one-actor/one-fence multi-shot test **without** generative video.

**P3 — Controlled generative finishing:**
- Export structural passes and evaluate 3D-conditioned image/video models.
- Add identity/style profiles, visual QA, selective repair, and render provenance.
- Compare first-pass compliance and correction cost against the deterministic baseline.

**P4 — Audio and specialist intelligence:**
- Persistent voice identities, dialogue assignment, lip sync, sound, editing support.
- Evaluate task-specific agents and optional specialist models. Fine-tune only where benchmarks justify it.
- Explore learned world models and other AI architectures as separate research tracks.

**P5 — Lu Film Studio DLC Workspace integration:**
- Migrate/reuse NVP production services behind a defined Lu Workspace integration contract.
- Keep film-specific tools in the Workspace or reusable native CEs, not in the mandatory Lu base core.
- Resolve extension lifecycle, permission broker, schema versioning, model registry, resource scheduling, and specialized UI ownership with explicit architectural decisions.
- Preserve vanilla Lu and allow other DLC Workspaces to coexist.

## 14. Open design decisions

1. How much of NVP remains an independently runnable application versus becoming the Film Studio Workspace runtime?
2. Which scene format is canonical outside UE5 (for portability, revisions, and headless tests)?
3. What is the minimal Character Identity / Representation / State schema and migration path from the existing casting ledger?
4. Which render passes and conditioning formats are actually supported by candidate local video models on the AMD target?
5. What degree of human approval is required before AI crew roles modify geometry, performances, or edits?
6. What quantitative consistency targets are acceptable for the first benchmark?
7. Which Lu Workspace and CE lifecycle/tool interfaces become formally approved contracts?

## 15. Original source map

- README.md — original motivation, filmmaking requirements, hardware notes, and **proprietary terms (unchanged)**.
- readme.md — legacy introduction, touchless pipeline, hardware and dependencies.
- backend/nvp_bible/*.json — sample casting, environment, optical, and temporal records.
- backend/nvp_core.py — ProductionBibleManager and local model configuration.
- backend/nvp_api.py and backend/nvp_stt_service.py — main API and STT prototype.
- backend/nvp_dp_engine.py and backend/nvp_acting_coach.py — role-specific prototype behavior.
- backend/nvp_project_manager.py, nvp_db.py, nvp_render_manager.py, nvp_version_control.py — project, take, and versioning prototypes.
- frontend/nvp_ue5_bridge.py — UE5 editor bridge prototype.
- src/*.js, frontend/NvpTouchlessAudio.js — UI and touchless-audio prototypes.

**Document maintenance rule:** When implementation changes, update the “exists versus proposed” status and attach evidence from tests or source files. Do not convert architectural aspiration into an implementation claim merely because a module or model is named.
