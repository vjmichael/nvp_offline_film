# NVP-ADR-STACK-001 — Reuse-first, conventional filmmaking engines and one-product packaging

**Date:** 2026-11-03  
**Status:** Creator-approved architecture direction; implementation audits pending  
**Priority:** Governs all future NVP feature proposals, superseding any earlier default to develop a custom feature when established software can do it.  
**Applies to:** NVP core, the future Lu Film Workspace DLC, optional production workers, visual editing/grading/animation/finishing, installers and build artifacts.  
**Does not change:** Film World/Data-First capture authority, frozen Digital Takes, source-preserving editorial, creator approvals, provenance, offline-first and single-installer UX.

## 1. Decision: adopt, compose and package before building

> **Do not implement a custom filmmaking operation when maintained, licensable software already performs that operation adequately.** NVP should **reuse existing applications, libraries, standards, effects and tools** and deliver them behind a consistent NVP interface. New bespoke algorithmic work is a **last resort**, allowed only when a narrowly stated operation cannot be accomplished by proven alternatives, either directly or by composing existing facilities.

This is not a general "write less code" suggestion; it is the default requirement on all implementation tasks. Existing custom prototypes are **not automatically permanent**. The reuse-first decision applies to planned and already prototyped features (especially grading/curves/scopes, timeline and EXR processing).

**Minimal original code is still necessary to make the product:** NVP-specific typed World/Take/Presentation contracts, immutable identity and custody/provenance, creator and AI authorization boundaries, deterministic workflow routing, adapter calls to external workers, bounded task supervision, integrated UX, installer manifests and cross-component verification. These are **orchestration and data integrity**, not competing replacements for image-editing, video-editing, rendering, VFX or audio engines. Keep such code narrow and testable.

A vendor application's preexisting UI need not be copied or embedded verbatim. Adopt the public supported library/API/CLI/interchange format, or run a contained auxiliary worker. Use the full application only when reuse of its UI/workflow is actually preferable and legally appropriate.

## 2. Strict custom-operation exception

Before authoring or extending custom processing logic, require an implementation decision record with:

1. **Exact unmet operation:** input/output, technical fidelity, timing, performance, quality target, portability and needed editor controls; not broad statements such as "NVP needs color grading."
2. **Evidence of market/library search:** at least two credible existing approaches **where available**, checked for active maintenance, standards and APIs; include older tools and compatible components in Claude's creator-supplied conventional toolchain.
3. **Composition attempt:** can existing engines solve the operation in sequence, through a plug-in, or via a supported interchange standard?
4. **Reproducible acceptance:** the same frozen NVP fixture (initially the existing 16-frame/two-shot Cycles HALF EXR test) for existing engines and any custom candidate. Verify exact source lineage, image samples, effect behavior, speed, memory, crash recovery, and round-trip.
5. **License and deployment audit:** actual selected binary build, transitive dependencies and codecs, Windows support, source distribution, licensing compatibility, maintenance, security updates and offline packaging.
6. **Gap and narrow scope:** describe the *specific* behavior unavailable through the evaluated software; seek creator approval for any algorithmic replacement and add a tracked expiry/re-evaluation gate for the prototype.
7. **No silent fallback:** if an adopted engine is missing or cannot perform a requested operation, report blocked/unsupported; never fabricate a successful master or quietly switch to an approximate custom method.

If an existing implementation performs correctly, **adopt it**; benchmark potential custom advantages only as evidence, not a default reason to invent a new system. **When an adopted library exposes exact domain transforms, do not replicate its math in NVP without a concrete demonstrated gap.**

## 3. Initial reuse candidates — evaluation, not automatically adopted

