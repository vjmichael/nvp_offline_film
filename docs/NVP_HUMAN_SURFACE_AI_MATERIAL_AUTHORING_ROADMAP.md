# NVP HUMAN-SURFACE — AI-assisted actor surfacing and material authoring

**Creator direction (2026-11-08):** Close the visual-realism gap between contemporary AI-generated human imagery and reusable, rigged, persistent OpenUSD film actors. Investigate generative AI as an **assistant for physically responsive 3D skin and surface materials**, with photorealistic humans as the first quality target. Stylized/anime/cartoon looks remain alternate artistic presentations of the same enduring character/world, not a reason to rebuild actors.

**Creator sequencing update:** HSURF-00 and all HSURF implementation are **deferred until the USD-FILM task family is finished**, including outstanding actual native render/acceptance work. Do not start HSURF-00 merely because USD-FILM-01F is underway. Modular architecture USD-FILM-02M and the rest of USD-FILM retain priority.

**Status: ROADMAP ONLY.** This commit does not implement a skin generator, install a texture model, produce cinematic renders, or prove photorealism. All technical and perceptual acceptance gates below are OPEN. NVP remains exclusively filmmaking.

## Design principle

**AI does not need to invent the film's 3D truth to improve its appearance.** Image and video generators are strong at plausible screen-space detail; NVP's challenge is to retain the *same* actor's believable appearance under genuinely changing camera positions, lighting, expressions, and time. A generated portrait is **not** automatically a UV texture, physically correct albedo, normal, roughness, thickness or scattering map.

The proposed bridge is:

```text
Approved ActorID + versioned mesh/UV/rig + source material + optional photographs/scans
    -> source-bounded AI/scan/procedural material candidates (NOT authoritative)
    -> multi-view projection / seam reconciliation / intrinsic decomposition
    -> typed PBR / skin / eye / lip / hair map pack + units/color metadata
    -> reviewed Blender Cycles skin/eye/hair shader build
    -> OpenUSD UsdShade / MaterialX source-bound look and renderer-specific adapter
    -> locked multi-shot, multi-angle, changing-light native renders
    -> objective failures + director visual review
    -> accepted immutable FilmIndex appearance revision linked to ActorID
    -> subsequent original Digital Takes reuse exact approved revision
```

**Source authority:** Existing FilmIndex + Production Bible ActorID appearance identity and immutable revisions, world/shot/Takes/Temporal Ledger, project-scoped OpenUSD source/asset/texture registry, WO3 MaterialX integrity, 01C verified scoped PNG mapping, WO6 native AI creator tools, host supervision and per-operation creator authorization. Reuse, do not create a second cast/material database or bypass prior WO3/01C SHA checks. Actual original film-time remains 7,056,000,000 integer ticks/s and 48 kHz source audio 147,000 ticks/sample; surfacing must remain independent of frame rate and voice.

**Blender** is the initial genuine modeling, texture projection, material assembly and Cycles rendering worker. **OpenUSD** is the canonical spatial/material association and reusable scene substrate; it does not synthesize photoreal skin itself. Blender shader nodes do not automatically round-trip perfectly through USD/MaterialX. Preserve a common approved shader/material semantic description plus separately tested renderer-specific realizations, never infer pixel parity from an imported USD material graph.

## Work packages and measurable exit criteria

