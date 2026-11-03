# NVP MASTER DESIGN — World-Aware Personal Film Studio

**Document ID:** NVP-MASTER-001  
**Revision:** 1.0 — 2026-11-03  
**State:** Established architecture and product-requirements baseline; individual open decisions remain explicitly open  
**Product:** Neural Virtual Production (NVP), the future Film Workspace DLC for Lu  
**Development baseline:** nvp/prod06e2c2-plantar-markers-floor-20261103  
**Scope of this revision:** Design consolidation only. No solver, host, model, or renderer implementation change.

> **Governing idea:** NVP makes a film, not a chain of unrelated AI-generated clips. The creator authors and approves the narrative and production decisions. A persistent, editable 3D world, versioned character identities, physical geometry, virtual cameras, animation, audio, and editing supply the film's continuity. AI proposes creative choices and structured production instructions; conventional tools calculate and verify physical results. Rendered media is an output of the project, not its source of truth.

## 0. How this document governs development

This is the single *top-level* NVP design baseline. It consolidates decisions, requirements, known source material, and an explicit roadmap; it is not a claim that every described feature has been built. **A new implementation does not amend the design simply because it works.**

**Decision vocabulary**

- **[C] Creator direction:** Recorded product or architectural direction from the creator and already reflected in NVP decisions.
- **[B] Baseline requirement:** Adopted in this master document to implement [C] consistently. Engineering details may still need acceptance.
- **[O] Open:** Material question to resolve before implementing the affected subsystem.
- **[K] Candidate:** Tool, dependency, algorithm, model, or approach worth evaluating, **not a mandatory dependency**.
- **[V] Verified implementation:** A narrow claim supported by identified source and a completed test/audit.
- **[D] Deferred:** Designed or anticipated but not yet a production capability.

When documents conflict, apply this order: **explicit later creator decisions**; this master design for cross-subsystem product/architecture; subsystem design and approved typed contracts for local details; actual source and test artifacts for implementation facts; and legacy descriptions/research suggestions as historical inputs. A lower-level document cannot silently override an approved higher-level requirement. Any conflict must be recorded in a design decision with affected downstream artifacts and creator approval where the product contract changes.

The original proprietary ownership and licensing statements in README.md are **unchanged** by this architecture document. This file does not grant rights to the code, media assets, or third-party references.

## 1. Purpose, users, and nonnegotiable product requirements

### 1.1 Product purpose [C]

NVP is an **offline-first, personal filmmaking system** for someone with an idea, including someone with no screenplay, 3D, or film training. The creator can work in plain language or open expert controls. NVP helps develop the idea into a screenplay, cast, sets, performances, lighting, camera coverage, sound, edit, and exported movie; it must also accept an existing authored screenplay without forcing an AI rewrite.

A movie is organized as **story events → scenes → performances and blocking → shots and takes → editorial sequence → mastered output**. Scenes include named principal actors, background actors, sets, props, geography, and dialogue with the correct speaker and listeners. Repeatable sets and characters preserve their identities through cuts and across the film. Short independent video-generation prompts do not constitute this workflow.

### 1.2 Mandatory principles [C/B]

1. **Creator authority.** AI does not silently rewrite an approved script, accepted Story Bible canon, identity, set geometry, performance, or edit. Proposals remain distinguishable from accepted changes. Deliberate artistic rule breaks are explicit, reviewable exceptions, not hidden constraint failures.
2. **3D-first persistent production.** Geometric space, named physical anchors, rigs, collision, and actual camera projection are represented independently of rendered pixels. Actors must not walk through walls merely because a generator supplied plausible frames.
3. **Narrative continuity is distinct from physics.** The approved screenplay, events, objective facts, character beliefs, and physical WorldState are separately versioned but linked. A character's mistaken belief never becomes objective canon.
4. **Local-first and portable.** Offline use is the default. AMD, NVIDIA, and CPU compatibility is an explicit design requirement; a CUDA-only model or renderer cannot be a universal prerequisite. Network/cloud use is opt-in, scoped, and disclosed.
5. **Human-editable at every stage.** Creator-directed scene and performance modifications survive regeneration. Stable IDs, provenance, targeted stale-state propagation, checkpoints, and rollback are required.
6. **Conventional production tools do the math.** AI produces typed scene sheets, performance cards, camera recipes, lighting/mic choices, critiques, or alternatives; geometry, timing, animation constraints, collisions, camera projections, audio processing, and render/edit operations run in deterministic or bounded conventional software.
7. **No fictional success.** Status distinguishes proposed, parsed, simulated, generated, saved, independently audited, rendered, physically tested, and shipped. A Python unit test is not a real Blender character-performance test; a render preview is not a finished film.
8. **One eventual Lu Workspace.** NVP will be a Film Workspace DLC within Lu, not a separately installed consumer AI desktop application. The existing standalone Python/React app is a disposable **development harness**; normal users must not need Docker, a manual model server, multiple installers, or a CLI.
9. **Recoverable media projects.** Local project content, licenses, versions, dependencies, and approvals must survive restart, portable reopen, and failed jobs. An output without traceable inputs is not an approved production take.
10. **Rights and consent.** Imported asset, music, actor/voice/likeness, dataset, and model rights are recorded and respected. A declared license string is not an independent legal determination.

