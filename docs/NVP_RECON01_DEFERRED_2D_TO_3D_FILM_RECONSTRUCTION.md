# NVP-RECON-01 — Reconstructing Conventional 2D Film into an Editable 3D Film World

**Status:** DEFERRED PRODUCT RESEARCH / FUTURE REVISION — no implementation authorized by this document.
**Priority:** Below native data-first filmmaking, continuous performance, shot staging, presentation and feature-film proof.
**Governing product distinction:** Original 2D video is an *observation of a world*, not the original world state. Reconstructed 3D is an *inference*, not a recovery of ground truth.

## Purpose

A future revision of Neural Virtual Production may ingest conventional flat footage (live action, animation, archival material, completed films) and **propose** a structured, editable OpenUSD world containing characters, scene geometry, cameras, motion, approximate lighting and a time-indexed interpretation of observed performances.

This is not required for the core NVP film workflow. The current priority is creating films natively from the data-first Digital Film World, not reconstructing an unknown world from flattened pixels. **Pause further FFMS2-versus-NVP frame-index benchmarking, INDEX-TIME-05/editorial imported-media UI, imported-media decoder optimization and source-video reconstruction integration until explicitly reprioritized.** Prior experimental branches and PRs remain available for future work, but are not gates for shipping the native filmmaking core. Do not merge/rebase the imported-video PR stack into the OpenUSD core branch merely to preserve speculative work.

## What can and cannot be inferred

A finished 2D frame combines geometry, material, illumination, camera optics, compositing, editorial manipulation and many hidden variables. The inverse mapping is not unique: different worlds and performances can generate similar pictures. From a **single view**, out-of-frame geometry, occluded hands, the far side of faces, physically disconnected props, focal ambiguity, light sources and hidden actor motion cannot be recovered with certainty.

A useful reconstruction must label every property as one of:

1. **Observed:** directly supported by source pixels, audio or known shoot metadata, with an exact source-PTS/time/shot/frame citation and region ID;
2. **Estimated:** computed from partial observations using calibrated tracking, multi-view geometry, pose, depth, segmentation, structure-from-motion, learned priors or temporal regularization;
3. **Synthesized:** generated content required to form a navigable world but not present in the source (hidden geometry, backstage room, unseen hands, missing speech articulation);
4. **Creator-corrected:** an edited or newly authored interpretation from a human;
5. **Creator-approved:** a frozen reconstruction interpretation for a particular requested downstream use.

Each label must retain confidence/uncertainty, source spans, model/algorithm version, constraints, and revision history. Model confidence is NOT a proof of source truth.

## Future candidate pipeline (research, not implementation)

1. **Rights and custody:** ingest an authorized original with source bytes/digests, frame PTS, audio clock, edit history when available, rights for transformation/training/derivatives, and explicit scope; reject unauthorized reuse. These are optional source-media subsystem operations, not the NVP film's master time authority.
2. **Shot and camera analysis:** detect cuts/dissolves/motion, derive calibrated camera intrinsics/extrinsics where observable, identify likely zooms/optical vs digital operations, document unobservable camera values.
3. **Spatial reconstruction:** infer depth, structure, camera-relative geometry, materials, light sources and a world coordinate convention. Fuse evidence from **multiple shots** only when actor/prop identities and editorial continuity justify it; do not assume distinct shots were captured in physically identical staging.
4. **Actors and acting:** track persistent actor identities within authorized footage, visible body and facial landmarks, hands, gaze and sound/timing. Rig and retarget where evidence supports it. Represent occluded joints and unobserved performance as explicit hypotheses with constraints—not silently perfect animation.
5. **Continuity hypotheses:** propose persistent scene objects/asset identities and a source-time Temporal Ledger linking observed actions across cuts, while retaining original shot boundaries and uncertainty. Never invent a single continuous action solely by interpolating a cut.
6. **Filmmaking-cheat reconciliation:** **crucial.** Camera coverage may intentionally move a chair, place an actor on a different mark, shift an eyeline, adjust lighting or alter spatial distance. A reconstruction engine must be allowed to infer an underlying plausible persistent world **plus independent shot-specific presentation override layers**, rather than trying to average artistic cheats into a falsely canonical set. Contradictions become candidate *intentional continuity exceptions*, flagged for director interpretation.
7. **Interactive human correction:** offer before/after reference view, original image with projected 3D overlay, uncertainty heat maps, alternative hypotheses, manual object/actor reassignment, camera and rig tuning, and 'mark as intentional cheat.' Do not claim full 3D equivalence by visual matching alone.
8. **Canonical source freeze:** once accepted, create immutable FilmIndex-referenced reconstructed scene/assets, time-addressed events, reusable character definitions and **separate non-destructive shot overrides**. Preserve traceability to original input and all creator changes; source remains independently accessible.
9. **Evaluation:** check reprojection on held-out frames/angles, geometry stability, appearance, motion identity, long-range temporal continuity, audio sync, editability, and explicit failures on hidden/unrecoverable regions. Evaluate creator approval separately from metrics.

## Why shot-specific OpenUSD overrides are necessary

A real production cheats camera blocking and staging. A photographed sequence can show the *same character* moved across a cut for sightlines, camera depth, clean eyeline or emotional focus. The original film is not necessarily evidence that the character teleported in a single continuous physical simulation. Future reconstruction should represent:

- an **estimated persistent world** and continuous performance where justified;
- **shot-local USD opinion layers** for blocking, eyeline intent, visibility, camera optics and lights;
- an authored **continuity policy**: intended match, intentional camera cheat, unknown, or director correction;
- source-PTS evidence for the original 2D shot and exact source-framing comparison;
- no automatic 'repair' of intentionally nonphysical staging.

A later renderer may use these interpretations to explore new views, but reconstructed geometry/acting in unobserved space remains uncertain and may not produce a believable unseen camera angle without additional artistry.

## Boundaries and acceptance before any future release

**Defer all engineering** until the director explicitly prioritizes this capability, native NVP authoring and shot override presentation are proven, and rights/privacy policy is settled. Later validation needs licensed multi-shot footage, documented camera-calibration evidence, independently measured pose/geometry/identity errors, source appearance and motion comparisons, deliberate-cheat reconstruction examples, cross-cut continuity review, offline performance and creator-approved revisions.

Early demos should be described as **reconstruction proposals**, never 'the original film recovered as accurate 3D.' This is a distinct future NVP capability, not a prerequisite for the native film editor, Digital Take, shot presentation or master generation.
