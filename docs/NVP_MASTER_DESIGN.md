# NVP MASTER DESIGN — World-Aware Personal Film Studio

**Document ID:** NVP-MASTER-001  
**Revision:** 1.1 — 2026-11-03  
**State:** Established architecture and product-requirements baseline; individual open decisions remain explicitly open  
**Product:** Neural Virtual Production (NVP), the future Film Workspace DLC for Lu  
**Development baseline:** nvp/prod06e2c3b-anatomical-landmarks-bvh-20261103  
**Scope of this revision:** Design consolidation plus creator-approved **data-first capture/presentation/editing architecture amendment**. No new capture pipeline, model adapter, renderer or editor implementation is claimed as complete.
**Governing amendment:** [NVP-ADR-DATA-FIRST-001](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md), with [technical package/index specification](NVP_DIGITAL_FILM_PACKAGES_AND_REGENERATION.md).
**Later creator-approved engineering policy:** [NVP-ADR-STACK-001 — Reuse-first component adoption and one installer](NVP_ADR_STACK01_REUSE_FIRST_AND_ONE_INSTALLER.md). It governs implementation method and supersedes any previous implied preference for custom processing algorithms.
**2026-11-05 AI-accessibility architecture review [O]:** [NVP-AI-01 — AI-accessible NVP internals](NVP_AI_ACCESSIBLE_ARCHITECTURE_REVIEW_20261105.md). The creator directed NVP to become easier for AI to assist humans; the linked document audits current strengths and proposes implementation gates. Its new protocol details remain design proposals until separately implemented and accepted.

> **Governing idea:** NVP creates **the structured, creator-approved data from which a film is captured and produced**, not merely unrelated AI-generated video clips. An editable Digital Film World supplies immutable Digital Take Packages; selectable conventional or AI engines produce versioned Presentation Packages; an indexed editor assembles those outputs into a final 2D film. Lo-fi preview is the director's inexpensive visualization, not the full production data or final visual quality. AI proposes or renders; verified domain data and the director remain authoritative. **The flat movie is a deliverable, not the only editable source.**

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

### 0.1 Reuse-first production engineering [C] — mandatory, 2026-11-03

The creator directs that NVP **reuse, repurpose and bundle existing, mature filmmaking software rather than reimplement standard operations**. A custom algorithm may be developed only for a **specific demonstrated operation** that existing licensed software, supported plug-ins or a composition of existing engines cannot perform adequately. The decision requires documented alternatives, a reproducible benchmark, license/deployment assessment and narrow creator-reviewed scope.

NVP is the **authoritative Digital Film World / Digital Take / orchestration and verification product**, not another independent video editor, color-science library, 3D renderer, compositor or audio DSP suite. Third-party programs and libraries may be embedded in a **single offline-first NVP desktop installer** subject to exact license, dependency, provenance and safety checks. Minimal adapters, typed records, worker management, identity-preserving interchange and permission/approval validation are NVP's custom integration work.

Immediately audit current homegrown grading curves and image routines against **OpenColorIO/OpenImageIO**, editorial against **OpenTimelineIO/MLT**, compositing against **Natron/OpenFX**, staging and animation against **Blender/OpenUSD and proven solver/motion tools**, and sound against established audio engines. Preserve original source/take immutability and independent output verification. **Do not silently migrate existing data, remove working code, or claim a package is legally redistributable without actual evidence.**

This is binding implementation guidance; consult [NVP-ADR-STACK-001](NVP_ADR_STACK01_REUSE_FIRST_AND_ONE_INSTALLER.md) for criteria and ordered tests. Earlier detailed feature-roadmap entries remain desired *capabilities* but no longer imply bespoke implementation.

### 0.6 Filmmaker-visible RAM/VRAM admission and production progression [ENGINEERING] — STACK-02C3

Every serious local task (model load/warmup/inference/offload, Blender/animation/render, compositing/encode) belongs to one shared **computer-resource and progress** concept. The filmmaker must see NVP's real RAM and VRAM headroom, *its own reserved task budgets*, which engine/task is working, why another is queued, and each **measured stage**—never a fake percentage or an invisible hang. The default profile is conservative, favors PC responsiveness, and cannot silently consume the entire RAM/VRAM allocation. Resource metadata and task phase events are durable and polled through NVP's native read-only API; the workspace UI always has a compact accessible progress center. Missing GPU telemetry is a reason to hold GPU work, not to invent capacity.

**Implemented development foundation:** standard Win32 RAM and DXGI per-process video-memory budgeting, Linux MemAvailable/PSI and AMD DRM GPU counters, optional NVIDIA NVML; cross-process SQLite FULL-sync reservations; RAM **max(2 GiB, 20% host)** and VRAM **max(1 GiB, 20% selected budget)** admission reserves; measured task-phase progress/unknown-percent spinners; OS-supervised Blender protected execution with two-sample critical-memory shutdown; stale heartbeat warning without falsely releasing a possibly active process. The writer's external local model server is currently **observed** rather than owned, and no claim is made that NVP loads/offloads its models or controls their VRAM. [Detailed design/acceptance and open gates](NVP_STACK02C3_RESOURCE_GOVERNOR_PROGRESS_AND_PC_SAFETY.md).