| ID | Work package | Deliverable and acceptance boundary | Status |
| --- | --- | --- | --- |
| **HSURF-00** | Actual existing skin/surface-capability audit | Inventory NVP actor meshes, UVs, real skinned/face rigs, MaterialX/OpenPBR and Blender/Cycles inputs, image/texture custody and applicable worker controls; report real missing capabilities and installed versions. No new generator merely from library availability. | OPEN |
| **HSURF-01** | Neutral human-head photographic baseline | Source-versioned, actually modeled/UV'd/rigged neutral head **plus eyes, eyelids, lips, teeth, hair/groom**, fixed calibrated light/camera/scale/OCIO profiles, unchanged meshes across comparison arms. Render real native Cycles frames of an unassisted baseline under ≥4 lighting setups and at least front, 3/4 and profile; retain source and render hashes. | OPEN |
| **HSURF-02** | Typed, versioned skin/material source contract | Link approved basecolor, roughness, micro-normal, geometry/displacement, subsurface/thickness/region masks, specular/oil/sweat, lips/eyelids and makeup/dirt overlays to exact **ActorID, mesh revision, UV layout/UDIM and material revision**. Every map records dimensions, units/range, linear-vs-color encoding, provenance, source SHA, compatible shader/worker versions, and whether it is observed, estimated or AI-generated. No baked lighting promoted to albedo without validation. | OPEN |
| **HSURF-03** | Image/scan-to-surface candidate workers | Reviewed, reproducible native tasks for photograph/photogrammetry/reference enhancement, image inpainting, texture synthesis and tightly bounded seam/hole filling. Accept optional original controlled multi-view capture and scan data; generate **candidate maps only** with uncertainty/provenance, no invented 3D ground truth and no remote-image requirement. Benchmark scan-assisted, constrained multi-view generated, and prompt-only strategies separately. | OPEN |
| **HSURF-04** | Multi-view projection and physically informed map derivation | True mesh/UV/UDIM projection, mesh/UV-space reconciliation, front/side/back texture continuity, ear/nose/neck fixes, pore scale/orientation, high/low-frequency separation, region mask boundaries, basecolor highlight/shadow removal; independent normal/displacement consistency. Roughness/SSS/normal inferred from photos is a **hypothesis**, not a measured physical value. Require deterministic shader/texture source reopens and seam/lighting QA. | OPEN |
| **HSURF-05** | Cycles skin/eye/hair shader profiles | Actual physically plausible multilayer skin (including SSS, roughness variation and microgeometry), wet eyes/tearline, eyelashes, lips/teeth/tongue, facial hair/peach fuzz and hair/groom. Scope material IDs, UVs and explicit color space per renderer; test OpenUSD/MaterialX source → real Blender nodes without pretending exact semantic conversion. Record optional sculpt/displacement/normal usage and realistic camera-to-subject scale. | OPEN |
| **HSURF-06** | Director-approved persistent appearance revisions | A candidate look is a **disposable stronger USD/Blender look layer** or isolated source revision. AI may propose selected maps/weights and prepare preview renders; only a host-verified director creative decision publishes an immutable FilmIndex appearance/look revision tied to one ActorID and existing rig/mesh UV. Older Takes retain old source looks; shot-level makeup, sweat, tears, dirt and injury are additive reversible look layers. Object-actors with no skin are not forced into the human workflow. | OPEN |
| **HSURF-07** | Real human-close-up and motion QC | Fixed source actor, multi-angle/multi-distance/multi-light photographs and **moving** cameras, skin under expressions and 3–5 seconds of actual speech/facial rig/eyelid motion. Include motion blur, shifts in exposure/lighting and temporal surface stability. Record seam errors, sliding/warping, highlights, eye moisture, lip boundaries, wrong pore scale, texture-swimming, specular-SSS artifacts. Fails if realism only appears in one flattering still. | OPEN |
| **HSURF-08** | Three-arm comparative evidence and renderer parity | Compare (A) vetted conventional manual/procedural skin, (B) scan/photo + AI repair, (C) AI-assisted candidate maps, on **same frozen mesh, rig, camera, light, render seed/budget**. Record CPU/GPU time, memory, image sequences, per-map hashes, blinded director preference, independent material/UV/scene replay and genuine Blender/Cycles pixels. Report conditions where AI is worse; do not promise generative video parity. | OPEN |
| **HSURF-09** | NVP native AI director/material-author orchestration | Expose bounded native verbs: `inspect_actor_surface`, `propose_material_maps`, `project_material_candidate`, `preview_look`, `compare_renders`, `reject_candidate`, `approve_appearance_revision`. Each operation requires exact ActorID/asset/mesh/UV/shot/revision and a host-authorized scope, runs through existing NVP supervised worker/ledger paths, has validated outputs/source SHAs, and can be interrupted, retried safely or discarded. AI cannot grant its own permissions or publish a final look by reporting success. | OPEN |
| **HSURF-10** | Original-world film integration | A new original world Digital Take (USD-FILM-01E/01F) uses the **same accepted ActorID appearance revision** in ≥3 differently lit/cameraworked shots, survives restart/revision and produces real independently inspectable frames and synced performance audio. Director can amend makeup/materials in a new version without regenerating the face, recasting, or overwriting earlier Takes. | OPEN |

## How a generative AI can *drive NVP*

**Yes. NVP's intended AI-first creator workflow already points in this direction.** A general-purpose or specialized multimodal model can be a **production coordinator, not the world's final authority or renderer**:

1. **Understand a director request** (“Give this character natural skin, subtle pores, a slightly sweaty forehead and realistic eye moisture; keep the original face and performance”).
2. **Read source-bound context** through WO6's existing native read host: Project, ActorID appearance/mesh/UV/rig versions, current world/shot/lighting, original Takes and approved creative settings. Query compact typed summaries instead of ingesting huge USDA files.
3. **Plan reviewed executable actions:** choose a photo/scan-assisted or AI-map candidate pipeline; identify which Blender/image-model/native worker is required, cost/resource bounds, source images and exact target material slots. A text or video model does **not** supply trustworthy final PBR parameters by merely saying it did.
4. **Invoke NVP's verified native tools** within current project/turn authorization: generate candidate images, project to UVs, validate maps, build real Cycles shaders, render fixed-angle and moving-shot tests, compare to the baseline. Tool discovery never grants authority.
5. **Inspect actual outputs:** use real files and measurements, ideally vision review of genuine rendered images plus reproducible native shader/map checks; present before/after, quality failures, source hashes and alternatives to the director.
6. **Apply the director's accepted creative decision** through a host-authorized immutable FilmIndex revision. Keep rejects and draft/look layers disposable. A model does not silently edit an ActorID's source or old Take.
7. **Continue after interruption** from actual journal and FilmIndex receipts, rather than assuming an interrupted worker completed. Plan the next step using verified evidence, not generated claims.

