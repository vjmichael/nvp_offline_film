# NVP USD-02 — Reusable USD assets and data-first scene-state evaluation

**Creator-approved direction:** NVP is a data-first filmmaking system capable of generating multiple visual presentations from the same frozen film performance. OpenUSD is the spatial/composition substrate; FilmIndex and the Temporal Ledger remain authorities for identity, time, authoring, consent and frozen creator approvals.

**Status:** Initial code, native regression tests and exact-head Windows/Linux CI committed. Native acceptance is OPEN until actual Windows 2025 / Ubuntu 24.04 Python 3.11/3.13 results have passed. This milestone does NOT claim character animation, generated pictures, final film mastering or native installer release readiness.

## USD-02A: NVP-authored reusable objects

`backend/nvp_openusd_assets.py` authors strictly typed Cube and Sphere geometry under `/Asset/Geometry`, with a canonical `/Asset` Xform root. Native USD emits a small text layer. FilmIndex stores the bytes as a project-scoped SHA-256 blob and creates a distinct immutable `asset` object revision identifying source shape, size and layer digest. A source revision may be used in multiple locations or scenes without duplicating the original USD blob.

`OpenUSDSceneBridge.publish(...asset_bindings=[...])` binds individual `/World/...` prim paths to exact asset IDs and revisions. It records document SHA, layer SHA, path and revision in the scene manifest; FilmIndex records one dependency per exact source revision even when an object is instanced more than once.

On reopen, the bridge loads only pinned project-scoped blobs, reconstructs native anonymous USD layers in memory, then adds USD reference arcs in a temporary stage session layer. **No user-specified asset file path, arbitrary USD import, third-party texture or external asset resolver is permitted here.** USD reference identifiers are transient process-internal values and are NOT stored as authoritative on-disk source paths. This deliberately limits scene capabilities while preventing unreviewed external asset references.

Changes to an asset produce a new `asset` revision; previous scene and Digital Take revisions keep their original exact SHA-bound asset references. Frozen Take manifests now retain the scene's exact asset-binding list. `verify_take` independently checks that the scene's asset-binding manifest has not changed.

## USD-02B: Temporal scene state

`backend/nvp_openusd_time_state.py` builds native OpenUSD world matrices and translations at an arbitrary integer NVP event-time tick, alongside the typed active actions found in the Temporal Ledger. It reports scene/timeline revision document SHA, scene roles, referenced asset identities, bounded active events and an independent data-only snapshot SHA.

The evaluator is a bounded interactive metadata/state query. It verifies exact FilmIndex source revisions of active events but **does not scan the entire film or render pictures** for each query. Full source manifest verification remains at freezing/acceptance boundaries. A preview is not a verified final master.

A changing performance remains authored as USD time samples and semantic Temporal Ledger events. Presentations may later evaluate the same state at 24fps or 60fps output times without changing the source take. USD-02 does NOT yet implement camera optics, rig-joint arrays, facial animation, realistic physics, motion constraints or audio synthesis. Those require a separate state-system and measured acceptance.

## Tests and remaining gates

`tests/test_nvp_openusd_reusable_assets.py` uses real `pxr.Usd`: twice-referenced geometry in one scene, its FilmIndex dependent edge, a moving actor at one second, a second instance of the state evaluator after reopening, creator-approved frozen take, asset revision 1 vs revision 2 preserved across scene/take versions, rejected foreign-project access, rejected arbitrary file path bindings, duplicate instance denial and invented creator approval denial.

`.github/workflows/nvp-usd02-native.yml` installs pinned `usd-core==26.11` and runs those tests plus USD-01 and Temporal Ledger regressions on Linux/Windows Python 3.11 and 3.13.

**Open:** Real GitHub CI result; native wheel bundled dependency/license audit; data-driven procedural asset descriptors beyond cube/sphere; authorized asset import/resolver; USD payload/variant and working-set policy; skeletal/facial/camera/lighting/audio motion; deterministic event evaluation order and constrained geometry/model changes; full Digital Take authorization/crash matrix; native desktop UI/installer and a truly rendered 2D presentation.

**Release reminder:** OpenUSD's TOST 1.0 requires preserving license/notices and careful trademark use. Arbitrary downloaded meshes and sample Pixar assets do not automatically inherit OpenUSD's software license and must be reviewed separately. The current NVP-authored primitive assets do not import external sample asset files.
