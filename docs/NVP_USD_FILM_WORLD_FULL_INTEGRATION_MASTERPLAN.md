# NVP USD-FILM — Full OpenUSD virtual-world filmmaking integration program

**Creator direction — 2026-11-08.** Maximize OpenUSD's native scene-composition, character, material, camera, lighting, animation, and large-world organization capabilities in NVP, then connect focused 3D engines and AI workers to supply behavior USD does not execute itself. Build coherent, reusable **filmable virtual worlds** and raise visual realism toward convincing contemporary generative-video imagery, with persistent characters, environments and physically coherent camera moves.

**Scope decision:** This is **pure filmmaking**. Digital twins, reconstructed historical geographies, simulated alternative futures and VR/game-engine experiences demonstrate how extensible the underlying scene model might become, but they are **not** authorized NVP production features in this program. Do not build a geographic truth database, chronology of the real world, interactive VR game runtime or scientific simulation platform without a separate creator decision. No performer/legal paperwork, license administration, rights matrices, consent screens or other non-filmmaking additions.

**Engineering stage:** PROGRAM AND ORDERED TASKS ESTABLISHED; no new engine, AI worker, native renderer or high-quality 3D output is claimed complete by this document. The existing FILM03-09E voice/face/lip-sync native-acceptance line remains active and must not be replaced or misrepresented as closed.

## Core architecture: record the world, not merely rendered pixels

- **OpenUSD = canonical structured 3D-scene substrate** for film geometry, assemblies, typed object relationships, materials, camera and light rigs, authored skeletal/facial animation, bounded physical state representations, variants, time samples and scene composition. OpenUSD does not solve IK, speech, animation logic, dynamics, denoising, texture creation or realistic image synthesis merely by defining a schema.
- **FilmIndex + Production Bible + Temporal Ledger = NVP's source authorities**, not substitutes for OpenUSD. These own stable ActorID/VoiceID, exact scene/Take/shots, immutable data revisions, creator artistic direction, event relationships, source media provenance, source-time fidelity and recovery receipts. Existing source time: 7,056,000,000 integer Film Time ticks/second; 48 kHz PCM corresponds to 147,000 ticks per sample. USD timecodes are double and original bridge bounds them to exactly representable ticks.
- **Blender/Cycles and other reviewed native workers = executors** of modeling, rig construction, cloth/physics/smoke, facial acting, cinematography and high-quality rendering. Other engines may be evaluated only for real functionality or fidelity not supplied by existing workers. Do not write a parallel NVP rasterizer, physics engine or rigging engine when existing capable reviewed libraries suffice.
- **AI = director-guided planner/operator, never authoritatively invents success.** An AI can propose new objects, assets, materials, physics states, rig motions and shots, then invoke typed native tools through NVP's existing host-supervised execution and immutable source revision rules. The Blender result or authored USD stage must be reopened, validated and reviewed. A text description or syntactically valid USD layer is not rendered visual success.
- **Renderer outputs = disposable derivations.** Film source and world objects are independently revisable, but a committed prior Take cannot be overwritten. Scene branches, lighting looks, costumes, dialogue performances, spatial sounds, VFX passes, editorial cuts and final masters may have distinct revision histories.

## Proposed source world graph (illustrative, NOT a required new schema)

```text
NVP FilmIndex / Production Bible / Temporal Ledger
  └── Film / Scene / Take (stable ids, canonical time, frozen versions)
       └── OpenUSD composed Stage
            ├── /World/Environments/...   (layout, geometry, terrain, structures)
            ├── /World/SetDressing/...    (props, references, instancers)
            ├── /World/Actors/...         (original ActorID-bound skinned meshes)
            │    ├── skeletons + body motion
            │    ├── facial blend shapes + speech articulation
            │    ├── eyes/gaze targets and corrective shapes
            │    └── clothing/hair/interaction cache references
            ├── /World/Cameras/...        (lenses, rails, focus, exposure metadata)
            ├── /World/Lights/...         (physical fixtures, sun, modifiers)
            ├── /World/FX/...             (rigid/soft/fluid/volume cache references)
            └── /World/Audio/...          (spatial sound placement and source links)
       └── Film-specific non-destructive layer stack
            ├── original asset and stage references
            ├── actor performance, audio, motion and simulation caches
            ├── director shot/camera/lighting/expression overrides
            └── disposable renderer- and output-specific presentations
```

