# USD-FILM-01 — scalable, source-locked OpenUSD film-world composition

**Engineering state: first code and native Windows/Linux tests committed; exact-head native acceptance OPEN.** USD-FILM-00 source-capability audits are independently queued and not assumed accepted. Stacked on USD-FILM-00 PR #128.

## Purpose

Move beyond a single scene into a **persistent, reusable, director-editable 3D world** assembled from existing FilmIndex-owned scenes and asset revisions. OpenUSD stays the spatial and animation substrate, not a separate simulation engine or video generator. FilmIndex + Production Bible preserve identity, revisions, immutable Digital Takes and film-time.

The initial implementation in **backend/nvp_usd_film01_world.py** deliberately starts with small typed, bounded world assemblies and makes loading measurable. This is a **real native USD composition layer**, not a production city streamer, renderer, massive-scale geometry pipeline, texture resolver or final editor GUI.

## Original source authority and storage

- Build from original `OpenUSDSceneBridge.open(project, scene_id, revision)` and `OpenUSDAssetRegistry.open(project, asset_id, revision)` only. Both verify FilmIndex's original SHA-addressed project-scoped source. An AI prompt or ordinary UI request cannot inject an arbitrary file path or external USD layer.
- Record a new **FilmIndex `world` revision** with exact scene/asset IDs, revisions, original document SHA, staged layer SHA, source metadata, and typed dependencies. The original `asset`, `scene`, `take`, authored animation, ActorID, audio, and film times remain untouched.
- The world manifest contains **no authoritative absolute paths or external resource URLs**. During `OpenUSDWorldComposer.open()`, original source scenes are reconstructed through the already trusted scene bridge, temporarily flattened for a self-contained *staging snapshot* and joined to source asset layers under private temporary SHA-named USD paths. These temporary reference paths are never stored in FilmIndex. Their bytes and exact source identities are rechecked on each world reopen. Temporary staging is destroyed on context exit. The source-staging step currently rereads/flattens all set layers before `LoadNone`; **that preprocessing overhead is measured and is not yet a fully lazy source resolver**.
- Source scenes must currently use the existing NVP native **meters / Z-up** schema. A legacy Y-up/centimeter USD set requires a reviewed explicit unit/axis migration; silently mixing coordinates is forbidden.
- Original scene/asset USD texture AssetPaths requiring unresolved image dependencies fail closed rather than producing missing-material film sets. Scalar preview materials may remain. Project-authorized texture/MaterialX resolution and full material fidelity are separate follow-up gates.

## True OpenUSD composition features

| World resource | Authoring | Runtime behavior |
| --- | --- | --- |
| Reusable sets | Named source scene ID + exact revision | Native USD **payload** under `/World/Sets/`, unloaded at Stage.LoadNone; explicit bounded Load/Unload on chosen sets |
| Props | Source asset ID + exact revision + meter position | Native **reference** (always composed) or lazy **payload** (explicit typed load/unload) |
| Alternate looks | 2–6 original source asset revisions per named variant | Actual **UsdVariantSet** `look`, director selection stored in world revision; ephemeral preview switches do not mutate prior revisions |
| Background collections | Named original asset prototype + bounded positions | Actual **UsdGeom.PointInstancer** with one source prototype and repeated positions; per-person animated ActorIDs are **not** instanced this way |
| World revision | Original source IDs/SHAs and exact compositional metadata | New `world` revision retains old world and original frozen scene Take; supports shot-to-shot reused source and independent look |

Current engineering budgets: 8 source sets, 40 named props, 8 variant objects, 12 instancer groups, 2,048 elements per group and 4,096 total instances, 70 unique sources, 128 MiB maximum private staged USD bytes. These are intentional alpha bounds, **not claims of production-scale city capacity**. Additional budgets for texture backing and large enough payload streaming must be measured before widening.

## Real working-set and restart evidence

The `WorldSession` object exists **only inside a private context manager**. On entry it opens the actual new composed USD root using `Usd.Stage.LoadNone`. It can load/unload selected original sets and lazy props and switch an authorized look variant in its disposable session. Receipt includes original world document SHA, staged file count/bytes, native Stage.LoadNone duration, per-set load/unload latency, current process RSS samples and loaded source names. RSS is **whole-process memory**, not an isolated USD working-set size; GPU VRAM, rendering pixels and genuine preview latency are NOT measured.

`tools/nvp_usd_film01_benchmark.py` creates **real USD** from one FilmIndex project: two independent original scenes, reusable source props and variants, and 1,200 actual PointInstancer positions. It publishes a world, reopens under a fresh Studio/FilmIndex, measures stage/open/load/unload, verifies one set loads without the other and that the original SHA survives restart. The evidence JSON labels all observations and open renderer/VRAM gaps.

`tests/test_nvp_usd_film01_world.py` has real native USD assertions for multi-set lazy payloads, source camera after load, lazy individual props, actual variants and prototype geometry, revision-specific asset changes, frozen source Take SHA/verify after newer world publication, fresh SQLite reopen, foreign-project failures, unexpected paths, invalid coordinates, excessive instancing and variant substitution refusal.

## Native acceptance and next subtasks

- **USD-FILM-01A — IMPLEMENTED CODE, native acceptance OPEN:** source-locked multi-scene world, exact durable FilmIndex source manifests, real USD references/payloads/variants/instancers, private staging, typed load/unload and preview look switching.
- **USD-FILM-01B — IMPLEMENTED TESTS, results OPEN:** 4-cell native Windows2025/Ubuntu24.04 Python3.11/3.13 source/Take regressions; 2-cell native original 1,200-instance resource benchmark, JSON evidence, restart source SHA.
- **USD-FILM-01C — NEXT:** efficient project-local **content-addressed resolver** that can stage only specifically requested sets, plus verified immutable texture/MaterialX dependencies and virtual cache. Current initial open still flattens every original set once, and a true large-world streaming guarantee must not be inferred merely from unloaded USD payloads.
- **USD-FILM-01D — NEXT:** shot-aware, camera/working-set-driven load policy, source actor individuality, multiple camera and set revisions, detailed resource benchmarking (CPU/GPU working set/VRAM), installed editor interaction and recovery acceptance.
- **USD-FILM-01E — NEXT:** integration of composed **world** revisions with original NVP scene/Take presentation, stage shot/lighting/actor ownership and renderer/AI work orders; existing `OpenUSDTakeCapture` currently freezes **scene**, not a whole world. This new world format is not yet directly a frozen playable multi-set Take.
- **USD-FILM-01F — NEXT:** genuinely rendered two-shot original set, source-stable repeated props, variants and ActorIDs with Windows/Linux installed validation; no film/renderer acceptance from USD file generation alone.

**CI:** `.github/workflows/nvp-usd-film01-native-world.yml`. A queued test is not a pass; source-only commits cannot close native acceptance. Failures require actual logs/artifacts and the final exact-head retry.

## Design boundaries

NVP remains **pure filmmaking**. No contracts, consent forms, legal-permission systems, geographic/digital-twin truth database, VR game engine or unrelated scientific simulations are being added. The persistent world should enable photorealistic film first; cartoon and stylized looks remain ordinary future style variants. Actors and facial direction still follow established FILM03 director decisions, including emotional matching by default and full creative override.

**Parent engineering plan:** docs/NVP_USD_FILM_WORLD_FULL_INTEGRATION_MASTERPLAN.md. **Status tracked in:** docs/NVP_DATA_ALL_TASK_LEDGER.md.