| Production responsibility | First-choice candidate or standard | Required evaluation |
| --- | --- | --- |
| Scene assembly, rigging, cameras, animation, high-fidelity rendering | **Blender** / Python bpy / Cycles; OpenUSD for complex interchange | Reuse existing robust animation, constraints, renders, drivers, shader nodes; no new renderer/rigging runtime |
| Source-space color and grading math, LUT and CDL | **OpenColorIO** (OCIO grading transforms, file transforms, configs, ACES) | Compare current NVP homemade curve, wheels and 3D LUT paths; adopt OCIO where equivalent or better |
| EXR/HDR image processing and thumbnail caching | **OpenImageIO** / OpenEXR | Image and tile caching, high bit depth, channel precision, codecs and throughput on same NVP EXR source |
| Editorial timeline representation and exchange | **OpenTimelineIO (OTIO)** | Exact film/source timecodes, clip IDs, handles, transitions; preserve custom FilmIndex lineage fields separately |
| Native timeline playback, transitions, compositing and encoding | **MLT Framework**, compare libopenshot | Multitrack renderer, realtime playback, preview, effect availability, codec and licensing requirements |
| Compositing, rotoscoping, masking, optical/VFX effects | **Natron** as an external worker and **OpenFX** host/plugin ecosystem | Avoid building another node compositor; consider plugin host's API and GPL/third-party plugin terms |
| Render/conversion, inspection and verification | **FFmpeg/FFprobe**, **DCP-o-matic** | Pin builds, reject GPL/nonfree codec surprises, use independent decode verification |
| Scene/spatial constraint solving | **OR-Tools CP-SAT**, trimesh and Blender BVH | Replace bounded homemade solver if real 3D constraint cases, performance and predictability benefit |
| Voice, dialogue timestamps, alignment, lip sync | Proven TTS, aligners and lipsync/animation tools | Test actual runtime, consent/license and retarget quality before writing custom phoneme/timing mathematics |
| Sound mixing, spatial sound, loudness and processing | **Ardour**, pyroomacoustics, Steam Audio or pedalboard, FFmpeg loudnorm | Preserve stems and approved mixes; use mature DSP instead of custom audio filters |
| Asset libraries and realistic environments | Licensed/CC0 libraries, Infinigen, procedural Blender workflows | Enforce per-asset license, attribution, frozen provenance and storage policy |
| Shot/camera intent selection, creator-approved World/Take data | Existing planning/optimization libraries where available; **NVP-specific orchestration for unserved gaps** | Preserve source-canon authority, runtime approvals, deterministic verification and source tracing |

All tools must be validated against actual NVP requirements. A popular application can still be rejected for a specific task if unmaintained, incompatible, illegal to redistribute as configured, lacking a stable interface, too expensive on the user's hardware, or unable to preserve the required input/output semantics. Record such rejection rather than extrapolating from brand reputation.

## 4. Package one user-facing application; do not reinvent everything inside it

**User contract:** one desktop NVP experience, one installer/uninstaller, no mandatory Docker/containers or command-line dependency installation. An advanced user may optionally open the native application for specialist work.

**Engineering contract:**

- Main NVP desktop shell owns project library, editor UX, AI proposals, authorization and immutable source lineage.
- Bundled **native libraries** may be loaded through documented APIs in compliance with their licenses. **Isolated local workers** with fixed executable paths are preferred for complex applications, GPL workflows and crash containment; do not assume process separation alone settles derivative-work or copyleft questions.
- Workers are independently pinned, signed or checksum-verified, version-queried, launched with minimal permissions, job-scoped file access, cancellation, time/resource budgets, durable status and explicit recovery. NVP never treats mere tool discovery as authorization.
- The installer carries a manifest of each **binary and exact build flags**, corresponding license notices, redistributable runtime DLLs/shared objects, transitive dependency info, applicable source offers/source bundles, export limitations, SBOM and security update procedures. Hash and record all distributed third-party bytes. Asset and plugin licenses are tracked individually.
- Avoid embedding several copies of the same huge toolkit when a compatible shared worker can serve multiple capabilities. Evaluate bundling size and startup time; optional installer feature selections may be supported within **one installer**, while core offline filmmaking remains usable without network access.
- Third-party worker failures do not mutate or corrupt frozen Digital Takes. On crash, NVP replays journals and only commits a derivative after independent validation.
- Use standard interchange (OTIO, USD, OCIO, OpenEXR, interchange manifests) wherever feasible; preserve NVP source IDs as validated metadata, not by claiming the interchange format knows NVP's private schema.

## 5. Non-negotiable license and redistribution review

Open source does **not** mean "can copy anything into any product without restrictions." The exact licensing for each selected binary, configuration, plugin and dependency matters.