### 1.3 Experience target [B]

A beginner can write a sentence or import an existing script, inspect understandable decisions, approve or change them, preview a scene, request a local revision, and export a playable film. A professional can bypass guidance and manipulate shots, rigs, lighting, timing, and edit choices precisely. These are two presentations of the *same project data*, not incompatible modes.

## 2. End-to-end filmmaking workflow

| Stage | Creator-visible artifact | AI responsibility | Deterministic and audited responsibility |
| --- | --- | --- | --- |
| Idea and story | Idea, logline, synopsis, beat sheet, treatment | Propose alternatives, critique, ask consequential clarifications | Save revisions, compare, accept/reject |
| Screenplay | Exact screenplay, scene headings, cues, dialogue | Suggest writing and scene breakdowns | Parse Fountain/text; later reviewed FDX/PDF import, stable line IDs, history |
| Story/Production Bible | Character and set identities, facts, event order, props, costume and voice references | Suggest typed entity links/continuity flags | Validate identity, facts, source links, before/after events, permissions |
| Physical staging | Set layout, real assets, anchors, colliders and actor spawn states | Propose relationships and assets | Layout solver, geometry, collision, bounds, immutable asset/provenance package |
| Blocking and performance | Timed actor marks, objectives, tactics, gaze, motion, foot/hand contacts | Suggest scene beats and performance cards | Navigation, clips, rig constraints, IK, timing, contact/collision audits |
| Cinematography | Shot list, lenses, sensor, camera trajectories, focus and coverage | Propose shot recipes and coverage patterns | Camera solver, projection/framing, occlusion, 180-degree warnings, continuity |
| Lighting and sound | Light rigs, virtual mics, voice takes, sound cues | Suggest creative presets and performance | Render lights, synchronize dialogue, spatialize audio, mix and measure levels |
| Takes and review | Versioned scene/take previews and audit reports | Subjective visual/acting critique, optional VLM review | Save/reopen, compare ground truth, validate frame/asset/approval provenance |
| Editorial | Source-referenced timeline, transitions, sound mix | Propose edits and alternative cuts | Open timeline representation, exact timecodes, deterministic export |
| Master | Playable validated movie and project/archive manifest | Optional enhancement/quality critique | Frame/audio encode, sync, container validation, independent playback |

**Entry paths:** (a) idea-first; (b) existing-script-first; (c) direct scene/shot editing for an already established project. Every stage is optional when the prerequisite data already exists; skipping must not manufacture unsupported story, sound, or geometry as "verified."

**Bidirectional revisions:** Script edits mark affected dialogue, performances, shots, and media stale while retaining earlier takes. Physical/action changes may *suggest* script or continuity updates but never rewrite the screenplay silently. Re-render only dependent shots when possible.

## 3. Canonical authority: narrative, world, and media

The **authoritative production ledger** is a versioned collection of creator-approved screenplay revisions, Story Bible facts and chronology, identity/asset registries, approved base staging, layered WorldState edits, performance/shot decisions, and approvals. It is not a single image, one prompt, a mutable Blender scene, or a video model's implicit memory.

### 3.1 Narrative authority [B]

- **Screenplay:** exact authored text and ordered scene display; parse boundaries, speaker cues, parentheticals, dialogue, action, line spans and revisions without changing original words.
- **Story Bible:** stable IDs for characters, places, props, approved objective facts, references, named aliases, and provenance.
- **Chronology and knowledge:** explicit story-event partial order; flashbacks and parallel scenes may be unordered until the creator defines relationships. Per-character knowledge and subjective beliefs are separately recorded; unrecorded knowledge is **unknown**, not "ignorant."
- **Scene Mind:** spoken claims, mistakes, deliberate deception, belief transitions and suggested contradictions remain distinct. A review may acknowledge an intentional contradiction without falsely changing canon.
- **Continuity:** wardrobe, held items, injuries, location, prop state and identity changes need explicit story/world events and dependency links.

### 3.2 Physical WorldState authority [B]

A scene is an editable 3D graph: immutable or revisioned assets, instance IDs, transforms, geometry, materials, collision, spatial anchors, connections, character rigs, poses, cameras, and timed state changes. Layering is **approved base → accepted AI edits → human edits/locks**, with human locked fields winning. New approved staging does not silently reapply old overrides; it requires validated rebase.

