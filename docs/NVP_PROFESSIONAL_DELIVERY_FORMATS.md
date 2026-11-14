# NVP Professional Film Delivery Formats — ProRes, DNx, EXR and DCP

**Date:** 2026-11-03  
**Decision:** Professional editing, VFX and theatrical deliverables are **first-class outputs** of NVP, alongside ordinary playable MP4s. There is no one universal "film industry standard video file."  
**Implementation status:** **ProRes 422 HQ MOV export implemented and verified on Linux native Blender/FFmpeg**, alongside H.264 MP4. Both formats were independently decoded, SHA-verified and re-opened from the same frozen take and PBR frames. Linux 445 tests (438 passed/7 skipped) and native presentation step passed on run 41700029191. **All five jobs passed** in run 41700029191, including Windows Python/React and Windows Blender geometry acceptance (Linux performed the actual ProRes video render). DNx, EXR and DCP remain implementation targets, not working claims.  
**Upstream:** [Data-First Filmmaking ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md), [full-motion implementation](NVP_PIPE01B_FULL_MOTION_PBR.md).

## Delivery hierarchy and intended use

| Purpose | File/package | Encoder / visual essence | NVP status (2026-11-03) |
| --- | --- | --- | --- |
| Fast review, preview, web | **MP4** | H.264/AVC, 8-bit 4:2:0 (yuv420p) | **Implemented and verified on Linux** |
| Professional editorial / mezzanine | **QuickTime MOV** | **Apple ProRes 422 HQ**, 10-bit 4:2:2 (yuv422p10le), fourcc \`apch\` | **Implemented and native-tested** on Linux; editorial interoperability across target NLEs not yet certified |
| Professional editing, particularly Avid | **MOV or MXF** | **Avid DNx HQX** (historical DNxHR HQX / DNxHD HQX), higher-quality bit-depth profile | **Planned**; specific codec/container/raster combinations need independent decoder and NLE import tests |
| Color/VFX/render source exchange | **OpenEXR frame sequence** (plus timing/provenance manifests) | Scene-linear high-dynamic-range channels with depth, mattes, object IDs, multilayer controls where supported | **Planned**; source must genuinely contain HDR/float passes, not an 8-bit PNG converted to EXR |
| High-end effects/compositing and transparent overlays | **ProRes 4444 MOV** or EXR | 4:4:4:4 including alpha when real source exists | **Planned**; correct alpha and high-bit-depth source must be independently checked |
| Theater projection | **DCP package**, **not one ordinary video file** | JPEG 2000 picture, compatible MXF, theater-compliant sound, composition playlists and associated standards | **Planned with strict independent conformance testing**, not a codec toggle or renamed MOV |
| Archival / studio interchange | Project's immutable package plus source assets and one or more non-lossy or near-lossless masters | Exact render settings, licensed dependencies, edits, source-version lineage | Data indexing foundation implemented; complete archive/export workflow not yet finished |

Apple: https://support.apple.com/en-ae/102207 (ProRes 422 HQ and 4444 profile distinctions)  
Avid: https://kb.avid.com/pkb/articles/en_US/Knowledge/Avid-DNx-naming-scheme-and-data-rates (current DNx family including HQX, 2026 naming guidance)  
Digital Cinema Initiatives: https://www.dcimovies.com/dci-specification/ (D-Cinema specifications).

## Implementation details — ProRes first

**Module:** \`backend/nvp_full_motion.py\` exposes \`FullMotionPipeline.render_video(..., output_profile=...)\`.

Current advertised output profile values:
- \`h264_mp4\`: H.264 / MP4 / \`yuv420p\` / 8-bit coded data, FFmpeg \`libx264\`.
- \`prores_422_hq_mov\`: ProRes / QuickTime MOV / \`yuv422p10le\` / HQ profile \`apch\` (FFmpeg \`prores_ks\`, profile 3).

Codec and container are distinct. **MOV is the wrapper; ProRes is the codec.** A file named \`.mov\` without the correct stream/profile is not an accepted ProRes HQ export.

Each completed video revision stores the chosen output profile, exact video codec/pixel format/codec tag, container MIME/extension, real frame count and FPS, source stage/actor/camera/take and frame-presentation hashes, immutable media SHA-256, encoder probe receipt, duration and audio timestamp metadata.

The independent reopen check re-hashes the complete output file and can invoke FFprobe to read *actual* codec, pixel format, codec tag (including ProRes HQ \`apch\`), width, height, exact frame count and timebase, followed by FFmpeg full decode. Any mismatch is rejected. The raw movie never becomes project authority.

### Efficient multi-format delivery without re-rendering the film

A critical architectural feature: \`render_video(..., source_frames_id=...)\` can reuse an existing, SHA-verified **full-frame presentation** that matches the same take, rendering engine/style, samples, dimensions and capture revision. It then **encodes another video format using exactly the same stored source frames**, without running Blender again or altering the approved take.

Example:

    Frozen Take 004 (24-fps timed scene)
            |
    Blender Cycles PBR  -> indexed frames, SHA-verified
            |                       |
      H.264 MP4 review         ProRes HQ MOV editorial
            |                       |
          presentation A        presentation B
             \_____ linked to same exact take and frame set _____/

This is ideal for NVP's future editor: the director can approve a high-quality visual result once and choose multiple delivery formats later. A format export does not require a new actor performance or a new generative model pass.

### Critical quality and color caveat

A **10-bit ProRes encoded stream is not necessarily a true 10-bit-quality render.** The current source in PIPE-01B is a Blender PNG image sequence generated from proxy meshes. FFmpeg correctly converts those images into ProRes 422 HQ-coded 10-bit 4:2:2 samples, but cannot restore genuine high-bit-depth, wide-gamut, HDR, alpha, texture or lighting detail absent in the source. This acceptance proves *correct codec/container/provenance and real source video*, not complete professional color-science or cinematography mastering.

Before shipping studio-quality deliverables, implement an explicit **color pipeline**: declared scene-linear working space, OCIO configuration and versioning, render/encoding transfer function, color primaries, range, mastering/display intent, grading metadata, pixel bit depth and independent sampled-value/round-trip tests. Do not label an output "Rec. 709 master", "DCI-P3", "HDR PQ" or "DCP compliant" without actual conversion and separate conformance evidence. Retain creator control over raster, frame rate and audio specifications, subject to delivery target constraints.

### Audio and professional editorial

Current video outputs contain **no real sound track**. There is only a structured, sample-aligned dialogue time manifest in the Digital Take and Presentation. A professional deliverable must eventually carry approved PCM audio tracks (e.g. 48-kHz 24-bit), explicit channel/stem routing and verified synchronization; sound/voice model choice remains with the filmmaker. For post-production interchange, provide compatible timeline metadata such as OTIO/AAF/XML **only after** validated editorial export and target-application round trips.

### Theatrical DCP is not ProRes MOV

DCP is a **digital-cinema package** with separate picture/audio essence and playlist/asset metadata and strict interoperability rules; it is **not** MP4 or ProRes in a MOV container. Build it as an explicit, separate output/workflow gate, with real standard-specific raster, frame rate, color-space, audio, MXF/playlist, KDM/encryption options and independent validation. Do not present a DCP option as functional before an actual cinema-compliant artifact is tested.

## Acceptance

- **PRO-01**: Preserve existing H.264 MP4 under default config and independent full video decode.
- **PRO-02**: Render a real approved frozen take into one complete full-frame intermediate; export ProRes 422 HQ **MOV** from those saved exact source frames while preserving their SHA hashes.
- **PRO-03**: Independent actual codec reading must prove \`prores\`, \`apch\`, \`yuv422p10le\`, exact 24 fps, correct dimensions and complete frame count; full decode.
- **PRO-04**: Persist separate project-scoped MOV SHA and media type; restart and compare source IDs, timing and images to H.264 presentation. Reject any swapped ProRes HQ tag, 8-bit stream, partial video or cross-project access.
- **PRO-05**: Never infer genuine high-bit-depth render/color mastering from the encoded ProRes wrapper. Capability report and docs must distinguish source quality from output format.
- **PRO-06**: Later DNx, EXR, ProRes 4444 and DCP require their own explicit valid output and external compatibility/conformance gates.

**CI:** https://github.com/vjmichael/nvp_offline_film/actions/runs/41700029191 — Linux native H.264 + ProRes 422 HQ actual movie generation/decode passed, 445 regression tests (438 pass, seven skipped), Vite build passed, Windows Python/React and Blender geometry success; **all five jobs green**.

**Next quality milestone:** high-detail actor/set representations and true source color pipeline. ProRes interchange will then preserve those renders to a much more useful professional standard.