This is a **conceptual ownership model**. Exact composition arcs, which prims exist in native USD versus FilmIndex metadata, and each individual renderer's supported schema subset require source-level design review. Never put opaque mutable external absolute filesystem paths into authoritative source USD.

## What NVP already has — reuse, don't replace

| Existing area | Relevant first-party implementation | What it does NOT yet establish |
| --- | --- | --- |
| Source OpenUSD scene/Take | `nvp_openusd_scene.py`, `nvp_openusd_take.py`, Temporal Ledger | Universal import, lazy multi-city stage or full-featured USD authoring GUI |
| Reusable bounded geometry | `nvp_openusd_assets.py`, authored asset bindings and revision-aware references | General creator assets, arbitrary mesh import, spatial LOD/payload scheduling |
| Skeletons / facial source | `nvp_openusd_skeleton.py`, `nvp_openusd_skinning.py`, FILM03-09D | General full-body IK, true eye solver, soft-tissue skin, corrective rigs or convincing lip-sync |
| Native camera/light | Native scene schema, SHOT/SLATE camera/lighting workers | Comprehensive lens distortion, focus pulls, calibrated exposure/light parity and photometric validation |
| PBR/materials | WO3 MaterialX/OpenPBR/texture identity validation and Hydra probes | Final Blender/Hydra shader and calibrated pixel/color parity |
| Visual presentation | SLATE/FILM01/FILM02 and Blender/Cycles workers | Entire shot photorealism, dense human close-ups, real film quality acceptance or reliable high-end GPU budgets |
| Actor source/audio | FILM03 source selection, voice sources, facial direction and phoneme adapter | Actual reviewed voice generation/conversion, genuine human-spoken phoneme accuracy and film-rated face/audio coherence |
| AI film operations | WO6 typed production operations, host supervisor/journal/recovery | Autonomous unrestricted scene construction, reliable art direction, or quality control without a director |

All earlier native CI gates keep their own status. Do **not** infer acceptance from this table, source imports, GitHub queues or proposed features.

## The work orders, in priority/dependency order

### USD-FILM-00 — Native capability / fidelity inventory [FIRST; OPEN]

**Deliverables:** Machine- and human-readable inventory of what our pinned `usd-core` Python installation, actual Blender importer/exporter, MaterialX bridges, Hydra delegates and native NVP adapters really support. Matrix per schema/feature: author/read/round-trip/edit/animate/render, Windows/Linux, exact versions, asset dependencies, known losses. Identify existing tasks and avoid duplicate subsystem creation. Verify true `UsdSkel` blendshape/joint round-trip; material/normal/UV; camera and light; instance/payload behavior; UsdVol; UsdPhysics; UsdMedia where installed. Count actual native test results; unsupported = OPEN. Confirm requirements and binary packaging (USD core vs USD imaging/Hydra are not interchangeable).

**Exit:** Reproducible capability report with observed native evidence and exact SHA/version per test, no unsupported capability masquerading as working.

### USD-FILM-01 — Composable and scalable film world [OPEN, depends 00]

**Build:** First-party, revisable source asset registry; NVP-controlled USD asset resolver for project-local content-addressed assets (no arbitrary remote references); authored references, payloads, variants, collections, inherited looks and useful instancing. Measured lazy-set loading/unloading by active shot, distance and editor working set. Preserve per-instance directorial individuality instead of incorrectly expecting instanced descendants to support unique edits: break out authored performers from shared prototypes when needed. Unit/axis/camera and model scale conversion must be explicit.

**Exit:** Two shots share a large set and common props; one shot has a non-destructive art-direction change without mutating the other. Confirm exact source/Take identities after restart and bounded peak RAM/VRAM, stage-open latency, missing-asset failure and partial loading.

### USD-FILM-02 — Creator-friendly world construction and geometry [OPEN, depends 01]

**Build:** Typed tool contracts to author/edit actual mesh, curves, geometry nodes/procedural scene assets and measured imports from Blender or another reviewed engine. Use source-preserving retopology, UVs, asset variants, scale, naming, and instanced city/set dressing. AI can describe an asset and ask a native worker to create it; validate actual triangle topology, geometry, UVs/material assignments and source correspondence. Photogrammetry and scan-derived content may be future film *inputs*, not a mandate to build a world-mapping platform.

**Exit:** A reusable interior, outdoor set and nonhuman actor are generated/edited through actual reviewed geometry workers and reopened natively in OpenUSD and Blender without proxy substitutions.