The public 3D stage is a reproducible *derived realization* of the ledger. Blender/UE5 objects may carry stable IDs and approval hashes for round-trip auditing, but a user-created change in a DCC tool is not authoritative until imported through an explicit reviewed revision. No generator may replace the only editable copy with a raster render.

### 3.3 Identity and style [C/B]

One **canonical character ID** may have multiple approved physical/stylized representations and LODs (photoreal, anime, cartoon, clay, stop-motion). Appearance, body/face rigs, materials, and animation timing may differ; scene identity, relationships, dialogue ownership, approved actions, and prop continuity do not silently change. A Style Profile records palette, shader, rig mapping, cadence, allowed alterations and provenance. Learned image/video models are *optional finishers*, never canonical historians.

## 4. Stable production data model and invariants

All data stores use project-scoped opaque IDs, typed schema versions, explicit reference ownership and semantic units. SQLite transactions protect authoritative records. SHA-256 content digests identify immutable source bytes, approval input graphs, and outputs. An approval hash is evidence of an exact reviewed revision, not a substitute for a trusted authorization boundary.

| Record family | Required identity and content | Key invariant |
| --- | --- | --- |
| Project/Film | Project ID, working data root, style profiles, format, history | Cross-project reads/writes forbidden |
| ScriptRevision/Scene/Dialogue | Text revision, scene ID, cue/line ID, source span, speaker/listener links | Authored words preserved unless explicitly edited |
| StoryEvent/CanonFact/MindState | Event/fact/actor IDs, chronology edges, approvals, belief/claim state | Objective truth not inferred from belief or utterance |
| CharacterIdentity/Representation | Actor ID, rig/mesh/style/voice references, rights, mappings | Representation change does not change identity |
| Asset/Instance/Anchor | Asset ID, immutable geometry digest, instance placement, named anchors | Replacing source geometry requires a new version/ID |
| WorldEdit/Approval | Exact base revision, typed path/value, author, lock, review, event journal | Stale/rejected proposals never affect approved state |
| Shot/Camera/Take | Shot IDs, range, frame rate, lens/sensor, camera track, blocking, source deps | Cuts and motion address actual frame/sample times |
| Performance/Contact | Beat ID, approved intent, rig, clip, contact windows, IK outcomes | Cannot apply an unapproved or impossible contact |
| Lighting/Audio | Source IDs, rig/mic/voice assets, sync/levels, source license | Speaker and timeline identity preserved |
| Render/Edit/Master | Input graph, software/model versions, frame hashes, timeline and audit | Media derived from approved take and reproducible lineage |

**Shared coordinate/time conventions [B]:** Internal spatial quantities are metric and explicitly labeled with a frame convention and conversion at each Blender/UE boundary. The current production previs baseline is 24 fps, with 1-based shot/animation frames where specified. Film-wide timecode, fractional-frame/subframe, variable source fps, audio sample clocks, and deterministic rounding must be defined by typed adapters before master export. No unspecified "units", "seconds", or raw joint axes may cross an interface unchecked.

### 4.1 Revision dependency graph

A changed screenplay line invalidates linked dialogue timings, performances, shot plans and media; a changed rig invalidates retargeting/skin/IK and dependent takes; a changed stage invalidates spatial blocking, cameras, collisions and downstream render; changed approved canon invalidates affected model-context proposals. **Invalidate and offer re-evaluation; do not delete unrelated accepted artifacts.** Every regeneration records its source IDs, source revisions, software versions, parameters, output hashes, warnings and rejection reasons.

### 4.2 Atomicity and recovery

Use durable transactions, append-only or reversible edit history, immutable approved snapshots, typed conflict checks, stageable export, atomic rename/commit of outputs, idempotent job IDs, cancellation boundaries and restart verification. A failed render or interrupted worker must not leave an output claiming an approval that never happened.

## 5. Logical architecture and component ownership

    CREATOR / NVP WORKSPACE
        |  idea, script, scene edits, reviews, approvals
        v
    NVP DOMAIN LEDGER (screenplay + Story Bible + WorldState + provenance)
        |  typed approved scene/shot/performance/take contracts
        +----> AI FILM CREW (creative suggestions only)
        |            | returns typed, source-scoped proposals
        +----> DETERMINISTIC PRODUCTION SERVICES
        |            set/layout/collision/navigation/camera
        |            motion/retarget/IK/voice/timing/lighting
        |            Blender stage / optional UE5 adapter / audio / edit
        +----> QA (independent save/reopen, geometry, timing, rights)
                     |
                     v
              VERSIONED TAKES / EDIT / FINAL MASTER

**NVP domain:** story and screenplay services, Production Bible, physical scene registry, actor/performance/shot schema, rendering and editorial contracts, continuity, project approvals and specialized UI.

