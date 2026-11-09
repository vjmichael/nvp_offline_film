# NVP USD-FILM — Data-first hybrid photoreal appearance and OpenUSD-controlled rendering

**Design note:** NVP-HYBRID-RENDER-00 (2026-11-09)
**State:** Recorded architectural direction and research candidates; NO generator, worker, installed integration, validated GPU compatibility, photo-real quality, OS acceptance, or released film is established by this note.
**Source reviewed:** Creator-provided *Claude-response-to-Film.txt* (2026-11-09). Source ideas below are distinguished from preexisting NVP creator decisions, NVP engineering interpretation, and external claims requiring fresh vendor/license/hardware review.
**Cross-references:** [NVP master design](NVP_MASTER_DESIGN.md), [USD-FILM full integration plan](NVP_USD_FILM_WORLD_FULL_INTEGRATION_MASTERPLAN.md), [all-task ledger](NVP_DATA_ALL_TASK_LEDGER.md), [human surface roadmap](NVP_HUMAN_SURFACE_AI_MATERIAL_AUTHORING_ROADMAP.md), [02M-E1 layered-district source design](NVP_USD_FILM02ME_LAYERED_GENERATED_DIRECTOR_POINTINSTANCER_ROADMAP.md).

## 1. Governing design decision — a film is data before it is pixels

The durable *Digital Film World*, creator-approved identity and narrative state, FilmIndex revisions, Temporal Ledger and composed OpenUSD stage remain the source of truth. The world holds persistent geometry, physical relationships, authored asset references, actor identity, stable performance, exact time and scene state. Camera, shot, lens, lighting, FX, styles and deliberate shot-only artistic cheats are reviewed **stronger opinions / presentation revisions**, never silent rewrites of the original Digital Take.

A frozen Digital Take is immutable **source performance**, not frozen video. Time is the established exact original **7,056,000,000 Film Time ticks per second**; sound originals stay 48 kHz PCM with **147,000 ticks/sample**. The edit is a revisioned selection of take/time intervals and approved shot overrides; camera coverage is presentation of one performance, not automatically nine newly recorded performances. Alternate genuine actor performances remain separate Takes and require explicit editorial activation.

The screen pixels are **derived deliverables**, not canonical geometry or acting. Nevertheless, source-pinned frame caches, shot approvals and final rendered masters are allowed and necessary: “never freeze pixels” is an editing *authority* principle, NOT a ban on immutable rendered evidence or approved deliverables. A rendered presentation cannot revise an old original world/Take.

## 2. Layering — composition is source organization, not proof of execution

The Claude note proposes sequence/location, set dressing, actor-per-performance, shot/lens, lighting, and FX/cache layers. This maps to existing NVP OpenUSD arcs, generated-vs-director layer strengths, actor/take revisions, selected-view editor and FilmIndex receipts. Use the existing proven architecture, not a second film database:

| Layer or package | Authority / lifespan | Required binding |
| --- | --- | --- |
| **L0 acquisition and reconstruction inputs** | Immutable original screenplay, controlled photos/scans, recorded PCM, captured actor sources, procedural seeds; *inputs*, not a substitute for revised authoring | Project / source revision, origin, SHA, creator approval, observed-vs-generated uncertainty |
| **L1 canonical authoring/performance** | FilmIndex + Production Bible + Temporal Ledger + OpenUSD composed world, ActorID/VoiceID, exact-time native motion, frozen Digital Takes; durable source | IDs, versioned USD layers and asset references, exact ticks, snapshot hashes, approved revisions |
| **Director/shot opinions** | Versioned strongest *presentation* revisions; camera, lens, chosen take, lighting look, staging cheat, lens stereo configuration where supported | Source Take and shot lineage, explicit human edit/approval, stable composition diff |
| **L2 derived compute caches** | Rebuildable source-linked simulation, texture bake, geometry LOD, animation acceleration, camera-space depth/normal/segmentation/motion/ID/pose passes | Source/shot SHA, camera/time range, worker/tool/model version, color/units, generation profile; cache invalidation |
| **L3 rendered image/sound packages** | Conventional Cycles/Hydra where actually verified, or *separately labelled* AI appearance synthesis; image sequence, spatially derived PCM, edit and final approved 2D presentation | Exact source and render-input hashes, renderer type, frame/tick mapping, audio lineage, independent file/result verification and director review |

OpenUSD can organize scene/layer/variant/source data; it does not by itself execute a physics solver, synthesize faces, run a generative video model, produce an accepted picture, or prove MaterialX shader parity. USD prim cameras and optional stereo roles are source metadata, not automatic stereoscopic runtime qualification.

## 3. Two separate appearance/render pathways

**A. Deterministic conventional render path (current baseline):** The selected OpenUSD world/shot and approved actor/take are interpreted by a host-supervised **real Blender/Cycles worker** and any separately validated renderer adapters; output is source-bound real pictures, optionally multi-layer OpenEXR and color-managed display transforms. Renderer-compatibility, shader/MaterialX mapping, lens, volumetric FX and human photorealism are measured per adapter. Blender is not the authoritative world database; no new NVP rasterizer should be built simply to “support USD.” Never claim that Arnold/RenderMan/Karma/Cycles all share identical Hydra pipelines without a native audit.