- **OpenColorIO / OpenFX** are BSD-3-Clause-based; retain notices and review dependencies. OpenFX plugin binaries may carry completely different licenses.
- **MLT framework** is LGPL-2.1, but some adjacent MLT applications/modules are GPL or separately licensed. Review the **specific executable/library** included.
- **Blender** and **Natron** are GPL-covered: comply with applicable source, attribution and derivative-work obligations. A separate process is not an automatic licensing exception.
- **FFmpeg** has LGPL and potentially GPL build configurations; exact `--enable-gpl`, `--enable-nonfree`, other codec flags, linked libraries and source distribution control whether a binary may be redistributed.
- **OpenUSD / OTIO / OIIO / Blender add-ons / commercial media assets**: inspect the particular release, included dependencies and redistributable terms instead of assuming a uniform umbrella license.
- Commercial restrictions on media assets, third-party LUTs, sound libraries, generated voices/models and plugin packs are **separate** from open-source engine licenses.

These are engineering risk requirements, not a legal opinion. Before an installer is shipped, obtain appropriate specialist legal review for ambiguous combinations.

Official reference links (informative): [OpenColorIO](https://github.com/AcademySoftwareFoundation/OpenColorIO), [OpenImageIO](https://github.com/AcademySoftwareFoundation/OpenImageIO), [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO), [MLT](https://github.com/mltframework/mlt), [OpenFX](https://github.com/AcademySoftwareFoundation/openfx), [Natron](https://github.com/NatronGitHub/Natron), [FFmpeg legal](https://ffmpeg.org/legal.html), [Blender](https://www.blender.org/about/license/), [OpenUSD](https://github.com/PixarAnimationStudios/OpenUSD).

## 6. Immediate priority: STACK-01 reuse benchmarks, not further bespoke effects

**Freeze new bespoke grading/curve/LUT math** until existing OCIO transforms and image-processing libraries are independently evaluated. The existing GRADE-UI-01, 02A, 02B1 test outputs remain **fixtures** and valid prototypes; they are not proof that custom processing should remain the final engine.

**Ordered test plan:**

1. **STACK-01A — OCIO+OIIO:** Use the exact existing original 16-frame/two-shot HALF EXR capture and test established OCIO `GradingRGBCurveTransform`, `GradingPrimaryTransform`, `CDLTransform` and standard LUT handlers. Compare numerical output, precision, scope evidence, CPU time, memory, Windows availability and library-backed error reporting to the NVP prototype. Use OpenImageIO for source reading/tiles/cache; choose OCIO as source of truth where it meets constraints.
2. **STACK-01B — OTIO+MLT:** Build a genuine editorial sequence with two source clips/cuts from those same frames using OTIO and render via MLT; verify frame/timing/source identity and source revisions. Compare libopenshot only if MLT fails a documented requirement.
3. **STACK-01C — Natron/OpenFX:** Prototype a mask/track/compose with a real upstream node graph or plug-in; independently decode and verify the result before considering any new custom compositor.
4. **STACK-01D — Blender/USD/assets/motion/audio:** Audit conventional scene-building, animation/retarget, mocap, mic/sound and asset library components from the original Claude proposal; introduce native tests only for compatible components.
5. **STACK-01E — Single-installer proof:** Produce a Windows NSIS or comparable single-installer manifest for the *selected* checked components, enforce offline operation, provenance, licensing and install/uninstall acceptance. Do not claim redistributability until licensed binary and transitive artifacts are audited.

A tool may not be added to the official runtime solely because its source has a recognizable open-source license. Selection is an **explicit measured decision** and a valid NVP feature must keep its existing authority, fidelity, independent verification and recovery contract.

## 7. Provenance and NVP differentiation

NVP's novel value is **one orchestrated, data-driven, creator-controlled production workflow**, not the invention of duplicate color-science, physics, 3D renderer, editor or VFX engines:

`Screenplay + persistent Digital Film World → approved scenes, assets and performances → immutable Digital Takes → engine-neutral versioned presentation jobs → standards-based editorial/grade/composite/audio workers → independently validated mastered deliverables`.

The user can edit or replace one derivation without silently rewriting source truth. AI coordinates or proposes; the creator approves; audited conventional tools execute. Retain simple lo-fi fixtures for correctness even while integrating high-quality assets and rendering.

**Conflict rule:** This later creator-approved directive supersedes any prior NVP roadmap statement implying that new custom core processing is desirable without a proven gap. Existing master document authority and separate source identity/authorization requirements remain in force.