**Lu host [C, integration deferred]:** owns model loading/streaming, model resources, scoped filesystem/tool grants, Protobuf IPC, Workspace lifecycle, user permissions, durable effects, cancellation, supervised workers, containment and recovery. NVP becomes a declared Lu Workspace, not a competing model manager or privileged dispatcher. The NVP standalone FastAPI and localhost LLM picker are development adapters only.

**Execution boundary [B]:** a typed NVP plan cannot execute arbitrary Python, shell or Blender code from model output. Trusted host-owned templates, bounded input validation, process containment and independent audit govern each production worker. Tool discovery never grants permission. Heavy media workers must be admitted against GPU/RAM budgets; priority and cancellation must not destabilize foreground Lu.

**Cognitum:** may be assessed as an optional source of physical/causal reasoning or character-behavior support, but is **not** a required NVP production dependency and must not replace validated geometry, motion constraints or creator authority. No current NVP film gate assumes Cognitum is installed.

## 6. Engineering toolchain — committed role versus candidate option

| Responsibility | Current or baseline choice | Candidates to evaluate, not automatically install |
| --- | --- | --- |
| Project state and typed records | Python NVP services, SQLite, versioned JSON, SHA receipts | Pydantic schemas, NetworkX event relations, sqlite-vec/LanceDB retrieval |
| Script parsing | Existing conservative text/Fountain-style breakdown | Fountain parser packages, lxml FDX, reviewed PyMuPDF/pdfplumber layout extraction |
| Local AI interface | Development-only loopback service; later Lu-provided inference | Local Qwen/Gemma and other qualified models; constrained JSON, GBNF/Outlines |
| 3D build and geometry | **Blender-first** trusted scripts and real save/reopen audit, GLB/trimesh | USD interchange, Blender BVH, OR-Tools CP-SAT, Holodeck/Infinigen-style set dressing |
| High-fidelity realtime stage | Blender baseline is current verified production test target | Unreal Engine 5 + Sequencer/CineCamera/Control Rig as an **optional** adapter |
| Characters and motion | Approved local rig/GLB, 7-role retarget, weighted skinning, authored BVH/clip | MakeHuman/VRM/MetaHuman/other licensed rig sources; NLA, mocap libraries |
| Performance/contacts | Existing 06E1 pure-Python two-bone solver is preflight only | Verified Blender IK, gaze/hand constraints, facial shape keys, ARKit-style expressions |
| Cinematography/edit | Metric projection and persistent 24-fps shot sequence | Toric-space multi-actor camera composition, camera rigs, OpenTimelineIO |
| Speech and sync | Speaker identity and measured dialogue-duration records | Piper/Kokoro/F5-TTS/XTTS/Chatterbox; WhisperX/MFA; Rhubarb/other visemes |
| Sound and lighting | Planned parameterized scene-bound design; not end-to-end implemented | pyroomacoustics/Steam Audio, Reaper/Ardour/pedalboard, practical light rigs, OCIO/ACES |
| Render/output | Blender Workbench native audit preview as tested engineering gate | Eevee/Cycles or UE5 offline media passes; FFmpeg mastering; optional conditioned video finishing |
| Validation | Deterministic constraints plus independent Blender reopen/audit | VLM cinematic quality critic; ACES QC, render passes, controlled generative comparison |

**Evaluation rule:** A research paper or named library is evidence of an approach, not proof of integration, license suitability, platform compatibility, or production quality. Choose dependencies after a measured need and capability/license test. Avoid per-stage permanent heavyweight model residency. Do not hard-code NVIDIA CUDA; measure physical Windows AMD execution and Linux development separately.

### 6.1 AI Film Crew roles

Director/planner, writer, script supervisor/continuity, production designer, DP/camera planner, acting coach, sound designer, editor and QA critic are *roles*, not necessarily separate simultaneous models. Each produces a reviewable typed proposal with explicit source IDs, version, uncertainty and reasoning summary. Roles consume only authorized project context. A critic's suggested fix never automatically supersedes a human-approved take.

### 6.2 Visual output strategy

First deliver a complete **deterministic 3D-to-video film**. It should be possible to create an intentionally simple but coherent film without a video diffusion model. Then benchmark optional structural conditioning (depth, segmentation, pose, identity, camera paths) and style enhancement. Any fine-tuning or new world-model research needs a demonstrated failure, a lawful dataset, hardware cost measurements and an independent comparison baseline.

## 7. Actor and performance design

A performance is more than skeletal joint keys. Link every scripted beat to a reviewable **Performance Card**: actor ID, objective, tactic, emotion/valence and arousal, subtext, gaze/listener target, energy/tempo, wardrobe/prop state, scene-local start/stop times, motion source and contact intent. AI may propose these cards; the director can edit or override them. Motion then follows a layered sequence:

