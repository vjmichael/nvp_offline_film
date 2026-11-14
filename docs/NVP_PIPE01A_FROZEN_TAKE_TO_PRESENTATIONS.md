# NVP-PIPE-01A — Digital Take to Actual Blender Presentations

**Date:** November 3, 2026  
**Decision:** [Data-First NVP ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md)  
**Predecessors:** [DATA-01 source index](NVP_DATA01_FILM_LINEAGE_INDEX.md), [CAPTURE-01 frozen take](NVP_CAPTURE01_FROZEN_DIGITAL_TAKES.md)  
**Status:** First conventional visual adapter implemented; native video output and model-agnostic AI provider registry are *subsequent work*. CI: [41691770710](https://github.com/vjmichael/nvp_offline_film/actions/runs/41691770710). Confirm individual jobs before claiming whole-workflow success.

## Why this matters

NVP's film world is an editable authority. A Digital Take Package freezes actual approved actor tracks, camera shots, blocking, timings and source assets. **A presentation is a derived and separately versioned interpretation of that take, not a rewrite of it.**

This gate implements the first concrete production link, with **real Blender Workbench rendered PNG media**, source-anchored image hashes and multiple style interpretations of one actual frozen performance. It is deliberately not sold as photorealistic, an AI video generator, a dubbed scene or a final movie.

## Implementation

**\`backend/nvp_presentation_pipeline.py\`** implements \`PresentationPipeline\`:

- \`available_engines()\` — truthful adapter capability metadata. The only installed/implemented engine is \`blender_workbench\`, with styles \`studio\` and \`flat\`, and modes \`keyframes\` (two sample frames per shot) and \`full\` (complete bounded frame interval).
- \`render(project_id, take_id, presentation_id, output_dir, engine, style, frame_mode, width, height, ...)\` — validates engine, style, output dimensions, IDs and immutable source, then asks the existing *frozen* take acceptance function to regenerate and audit an actual native \`.blend\` file. The live screenplay/world is never queried for source data.
- A **trusted static Blender worker script** loads the reopened \`.blend\`, selects the exact saved camera for each chosen shot/frame, applies the chosen Workbench shading style and renders actual PNG files. NVP verifies the independent Blender receipt, output frame order, camera/shot IDs, source digests and PNG dimensions before publication.
- Each PNG is stored in DATA-01's **per-project SHA-256 immutable blob store**; the \`kind=presentation\` FilmIndex record binds exact take ID/revision/hash, style, Blender version, frame policy, frame/shot list, image hashes and audit receipt. This record's status is **\`rendered_unreviewed\`**, never a false director approval.
- \`reopen(project_id, presentation_id)\` reopens the original frozen take and every stored PNG by exact content SHA, validates the source-take dependency, native recipe and shot/frame policy, and reports actual stored frames.

A second presentation uses a **different presentation ID** and style without touching the first or the original take. Creating a duplicate ID fails; a failed or timed-out worker leaves no false-approved presentation record. An incomplete job may leave staged files or unindexed/orphan blobs to reconcile later; transactionally durable worker journals remain a later gate.

## Data graph example

    film project / approved living scene
       |
       +-- World Revision SHA ---------------+
       |                                      |
       +-- Approved Performance SHA ----------+--> Take 004 SHA (frozen)
                                                   |          |
                                     Studio style renderer    Flat style renderer
                                            |                  |
                                        PNGs + SHA         PNGs + SHA
                                            |                  |
                                       Presentation A     Presentation B
                                            +------------------+
                                                       |
                                         future editor review/timeline
                                                       |
                                           future flat 2D final film

This is **one authoritative capture and multiple presentation variants** with complete reverse links. An AI-enhanced variant will later use the same contract but only claim the controls the selected model actually supports.

## Rendering modes and precise claims

| Mode | What actually gets rendered | Supported result |
| --- | --- | --- |
| \`keyframes\` | **Two actual stills per captured shot**: shot start and an interior midpoint | Sampled presentation/storyboard; **not a complete motion clip** |
| \`full\` | **Every frame of every captured shot**, subject to a 2400-frame per-job budget and bounded resolution | Frame-accurate PNG sequence at captured FPS; **no audio, codec or film mastering yet** |

Native acceptance intentionally renders just four real images for a **two-shot frozen take** in each of two styles. This keeps the CI hardware/time budget bounded and verifies output media and lineage without pretending that a four-image sample is a movie.

**Supported material/visual quality:** procedural colored proxy geometry, camera/lens and actor movement presented through Blender Workbench. No claim of high-resolution photorealism, human facial rigs, ambient sound or neural video generation. Workbench is the first deterministic presentation baseline; later high-quality Blender/Eevee/Cycles or user-chosen generative adapters can be added without changing the stored take format.

## Independent acceptance

- \`tests/test_presentation_pipeline.py\` (CPU/local): refuses fake engines, unknown style and invalid output constraints, verifies frame coverage and 24-fps cut boundaries, ensures no output was indexed when Blender is unavailable, rejects forged/unlinked presentation metadata, and verifies original capture integrity across DB reopen.
- \`tools/nvp_pipe01_fixture.py\` (real Linux Blender 5.2.3): creates a real approved moving-actor 120-frame take with two camera cuts, *modifies the live world after capture*, then produces two differently styled Workbench presentations. Reopens both through **a separate Studio/FilmIndex instance**, reads every actual PNG's source hash, asserts different media between styles and verifies source take/world SHA was unchanged.
- Existing Windows full Python/React and native Blender rig/capture tests remain mandatory. Windows no-GPU Blender tests do **not** claim full Workbench presentation raster rendering until separately proven.
- Native worker emits renderer version, actual filenames/cameras, source proof and frame receipts; results are stored under CI artifacts. No model tokens or network calls needed.

**CI run:** https://github.com/vjmichael/nvp_offline_film/actions/runs/41691770710. The Linux Python suite ran **436 tests (429 passed, 7 skipped)** including an adversarial forged Blender receipt check. The actual native Linux Blender step **rendered two styles from the same frozen take and passed independent indexed image/lineage verification**. Windows Python and Windows Blender are separate acceptance jobs and must each be checked before claiming whole-workflow completion.

## Limitations / next gates

1. **PIPE-01B**: Real *full-motion* complete-range presentation and encode/decode video (e.g. FFmpeg), stereo audio/timeline alignment, artifact playback; high-quality Blender rendering.
2. **PIPE-01C**: Independent user-selectable video/voice AI provider adapters, declared capabilities, VRAM/rights/provider limits, conditioning assets and optional Lu model load/unload supervision.
3. **EDIT-01**: Source-aware review and selective per-shot republishing, cost/scope estimates, side-by-side comparison and director approval of chosen variant.
4. **MASTER-01**: Assemble approved presentation ranges into flat playable 2D film with sound and a fully retraceable project index.

**Safety:** NVP never executes arbitrary generated Python, never trusts model-provided import paths or output hashes, never silently replaces a frozen capture, never claims an absent AI backend is operational. This phase is a *verified media and lineage contract*; its aesthetic production quality is explicitly preliminary.
