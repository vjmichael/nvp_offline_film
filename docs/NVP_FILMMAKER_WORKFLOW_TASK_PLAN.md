# NVP — Revised filmmaker-workflow engineering task plan

**Plan date:** November 10, 2026 (America/Phoenix)  
**Status:** Planning/documentation; **no task-group implementation is completed by publishing this plan**.  
**Product contract:** [NVP_FILMMAKER_WORKFLOW_PRODUCT_SPEC.md](NVP_FILMMAKER_WORKFLOW_PRODUCT_SPEC.md) and [issue #150](https://github.com/vjmichael/nvp_offline_film/issues/150).  
**Lu integration issue:** [#152](https://github.com/vjmichael/nvp_offline_film/issues/152).  
**Current PLAN-04 review PR:** [#151](https://github.com/vjmichael/nvp_offline_film/pull/151).  
**Canonical data-first production integration:** draft [PR #74](https://github.com/vjmichael/nvp_offline_film/pull/74) (moving; recheck exact head before any ports).

## Product goal and architecture constraints

The filmmaker sees only **Script (optional) → Set Up Scenes → Film Scenes → Edit Film → Export Film**. Technical systems are AI tools, **not user screens**, even for advanced filmmakers. Core scene setup must produce an actual navigable low-poly 3D world. A screenplay can supply scene headers, characters and dialogue; **the director still decides performance**. Actor-free/no-dialogue films are supported.

**Immutable invariants across every group:**
1. OpenUSD / FilmIndex authoritative source, exact Film Time, original PCM, stable ActorID when applicable; frozen Digital Takes do not change.
2. Camera previews/defaults do **not** freeze one 2D viewpoint. Post-Production can reframe source worlds from new valid cameras without reshooting or rewriting source.
3. **Zero FFmpeg** in the entire active workflow including final delivery; no hidden fallback.
4. Lu owns its GGUF and host permissions; NVP may not silently run another model, grant tools to AI, or leak a locked project.
5. Actual human authorization for protected commits/filming/worker actions; approvals are one-use and cannot be replayed after cancellation, crash or restart.
6. Separate **creative UI** from private developer diagnostics; “advanced” means *advanced filmmaking*, not internal process controls.
7. **Evidence rule:** Source implementation, mocked tests, exact-head native execution, physical installed use, and artistic acceptance are different statuses. No promoting old-branch CI to an integrated head. GitHub Actions supports development but should not stop independent coding work.

## Status legend

- **Verified, scoped:** a particular native test/artifact passed at a precise SHA; not a complete user journey.
- **Partial:** some code/UI exists, but key integration and/or physical evidence is missing.
- **Not built:** only specification/prototype/mock exists or the required full capability is absent.
- **Open acceptance:** targeted head/test or physical machine evidence required.

## Ordered work groups — one group at a time

### G01 — PLAN-04 genuine physical acceptance and clean integration
**State:** Native Cycles source build, separate Blender reopen, original scene/Take hash checks and consolidated installed-app CI were verified on the isolated PLAN-04 line. Physical approval and 27B GPU evidence are **OPEN**.

- **G01-A:** Obtain latest exact-head PR #151 run, source/installer checksum and durable renderer receipts; inspect new failures, repair only observed native defects. Preserve previously passing Blender 4.0.2 denoiser behavior and strict worker custody.
- **G01-B:** On physical Windows installed NVP: first-dialog refusal, second-dialog refusal, real consent, active render cancellation, kill/exit verification, restart recovery and one-use grant replay refusal. Inspect **actual Windows Job Object/process-tree and SQLite worker journal**, not just UI text.
- **G01-C:** On the physical Radeon AI Pro R9700, load the intended **Qwen3.8-27B GGUF** using a pinned local runtime, verify model binary/weight hashes and real completion, record per-process RAM, GPU adapter, dedicated VRAM and resource admission. A Qwen3-0.6B Linux smoke is not 27B acceptance.
- **G01-D:** Only after physical proof, compare isolated PR #151 and moving PR #74 source/ABI/Film-Time/PCM contracts; selectively port compatible changes; reject blind merges, preserve zero-FFmpeg audit, run consolidated exact-head Windows/Linux plus installed acceptance.

**Exit:** one source-bound native evidence ledger with real operator approvals/refusal/cancellation/restart, no orphan/replayed work, real model/VRAM proof, SHA-verified outputs, and a passing reconciled PR #74 head. **Blocker:** physical workstation operations cannot be claimed from a cloud runner.

### G02 — Lu-hosted NVP Film Workspace + usable AI model
**State:** Contract and research exist; functional installed Lu ↔ NVP Workspace with shared 27B inference **not accepted**. Dependency: G01 source evidence where reusable; does not require feature-length rendering.

- **G02-A:** Stabilize generic Lu Workspace registration/open/suspend/resume/close, typed versioned IPC and project-scoped permissions **without embedding filmmaking logic into Lu core**. Verify unavailable/unauthorized workspace denial.
- **G02-B:** Create a narrow NVP film adapter for Lu-owned inference. Detect verified model states: disconnected, available/unloaded, loading, ready, busy, timed-out, failed. Show human-readable status and retry; no NVP-side second GGUF or self-configured localhost privilege.
- **G02-C:** Deliver bounded asynchronous proposal/response, progress, cancellation and restart-safe receipts for idea-to-script and script-to-scene tasks. Strict parser/grounding/provenance: model may **propose only**; user authorizes revision, scene and production changes.
- **G02-D:** Share Lu GPU/RAM admission, execution supervisor and native authorization with NVP project scope; ensure a busy model or a cancelled inference never locks the scene editor or drops drafts.

**Exit:** physically open NVP as a Lu workspace with one loaded real local 27B model, real visible ready/busy/error states and a source-anchored proposal. Check that Lu still works with NVP disabled and no second copy of the model appears. **No assertion that a DLC is already installed.**

### G03 — Movie home, secure projects and filmmaker-only navigation
**State:** Current installed UI shows some chat/scene panels, but the creator rejected the exposed engineering submenu; full design/security acceptance **open**. Dependency: G02 for AI-connected experience; manual mode may remain useful offline.

- **G03-A:** Chat-first home + left film-project sidebar; startup **New Movie / Resume Working** dialog and remembered last meaningful creative step.
- **G03-B:** Real **Locked/Unlocked** project access: prevent access to source files/previews/model context/worker actions until project unlock. Design OS/user identity, key custody/encryption or equivalent defensible security, idle lock and safe recovery; test cross-project access *below* the UI.
- **G03-C:** Replace top-level engineering navigation with the five-step journey. Separate the Film Scenes workspace from the dedicated Edit Film/Post-Production window. Advanced user panels contain filmmaking choices only.
- **G03-D:** Accessible focus/keyboard/large project list handling, cancel/undo/reopen and simple help. Any private debugging view must be external to the filmmaker application, not an Advanced Studio tab.

**Exit:** an untrained user creates/resumes/unlocks a project, sees a clear next film step and no engineering subsystem. Locked data cannot be accessed by IPC tricks, another scene, or restart.

### G04 — Pre-Production: optional script, idea intake and Production Bible
**State:** Saved screenplay, line search, script scene cards and some actor/location extraction exist; real AI screenplay completion and full scene-grounding flow remain **partial**. Dependency: G02–G03.

- **G04-A:** New Movie first screen: import `.fountain`/`.txt` screenplay or type an idea; optional dismissible **Script / Just an idea** prompt; **Next** at lower right. Preserve original script hashes, revisions and project ownership.
- **G04-B:** Parse scene headers/script lines into stable SceneIDs; distinguish INT/EXT, named location, time, and scene ordering. Link speaker dialogue to known ActorIDs only when unambiguous; human/animal/voice characters are optional.
- **G04-C:** For scripts, create draft scene roster/location/props plus dialogue map. For ideas, create only **Scene01** and invite incremental **Add scene**; don't assert an automatic complete film.
- **G04-D:** Maintain readable Production Bible: story, character/ActorID roster, era/season/time/day, locations, weather, wardrobe, props, dialogue and continuity. Record script-given / director-given / AI-proposed / approved / unknown facts distinctly. Reconcile mismatched movie title and sample script instead of displaying it as if derived from the user's premise.
- **G04-E:** Targeted AI clarifications for missing relevant information, never compulsive questions or invented humans/dialogue.

**Exit:** real sample screenplay and idea produce correct editable creative records and revisioned provenance; dialogue links only to the right character; nature scene with zero actors passes. This group creates planning data, not a claim of visible geometry—that is G05.

### G05 — Set Up Scenes: **the core visual Scene Generator**
**State:** **G05 source implementation authored** on `nvp/g05-visual-scene-authoring-20261111`: G04-driven actual OpenUSD world generation, editor interaction, proposal-only AI scene decoration, immutable versions, director approval and exact-source G06 handoff. Native installed-app and model acceptance **not yet run** under the creator's build-first policy; do not mark verified. G02 remains deferred; G04's development source is the stack base. See [G05 implementation handoff](NVP_G05_VISUAL_SCENE_IMPLEMENTATION.md).

- **G05-A:** Typed, unapproved ScenePlan from scene headers/Bible/director input: setting, environment, time, weather, props, ActorIDs, actor-free environmental actions, dialogue references and known unknowns. Stale revision/source/foreign-project denial.
- **G05-B:** Build a bounded real OpenUSD low-poly scene: ground/world, editable set assets, placeable props, actors as correctly bound placeholders *where requested*, basic sun/weather/lighting and cameras. Create data, not static images pretending to be a 3D stage.
- **G05-C:** Visible interactive scene viewport with orbit/select/move/rotate, save/undo/reopen, scene list and contextual compact AI popups. Handle asset offline/relink and memory/VRAM limits without losing source.
- **G05-D:** Context scene direction questions: “Where is this location?”, “What season/time of day?”, “Any rain/snow/fog?”, “What happens?”, “Who/what is in the scene?”, “Does anyone speak?” Ask only when information is absent and materially needed.
- **G05-E:** Scene revision/approval and Production Bible binding: original source hashes preserved, no unapproved worker launches or frozen Take creation. Reusable world assets and material/lighting basic look; advanced photoreal polish later G09.

**Exit:** both a script-derived kitchen with ALEX/SAM and an actor-free foggy mountain valley are *visibly present* as actual independently reopened USD stages, editable via simple controls, linked to correct source/Bible records. This is the first genuinely usable NVP creative milestone.

### G06 — Film Scenes: context notes, performance and immutable Takes
**State:** **G06 source implementation authored** on `nvp/g06-filming-performances-original-takes-20261111`: director performance/ambient event timeline, 3 native 3D camera previews, original microphone PCM and scene-time placement, ActorID-bound optional local AI performance notes, immutable original OpenUSD/PCM Takes, retakes, wardrobe continuity, camera independence and G07 readback. Native microphone, GGUF, installed runtime, crash recovery and full production-security acceptance **not executed** under the creator's build-first policy. In-progress microphone samples are not durably recoverable after a host crash, although finished committed sources/Takes persist; see [G06 implementation and gaps](NVP_G06_FILMING_IMPLEMENTATION.md). G05 is the source base; G07 is next.

- **G06-A:** Director/actor/prop/ambient-event manipulation for real performance: animation paths (walk/run/jog/crawl), expression, dialogue timing, interactions and environmental motion. Maintain actual scene/world transforms and source semantics, not frame-index authority.
- **G06-B:** Right-click actor → **Give Note** anchored AI popup. Every note carries exact project/SceneID/ActorID/revision/time/scope. Preview, edit, accept/reject; preserve note history. Non-character scenes use context actions on environment/props.
- **G06-C:** Right-click **Change Wardrobe** (or scene object variant) as reviewed versioned OpenUSD binding plus Production Bible update. No mutation of previous frozen performances.
- **G06-D:** Default **three camera viewpoints / wide, medium, close-up** previews. Director can reposition/lens/light as needed or skip framing; no mandated nine rolls or fixed film-FPS authoring.
- **G06-E:** Native source picture/world, actor events, voice/dialogue/original PCM and spatial sound recorded at exact Film Time; explicit creator approve/refuse/retake/freeze with durable no-replay worker custody.
- **G06-F:** Independently reopen and verify immutable Take, original ActorID/props/world/source audio, camera-independent performance and crash/restart recovery. Source playback remains correct after preview changes.

**Exit:** film one short staged performance (plus an actor-free environment sample), make and refuse notes, take a retake, freeze original data, and reframe **without changing the Take digest**.

### G07 — Edit Film: separate Post-Production workspace
**State:** **G07 source implementation authored** on `nvp/g07-source-editing-20261111`: real separate Post-Production editor, source-bound frozen Take EDL and exact Film Time trims/splits/reordering/transitions, independent camera reframing, versioned looks and original PCM spatial/mix decisions, selective OpenUSD picture and disposable 48-kHz sound previews, bounded local AI editorial proposals with explicit director approval, missing-source refusal, durable edit/restore history and original-source G08 handoff. See [G07 source implementation](NVP_G07_NONDESTRUCTIVE_EDITOR.md). **Installed Windows, physical GPU/audio, real loaded-GGUF, compiler/CI and end-to-end regression acceptance have not been executed** under the creator's build-first policy. Production-quality render, full-duration mastered playback and movie export remain for G08; G09 quality later. Dependency: G06 implementation branch.

- **G07-A:** Build a **separate editable window** for selecting frozen Takes, camera/view decisions, cutting, trimming, transition choices and time-aligned assembly; maintain source-to-presentation reference and no source overwrite.
- **G07-B:** Re-evaluate a frozen world from different valid camera positions and lens settings **after filming**, including new positions not picked during Production; choose rendered view only as a derivative.
- **G07-C:** Sound editing/mixing and native spatial source decisions; color management/grade as non-destructive versions; scene/shot previews and selective render/regeneration.
- **G07-D:** Durable edit decision list, undo/versioning, independent reopen, missing-asset handling, preview progress, cancellation and recovery.

**Exit:** editor reassembles and reframes the same frozen Takes; pixel/audio change is observable while original source hashes remain unchanged. No work is returned to an engineering tab.

### G08 — Export Film and the first real 30-second film
**State:** **G08 source implementation authored** on `nvp/g08-native-film-export-20261111`: first-party no-FFmpeg 640×360 MJPEG+48kHz PCM stereo AVI, actual G07/G06 OpenUSD scene-time rendering, picture cuts/dissolves and sound edits, native export worker with exact source SHA and progress/cancel/restart job history, separate ordinary-movie verifier decoding every JPEG and PCM chunk, atomic no-overwrite delivery, sealed in-memory encrypted-movie rendering and authenticated AES-GCM output, and filmmaker-facing Export Film controls. See [G08 native delivery handoff](NVP_G08_NATIVE_FILM_DELIVERY.md). **No real completed/independently played 30-second film, exact-head native test, installed app operation, quality acceptance or full crash matrix has run** under the creator's build-first policy. First output is a simple standard-definition playable AVI design, **not** a theatrical/long-form master; G09 must add production-quality delivery and further native/recovery/security integration. Dependency: G07.

- **G08-A:** Implement/verify native **zero-FFmpeg** selected-view render and encode/package path with licensed adapters only, exact Film-Time mapping, original PCM, synchronized audio and non-clobber derivative output.
- **G08-B:** Render one actual 30-second production from approved Takes. Suggested test profile: **24fps = 720 derived picture samples**, **48 kHz = 1,440,000 original audio samples per channel**. These are *export parameters*, never source/Take identities.
- **G08-C:** Independent second-process reopening/decoding, visual continuity, audio continuity, source/asset SHA verification, interrupted render/restart and cancellation with no false completion receipts.
- **G08-D:** Physically inspect the real movie in installed Windows NVP and sign off creative and technical quality. Preserve original reusable 3D data for later alternate camera export.

**Exit:** downloadable/viewable real 30-second film and verifier report with continuous picture/sound, preserved frozen sources, genuine output hashes and no FFmpeg use.

### G09 — Production quality, actors, sound, theater and long-form scale
**State:** **G09-A + G09-B source integration authored**. A: editable Take-bound environments, derived PBR/MaterialX OpenUSD and approved export look SHA on `nvp/g09-production-environments-20261111`; see [G09-A ledger](NVP_G09_A_ENVIRONMENTS.md). **B:** `nvp/g09b-actor-performance-20261111` adds original ActorID-only performance history and consent, source-based articulated native UsdSkel humanoid/face geometry, genuine recorded-PCM audio audition/jaw envelope, precise edited-shot sound-offset/mute synchronization, reviewed expression/wardrobe/appearance, reuse only under the same ActorID, and filmmaker Post-Production controls. G07/G08 ordinary and encrypted exports pin the approved actor SHA and independently reopen derived actor USD; see [G09-B ledger](NVP_G09_B_ACTORS_PERFORMANCE.md). **G09 remains open:** A2/A3 real Blender/Cycles/EXR render and asset quality, B2/B3 high-fidelity motion/facial/voice/hair/cloth, C native spatial/continuous A/V, D mastering/DCP, E sustained long-form scale, F distribution and security. No native, installed, CI/PR or physical GPU/owner acceptance was run under the build-first policy. Continue G09-C next without GitHub Ops detours.

- **G09-A — Environments (USD-FILM-02M):** reusable districts/interiors, object-level editability, LOD/culling, PBR/MaterialX, lighting, real Cycles/OpenEXR visual and hardware tests.
- **G09-B — Actors (FILM03/USD-FILM-03):** source-implemented approved per-ActorID original Take animation and continuity, actual USD Skel timed joint animation plus stylized body/face, original-PCM energy-driven jaw and G07 edit-offset/mute sync, director voice audition/review and expression cue timeline; **not yet** expressive qualified synthetic voice, phoneme alignment, calibrated mesh/skin/hair/cloth, real imported acting assets or native installed acceptance.
- **G09-C — Native 3D A/V (DA-02/03/04):** physical microphone/camera/device capture, continuous native spatial sound, HRTF/obstruction as warranted, accurate drift/latency, uninterrupted synchronized film-time playback, OS process-tree and recovery.
- **G09-D — Finishing:** ACES/OCIO/MaterialX parity, sound finalization, independently verified professional export, **SMPTE DCP Bv2.1** compliance with external checker and physical cinema playback only after actual qualifying output.
- **G09-E — Sustained scale:** verified 30-minute film first, then 60–90-minute features, 2–3-hour productions, large asset volumes, bounded CPU/RAM/VRAM and restart-resumable render/output; no blanket longform claims from short demos.
- **G09-F — Distribution:** integrated Lu Film Workspace lifecycle, protected persistent library and installer/uninstaller data preservation, licensed runtimes and safe updates.

**Exit:** independent output/quality gates **per subtask**; do not infer feature-length readiness from a 30-second test.

## Single-group execution discipline

1. **Start with G01.** Do not start G02 simply because G01's CI is green; G01 physical/user-machine evidence and reconciliation are distinct obligations. If local physical access cannot be obtained, report it as **blocked**, with a real installer/evidence procedure rather than a false pass.
2. For each task group, allow smaller subtasks but **stop after the group**. Report: (a) what source changed, (b) actual failures, (c) exact SHA/native and physical evidence, (d) next task group, (e) remaining groups.
3. Run a consolidated exact-head Windows/Linux gate at a completed group, inspect its actual compiler/test/log/artifact results. Continue independent development while CI runs. Separate physical GUI/GPU tests from CI.
4. Keep work on independently reviewed branches, **not wholesale-merging incompatible donor stacks**. PR #74 remains the authoritative data-first target; confirm exact moving head and source/ABI before any selective port.
5. NVP may expose a helpful user-level error and **Retry**, but a completed-looking UI state is never evidence of native work, an approved Take, or a finished presentation.

## Crosswalk to the prior seven-group backlog

| Prior group | Preserved in revised workflow |
| --- | --- |
| 1. PLAN-04 physical closeout | **G01** |
| 2. Studio UX / Scene Library | **G03–G05**, *after G02 Lu workspace integration* |
| 3. PLAN-02-E/F first film | **G06–G08**, with G05 visual scene setup prerequisite |
| 4. USD-FILM-02M environments | **G05 baseline + G09-A advanced** |
| 5. FILM03 / USD-FILM-03 actors | **G04 ActorID + G06 basic performance + G09-B film-quality actors** |
| 6. DA-02/03/04 native A/V | **G06 baseline + G09-C advanced native capture/spatial/audio** |
| 7. Professional finishing/scale | **G07–G08 baseline + G09-D/E/F** |

**New dependency introduced by user decision:** Lu ↔ NVP shared model/authority integration is now **G02** and must precede broad user-interface redevelopment. This does *not* mean NVP should stop implementing film-specific data/renderer internals where they can be independently verified. The source-first architecture continues; its implementation remains backstage to the director.

## Immediate next work order

**G01**: complete physical installed NVP approve/refuse/cancel/restart and actual Windows worker-journal custody, genuine Qwen3.8-27B/Radeon RAM+VRAM proof, then conditionally reconcile PR #151 with canonical PR #74. Until that evidence exists, **G01 stays open**.  
**Then G02**: Lu Workspace host handshake/shared inference and real ready/busy status.  
**Then G03–G05**: deliver the first genuinely visible, simple Set Up Scenes experience.  
**Then G06–G08**: film, edit and export the first real movie.  
**Then G09**: longform/advanced-quality gates.