**B. Optional generative appearance path (research and later gated integration):** From **the same** selected source world and camera/time range, a protected native render worker may produce aligned control evidence: depth, normal, object/instance IDs, segmentation, outlines, motion/flow, shading/lighting references, and actor skeletal/facial pose where actually supported. A separately reviewed image/video model consumes approved control passes, look references and shot parameters to create **candidate photoreal image frames** for the same shot. The AI output is **not** canonical geometry, not a UV/MaterialX material and not guaranteed to preserve any camera, expression, body pose, spatial depth, frame boundary or actor identity. Control channels improve the odds; they are not a proof of 3D understanding or precision.

**Hybrid selection:** The director may use path-traced hero action and material-validated actor closeups, selective AI appearance for background/crowd/sky or matte/VFX/retouch passes, or a composed mixture. These are *potential* creative strategies, not an assertion that the current model meets human-face, hair, teeth, eyes or cloth quality. A real film can mix accepted outputs only through an explicit source-pinned shot/render/effect decision and preserved original reference renders.

## 4. Data-first shot and tool contracts (proposed, not existing API)

- An authored shot references an exact original source Take revision, time interval in integer Film Time, camera prim/rig/lens, scene/layer snapshot, lighting/look, soundtrack/voice references and director-approved SHOT-01 changes. Choose a different approved camera or take by revising presentation/edit metadata; do not duplicate and silently overwrite the acting.
- Generate **read-only** source control passes via a reviewed native renderer: camera depth, segmentation/IDs, pose tracks, normal/rough shading and optional optical motion. Confirm actual saved samples, camera alignment, units, alpha/occlusion and pixel dimensions, rather than assuming a model accepts every pass.
- Film verbs suggested by Claude — *block_actor*, *set_camera*, *set_lighting_preset* — are **candidate typed NVP operations**, to be mapped to WO6/USD-FILM-07 per-operation review, diff, one-use host authorization, stable provenance, independently checked output and rollback. Do not create general-purpose arbitrary Python, CLI or unaudited model-executable permissions.
- The generator consumes only an approved bounded package; inputs include verified camera/time/scene/passes, exact ActorID look/approved reference, prompt/reference hashes and model identification, seed/control weights when supported, color encoding, target resolution, hardware/time limits and destination. Record failed/partial attempts, not only chosen clips.
- Candidate generations live in isolated disposable layers and manifests. A human selects or rejects candidate appearance; acceptance creates a **new** versioned presentation/effect record with original source links and audit receipts. It never replaces ActorID, mesh/rig/UV, frozen Take, performed dialogue or original 48 kHz sound.
- Render/review accepts verified stills or *original* derived image sequences, source-timed frame mapping, genuine soundtrack continuity and selected-view conform. Final picture/sound flattening only on creator approval. Preserve 01Q/01R/01S/01T batch scheduler and playback semantics; no mandatory full nine-camera render.
- **ZERO-FFMPEG DIRECTIVE:** Do not introduce any FFmpeg executable, binary, library, transitive dependency or fallback. OpenEXR, OpenColorIO/ACES, OpenTimelineIO and similar components are possible specialized interfaces **only after** actual supported version, licensing, native portability and non-FFmpeg dependency closure checks.

## 5. Human-surface distinction — reusable 3D material vs single-shot AI pixels

**HSURF** addresses long-lived physically responsive *source geometry/materials*: genuine mesh UV/UDIM maps, PBR base color separated from baked illumination, roughness/specular, pores/normals, subsurface/scattering, eyes/lips/hair and repeatable Blender/Cycles/MaterialX look realizations under changing light and camera. Original ActorID identity, joint/facial animation and source material revisions survive re-camera and other scenes. AI photos/texture candidates need scan-assisted or multi-view projection and validation before they become approved maps.

**Hybrid rendering** addresses *a particular final shot's derived pixels* and may produce a convincing single image sequence without solving reusable 3D materials. It may help with reference, reconstruction, low-strength VFX appearance, crowd/background proposals, look trials or selective post-processing, but a photoreal frame never certifies a reusable head, texture map, physically correct lighting or source actor identity. These two paths must share source provenance but cannot be collapsed into one “AI skinning” checkbox.

**Creator sequencing retained:** Finish the USD-FILM task family, including 02M-E2 source geometry/material/lighting and outstanding genuine native rendering acceptance, **before starting HSURF-00 implementation**. This document records the hybrid proposal now; it does not install models or change that priority.

## 6. Verification gates: no synthetic pixels presented as accepted film

A candidate is not accepted because it is attractive or one generated frame looks good. Require saved original source and control passes plus independent readback at exact shot/time, stable background/foreground masks, appropriate depth/parallax/occlusion, object contacts, camera consistency, actor face/clothing/skin identity and eye/mouth landmarks, real audio/viseme timing, shot-to-shot lighting consistency, temporal flicker/geometry drift, frame count and editorial duration. Separate physical render/AI output labels, source hashes and director-perceptual review.