**USD-FILM-02M — queued modular architecture construction:** The creator approved a reusable building-kit approach that separates a street-facing façade from the building core/rear, floors, roofs, corners, bays, storefronts and interiors. Assemblies must use exact first-party asset IDs/revisions, dimensions in meters, Z-up, oriented connector sockets, scale/tolerance rules and deterministic seed+selected-module manifests. OpenUSD references/variants/instancing carry the reusable geometry; scene-cell streaming/hysteresis is a separate runtime decision. Validate real mesh fit, camera reverse-angle parallax, materials and lighting and produce true Cycles acceptance before claiming visual quality. **Detailed deferred implementation:** `docs/NVP_USD_FILM02M_MODULAR_ARCHITECTURE_ASSEMBLY.md`. Do not replace the ongoing 01F source-to-render work with 02M yet.

### USD-FILM-03 — Fully directed actors: rig, eyes, face, body, apparel [OPEN, depends 00/02 and FILM03-09E]

**Build:** Mature UsdSkel authoring/editing, inverse kinematics and constraints through Blender or reviewed solvers, reusable body/gait motions, semantic gaze target and eyelid tracking, face/lip/jaw/tongue and corrective shape targets, scene/object interaction, skin deformations, cloth/hair/groom outputs. Preserve ActorID, human voice performers' creative contributions, VoiceID, final dialogue waveform and director-controlled face/body choices. Face **matches performed vocal emotion by default**, explicit artistic expression overrides always win. Represent solved poses and baked animation in USD; USD does not provide the acting intelligence itself.

**Exit:** Three recurring distinct actors (including nonhuman) retain identity across shots; real spoken line matches actual mouth geometry and eye/gaze; skin/hair/costumes do not break; authored facial emotional contrast survives render and reopen. No fake phone/mouth acceptance.

### USD-FILM-04 — Interactions, physics and simulation caches [OPEN, depends 01/03]

**Build:** USD-described collision/rigid-body/joint relationships with an actual reviewed physics solver, skinned collision contacts, constraints, cloth, hair, fluid, smoke/volumes and breakage where required by a *film shot*. Deterministic or replay-verifiable fixed inputs/time-state handoff, bounded simulation caches and topology changes; records exact cached original/source time, solver/version, mesh/volume identity, seed, renderer dependency. Prefer Blender/specialized workers over writing a new simulation engine.

**Exit:** Actor picks up, passes, drops and collides with a prop; a cloth/hair/FX example maintains continuity across a two-shot cut and after render resume. Failure or nondeterminism is recorded, never labeled exact physics.

### USD-FILM-05 — Photographic shading, lighting and look control [OPEN, depends 00/01/02]

**Build:** Full MaterialX/UsdShade-to-reviewed-renderer look decisions; PBR roughness, layered material response, microgeometry, surface normals/displacement, subsurface skin, eyes/teeth/hair, transparent/translucent materials, consistent texture spaces and UDIM only where supported. Existing native USD lights plus sun/sky/HDRI, area light/cookie/IES where actually supported, measured shadow softness/caustics/indirect lighting. Director-editable looks as non-destructive USD overrides; measured color transforms with OCIO/scene-linear discipline. No unverified “we support MaterialX” claim just because source graph parses.

**Exit:** Lighting calibration chart plus chrome/glass/skin/fabric/donut/box/sphere reference render passes (including sphere through donut hole and proper occlusion); physically coherent responses in an actual Blender/Cycles renderer, and any independently supported Hydra delegate compared by real pixel/color evidence.

### USD-FILM-06 — Cinematography, scene-time and sound continuity [OPEN, depends 01/03/05]

**Build:** Original USD cameras and NVP cinematography: calibrated lens/frustum, sensor size, aperture, depth-of-field, focus racks, camera rig/rails, motion blur/shutter, exposure and lens distortions via an actual optical rendering pipeline. Audio placed spatially in the scene but source timing/mix belongs to NVP's existing exact PCM and edited timeline; source clock independent from frame rate. Respect scene scale, world position, editing cuts and source time during moving cameras.

**Exit:** A two-camera multi-shot actor scene with controlled focus pulls, predictable DOF/motion blur, sample-accurate spoken sound and repeatable non-destructive shot variations. Check actual lens data through an independent renderer/reader.

### USD-FILM-07 — AI-to-native virtual-world composition [OPEN, depends 00–06 incrementally]