1. Preserve approved body/root path and scene-time schedule.
2. Retrieve or author a permitted motion clip, normalize/retarget it to an explicit verified rig.
3. Apply validated foot and hand contacts, gaze, head/body posing and eventually procedural micro-motion.
4. Drive facial expressions and mouth/visemes from the character's licensed voice/timed dialogue.
5. Evaluate geometry, collision, limits, foot skating, prop attachment, speaking/listening eyelines, silhouette and continuity over the whole shot.
6. Save versioned actions/takes; independently reopen and evaluate native geometry before director approval.

No arbitrary bone-name guessing, automatic facial identity generation, unlicensed source motion, or invented missing keyframes may be reported as verified performance. The character may be visibly simple at first; reliable geometry and intentional acting come before photoreal polish.

### 7.1 NVP-PROD-06E: specific design gate for foot IK

**Current [V]:** PROD-06D imported a real Cesium Man skinned humanoid and audited retargeting and deformation; PROD-06E1 established bounded preflight math; PROD-06E2A independently verified the eight real left/right bone identities and rest hierarchy; PROD-06E2B now applies approved **ankle-lock two-bone IK** to real imported thigh/shin pose bones, bakes keys and independently compares a saved/reopened Blender scene against the untouched baseline. Neither the 06D lowest-mesh-vertex proxy nor the 06E2B ankle joint proves physical **shoe-sole contact**. Moving-root locomotion, dynamic-floor support, sole geometry and knee-biomechanics remain future work.

**Required next design-to-code contract [B]:**

- Introduce separately approved **left and right** hip/thigh, knee/shin, ankle/foot and pole targets, bound to **verified actual imported bone names, rest matrices, hierarchy, segment lengths and scene coordinate transforms**. The seven prior retarget roles alone are insufficient evidence for complete anatomical chains.
- The director selects the floor/surface, stance/contact windows, target anchors, correction allowance, bend direction and purposeful exceptions. Contact on a moving platform must bind to a stable platform-local anchor, not global ground zero. Sliding tolerance and ground penetration thresholds must be measurable.
- A contact record is tied to the exact approved character/retarget plan, asset SHA, motion clip, take, frame range and revision. Stale or different-project changes refuse export. Approval checks occur *before* Blender execution and are rechecked by the audit process.
- Solve in a declared coordinate frame, with target/root transforms and bone orientations explicitly converted. **Do not rewrite approved root trajectories or camera keys** to fake stationary feet. Refuse unreachable, degenerate or unsafe solutions; expose residuals and require a human choice rather than silently moving a foot or stretching a limb.
- Apply actual Blender pose constraints/keys through fixed trusted code; render and reopen the baked file. Evaluate **foot-specific** marker trajectories, sliding during declared contacts, ankle-floor separation/penetration, segment-length conservation, knee direction, bone ceiling, skinned mesh deformation, obstacle intersections, and unchanged camera/root/identity/approval hashes.
- Test neutral standing, single-foot plant, alternating gait, simultaneous support, turns, slopes or displaced surfaces, moving actor root, unreachable steps, rig-axis mismatch, cancellation/restart and explicit creative violations. Use licensed real external rig evidence (pinned Cesium Man) **plus** synthetic adversarial fixtures. A geometric proxy is never a replacement for the real-human audit.
- Linux and Windows must complete actual Blender save/reopen and numeric audit. A headless Windows GPU limitation may omit the preview PNG but not native geometry verification; Linux renders a real preview. Compare identical clips with/without IK, report per-frame residuals and measured runtime/peak memory.

**Definition of done for the entire physical foot-contact gate:** approved leg/sole geometry; deterministic stance and IK; native Blender application; independent mesh-contact and joint-angle geometry verification; actual audited external character on Linux/Windows during **moving-root gait**; documented limitations. **The narrower 06E2B ankle-marker lock is verified but does not close this full criterion.** A unit-test count or pleasing preview cannot satisfy it.

**Important known boundary [O]:** "physically credible gait" requires dynamics/contact timing beyond a two-bone kinematic solution. Do not claim full locomotion or film-grade acting merely because the foot lock passes. A subsequent motion/quality milestone must evaluate walk/run/turn, hands/props, gaze and performance cards.

## 8. Camera, light, sound and editorial design

### 8.1 Cameras

Shot recipes define subjects/listeners, framing, sensor, lens, perspective, focus, lead/head room, intent, duration and movement. The conventional solver must compute camera transforms from real staged geometry, reject or quantify collision/occlusion, report framing residuals, and diagnose multi-subject infeasibility. Coverage patterns (master, singles, OTS, inserts, action follow) are data libraries. Screen-direction, eyeline, 180-degree and 30-degree rules are **warnings with intentional overrides** when the director makes an explicit choice, not blanket prohibitions.

### 8.2 Lighting and styles

Typed rigs map script time/weather/practicals and artist-selected mood to actual named lights, exposure and consistent color handling. Physical lights and camera exposure cannot depend only on an adjective in an AI prompt. Keep consistent color space and document ACES/OpenColorIO transforms if chosen. Style renders are repeatable derivatives of one approved shot/take or explicitly changed representation.