Check at minimum:
1. **Control fidelity:** compare the AI output to genuine Blender/OpenUSD camera depth/segmentation/pose/edge control passes. Report qualitative and quantitative disagreement; do not invent thresholds before evaluating a specific model/camera.
2. **Temporal and identity continuity:** same ActorID traits across closeups, expression frames, camera changes, lighting, other shots and mouth-synced 48k PCM dialogue; explicit occlusion/visible-surface and motion checks. Fixed seeds/reference images alone do **not** ensure identity.
3. **Replay and provenance:** exact original Take/asset/world/shots, source SHA, control-pass SHA, prompt/reference/model checkpoint, sampler/seed/strength/profile, renderer hash and revision, OS/hardware/precision, resulting files, cost/time and cancellation/recovery receipts. If a generator is nondeterministic, record that fact and original candidate bytes; do not falsely promise bit-for-bit repeatability.
4. **Operational safety:** host review, one-use authority, bounded CUDA/ROCm CPU/GPU memory where tested, no silent uploads, installed Windows/Linux native worker and real process-tree cancellation/interrupt recovery, license/export dependency audit, and no unverified downstream success.
5. **Editorial/creative outcome:** source-locked original performance/camera/audio, explicit shot revision or approved special effect, real output inspection by the director, actual film conform and final approved version. Treat accepted raster caches and final master files as immutable *derived* artifacts.

## 7. Named research candidates from Claude (not confirmed native integrations)

- **NVIDIA Cosmos Transfer / Omniverse Replicator:** proposed multimodal video control and rendered camera passes; model version, license, real I/O schema, facial realism, required GPU vendor/VRAM and export reliability need independent review. Do **not** assume a 32 GB AMD/ROCm card can run a CUDA-targeted model.
- **Wan VACE / ComfyUI:** proposed locally run video/control-pass candidate. Confirm actual version and depth/pose/control fidelity, weights/requirements, ROCm support on the deployed AMD and native host-compatible worker packaging. Do not assume a successful screenshot equals stable human dialogue.
- **Commercial video-to-video** (examples cited: Runway, Luma): optional research only, **not** a required cloud provider, upload workflow or accepted substitute for local-first offline NVP.
- **Other production tools named by Claude:** OpenTimelineIO (editorial interchange), OpenColorIO/ACES (color), OpenEXR (render passes), MaterialX (material semantics), OpenAssetIO (asset lookup), OpenRV (review), OpenCue (batch rendering), photogrammetry/reconstruction and Unreal/MetaHuman/Audio2Face. Their inclusion in the note is a **candidate landscape**, not claims of supported APIs, bundled licenses, hardware compatibility, correct output, or a mandatory new system.
- The source's descriptions of model control capabilities, vendor readiness, “enough VRAM,” renderer availability and industry working-group membership are **unverified input claims**. Audit primary vendor docs and native versions before designating a provider production-ready.

## 8. Ordered integration with existing NVP roadmap (all new gates OPEN)

| Gate | Existing owner / task | New evidence and acceptance |
| --- | --- | --- |
| **HYBRID-00** — research/capability and licensing audit | USD-FILM-00 / 05 / 08 | Exact control pass availability and real inputs, model/runtime/VRAM/ROCm/offline/license/FFmpeg-closure matrix, no installed model just from concept |
| **HYBRID-01** — source-bound control pass exporter | USD-FILM-01/06/08, 01Q/R/S/T | Real original Take + selected camera/time → rendered depth/ID/pose/normal/shading sequences with immutable source hashes, verified geometry and soundtrack linkage |
| **HYBRID-02** — reviewed appearance candidate worker | USD-FILM-07/08 | Optional model accepts approved bounded passes; per-operation host review, one-use grant, resource limits, native process cleanup, provenance and reproducible output recording |
| **HYBRID-03** — independent image/temporal QC and selection | USD-FILM-09/10 | Cross-shot ID/pose/depth/lighting/flicker comparison, source→picture/audio audit, separate CG-vs-AI labels and creator-approved edit/effect revision |
| **HYBRID-04** — original complete selected film evaluation | USD-FILM-10 / 01T | Real 30–60-second original film with approved selected-view picture and PCM soundtrack, comparisons against actual traditional renders and installed Windows/Linux acceptance |
| **HSURF-00–10** — reusable human materials | Existing HSURF roadmap AFTER USD-FILM | Separate physically based actor-map/material baseline and genuine photoreal multiview human look; not replaced by hybrid rendered pixels |

**No change to current execution priority:** continue USD-FILM-02M-E2 and remaining 00–10/native/installed gates as already recorded. This amendment supplies research design and acceptance requirements, not a new immediate implementation branch or implied task completion.

**Source-grounding note:** Claude's uploaded film response supplied the layer stack, Fountain/script-to-shot proposal, optional classic CG/AI-controlled render split, control-pass examples and industry software names. The authority model, exact Film Time/PCM numbers, source/worker security, non-destructive revisions, no-FFmpeg mandate, 01Q–01T pipeline and HSURF deferral come from NVP's existing creator-approved design. Stronger QA, provenance and nonclaims are engineering interpretation to guard against substituting generated pixels for actual reusable 3D data.