**Build:** Typed native tools for adding/editing source-approved geometry, actors, set dressing, materials, physics simulations, cameras, lights and performance layers. AI can translate director intent into a proposed *scene diff*: what will change, why, expected tools/outputs and dependencies. Source authority remains FilmIndex/Production Bible; the director can inspect, revise, branch and approve creative results. Progress, cancellation, bounded worker execution, recoverability and real artifacts from current WO6/execution layer are reused; no separate general-purpose AI orchestration ecosystem.

**Exit:** Given a film script and an original set, AI produces three actual, editable proposed shot arrangements, supervised workers generate real geometry/rendered frames, and the creator can select/undo/compare them without overwriting an original scene.

### USD-FILM-08 — Renderer interoperability and large-scale runtime [OPEN, depends 00/01/05/06]

**Build:** Compare native Blender USD import/export, Cycles render and independently available Hydra delegates for exact original geometry, animation, materials, optics and light features. Measure pixel differences, dropped features, time-sampled property fidelity, texture/color transform semantics, AOV/depth/normal/motion passes, CPU/GPU memory and time to first preview. Use shot-specific lazy USD payload working set, authored LOD/instances, preview-vs-final render budgets and chunked film render/restart. A renderer switch is not mandatory; Blender remains the film-grade reference path unless evidence says otherwise.

**Exit:** Same frozen scene produces independently verifiable source-equivalent animation and consistent, explicitly documented visuals across the supported renderer path(s); 30–60s original film frames stream through bounded resources and crash/resume without source corruption.

### USD-FILM-09 — Photorealism and temporal coherence acceptance [OPEN; continuous from 05 onward]

**Goal:** Aim for *visually convincing*, controllable film outputs on par with strong contemporary 2D generative videos in selected shots, while keeping a consistent 3D world and editable production data. This is a **quality target, not a verified capability or a guarantee of automatic equivalence**.

**Evidence, not adjectives:** Require actual render/image sequences inspected at full presentation size plus audio when relevant. Review at least (a) hard-surface reflective object/product shots, (b) indoor/outdoor environmental photography, (c) human/creature close-up if the film uses one, and (d) moving-camera/moving-subject sequences. Check actual geometry, materials, skin/hair/eye detail, real light transport/shadows/occlusion, natural motion/weight/contacts, optical depth/focus, visible speech synchronization, temporal flicker, identity continuity, set dressing stability and cross-shot continuity. Distinguish rendering fidelity from story/acting quality. Evaluate quality at fixed resources and record GPU/CPU time, RAM/VRAM, renderer seed/configuration, camera/lens and exact source SHA. Include director blind/side-by-side review and independent technical verification; do not use image-generation reference frames as supposed 3D render receipts.

**Tiered gate:** Stage A: credible product/object renders; B: photographic film set/environment; C: believable voiced expressive actor close-up and multi-shot narrative. A passing object test is not evidence of believable skin or speech. Do not infer photorealism from 4K, high bit depth, MaterialX nodes or rendering-engine names.

### USD-FILM-10 — Integrated film-creator acceptance [OPEN, after 01–09 essential subset]

**Scenario:** A 30–60-second film (minimum 3 distinct shots) featuring a persistent world, at least one scripted voiced actor (or artistically chosen non-mouth performer), meaningful prop interactions, camera/light/motion, two distinct directorial revisions, original synchronized sound, actual Blender/Cycles picture, independent saved scene/reopen checks and a complete playable master. Use existing FILM01/FILM02/FILM03 and WO5/WO6 acceptance; do not replace or duplicate their ledger gates. End-to-end renderer is production grade only after human visible/audible film review and technically verifiable source-to-master continuity.

**Exit:** Source-authentic, reproducible, editable film from one coherent OpenUSD world—rather than a set of unrelated generated video clips or a synthetic test that merely prints PASS.

## Explicit design guardrails