### 8.3 Voices, mics and sound

Each line has a canonical speaker and approved voice identity; synthetic voice use requires rights/consent metadata. Measured audio timing (not assumed words-per-minute) drives visemes, cues and camera scheduling. Virtual mic choice/placement should follow room/camera geometry; foley comes from explicit physical events such as verified foot contacts. Store dry originals, processed stems and mix decisions with timing/rights lineage. Loudness and sample-rate conversion must be measured before export.

### 8.4 Non-destructive editing

Editorial references immutable take versions by stable clip ID, source in/out frame, rate, audio stem ID, transition and approval. OpenTimelineIO is a candidate interchange, not a dependency already deployed. A cut points to source takes; it cannot quietly erase the underlying production state. Final video requires real frame encoding, coherent audio sync, project/source manifest, and independent decode/playback inspection.

## 9. Verification, quality and release gates

**Evidence ladder:** static schema/AST → local unit tests → integration and restart tests → native engine save/reopen plus independent audit → licensed external asset acceptance → rendered media QA → end-to-end playable film → target-OS user and hardware acceptance. Passing one level does not imply later levels.

**First meaningful vertical slice [C/B]:** a **60–90 second, two-person interior scene** with the same actors and set across **6–8 approved shots**, correct spoken dialogue and reactions, timed performances, deliberate camera coverage and exportable **1080p at 24 fps with synchronized sound**. Reopen the project after restart, alter one scene decision, and demonstrate bounded rework of only its dependent shots. Examine the actual encoded movie, not merely the render script.

**Representative continuity stress case:** an actor meets a fixed obstacle, stops/turns without penetration, is seen from several cuts, speaks to a correct listener, and retains consistent costume, body/face identity and prop state. Repeat across intentionally different styles without allowing output-specific identity drift.

**Quality metrics to capture:** valid scene geometry; project/asset/license integrity; actor/prop continuity; camera framing residuals; contact slide/penetration and limb-length errors; correct speaker/viseme and audio alignment; repeated-shot action order; local edit repair cost; CPU/GPU/VRAM/peak RAM, latency and render time; cancellation/restart; deterministic rerun checks. **Numerical thresholds not already specified in a subsystem contract remain [O] and must be established from measured baselines before being called acceptance criteria.**

**Security/rights gate:** limit import bytes and parser complexity, prohibit model-authored arbitrary code, isolate untrusted Blender/media parsing in a host-supervised worker when shipped, record licenses/source hashes and voice/likeness consent, and forbid unauthorized network activity. CI success alone does not prove safe arbitrary real-world asset handling.

## 10. Actual baseline as of 2026-11-03

This table describes code and observed tests on the active *development branch*, not the default main branch and not a shipped consumer film system.

| Milestone | Scoped implementation/evidence | Status |
| --- | --- | --- |
| Story foundation and WR01–WR06 | Local screenplay drafts/history, approved Bible and knowledge/chronology, scene-mind model, reviewable proposals | Implemented in developer services; real-model creative quality and end-to-end UI remain separate |
| PROD-01–04 | Deterministic scene, approval, WorldState overlays, immutable GLB import, actor A* paths, metric cameras, native Blender audit harness | Implemented; see engineering acceptance; old documents contain earlier host-specific "Blender missing" statements |
| PROD-05 | 24-fps, revisioned shots/cuts/dialogue timing and Blender export | Implemented with targeted native acceptance |
| PROD-06A/B/C | Seven-role authored/BVH motion, weighted skinning, registered rigged GLBs and explicit bone mapping | Implemented with scoped native regression |
| PROD-06D | Licensed pinned Cesium Man external humanoid rest-frame calibration and saved-file geometry audit | **Verified Linux and Windows workflow** in GitHub run 41579956711 at commit fc1877e; Windows geometry-only does not assert GPU preview |
| PROD-06E1 | Pure-Python two-bone foot-plant mathematical preflight, tests and bounds | Implemented; CI run 41584304356 completed successfully; **not native IK** |
| PROD-06E2A | Explicit eight-bone left/right anatomical leg identity and Blender rest-hierarchy observation | **Verified** real Cesium Man source rig on Linux and Windows Blender 5.2.3, workflow run 41655290749; measured source-rest upper/lower/foot lengths; **no IK applied** |
| PROD-06E2B | Explicit bilateral contact windows/poles, stage-scale-aware armature-space IK, actual thigh/shin keys, independent pristine-vs-reopened full-take validation | **Verified scoped native ankle-lock** on Linux and Windows Blender 5.2.3, workflow run 41659667221; 120 frames each, maximum ankle residual 6.3361e-7 m, local segment-length residual 6.9276e-7 m; **not sole contact or gait** |
| PROD-06E2C1 | Read-only native candidate foot mesh survey using imported ankle/toe deform groups during approved IK stance windows | **Verified scoped native survey**, Linux/Windows Blender 5.2.3, run 41662467122; candidate lowest vertices ~6.8 mm below assumed Z=0; **not physical sole contact** |
| PROD-06E2C2 | Versioned heel/ball/toe mesh-vertex indices, real NVP_FLOOR geometry digest and per-frame Blender collision/clearance measurement | **Real native Linux/Windows measurement verified** in run 41665538274; physical contact **failed** fixture tolerances, heuristic markers not anatomically certified; full Python regressions repaired separately |
| PROD-06E2C3 and later | Validated plantar masks/ground-truth heel/metatarsal/toe references, mesh-BVH floors, moving-root and joint biomechanics, contact correction | **Not complete** |
| Lu Workspace package | Signed, registered, contained NVP DLC running inside Lu | **Deferred and not verified** |
| Physical target machine | Windows NVP film workflow with AMD R9700 GPU, finished output, integrated input | **Not yet verified** |

