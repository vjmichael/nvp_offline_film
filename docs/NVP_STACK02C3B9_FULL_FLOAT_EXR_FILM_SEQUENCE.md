# NVP-STACK-02C3B9 — Full frozen Digital Take to scene-linear 32-bit OpenEXR

**Scope: independent NVP production. Lu/DLC Workspace interface remains deferred until after Lu v1.0.**

## Architectural boundary

The original frozen DTP remains FilmIndex's authoritative, immutable world/performance/shot/timing data. B8's native Blender `.blend` and technical PNG are **derived presentations** indexed separately. B9 reads that verified indexed Blender project as source, takes a separate explicit creator approval for the requested complete frame sequence, then produces *all* frames as new derived OpenEXR files. The digital take is never held in persistent RAM or VRAM just to keep it available.

## Real native 32-bit EXR path

1. `NativeEXRSequence.create_from_trusted_native_action` verifies the indexed B8 presentation and frozen take SHA/lineage. It requires an injected **trusted local creator-presence callback** approving the exact film/take, indexed Blender source, 24fps frame count, resolution, batch size, memory budget, RGBA Float32 depth and Raw scene-linear output. There is no browser POST endpoint granting execution and no Lu dependency. CI's callback is a test-only simulated native event.
2. Each frame batch has at most **eight** indexed frame numbers and is separately journaled. The original `.blend`, plan and vetted first-party Blender script are copied exclusively, fsynced and SHA-pinned in the existing native worker root. No arbitrary model-supplied code/filename/worker command is accepted.
3. `ApprovedBlenderDispatcher`, `ApprovedTaskBindings`, the measured RAM governor and `BlenderWorkerSupervisor` seal exact operation specs, deny unsafe memory pressure **before launch**, and run the actual pinned Blender binary inside OS containment. Chunk worker outputs are explicit, bounded files (`frame_000001.exr` etc.); the worker verifies magic, bytes and SHA for every declared frame before marking success.
4. The pinned writer uses Blender `OPEN_EXR`, `RGBA`, `color_depth=32`, `exr_codec=ZIP`, **`view_transform=Raw`**, zero exposure and unit gamma. It evaluates the original frame-addressable camera cut markers and actor keyframe animation for each frame. In B9 CI the image dimensions are **160×90** to make full 120-frame real execution practical; production configuration accepts up to 1920×1080 under a separately approved RAM budget.
5. `inspect_exr_header` parses the **real OpenEXR headers** independently, requiring single-part scanline data, the correct data/display dimensions, and IEEE-754 32-bit **FLOAT** (not HALF or UINT) for **R/G/B/A**. A second independent resource-admitted Blender worker reads each EXR back as actual floating-point image pixels and checks float buffers, true dimensions, expected RGBA channel length and sampled finite numeric pixel values. The readback JSON also pins the original EXR SHA, rather than claiming a header alone proves image data.
6. Only when **every frame from 1 to the original frozen take's last frame** is rendered and independently audited may `publish_exr_sequence` stream and index each EXR as a project-scoped `image/x-exr` media blob. The new content-addressed `presentation` manifest preserves frame-to-SHA mapping, independent pixel-audit receipts, original DTP revision-1 dependency, source Blender SHA, working write mode, and explicit color-delivery limitations.
7. `verify_indexed_exr_sequence` reopens **all** content-addressed frames, rechecks hashes, RGBA Float32 headers, continuous frame numbering, original frozen FilmIndex take, and native independent pixel-readback receipts after an app restart. Missing, substituted, duplicated or truncated frames cannot be accepted as a complete sequence.

## Color science: what is proven and what is not

B9 targets a **genuine Blender scene-linear floating-point image buffer written as 32-bit OpenEXR**, not an 8-bit PNG written into a high-bit-depth file. Float channel type and actual decompressed float pixel values are independently checked. Blender's `Raw` view transform is used to avoid baking a display look into the EXR. This is *not yet* proof that the input textures, lighting primaries, monitor transform or working OCIO config all follow a specific ACES configuration. The manifest deliberately records `aces_compliance_verified=False` and `ocio_config_identity_verified=False` until a later color-managed acceptance gate. A straight EXR sequence is not a DCP, ProRes master, audio mix or finished film.

Official format references: [OpenEXR File Layout](https://openexr.com/en/latest/OpenEXRFileLayout.html) and [OpenEXR Technical Introduction](https://openexr.com/en/latest/TechnicalIntroduction.html). Blender supports `OPEN_EXR`, channel depth and codec through [`ImageFormatSettings`](https://docs.blender.org/api/main/bpy.types.ImageFormatSettings.html).

## Safety and remaining work

- User-visible 'render all frames' controls must be introduced only after **installed NVP native host user-presence verification**. Test fixtures never count as creator authentication in shipped software.
- Every native worker remains a temporary, constrained process; finished frames and indexing stay on disk. Uncertain crash/worker cleanup and GPU VRAM pressure remain conservative OS/resource reconciliation tasks.
- FilmIndex DTP and derived presentations are **durable**. Restart-safe re-verification is implemented; retrying failed workers requires fresh authorized identities and cannot overwrite old output.
- Larger shots should later use adaptive batch sizes and per-frame exposure/luminance metrics; 160×90 CI rendering only proves genuine pixel format, not high-resolution cinematic image quality.
- Full professional ACES/OpenColorIO config fingerprinting, accurate scene colorimetry, high-fidelity rigged motion, image sequence mastering, audio and DCP remain later NVP gates.

**Development PR:** B9 draft stacked on B8; no edits to Lu or Cognitum.
