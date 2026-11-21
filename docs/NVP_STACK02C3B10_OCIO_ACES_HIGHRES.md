# NVP-STACK-02C3B10 — Production-resolution EXR and official OCIO/ACES 2.0 color conversion

**Project scope:** NVP film engineering only. Lu–DLC workspace integration stays postponed until after Lu v1.0.

## Purpose and deliverables

B9 proved an actual 120-frame 24fps sequence of native Blender `OPEN_EXR` **32-bit float RGBA** images at 160×90, with separate independent Blender float readback and original Digital Take lineage. B10 adds **actual higher-resolution image rendering** and a separate **official, pinned OpenColorIO ACES 2.0 conversion**, without claiming that a color-space label or an 8-bit proxy creates genuine scene-referred detail.

### High-resolution admission and true rendering

`backend/nvp_b10_render_profiles.py` defines deterministic resource limits. Profiles are conservative **minimums**, not a guarantee a home PC can actually meet them. Every approved render also uses the original OS-measured resource guardian's 20%/at least 2048-MiB RAM headroom:

| Output | Maximum frames per native render worker | Minimum requested RAM |
| --- | ---: | ---: |
| 640×360 or smaller | 8 | 1024 MiB |
| up to 1280×720 (HD) | 2 | 2048 MiB |
| up to 1920×1080 (Full HD) | 1 | 3072 MiB |
| up to 3840×2160 (UHD/4K) | 1 | 8192 MiB |

**UHD/4K is currently a planning/capacity profile, not executable:** B9's Workbench worker does not yet declare a measured GPU-device VRAM reservation. B10 refuses 4K execution until a device-scoped GPU budget is admitted by NVP's resource governor. A declared 8192-MiB RAM floor alone is insufficient to protect a workstation GPU. Full HD and HD remain the executable native B10 paths; real Windows VRAM/stability acceptance is still open.

Every frame still uses B9's exact frozen-take source, saved Blender project, 32-bit RGBA ZIP OpenEXR writer, measured CPU/RAM admission, bounded OS-contained worker, second native readback and content-addressed FilmIndex publication when all frames are present. The full take's estimated uncompressed RGBA32 bytes are checked against free disk **including output duplication during archival** before accepting whole-sequence consent. Higher-resolution native work needs explicit resolution, RAM and chunk-count consent; it cannot silently escalate the workload.

B10 Linux CI executes one genuine Blender 1920×1080 Float32 EXR frame with independent native readback, while B9's complete **120-frame** test remains 160×90. **A complete 120-frame Full HD or 4K production run is not yet claimed**; full-frame higher-resolution stress, Windows GPU workloads, independent lighting/artistic acceptance and actual rigged actor fidelity remain separate gates.

### Official ACES 2.0 conversion and provenance

`backend/nvp_b10_ocio.py` uses the **official OpenColorIO 2.5.2 library** and immutable named built-in **`ocio://cg-config-v4.0.0_aces-v2.0_ocio-v2.5`**. It loads that exact library/config, requires the ACEScg output color space and supported Rec.709 linear input, validates config and records serialized SHA-256 plus OCIO cache identity. It reads actual original Float32 EXR channels into CPU float arrays and applies the real `getProcessor(source_space, 'ACEScg').getDefaultCPUProcessor().applyRGB` processor to **all** RGB pixels. Alpha is preserved untouched. The output is a separate, genuine 32-bit OpenEXR with explicit ACEScg/AP1/D60 `chromaticities`, config identity and original frame hash; no display-view/Output Transform is baked into the scene-referred ACEScg frame.

`backend/nvp_b10_color_worker.py` stages this transform with a separate creator action and exact film, indexed image SHA, OCIO config SHA, source/target spaces, file identity and RAM budget. An **OS-contained native Python process** runs it through the existing TaskLedger/ApprovedTaskBindings for queueing, measured headroom and durable authorization. It cannot start from a browser POST or model prompt. Another **separately executed host verifier** reopens actual source/output files and independently compares representative transformed pixel values to the official OCIO processor, revalidates AP1 color primaries, confirms alpha preservation and checks source/output SHA. Unsafe workers retain resource reservations until cleanup is proven.

`backend/nvp_b10_color_publish.py` registers a **new FilmIndex `presentation`**, keeping typed dependencies to the original frozen Digital Take and original scene-linear EXR presentation. It stores the transformed image as project-scoped `image/x-exr`, saves the conversion receipt, verifies the original source before publication and independently reopens all bytes and color evidence after restart. NVP does not mutate the frozen Digital Take, alter the original B9 image, or keep either image resident in VRAM after the worker ends.

### Color truthfulness and remaining limits

- **Proved when B10 native acceptance passes:** genuine RGB 32-bit data was processed by a versioned official ACES 2.0 OCIO config into ACEScg/AP1 floating-point image data, with independently checked samples and durable original-source lineage.
- **Not yet proved:** universal declaration of a B9 input file's original RGB chromaticities from Blender's current custom OCIO config. B10 assumes/declares the standard Blender default scene-linear **Rec.709/D65** primaries for that input and reports `full_blender_input_primaries_proven=False`. User-supplied custom OCIO configurations need separate native input-color-space attestation. A subsequent color-integrity gate will remove this explicit qualification.
- **Not yet delivered:** an actual ACES 2.0 **DisplayViewTransform** to a measured sRGB/P3/Rec.709 monitor, grading controls, certified output viewing transform, perceptual gamut-mapping approval, full-resolution 120-frame delivery, video/audio mastering, ProRes, IMF or DCP. ACEScg working-space conversion is not the same thing as an output display transform.
- **Security:** Only the native host-supplied authenticated local creator event can authorize new job types. Test fixtures' event objects merely simulate user presence; installed NVP desktop user-presence UI remains open.

## Acceptance and dependencies

CI workflow `.github/workflows/nvp-stack02c3b10-ocio-highres.yml`: Windows/Linux pinned PyOpenColorIO 2.5.2 and OpenEXR 3.3.4 actual Float32 pixel tests; high-resolution admission/disk refusal; actual Linux Blender 1920×1080 native EXR + separate native float readback; official CPU OCIO conversion in a **different, OS-contained resource-admitted process**; independent pixel proofs; FilmIndex re-opened original source plus derived ACEScg presentation. React source/permission regression retained. No Lu runtime dependence.

Open technical references: [OpenColorIO ACES 2.0 CG configuration](https://opencolorio.readthedocs.io/en/v2.5.2/configurations/aces_cg.html), [OpenColorIO processors](https://opencolorio.readthedocs.io/en/v2.4.2/api/processors.html), [OpenEXR Python pixels](https://openexr.com/en/latest/python.html), and [Blender scene-linear color-management roles](https://docs.blender.org/manual/en/4.5/render/color_management.html).

**Repo:** NVP B10 draft, stacked on B9. Previous B9 acceptance remains its own separately documented gate.