**Evidence references:** see docs/PROD01_TO_PROD04_ENGINEERING_ACCEPTANCE.md, docs/PROD05_TIMED_SHOT_SEQUENCE.md, docs/PROD06_RIGGED_MOTION.md, docs/PROD06B_WEIGHTED_SKIN_RETARGET.md, docs/PROD06C_RIGGED_CHARACTER_IMPORT.md, docs/PROD06D_EXTERNAL_CHARACTER_CALIBRATION.md, docs/PROD06E1_FOOT_PLANT_PREFLIGHT.md, docs/PROD06E2A_LEG_IDENTITY.md, docs/PROD06E2B_ANKLE_LOCK.md, docs/PROD06E2C_SOLE_REGION_AUDIT.md, and docs/PROD06E2C2_PLANTAR_GEOMETRY.md. Independent scoped evidence: https://github.com/vjmichael/nvp_offline_film/actions/runs/41579956711 (06D), https://github.com/vjmichael/nvp_offline_film/actions/runs/41584304356 (06E1),  https://github.com/vjmichael/nvp_offline_film/actions/runs/41655290749 (06E2A native identity), and https://github.com/vjmichael/nvp_offline_film/actions/runs/41659667221 (06E2B Linux/Windows native ankle IK).

## 11. Ordered engineering roadmap, with exit conditions

| Gate | Deliverable | Cannot be declared finished until |
| --- | --- | --- |
| NVP-DESIGN-00 | This cross-subsystem master baseline and source traceability | Master exists in active repo, linked for discoverability; open options labeled |
| NVP-PERF-01 / PROD-06E2B | Completed *scoped ankle IK* on explicitly mapped imported rigs | Independently reopened ankle-lock, preserved roots/cameras and original non-contact motion on Linux/Windows: **verified** |
| NVP-PERF-01C / PROD-06E2C3 | Produce physically credible, independently verified sole contact on moving characters | Artist-certified plantar contact region, per-frame independent skinned mesh-floor tests, joint limits, moving-root gait, and transition continuity on external rigs |
| NVP-CHAR-01 | Anatomically credible character structure: proportions, skeletal joints, physical constraints, mesh topology and weighted skin deformation | More than one licensed character/shape, measured geometry, pose/collision tests, stable skin volume and independently reviewed rendered performances |
| NVP-PERF-02 | Performance cards, contact-driven movement, gaze, prop handling | Scene actions and listeners perform visibly correctly across cuts; repeatable native checks |
| NVP-CAMERA-02 | Moving virtual camera, coverage patterns, depth/occlusion validation | Measured actual-frame camera paths, edits and deliberate cinematic overrides |
| NVP-LIGHT-01 | Motivated lighting, exposure and style management | Scene/camera-consistent rendered passes with color/provenance checks |
| NVP-VOICE-01 | Licensed local speech, speaker timing, visemes, dialog stems | True audio measured and synchronized to character and shot frames |
| NVP-AUDIO-01 | Spatial microphone presets, ambience, foley and mix | Sound tied to shot geometry/contact/time; loudness and sync acceptance |
| NVP-EDIT-01 | Versioned non-destructive multi-shot editorial representation | Timeline references immutable takes and passes cut continuity validators |
| NVP-MASTER-01 | 60–90 second playable film vertical slice | Reopen, regenerate targeted shot, render/export/decode actual 1080p24 movie with sound |
| NVP-HOST-00–05 | Integrated Lu Film Workspace DLC *after Lu v1.0* | Signed admission, typed scoped IPC, shared model, containment, restart/cancel/cleanup on target OS |
| NVP-RESEARCH | Optional conditioned generative finishing and learned physical support | Beats deterministic baseline on recorded quality, cost, consistency and rights criteria |

