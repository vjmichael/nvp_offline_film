# NVP-PIPE-01B — Full-Motion, Physically Based Presentations

**2026-11-03 professional delivery amendment (PIPE-01B-PRO01):** The original implementation below established **H.264 MP4 full-motion rendering**. The current pipeline additionally exports **ProRes 422 HQ QuickTime MOV** (encoded 10-bit 4:2:2, `apch`), with independent codec/decode verification and reuse of exact stored full-frame presentation PNGs **without a new Blender render**. Read [Professional Delivery Formats](NVP_PROFESSIONAL_DELIVERY_FORMATS.md) for the authoritative export profile table, acceptance, source-bit-depth limits and DNx/EXR/DCP boundaries. The historic two-MP4 fixture below was extended to also encode an actual ProRes MOV in run [41700029191](https://github.com/vjmichael/nvp_offline_film/actions/runs/41700029191). The codec and container do not imply finished color management or theatrical DCP compliance.

**Date:** 2026-11-03  
**Implementation scope:** Complete frame-accurate, bounded, playable MP4 video from a frozen Digital Take, two conventional Blender engines, CPU Cycles PBR lighting/materials, independently reverified video/media provenance.  
**Status:** **PIPE-01B1 conventional full-motion foundation fully passed on all five jobs** in [run 41697002642](https://github.com/vjmichael/nvp_offline_film/actions/runs/41697002642). **Professional MOV extension independently passed** its Linux Blender/FFmpeg and Python acceptance in run 41700029191 (445 tests, 438 passed, 7 skipped); Windows conclusions are tracked separately. This remains **proxy geometry, no waveform audio and no DCP**.  
**Design authority:** [Data-First ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md) · [NVP Master Design](NVP_MASTER_DESIGN.md) · [PIPE-01A](NVP_PIPE01A_FROZEN_TAKE_TO_PRESENTATIONS.md).

## Product requirement

**The Film World remains the source; the Digital Take remains immutable; a high-quality presentation is a derived video.** Unlike the PIPE-01A four-still visual samples, PIPE-01B actually processes **every recorded frame** in each selected camera interval and encodes a playable, frame-accurate movie. The creator may re-render the same approved take under a different visual style, retaining both versions and their original sources.

## Implemented components

1. **\`backend/nvp_presentation_pipeline.py\`** now declares two *real*, independently selected conventional rendering engines:
   - \`blender_workbench\`: \`studio\` and \`flat\` — inexpensive proxy visualization.
   - \`blender_cycles\`: \`pbr_studio\` and \`pbr_noir\` — offline CPU Cycles with principled PBR shaders, scene lighting, world background and softened proxy geometry edges, plus the existing source actor/camera animation.
   - All outputs remain derived from the same frozen, director-approved 3D scene and camera/actor tracks. The original authoritative geometry and scene are **never modified** by the presentation's visual treatment.
   - The PBR path is designed without CUDA/RTX dependence: Cycles CPU. GPU acceleration and high-resolution performance must be separately measured on physical target hardware.
2. **\`backend/nvp_full_motion.py\`** introduces \`FullMotionPipeline.render_video\`:
   - Reopen and audit the frozen approved take without consulting the current living stage.
   - Reject unknown/mismatched engines and styles or missing required Blender, FFmpeg/FFprobe.
   - Render **all source frames**, preserving actual camera cut positions and native 24-fps timeline.
   - Encode H.264/4:2:0 MP4 using FFmpeg **without audio**; probe exact frames/width/height/FPS and decode the complete video as an independent acceptance check.
   - Publish a video media SHA/size and frame-level presentation hashes. The movie is built from SHA-verified stored frame bytes, not unchecked temporary renderer output.
   - Register an immutable **\`kind=presentation\`** motion record with typed direct links to both the original \`kind=take\` and the intermediate full-frame \`kind=presentation\`.
   - Persist the actual renderer/styling, source hashes, frame count, video codec receipt, duration, director review status \`rendered_unreviewed\`, and dialogue time positions in the 48-kHz sample clock.
   - Independently reopen the exact media and source after restarting Studio. \`reopen(...,check_decode=True)\` performs a fresh FFprobe check plus full decoder verification.
3. **\`backend/nvp_film_index.py\`** adds \`put_media_file\` and \`verify_media_file\` for streaming SHA-256 ingestion/verification of media files **up to 2 GiB**, using no-clobber immutable disk storage and scoped database receipts, without holding a whole MP4 in RAM. The earlier strict in-memory manifest and PNG limits remain intact.
4. **\`tests/test_full_motion.py\`** tests explicit codec/renderer capability, dialogue sample timing, wrong provider and style refusal, even H.264 dimensions, immutable media after restart, cross-film isolation, corrupt-media refusal, unsafe symlinks, over-budget files, forged presentation records and false FFprobe claims.
5. **\`tools/nvp_pipe01b_fixture.py\`** is an independent native acceptance: build/approve a real moving actor with two camera shots, freeze it, edit the live WorldState to invalidate the current scene, then render **two full 16-frame, 24-fps, 128×72 H.264 presentations**. One uses Workbench flat and one uses Cycles PBR studio. Probe/decode both actual MP4s and compare image/video hashes, exact take source hashes, both camera cut ranges, and identical dialogue time manifests. Reopen all film records after process restart. This is a *small deliberately bounded* native fixture, not a benchmark of consumer hardware or 1080p render throughput.

## Data lineage

    Film World / actual approved 3D scene
         |
    Digital Take (immutable SHA, 24fps actor/camera/dialogue)
         |                                    |
      full-frame Workbench                   full-frame Cycles PBR
         |                                    |
      frame presentation A                 frame presentation B
      PNG source SHA per frame             PNG source SHA per frame
         |                                    |
     FFmpeg H.264 MP4 A                    FFmpeg H.264 MP4 B
         |                                    |
     motion presentation A                motion presentation B
        \________ indexed directly to same frozen original take ______/

Each movie and intermediate frame presentation has its own stable identity and typed provenance. A new style produces a **new derived output**, not an edited source take. Video encoding is verified against the *selected production frames*, not mere metadata.

## Audio timing: implemented versus not implemented

Dialogue-line start frames and measured frame durations already belong to the frozen take. PIPE-01B translates them to **48,000 samples/sec coordinates**, which are exact for the current 24-fps project clock (2,000 samples/frame), and records \`speaker_id\`, \`line_id\`, start sample and duration in the motion package.

**No audio waveform is generated, imported, aligned or muxed in the MP4 at this gate.** The movie has **video only**; timing metadata is a future sound production contract, not a fabricated voice or soundtrack. NVP-AUDIO-01 and later sound mastering should attach genuine approved voice takes, room sound and dialogue alignment then mux audio without modifying the approved image source.

## High-fidelity meaning and limits

**Proven technical advance:** Conventional Blender Workbench proxy rasterization can be replaced by **physically based Cycles CPU shading with lights/materials** while preserving original take, geometry identities, camera and motion. Full-frame 24-fps motion can be encoded as a real video and independently decoded.

**Not yet proven:** high-polygon or photoreal licensed human meshes; calibrated facial animation and visemes; detailed costume/face consistency; studio-quality virtual cinematography; final hi-fi asset retargeting; real voice generation; simultaneous audio-video finished film; AI video generation; high throughput on ordinary hardware. The existing NVP rig/GLB work is a separate foundation to integrate into presentation representation switching later.

**Current explicit limits:** at most **240 frames per movie job** (10 seconds at 24fps), 64–1920 wide by 64–1080 high with even dimensions, 1–128 CPU Cycles samples, H.264 MP4 yuv420p; FFmpeg/FFprobe must be available. Longer shots require segment/chunk scheduling and validation; production-grade 1080p/4K workloads need hardware and time benchmarks rather than promises. Source changes must create new captured takes when authoritative camera/performance data change.

## Acceptance gates

| Acceptance | Evidence required |
| --- | --- |
| Full coverage | Every frame from every saved source shot is rendered and verified, no gaps or duplicated shot transitions |
| Source fidelity | Reopen a frozen take after the living stage changes, preserve exact source world/camera/motion hashes |
| Physical rendering | Native Blender Cycles CPU produces a visibly different, valid PBR presentation; not just a new name for Workbench |
| Native movie | FFmpeg produces real nonempty H.264 MP4; FFprobe counts actual frames and checks FPS, dimensions and yuv420p; FFmpeg independently decodes entire file |
| Durability | Reopen project and *both* encoded videos by content hash after Studio restart; tampered media is rejected |
| Choice | User can explicitly request either conventional engine and its supported style; unsupported video/voice models refused rather than silently substituted |
| Cross-platform | Linux real Blender/FFmpeg, Windows Python and native Blender legacy acceptance; Windows native GPU/movie support only if independently tested |

**CI run:** [NVP-PIPE-01B native/regression](https://github.com/vjmichael/nvp_offline_film/actions/runs/41697002642): Linux Python success (443 tests, 436 pass, 7 skip); Linux native Blender/FFmpeg success (two 16-frame 24-fps H.264 movies from one frozen take and separate `pbr_studio` vs `flat` presentation, both independently decoded); Linux React build success; Windows Blender geometry success. Windows Python/React acceptance was still running at this documentation update. Do not claim whole-workflow completion until it finishes.

## Subsequent work (keep priority)

- **PIPE-01B2:** Replace proxy-only visual representations with licensed high-detail 3D actors, sets, costume variants and stable rig/LOD identity mapping, reusing prior GLB/rigged-character work. Independent visual, camera and identity audits.
- **PIPE-01B3:** Chunk long scenes, publish robust resumable per-shot render jobs, support 1080p/4K and real performance benchmarks, richer film color/lighting/render passes.
- **NVP-AUDIO-01:** Actual chosen voice/TTS/speech-to-speech backend, documented rights, 48-kHz audio stems, line regeneration and lip-sync integrity.
- **NVP-PIPE-01C:** Capability-negotiated user-selectable video AI controls, structured depth/pose/camera and reference assets, with optional Lu load/unload supervision. AI remains a derived, reviewable presentation.
- **NVP-EDIT-01:** Compare finished video variants and selectively re-render a defective shot. **NVP-MASTER-01:** assemble approved video+audio versions into the flat 2D master.

This gate proves the **rendering chain**; it does not silently declare the **complete end-user filmmaking workflow** finished.