This orchestration may use a language/multimodal model for direction and reasoning, a separate image model for texture candidates, a reviewed geometry/retopology/photogrammetry process, and Blender/Cycles for material execution and film pixels. **They need not be the same model.** No MCP dependency or additional model runtime is required by the roadmap; native first-party operations are the default. Existing **WO6 AI-first film assistant** and **USD-FILM-07 AI scene composition** own the generic direction/execution infrastructure. HSURF-09 adds domain-specific surfacing capabilities to that infrastructure rather than creating a new agent ecosystem.

### What about generative VIDEO helping?

Treat the video generator as a **proposal or bounded derived-image/VFX tool**: plausible lighting/mood examples, actor look reference, background matte/inpainting, or isolated postprocess passes anchored to known camera/depth/segmentation/motion data. Never take video-generated view-dependent detail as reliable world material geometry or a persistent identity record. Validate multi-view parallax and multi-frame stability; avoid independently regenerating skin or landmarks frame-by-frame. Exact 3D source, camera, rig, UV and actor identity stay in OpenUSD/FilmIndex. A photoreal 2D sequence is not independent proof of a photoreal repeatable 3D actor.

## Native material/quality acceptance matrix (minimum)

- **Identity and geometry:** Same ActorID, mesh revision, UV/UDIM layout, eye and lip shapes across all test arms and shots. No hairstyle/face-shape substitutions hiding surface shortcomings.
- **Map validity:** No NaN/invalid values; correct pixel channel types, texture dimensions, repeat/UDIM tiles, tangent basis and normal handedness, appropriate real pore scale; texture map SHA/FilmIndex source consistency and no unapproved external filesystem/remote paths.
- **Illumination independence:** Test daylight, neutral soft studio, harsh side/rim lighting, and warmer practicals; separate albedo/color from specular/illumination contamination; use controlled color management and display/view transforms.
- **Spatial coherence:** Validate seams and texture projection over front/3/4/profile, scalp-to-forehead, face-to-neck, ear/jaw and high-motion mouth/lids.
- **Temporal coherence:** Real animated facial expressions and short dialogue; skin/eyes/hair respond plausibly as camera, lighting and rig move. Report unstable details rather than relying on one still.
- **Photoreal close-up:** Real Blender/Cycles rendered pixels with saved scene, exact material/render config and per-frame provenance; blind side-by-side director/human review against approved real references. No fake or generated frame passed off as a Cycles render.
- **Resource/cost:** Map sizes, disk cache, CPU/GPU VRAM where actually measured, render time, worker execution/cancellation, restart/restore and installed Windows/Linux behavior. The source audit alone does not establish installed renderer quality.
- **Creative style:** Only after a stable physical baseline, validate anime/toon/painterly looks as explicit style profiles. Nonphotoreal does not automatically mean animation/performance is easy.

## Boundaries and immediate order

**Start with HSURF-00 → HSURF-01 → HSURF-02.** Inventory actual source/renderer/rig capabilities, build one repeatable neutral-human test head, define source-authoritative map identity/units before installing an arbitrary image generator. Then HSURF-03/04/05 candidate synthesis and native surfacing; HSURF-06/07/08 quality/revision acceptance; HSURF-09/10 AI director and original film integration.

**Integrate with existing work**: USD-FILM-02 geometry/UV authoring; USD-FILM-03 body/face/eye rig; USD-FILM-05 photo shading/lighting; USD-FILM-07 typed AI operations; USD-FILM-08 actual renderer asset builds; USD-FILM-09 visual photoreal assessment; USD-FILM-10 full short; FILM03-09E human speech/face alignment; USD-FILM-01E/01F original world Take/render acceptance; WO3 MaterialX and WO6 creator AI operations.

**No scope drift:** No new digital-twin, geographic reconstruction, VR gameplay/runtime, scientific simulation platform, unrelated legal/performer-rights workflow, or mandatory MCP server. This is a first-party filmmaking material and actor-appearance research/production workstream. Never equate a convincing 2D image, authored USD graph, runnable Blender or a generated candidate with accepted photorealistic human film quality.