**Required follow-up:** true RAM/VRAM contention on Windows AMD Radeon and installed app, provider-managed AI load/unload ownership+progress, automatic priority/queue dispatch, true source-measured render progress, full engine-path adoption, OS-reconciled stale reservations, and packaging. NVP user consent is mandatory before unloading a model shared with another app. No film/take original is modified by these scheduling decisions.

### 0.5 Strict delegated Linux whole-Blender-process-tree custody [ENGINEERING] — STACK-02C2

The Linux worker now supports explicit, content-hashed **`require_linux_cgroup_v2=True`** tasks. This selects the *established cgroups v2 kernel*, not an NVP-built process sandbox: discover a systemd `Delegate=yes` scope, enable `memory` and `pids` controllers within that delegated boundary (requiring `DelegateSubgroup` for the NVP host), move the pinned Blender worker into its own resource-bounded leaf **before** `execv`, and start an independent guardian **outside the worker cgroup** before any Blender code executes. On hard NVP host exit, guardian receives a kernel pipe EOF and writes to **`cgroup.kill`**, covering detached descendants that would escape the previous process-group/parent-death mechanisms. The guardian must observe `cgroup.events populated=0` before source-audited job acceptance.

**Measured technical gate:** Four actual delegated kernel tests passed, including a host `os._exit` while a direct worker and separately-sessioned grandchild were running. Actual pinned Blender 5.2.3 independently passed its scene build, real PNG/.blend, nine-check original source geometry re-audit, cancellation and bad-worker refusal under strict cgroup containment. Existing Windows Job Objects and legacy development regressions remained green. [CI 41770547351](https://github.com/vjmichael/nvp_offline_film/actions/runs/41770547351) passed **5/5 jobs**, adding direct **Blender 5.2.3 and Ubuntu Blender 4.0.2 real-app host-hard-crash tests**: each launched a detached grandchild, NVP exited via `os._exit(37)`, kernel guardian killed all processes, removed the cgroup and recovered the job as INTERRUPTED rather than accepting abandoned output. A normal Linux session without cgroup delegation **refuses strict execution**; no Docker, sudo or undelegated systemd cgroup edits are acceptable fallbacks.

**Release boundaries:** strict Linux mode is **opt-in** pending production systemd user-service installation/delegation. This does not establish GPU VRAM safety, final commercial distribution, a whole-film GPU renderer test or comprehensive Blender path migration. The hard-exit process-tree test and the pinned Blender strict-mode test are independent; a combined Blender-specific hard-crash case remains valuable. [Full source-level acceptance report](NVP_STACK02C2_LINUX_CGROUP_WHOLE_TREE.md).

### 0.4 Multi-instance exclusive production-worker custody and native Windows Blender [ENGINEERING] — STACK-02C

**Accepted technical gate:** Windows and Linux NVP worker journals now use a **kernel-backed cross-process owner lease** around each Blender execution and cold-start recovery. Competing hosts cannot claim the same workspace while its current owner is rendering; hard host exit releases the lock, and later recovery still marks incomplete jobs INTERRUPTED instead of inventing success. The lease is local single-machine filesystem authority, **not** a distributed network lock or a licence for independent unrelated hosts to mutate the Film World.

**Genuine Windows engine proof:** Official SHA-verified portable Blender 5.2.3 was independently launched under the existing Windows Job Object, generated a real .blend and PNG, then re-opened the creator-approved original ProductionScene through a separate native Blender process with **9 identity/geometry assertions passed**. GPU-less Windows CI uses **Blender Cycles CPU** because the Workbench renderer crashed during WGL/OpenGL initialization; no custom renderer was added. Linux real Blender remained independently accepted. [All four jobs passed in GitHub run 41767354797](https://github.com/vjmichael/nvp_offline_film/actions/runs/41767354797).

The authoritative World, frozen Digital Takes, approved-scene and original FilmIndex provenance contracts are unchanged. Further engineering gates remain mandatory for **Linux whole detached-process-tree cgroup cleanup**, VRAM/system-RAM load guards, complete Blender/Cycles animation-path migration, packaging and GPL compliance. [Detailed STACK-02C evidence and task list](NVP_STACK02C_HOST_LEASE_AND_WINDOWS_BLENDER_ACCEPTANCE.md). This is not a release-ready installer.

### 0.3 OS-contained native Blender production work [ENGINEERING] — STACK-02B

Following the accepted external Blender worker and durable SQLite ledger, NVP now uses **Windows Job Objects (suspended-first execution, kill-on-close and bounded job committed-memory)** and **Linux kernel parent-death signaling with a bounded address-space cap**. In both cases Blender is still an independent executable; this is host integration, not a new rendering engine or a GPL library linked into NVP. The source/take/film custody and creative approval rules do not change.

The actual limits of Linux `PR_SET_PDEATHSIG` are explicit: it kills the immediate Blender worker after a hard supervising-thread/process death, but does not establish descendant-tree cleanup equivalent to cgroups v2. Windows Job Objects can cover the child tree and require direct process-tree crash tests. Neither mechanism is GPU VRAM control or multi-instance host leasing.

See [STACK-02B implementation, measured acceptance and open gates](NVP_STACK02B_OS_WORKER_CONTAINMENT.md). Next tasks: Linux cgroup or guardian tree guarantee; actual Windows Blender native worker validation; multi-instance worker-lease protection and all-path supervisor migration; hardware memory/VRAM load guardrails; single NSIS installer with license/SBOM/source notices. Do not claim those as complete based on a job-level unit test.

### 0.2 Blender-first GPL-aware external-worker boundary [C] — approved 2026-11-03

NVP will use **Blender as its primary independent 3D production worker** for scenes, actors, animation, lighting, cameras and rendering. NVP remains a **separate proprietary orchestrator**; job data and derived artifacts cross a standards-based file/CLI boundary instead of linking Blender GPL libraries into the NVP process. Distributable `bpy` adapters must be separately GPL-reviewed/licensed. Original Digital Film World and frozen Takes remain authoritative; `.blend` and rendered EXRs are derived versions. **A separate OpenUSD runtime is deferred**, not required for the baseline installer; Blender-native USD import/export is available for limited interchange, with actual composition fidelity checked before use. Only a *demonstrated multi-application layer/reference/variant composition gap* justifies independent OpenUSD integration. See [NVP-ADR-STACK-002](NVP_ADR_STACK02_BLENDER_WORKER_USD_DEFERRED.md). Commercial packaging remains gated by real redistribution compliance and native worker acceptance.


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

**New capture/render/editor distinction [C/B]:** Filming occurs against cheap proxy/LOD geometry and cached draft audio, while capturing **camera, actors, world, props, dialogue, timing and production approvals** as a frozen, immutable Digital Take Package, **not a low-quality video as the only master**. One take can be interpreted into multiple presentations using different permitted styles or generators. The user can edit that take's source or rerun only affected presentations, then assemble a flat 2D movie with audio. All versions remain indexed. See the [data-first ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md).

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

### 3.4 Digital Film World -> Digital Take -> Presentation -> Final Film [C/B]

**New formal product architecture (2026-11-03):** See [NVP-ADR-DATA-FIRST-001](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md) and [NVP-DATA-SPEC-001](NVP_DIGITAL_FILM_PACKAGES_AND_REGENERATION.md).

| Production layer | Authority | Why it matters |
| --- | --- | --- |
| **Digital Film World** | Mutable only through reviewed, versioned changes to authoritative film records: story, scenes, actor/asset identity, spatial environment, style, lighting, performance intents, cameras and sound | Defines the world and actions, independent of preview quality |
| **Digital Take Package** | Immutable approved snapshot/manifest of specific scene and time interval, camera/mic/performance, dialogue/sound timing, and exact frozen asset/scene references | Can be reproduced, audited, branched and processed again without re-filming |
| **Presentation Package** | Derived video/audio/render passes and receipts produced by a selected conventional or AI backend, with style, model, constraints and quality review | One take may generate many visually different presentations, without secretly rewriting source |
| **Editorial revision and final 2D master** | Exact selected presentations/audio, cuts and mix, then decodable video file with lineage receipts | Audience sees a flat film, but director retains every editable production layer |

**Single indexed graph:** stable project-scoped IDs, content digests, typed dependency links, versioned approvals and backwards/forwards lookup connect the layers. A new world revision does not mutate a frozen take. Presentation revisions cannot rewrite world canon. A request to change only one actor, line, shot, camera or style re-executes **only the actual dependent shot/time window**, including temporal overlaps as needed by the chosen model; unaffected approved hashes remain intact.

**Low-spec contract:** no user requirement to keep hi-fi assets or diffusion/voice models resident while directing or editing. The lo-fi stage is an efficient **visualization of authoritative production data**. Expensive rendering or generation runs later, per selected scope, with measured resource admission and recoverable outputs. A creator can select video and voice engines independently, while adapters must disclose unsupported conditioning. The host or Lu schedules worker loading/unloading; model runtime requirements remain real.

**Acceptance priority:** demonstrate the complete Digital Film World -> frozen Digital Take -> two presentations -> source-aware selective revision -> playable 2D film vertical slice **before** treating advanced foot anatomy/photorealism as a blocker. Existing Blender geometry/rig work remains relevant but is not proof of this pipeline.

## 4. Stable production data model and invariants

All data stores use project-scoped opaque IDs, typed schema versions, explicit reference ownership and semantic units. SQLite transactions protect authoritative records. SHA-256 content digests identify immutable source bytes, approval input graphs, and outputs. An approval hash is evidence of an exact reviewed revision, not a substitute for a trusted authorization boundary.

| Record family | Required identity and content | Key invariant |
| --- | --- | --- |
| Project/Film | Project ID, working data root, style profiles, format, history | Cross-project reads/writes forbidden |
| WorldRevision/SceneRevision | Project-scoped accepted exact revisions, approved dependency manifests and source hashes | A current edit cannot mutate an earlier captured take |
| DigitalTake/TakeManifest | Take ID, immutable capture SHA, actual approved scene revisions, camera/performance/audio time tracks and asset references | Capture is frozen; revisions create new captures/branches, not in-place overwrites |
| PresentationRevision/ProductionJob | Presentation ID, exact take SHA, model/backend/style/conditioning, audio/video passes, status and output digest | Rendering/AI may not rewrite source; unsupported model controls must be surfaced |
| EditorialRevision/FilmMaster | Selected precise presentation/audio spans, cuts/mix, encoded flat film and output lineage | Re-editing/rerendering preserves source, unrelated takes and historical masters |
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

First deliver a complete **deterministic data-first 3D-to-video film**: proxy visualization -> approved immutable capture -> conventional 3D presentation -> edit -> decodable final 2D film. It should be possible to create an intentionally simple but coherent film without a video diffusion model. Next, generate additional presentations of the *same captured take* and benchmark optional structural conditioning (depth, segmentation, pose, identity, camera paths), user-selected video/voice models and style enhancement. Unsupported controls require explicit warning/refusal; output-model hallucinations are not source truth. Any fine-tuning or world-model research needs demonstrated failure, lawful data, hardware cost measurements and independent comparison. Keep interactive filming separate from heavy AI model residency.

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
| PROD-06E2C3A | Approval-bound, bounded skinned vertex-to-floor correction using actual imported thigh/shin IK, separate native output, independent full-take source/output audit | **Verified scoped real toe-marker contact** on Linux and Windows Blender 5.2.3, run 41670220453: 120 take frames, 25 modified contact leg-frames, 215 preserved noncontact leg-frames; limb-length residual below 0.0000004 m; **not certified plantar anatomy/gait** |
| PROD-06E2C3B | Provenance-bound heel/MT1/MT5/hallux underside attachments; read-only skinned anatomy observation; actual Blender triangle BVH floor and slope support verification | **Cross-platform native BVH geometry verified**, Linux/Windows Blender 5.2.3, workflow run 41674405456: 25 real corrected toe-marker samples, zero penetration and max gap ≈0.273 mm; 12-degree sloped test verified and unsupported 70-degree slope refused. **No independently reviewed actual Cesium Man anatomical foot attachment has been supplied; physical anatomy certification remains blocked** |
| PROD-06E2C3C and later | Reviewed/rights-cleared actual plantar pad annotations, moving characters on sloped and changing floors, whole-skinned-mesh surface collision, support forces and true gait biomechanics | **Not complete** |
| NVP-DATA-FIRST-001 (creator decision) | Four-layer Film World -> frozen Digital Take -> indexed derived Presentation -> editorial/final film authority; model/backend choice; low-spec stage and selective re-render | **Documented and accepted as direction [C]; end-to-end engineering gates deferred**. See ADR and SPEC; no source/runtime feature implied |
| NVP-DATA-01A immutable film index | Shared Studio SQLite + SHA-addressed film blob store; typed immutable source/derived revisions, dependency graph and impact lookup | **Cross-platform Python/Blender workflow passed** run 41685642782: original Linux 419 (412 pass, 7 skip); docs/NVP_DATA01_FILM_LINEAGE_INDEX.md |
| NVP-CAPTURE-01A frozen real timed take | Director-approved 24-fps WorldState + ShotSequence (actor paths, two cameras, measured dialogue, approval proof) -> SHA-bound immutable world/performance/take, transactional stale-source guard; reopened source plays after director changes live WorldState | **Linux 428 tests (421 pass, 7 skip), native Blender saved/reopened/audited the original frozen take successfully on both Linux and Windows Blender 5.2.3 in run 41688771494.** Native Linux preview rendered; Windows geometry-only audit. **Not hi-fi/voice production.** docs/NVP_CAPTURE01_FROZEN_DIGITAL_TAKES.md |
| NVP-PIPE-01A Blender sampled/full presentation adapter | `PresentationPipeline` reads exact frozen CAPTURE-01, generates real Blender Workbench studio/flat media, verifies per-frame PNG dimensions/SHA and writes immutable presentation lineage; keyframes gives 2 stills per shot, full mode processes bounded frame range | **Implemented; 436 Linux Python tests (429 pass / 7 skip), real Blender 5.2.3 generated two distinct style presentations, independently reopened actual PNG media and verified unchanged source take in run 41691770710.** Windows Python/Blender status tracked separately. Does not yet offer neural video/voice, hi-fi assets, final video codec or editor approvals; see [PIPE-01A evidence](NVP_PIPE01A_FROZEN_TAKE_TO_PRESENTATIONS.md) |
| NVP-PIPE-01B1 full-motion PBR conventional renderer/MP4 | Same immutable approved take -> bounded **full-frame** Blender Workbench or Cycles CPU physically lit PBR presentations -> SHA-stored source frames and streamed immutable MP4 -> FFprobe frame/FPS validation and independent full H.264 decode; 48kHz timecoded dialogue metadata; restart/provenance checks | **Implemented, Linux 443 Python tests (436 passed, 7 skipped), native Blender+FFmpeg two real 16-frame MP4s at 24fps in run 41697002642 (PIPE-01B native step passed).** Existing proxies still underlie actors/sets; not photoreal actor geometry, no actual voice/audio track, no long film/editor yet; [PIPE-01B documentation](NVP_PIPE01B_FULL_MOTION_PBR.md) |
| NVP-PRO-01 professional mezzanine export | Authoritative Digital Take/verified full-frame presentation may be encoded into **H.264 MP4 review** and **ProRes 422 HQ 10-bit 4:2:2 MOV** editorial files without re-rendering or altering the film world; exact codec/tag/FPS/pixel format, content SHA and production lineage checked on reopen | **Implemented and independently verified: 445 Python tests (438 passed, 7 skipped), true ProRes 422 HQ MOV (`prores`/`apch`/`yuv422p10le`) + H.264 MP4 native decode, and all five cross-platform jobs passed in run 41700029191.** Current source PNG/characters are 8-bit proxy; 10-bit coding does not imply 10-bit scene detail or color-managed master. **DNx, ProRes 4444, OpenEXR, audio tracks and SMPTE theatrical DCP are distinct later gates.** See [professional delivery profiles](NVP_PROFESSIONAL_DELIVERY_FORMATS.md) |
| NVP-PRO-02A DNxHR HQX and guarded cinema DCP | Real DNxHR HQX MOV industry editorial encode, decode and content-hash provenance from frozen PBR frames; cinema DCP source preflight with 2K Flat/Scope SMPTE 24fps, sound/refusal and DCP-o-matic optional adapter; test-only package structure/asset SHA checks | **DNxHR native Linux step passed; 454 Python tests (447 pass, 7 skip); full Windows CI tracked in run 41710387683.** DCP package **not yet generated**: official DCP-o-matic 2.18.51 Ubuntu CLI download returned HTTP 403 in run 41709815064. No theater-readiness claim. See [PRO-02 report](NVP_PRO02_CINEMA_DCP_DNXHR.md) |
| Lu Workspace package | Signed, registered, contained NVP DLC running inside Lu | **Deferred and not verified** |
| Physical target machine | Windows NVP film workflow with AMD R9700 GPU, finished output, integrated input | **Not yet verified** |

**CAPTURE-01 implementation evidence:** docs/NVP_CAPTURE01_FROZEN_DIGITAL_TAKES.md · https://github.com/vjmichael/nvp_offline_film/actions/runs/41688771494. The new Linux/Windows native frozen-take acceptance steps passed; check independent conclusions for the remaining full-workflow jobs.

**Evidence references:** see docs/PROD01_TO_PROD04_ENGINEERING_ACCEPTANCE.md, docs/PROD05_TIMED_SHOT_SEQUENCE.md, docs/PROD06_RIGGED_MOTION.md, docs/PROD06B_WEIGHTED_SKIN_RETARGET.md, docs/PROD06C_RIGGED_CHARACTER_IMPORT.md, docs/PROD06D_EXTERNAL_CHARACTER_CALIBRATION.md, docs/PROD06E1_FOOT_PLANT_PREFLIGHT.md, docs/PROD06E2A_LEG_IDENTITY.md, docs/PROD06E2B_ANKLE_LOCK.md, docs/PROD06E2C_SOLE_REGION_AUDIT.md, docs/PROD06E2C2_PLANTAR_GEOMETRY.md, docs/PROD06E2C3_MESH_CONTACT_CORRECTION.md, and docs/PROD06E2C3B_FOOT_ANATOMY_AND_BVH.md. Independent scoped evidence: https://github.com/vjmichael/nvp_offline_film/actions/runs/41579956711 (06D), https://github.com/vjmichael/nvp_offline_film/actions/runs/41584304356 (06E1),  https://github.com/vjmichael/nvp_offline_film/actions/runs/41655290749 (06E2A native identity), and https://github.com/vjmichael/nvp_offline_film/actions/runs/41659667221 (06E2B Linux/Windows native ankle IK).

## 11. Ordered engineering roadmap, with exit conditions

| Gate | Deliverable | Cannot be declared finished until |
| --- | --- | --- |
| NVP-DESIGN-00 | This cross-subsystem master baseline and source traceability | Master exists in active repo, linked for discoverability; open options labeled |
| NVP-DATA-01 | Immutable film index/data objects, typed dependency graph and frozen-source storage (foundation implemented) | **DATA-01A Python accepted on Linux**, independently reopened real approved proxy scene and malicious/cross-project tests; final complete gate also requires capture-level integration, Windows evidence and source-lineage authoring in film UX |
| NVP-CAPTURE-01 | Frozen approved timed proxy world/sequence into source-hashed, indexed take **with native Blender replay from frozen data**, implemented for current proxy scope | CAPTURE-01A accepted: 24-fps camera/actor/dialogue data and source approvals independently reopened and natively replayed after live scene change on Linux and Windows. **Expanded audio sample clocks, full character/facial performance and hi-fi outputs remain subsequent gates** |
| NVP-PIPE-01 | Source-indexed multi-presentation pipeline with physically-based full-frame rendering and playable video (first conventional backends implemented) | PIPE-01A verified per-frame media lineage; PIPE-01B1 verified full MP4 and CPU Cycles PBR proxy presentation. **PIPE-01B2 still needs detailed licensed actor/set representation mapping and scaling/quality acceptance; PIPE-01C still needs real optional video/voice AI backend choice, adapters and scheduler** |
| NVP-RECOVERY-01 | Transactional capture/render jobs and recoverable media artifacts | Kill/restart on incomplete job leaves prior approved source/output unchanged and reconciles job journal |
| NVP-PERF-01 / PROD-06E2B | Completed *scoped ankle IK* on explicitly mapped imported rigs | Independently reopened ankle-lock, preserved roots/cameras and original non-contact motion on Linux/Windows: **verified** |
| NVP-PERF-01C / PROD-06E2C3C | Bind independently reviewed actual plantar landmarks to real characters, then integrate full-foot support and moving characters | Licensed and independently reviewed heel/MT1/MT5/hallux attachment, validated mesh floor/slope contacts, whole-foot penetration, contact force and turning/rolling gait |
| NVP-CHAR-01 | Anatomically credible character structure: proportions, skeletal joints, physical constraints, mesh topology and weighted skin deformation | More than one licensed character/shape, measured geometry, pose/collision tests, stable skin volume and independently reviewed rendered performances |
| NVP-PERF-02 | Performance cards, contact-driven movement, gaze, prop handling | Scene actions and listeners perform visibly correctly across cuts; repeatable native checks |
| NVP-CAMERA-02 | Moving virtual camera, coverage patterns, depth/occlusion validation | Measured actual-frame camera paths, edits and deliberate cinematic overrides |
| NVP-LIGHT-01 | Motivated lighting, exposure and style management | Scene/camera-consistent rendered passes with color/provenance checks |
| NVP-VOICE-01 | Licensed local speech, speaker timing, visemes, dialog stems | True audio measured and synchronized to character and shot frames |
| NVP-AUDIO-01 | Spatial microphone presets, ambience, foley and mix | Sound tied to shot geometry/contact/time; loudness and sync acceptance |
| NVP-EDIT-01 | Indexed source-aware editor, non-destructive timeline, presentation review and selective regeneration | Change one shot/line/style, preserve unrelated approved hashes, regenerate actual dependency scope, compare/rollback and verify cut continuity |
| NVP-MASTER-01 | Complete linked Digital Film World -> Take -> Presentation -> 2D film vertical slice | Reopen indexed world/take/presentations, selectively rerender a chosen shot, export/decode actual playable film with synchronized sound and provenance |
| NVP-PRO-01/02 | Professional edit/VFX/cinema deliverables separate from preview MP4 | **H.264 MP4, ProRes 422 HQ MOV, DNxHR HQX MOV** implemented with codec-aware indexing; DCP-o-matic test-only adapter/preflight implemented but vendor CLI download blocked (HTTP 403), so real DCP validation and theatrical screening remain gated; EXR/DPX/ProRes4444/MXF, soundtrack/OCIO and projector compatibility still pending |
| NVP-HOST-00–05 | Integrated Lu Film Workspace DLC *after Lu v1.0* | Signed admission, typed scoped IPC, shared model, containment, restart/cancel/cleanup on target OS |
| NVP-RESEARCH | Optional conditioned generative finishing and learned physical support | Beats deterministic baseline on recorded quality, cost, consistency and rights criteria |

This roadmap is dependency-based rather than a rigid promise about dates. Work in parallel only when source IDs, types, approval boundaries and recovery semantics are fixed. **The next implementation emphasis should establish the core data-first film workflow, not require detailed foot biomechanics to prove the first actual film.** Documentation and acceptance contracts do not themselves establish implemented functionality.

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

**2026-11-03 creator architecture decision:** [NVP-ADR-DATA-FIRST-001](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md) is the governing accepted decision for source data, frozen takes, presentations, low-spec previews, model/backend selection, non-destructive selective regeneration and final flat film. [NVP-DATA-SPEC-001](NVP_DIGITAL_FILM_PACKAGES_AND_REGENERATION.md) translates it into proposed records and acceptance gates. **Neither file represents a tested implementation.** Older use of “take” or “render” must be interpreted consistently with this more precise layering; existing actual source and tests remain the arbiter of implemented status.



**Direct working source files:** README.md (original mission and preserved proprietary terms); docs/SOLO_CREATOR_DIRECTION.md; docs/IDEA_SCREENPLAY_VIDEO_PIPELINE.md; docs/LU_DLC_WORKSPACE_CONTRACT.md; docs/PROD01_TO_PROD04_ENGINEERING_ACCEPTANCE.md; all PROD-05/06 milestone specifications; approved Bible and chronology/Scene Mind docs; and implementation modules/tests on the development branch.

**Historical architecture, preserved rather than replaced:** docs/NVP_WORLD_AWARE_FILM_STUDIO_DESIGN.md on branch docs/nvp-world-aware-film-studio-design-2026-10-26. Its enduring principles—canonical WorldState, identity/style separation, director approval, optional world-model/render finishing, independent evidence—are carried forward. Its older suggestion of UE5 as a necessary first engine and older Lu delivery ordering are superseded by the newer Blender-first engineering baseline and explicit deferment until Lu v1.0.

**Creator-supplied conventional reference:** claude-filmproduction(1).txt (110-line archived design) describes Fountain/FDX/PDF parsing, SQLite+retrieval/graphs, named anchors, asset sources and rights, OR-Tools layout, rigs/mocap/IK, acting performance cards, Toric-space cinematography, virtual mics/audio, motivated light rigs, OTIO, and orchestration by typed AI proposals. These are reflected as **candidate tool choices**, not claims that all are integrated.

**Other source referenced by PROD-01–04:** film-world-model-toolchain.md, previously supplied during NPV 01, is cited in those engineering records. The full original attachment was **not independently retrievable in this consolidation pass**; do not assert an exact verbatim concordance or silently invent passages. Its known endorsed principle—persistent editable physical world plus AI/deterministic division—is corroborated by the checked implementation and subsequent decisions. Reconcile any newly recovered unique requirements through an explicit master revision.

**Change discipline:** record new decisions as a dated design amendment or ADR with who authorized it, why, status [C]/[B]/[O]/[K]/[V]/[D], affected modules and migration/verification requirements. Keep the implemented-status table synchronized with actual test links. Never edit a past result to look like an independent acceptance that did not occur.

---

**Master baseline established for NVP, not a feature-completion certificate.** Next authorized implementation scope: real character foot IK, beginning with actual leg-chain identity, approval dependency, and independent Blender geometric acceptance.

**2026-11-03 external set geometry research note:** More accurate buildings/sets may be sourced via type-checked IFC and imported assets instead of procedural boxes. Evaluate [IfcOpenShell/Bonsai](https://github.com/IfcOpenShell/IfcOpenShell) for real architectural topology and [Poly Haven CC0](https://polyhaven.com/license) for scanned materials/props only after measured, rights-reviewed importer acceptance. Neither is presently a required production dependency.

**2026-11-03 C3A verified development evidence:** [GitHub workflow run 41670220453](https://github.com/vjmichael/nvp_offline_film/actions/runs/41670220453) individually passed both real Blender native geometry jobs (Linux/Windows); Linux Python regressions and React build passed. The static fixture corrected a source toe-candidate floor gap while preserving the root, cameras, and 215 noncontact leg-frame side samples. This does **not** establish authentic plantar landmark anatomy; the original misclassified heel/ball markers remain excluded from corrected contact and require independently reviewed annotation. The Windows full Python regression was pending when this note was authored.

**2026-11-03 C3B scope update:** [Cross-platform native Blender run 41674405456](https://github.com/vjmichael/nvp_offline_film/actions/runs/41674405456) has passed both real Blender BVH geometry jobs and Linux Python regressions. The annotation schema is implemented, but **not validated against independent labeled plantar landmarks for the licensed Cesium Man fixture**. Motion-capture heel/metatarsal tracking points and automatically selected mesh vertices cannot be substituted for medically/artist-reviewed plantar pads. A static inclined triangle BVH query is proven; human gait on that incline, balance, collision forces and full-body realism are future gates. The Windows Python job's result remains independently tracked in the workflow.


## 14. NVP-AI-01 — Source-aware AI assistance review [O], 2026-11-05

The creator's requirement is for NVP to make real film-production work easier for AI to accomplish on a human's behalf. **Do not replace NVP's data-first authority model.** Preserve FilmIndex identity, approved Story Bible, immutable captures, worker custody, measured resource scheduling and creator review. Add a consistent **read-only reference resolver**, bounded **capability catalog**, **task-aware provenance-backed context**, verified **tool/asset environment inventory**, **change-impact preview**, **evidence/recovery status**, and central **engineering-state ledger**. Each belongs above existing services rather than duplicating them.

See [NVP-AI-01 architecture review and ordered acceptance gates](NVP_AI_ACCESSIBLE_ARCHITECTURE_REVIEW_20261105.md) for exact source findings, ownership, priorities and tests. A new [engineering-state and resumption ledger](NVP_ENGINEERING_STATE.md) summarizes current exact-source verification boundaries, developer toolchain/resource discovery and next action. **Initial AI-01 code now exists** in backend/nvp_ai_refs.py with tests/test_nvp_ai_refs.py: read-only source revision lines, historical snapshot retrieval and bounded context. This is not yet a generally exposed AI tool or a full reference protocol. The review was created from PR #45 source and passes 51 targeted existing Python tests, **not** acceptance of newly proposed AI APIs, Lu integration or the Windows installed alpha. First additive engineering step: AI-01 read-only source resolver; maintain the installed Windows alpha and full-film release gates in parallel. Discovery, an AI role, or memory recall cannot grant authority. Later Lu adapter work is expressly deferred until Lu v1.0 interfaces are ready.


## 15. NVP-MASTER-01A — 30–60-second source-indexed technical audiovisual review (2026-11-05) [V, limited]

**Creator priority:** Pause Windows NSIS installer work; concentrate development on the authentic film-production pipeline and ultimately a full AI-assisted/AI-generated short. This does **not** erase the still-open distribution acceptance gate; it is no longer the immediate workstream.

NVP's initial per-worker safety ceilings are materially shorter than a 30–60-second short: PIPE-01B initially stops at 240 frames, and multiple B13/B14/AUDIO stages stop at 480 frames. Do **not** simply remove resource, duration or crash-recovery bounds. Instead, **MASTER-01A** builds a 720–1,440-frame review from separately indexed and independently verified reels of no more than 480 frames each.

Implemented `backend/nvp_longform_review.py`, a developer-only `tools/nvp_longform_review.py` entry, and native `tests/test_nvp_longform_review.py`. It reads source revisions and SHA-registered real ProRes HQ/PCM24 media from existing FilmIndex projects, probes exact 24fps/48kHz streams, checks contiguous packet timestamps, compares compressed video frames and decoded PCM samples byte-for-byte, then joins with native FFmpeg, verifies the combined 30–60-second output, and registers a **new unapproved** presentation with exact source-reel dependency edges. The original sources remain immutable. Native Linux acceptance with real FFmpeg verified a 36-second (864-frame) review, 60-second (1,440-frame) ceiling, persistence after reopening, corruption refusal and other negative inputs; a targeted 30-test Python regression passed. Windows/Linux Python 3.11/3.13 acceptance was added to existing native editorial CI but is not yet accepted. A broader unrelated AUDIO-01J suite timed out in this environment and is not claimed passed.

**Authority boundary:** This produces neither AI footage nor a creator-approved film. Its test media is procedural color and sine-tone technical fixtures. It does not prove coherent characters, acting, voice, scene continuity, sound mastering, model generation, actual film editing UX, authorized host supervision or final distribution. The optional developer CLI is **not** an AI tool permission grant. Reuse existing host/worker/journal infrastructure for the next integration, rather than introducing another privileged executor.

See [MASTER-01A contract, tests and next gates](NVP_MASTER01A_LONGFORM_TECHNICAL_REVIEW.md). **Next target: MASTER-01B native host/cancellation/recovery**, followed by actual capture/performance/voice-generated reels and a creator-approved continuous 30–60-second short. Preserve the separate data-first/Digital Take/Pipeline/FilmIndex authorities.


## 16. NVP-MASTER-01B — Supervised native multi-reel technical film assembly [V, scoped] (2026-11-05)

A film assembly must not run as an uncontained or unauthenticated backend subprocess. **MASTER-01B is implemented and has passed scoped native Linux tests:** the trusted native host binds exact creator authorization to source FilmIndex SHA/revisions, real FFmpeg/FFprobe versions, RAM reservation and task deadline; persists a sealed plan; uses the established ApprovedTaskBindings, TaskLedger, WorkerHostLease, OS child containment and resource watchdog; and publishes an **unapproved** multi-reel technical review through an isolated worker. After a verified worker stop, the host independently reopens media and source lineage before issuing a success receipt. No new application-facing AI tool or general write authorization has been introduced.

A genuine hard host-process crash was injected **after the durable worker-stop witness and before TaskLedger completion**. A new host verified and completed the existing FilmIndex revision without rerendering it, then released its reservation. Controlled cancellation, denied/replayed approvals, altered input and plans, rejected arbitrary native executable paths, and missing stop-witness retention were tested. **46 local Linux tests passed in three groups (9 MASTER-01B, 7 MASTER-01A, 30 FilmIndex/scheduler/worker lease).** Native Windows Job Object acceptance and strict Linux cgroup-v2 delegated whole-tree recovery are NOT accepted. The default Linux child mode does not prove orphan-free grandchild cleanup after an uncontrolled host crash; uncertain work must retain its reservation.

See [MASTER-01B contract, test matrix, recovery and gaps](NVP_MASTER01B_NATIVE_SUPERVISED_REVIEW.md). Its source reel fixtures are procedural color and sine audio, not AI-generated performances. Creator film approval, full cinematic film, and feature-film readiness remain open. **Next: MASTER-01C two-phase host-owned staging/publication**, then actual immutable Digital Take, voice, motion and picture/sound reel integration. Per creator instruction, NSIS installer work stays paused.