1. **Do not replace working systems** or introduce new renderers, 3D/physics engines, agents or legal facilities absent a specific measurable filmmaking gap and creator sign-off when outside approved scope.
2. **Do not claim a digital twin is real geography.** If later approved as a separate initiative, source measurements, confidence, provenance, estimated/inferred reconstruction and historical speculation must be visibly distinguished. USD can record hypotheses; it cannot manufacture missing ground truth.
3. **Do not confuse USD schemas with operational simulation.** UsdSkel stores shapes, not facial acting intelligence. UsdPhysics describes physics properties, not a guaranteed simulator. UsdMedia doesn't produce a film mix. Hydra renderer delegate fidelity depends on actual installation.
4. **Do not force facial emotion** to match a voice when director has explicitly chosen otherwise. Voice-matched expression remains the default.
5. **Do not equate source acceptance with image acceptance.** Native code compilation, schema parse, USD layer validity and even successful Blender execution are separate from visual realism and perceptual performance quality.
6. **Keep world history through immutable sources and explicit revisions.** Do not rewrite a prior frozen Take to make a later version look correct. Later changes can coexist and be compared at original timeline ticks.
7. **No frame-rate-locked authoritative world.** The Film Time/48-kHz sample mapping and source-time semantics remain intact; presentation FPS is an output choice.

## Linked HUMAN-SURFACE photoreal human and AI-assisted material workstream [ROADMAP; ALL OPEN]

The creator has additionally approved an **AI-assisted 3D human surface/material authoring roadmap**, emphasizing photoreal skin and believable eyes/lips/hair *under multiple lights, cameras and expressions*, not single-view generated portraits. The authoritative task specification is **`docs/NVP_HUMAN_SURFACE_AI_MATERIAL_AUTHORING_ROADMAP.md`** (HSURF-00 through HSURF-10). It expands—**does not replace**—USD-FILM-02 (geometry/UV/scan), USD-FILM-03 (performing actors), USD-FILM-05 (skin shaders/lighting), USD-FILM-07 (typed AI scene operations), USD-FILM-08 (real renderer asset builds), USD-FILM-09 (photoreal visual acceptance) and USD-FILM-10 (actual short).

**AI-driven NVP is an intentional creator workflow, not an autonomous source-of-truth model.** Existing WO6 creator-approved AI operations and native host supervision remain the foundation: AI plans, reads bounded exact source records, proposes source-bound map variants, selects the proper specialized image/Blender worker, obtains real render evidence and offers revisions. Only creator-reviewed material/ActorID appearance changes become source revisions; old Digital Takes are immutable. AI image/video candidate outputs are not passed off as physical 3D measurements, independently rendered Cycles frames or consistent skin across angles. The director can reject or undo proposed looks. Preserve native-tool default, optional MCP, and filmmaking-only scope.

**First priority:** audit existing source meshes/UVs/MaterialX/Blender capabilities, then build the repeatable neutral human-head multi-light baseline and the typed ActorID-bound PBR map contract before attempting open-ended image generation. This roadmap makes no implementation/CI/photorealism acceptance claim.

## Recommended immediate sequence

1. Finish **FILM03-09E** real phoneme+rig+Blender/auditory integration and inspect exact-head native 09C/09D results. Continue film production while CI reports; don't declare pass on queued work.
2. Start **USD-FILM-00** with actual USD/Blender/Hydra/MaterialX native capability matrix on the existing source tree and pinned versions.
3. Develop **USD-FILM-01** reliable asset resolver + variants/payload/lazy composition with measured scale, then expand **02/05** geometry and materials/lighting (photoreal object/environment baseline).
4. Advance **03/04/06** character/gaze, interactions, cinematography and sound only with concrete shot requirements and actual on-screen tests.
5. Layer **07/08** AI scene composition + render parity/performance, then run **09/10** comparative quality and real original short-film acceptance.

## Technical references (design input, not proof NVP integrates these APIs)

- OpenUSD scene composition and schema overview: https://openusd.org/release/intro.html
- OpenUSD instancing semantics and per-instance override restrictions: https://openusd.org/release/api/_usd__page__scenegraph_instancing.html
- OpenUSD native schema domains (Lux, Media, Render and others): https://openusd.org/release/user_guides/schemas/index.html
- UsdSkel skeleton, blend shapes and large-character tradeoffs: https://openusd.org/release/api/_usd_skel__intro.html
- Hydra renderer/scene delegation: https://docs.nvidia.com/learn-openusd/latest/beyond-basics/hydra.html
- MaterialX integration across USD/Hydra: https://openusd.org/release/api/_page__material_x__in__hydra__u_s_d.html

**Governance:** Creator-authorized filmmaking expansion only. New digital-twin, game, metaverse, real-geographic archive, scientific-simulation or unrelated platform features require separate design approval before any development. The roadmap is intentionally larger than immediate implementation and should be worked methodically, one independently verifiable gate at a time.
