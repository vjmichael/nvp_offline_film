# NVP-ADR-STACK-002 — Blender-first external production workers; OpenUSD deferred

**Date:** 2026-11-03  
**Status:** Creator-approved architecture selection; runtime packaging and compliance verification remain future gates  
**Supersedes:** Any prior assumption that a separate OpenUSD runtime is mandatory for NVP's first commercial production pipeline  
**Related:** [STACK-001 reuse-first and single-installer policy](NVP_ADR_STACK01_REUSE_FIRST_AND_ONE_INSTALLER.md) and [data-first capture authority](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md)

## Decision

**Use Blender as NVP's primary external 3D production engine.** It already handles scene construction, rigging, animation, lighting, cameras, rendering and import/export. NVP will not duplicate these capabilities in a new proprietary 3D runtime.

**Do not require a standalone OpenUSD SDK/service as part of the baseline installer.** The NVP data-first architecture does not depend on USD: the authoritative Digital Film World and frozen Digital Takes remain versioned NVP production data, not a `.blend` or USD scene. Blender scenes, OpenEXR renders and any USD files are derived/versioned representations.

**Keep USD as an optional interchange format** through Blender's own USD importer/exporter when supported, rather than pulling in the OpenUSD API by default. A dedicated OpenUSD composition worker is considered only after a demonstrated need for cross-application layering, reference/variant composition, very large federated scenes, or multi-team collaboration that Blender's importer/exporter cannot handle. Do not claim full USD semantic round-trip fidelity merely because a file imports successfully: Blender's published limitations on USD layers, references, variants, some shaders and other concepts require exact per-use-case tests.

This decision does **not** ban a user from exporting/importing USD when Blender supports it.

## Worker boundary (proprietary NVP core ↔ independently licensed Blender)

```text
NVP proprietary desktop app:
  Film World + creator-approved screenplay + approved scene/camera/performance contracts
    -> immutable Digital Take manifest + content-addressed source IDs
    -> bounded render/export job in NVP-managed work directory
    -> independent Blender worker invocation (CLI/executable)
    <- generated .blend / EXR / preview files and optional worker receipt
    -> NVP independent audit, hash registration, durable FilmIndex version
    -> director-visible draft Presentation (not automatically accepted)
```

NVP's proprietary process should **not link Blender GPL libraries** or import Blender's `bpy` API directly. Its interface to Blender is a documented **external command-line and standards-based file boundary**. Any *distributed Blender-side Python adapter/scripts that call `bpy`* require an explicit GPL compliance review and appropriately licensed distribution; they are **not** automatically proprietary merely because NVP generated or launches them. Keep such adapters minimal, independently versioned and replaceable. Using separate processes alone is not a complete copyright/legal determination.

The final retail installer can deliver NVP and an unmodified independently licensed Blender executable, subject to the actual release's GPL notices/source distribution obligations and an attorney's review of the precise integration. Do not restrict users' GPL rights to Blender under NVP's proprietary EULA.

### Native worker execution requirements

- NVP invokes a **fixed, version-checked executable**, never arbitrary commands from a model-generated scene or a user's project filename.
- The job contract contains project/take IDs, frozen input SHA-256s, expected resolution/frame range/quality, output directory allowlist, resource limits and a unique idempotency key; it contains **production data**, not opaque shell snippets.
- NVP supervises the process (bounded memory/time and child cleanup, progress, cancel/restart recovery), logs its version and executed operation, and never treats tool discovery as authorization.
- The Blender-side adapter constructs/opens the scene and runs existing Blender operations. GPL-covered adapter scripts, if distributed, must be independently licensed/compliant.
- NVP verifies source lineage, timing/raster/bit depth, camera IDs, scene geometry/canonical IDs, file hashes and other required effects **before** committing any derived Presentation. A failed worker never edits the original World/Take or silently commits partial output.
- The user experiences **one NVP interface and one installer**, with no compulsory Docker or command-line setup. Optional standalone Blender GUI access remains an advanced workflow, not the primary UX.
- A `.blend` file is a *renderer/production artifact*, not automatically the authoritative NVP Film World. NVP changes and reviews take place through typed user-approved versioned source records.

## USD re-evaluation trigger (specific, not hypothetical)

Do not integrate a separate OpenUSD runtime solely because it is an industry standard. Open an `STACK-USD-01` evaluation only when a proven project needs one of:

1. Non-destructive composition of USD **references/variants/layers** across separate DCC applications, which Blender's native import/export cannot preserve adequately;
2. Very large scenes managed in reusable, independently authored subassemblies with measured scalability problems in the Blender-only workflow;
3. Actual external collaboration/facility handoff requiring USD composition semantics instead of a simple geometry/animation interchange;
4. A demonstrable asset/rigging/camera fidelity defect that cannot be solved with supported Blender native features or other mature interchange options.

Evaluation uses the same frozen NVP fixture and records measured interchange fidelity, versions, CPU/memory, Windows packaging footprint, licensing, source identity and rollback behavior. If no demonstrated gap exists, retain Blender-only.

## Source references (verify against the selected release before shipment)

- [Blender licensing FAQ](https://www.blender.org/support/faq/) — external proprietary orchestration and Blender Python API script distinction; GPL redistribution obligations.
- [Blender USD import/export documentation](https://docs.blender.org/manual/en/latest/files/import_export/usd.html) — supported geometry, animation, camera/material types and current feature/round-trip limitations.
- [Pixar OpenUSD project](https://github.com/PixarAnimationStudios/OpenUSD) — scene-description interchange and composition, not a replacement for the Blender DCC/render pipeline.

**Delivery condition:** Architecture approved here; no claim of a finished commercial installer or legal clearance for the selected Blender distribution. That requires STACK-01E binary/worker/license/NSIS acceptance.