This roadmap is dependency-based rather than a rigid promise about dates. Work in parallel only when source IDs, types, approval boundaries and recovery semantics are fixed. **The next solver task starts only after this master baseline is established; no solver completion is implied by this document.**

## 12. Open architecture decisions — do not silently settle these in code

1. **[O] Canonical exchange schema:** when a portable USD scene layer becomes useful versus the existing versioned JSON/GLB/Blender-derived scene. Preserve IDs and authorship in any adapter.
2. **[O] Full character rig contract:** beyond the current seven roles, how to represent human and nonhuman joint chains, joint axes, hierarchy, joint limits and rig-dependent contact semantics; what constitutes a quality-certified rig.
3. **[O] Realistic locomotion quality:** measured thresholds for foot skate, penetration, stance slippage, arm/prop interaction, facial and emotional fidelity, and whether a dynamics solver is justified.
4. **[O] UE5 role:** optional high-end runtime/Sequencer integration and asset interchange after a complete Blender deterministic vertical slice, not a prerequisite that blocks first film delivery.
5. **[O] Speech and license portfolio:** which fully local voices, aligners, facial rigs and stock/mocap/asset libraries have acceptable license/performance characteristics on target hardware.
6. **[O] Portable editing interchange and color management:** exact source frame/timecode policy, OTIO/FFmpeg adapters, color transforms, artifact format, and archive structure.
7. **[O] Hardware resource admission:** measured AMD Windows and Linux rendering/inference compatibility, VRAM peak, process containment and worker scheduling when hosted by Lu.
8. **[O] Measured release thresholds:** real-film acceptance numbers for collision, sync, 3D consistency, photoreal finish, repair time and render throughput.
9. **[O] Automated quality critique:** which assertions remain hard deterministic checks and which subjective evaluations may use a VLM without vetoing director intent.
10. **[O] Exact Lu DLC registration:** package signing/version, actual Workspace API/tool codec, effect declarations and review UX when Lu integration is authorized.

## 13. Source traceability and reconciliation

**Direct working source files:** README.md (original mission and preserved proprietary terms); docs/SOLO_CREATOR_DIRECTION.md; docs/IDEA_SCREENPLAY_VIDEO_PIPELINE.md; docs/LU_DLC_WORKSPACE_CONTRACT.md; docs/PROD01_TO_PROD04_ENGINEERING_ACCEPTANCE.md; all PROD-05/06 milestone specifications; approved Bible and chronology/Scene Mind docs; and implementation modules/tests on the development branch.

**Historical architecture, preserved rather than replaced:** docs/NVP_WORLD_AWARE_FILM_STUDIO_DESIGN.md on branch docs/nvp-world-aware-film-studio-design-2026-10-26. Its enduring principles—canonical WorldState, identity/style separation, director approval, optional world-model/render finishing, independent evidence—are carried forward. Its older suggestion of UE5 as a necessary first engine and older Lu delivery ordering are superseded by the newer Blender-first engineering baseline and explicit deferment until Lu v1.0.

**Creator-supplied conventional reference:** claude-filmproduction(1).txt (110-line archived design) describes Fountain/FDX/PDF parsing, SQLite+retrieval/graphs, named anchors, asset sources and rights, OR-Tools layout, rigs/mocap/IK, acting performance cards, Toric-space cinematography, virtual mics/audio, motivated light rigs, OTIO, and orchestration by typed AI proposals. These are reflected as **candidate tool choices**, not claims that all are integrated.

**Other source referenced by PROD-01–04:** film-world-model-toolchain.md, previously supplied during NPV 01, is cited in those engineering records. The full original attachment was **not independently retrievable in this consolidation pass**; do not assert an exact verbatim concordance or silently invent passages. Its known endorsed principle—persistent editable physical world plus AI/deterministic division—is corroborated by the checked implementation and subsequent decisions. Reconcile any newly recovered unique requirements through an explicit master revision.

**Change discipline:** record new decisions as a dated design amendment or ADR with who authorized it, why, status [C]/[B]/[O]/[K]/[V]/[D], affected modules and migration/verification requirements. Keep the implemented-status table synchronized with actual test links. Never edit a past result to look like an independent acceptance that did not occur.

---

**Master baseline established for NVP, not a feature-completion certificate.** Next authorized implementation scope: real character foot IK, beginning with actual leg-chain identity, approval dependency, and independent Blender geometric acceptance.

**2026-11-03 external set geometry research note:** More accurate buildings/sets may be sourced via type-checked IFC and imported assets instead of procedural boxes. Evaluate [IfcOpenShell/Bonsai](https://github.com/IfcOpenShell/IfcOpenShell) for real architectural topology and [Poly Haven CC0](https://polyhaven.com/license) for scanned materials/props only after measured, rights-reviewed importer acceptance. Neither is presently a required production dependency.
