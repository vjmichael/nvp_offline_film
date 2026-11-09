# USD-FILM-02M-HR — actual approved district in original frozen actor/camera Cycles shot

**Task group:** 02M-H real 01D/01E shot quality after P0-F-01. **Date:** 2026-11-09.
**State:** source implementation and native tests **AUTHORED**, independent Windows/Linux/OpenUSD/Cycles jobs **NOT EXECUTED / NOT ACCEPTED**. This task never represents a human-approved render or finished film.

## Objective and source invariants

Make a genuine original film frame where approved native 02M modular building geometry, PBR materials, original 01E ActorID/performance and 01D camera are in the **same** derived USD shot at an exact original Film Time tick. The district alters staging and scene occlusion; the source camera/actor/voice/PCM/immutable world and existing Takes do not change. The filmmaker must be able to revise an approved district without reshooting the performer.

This does not generate fake humanoids, rearrange original footage, replace actual Cycles images with a still, treat an AI model answer as a worker grant, or convert the actor's Take to editable frames.

## New code, reusing current NVP architecture

- `backend/nvp_usd_film02m_h_render_handoff.py` adds `stage_approved_original_shot` and `ReviewedDistrictShotCyclesHost`. The first reopens the immutable **approved** 02M-H world/actor/camera shot binding; rejects wrong source, Take or film tick; uses original `01F._snapshot_usd` for the genuine frozen source and original PCM association; calls `02M-E2.source_district_render_view` to expand only bounded visible approved PointInstancer modules into actual source-PBR USD meshes. It adds district geometry at its approved origin to a disposable derived USD stage only. Original camera matrices and actor geometry are checked before and after insertion.
- Stage exports to a temporary file then atomically replaces the private shot snapshot. It reopens the **actual disk bytes** using an anonymous Sdf layer to avoid a false pass from cached OpenUSD layers. Checks every imported original district mesh and bound PBR source material. No Blender process is started by `stage`; no director source revision is written.
- Render host accepts only a **fresh operation-specific director decision** for the exact binding SHA, source world Take SHA, 01D camera SHA, district document SHA, original film tick and derived native USD file SHA. It reopens the approved binding after review and dispatches the pre-existing 01F first-party Cycles script through `BlenderWorkerSupervisor` and its durable native receipts. This is separate from binding approval; no authority is inferred from stored historical approval or model text.
- `tools/nvp_usd_film02mh_blender_reopen.py` runs in a **second native Blender process** after the real render. It loads the real saved `.blend`, verifies source world Take/camera SHA metadata, original ActorID roots, genuine building root objects, actual saved mesh/PBR objects and exact source scene SHA. The first render PNG and `.blend` SHA are independently checked. It cannot synthesize or repair missing actors/materials.
- `ReviewedDistrictShotCyclesHost.compare_approved_revisions` renders **two different approved revisions of the SAME district** over identical original performer/01D camera/Film Time. It requires different real Cycles PNG hashes **and** at least 250 meaningfully different pixels, along with both independent saved-scene reopen receipts. The source actor/PCM Take SHA, camera/shot SHA, approved district revision SHA and original world invariants are checked again after rendering. This pixel test verifies a genuine changed photographed environment, not shot artistry or photoreal human performance.

## Native acceptance and proof boundaries

Added `tests/test_nvp_usd_film02mh_real_shot_render.py`. The real 01F original 30-second source fixture supplies four authentically linked actor meshes, world camera/01E world Take and original PCM; the test publishes six genuinely assembled building USD source modules and two source-approved district revisions. Source-only tests verify two distinct derived USD layers over exactly the same frozen actors, identical camera, original source geometry, real PBR material references and unchanged immutable Takes.

The dedicated `NVP_FILM02MH_BLENDER_BIN` integration test runs two real **Blender 5.2/Cycles** jobs through the protected supervisor, reopens both saved `.blend` files under separate protected workers, compares at least 250 visibly different pixels, verifies exact original source SHA and exports 320×180 PNGs, Blender projects, native audit receipts and the source USD. If Blender is not configured, that test **skips** in generic source runs — this is **not** native render acceptance.

One **manual-only**, consolidated end-of-group native Windows/Linux/OpenUSD and official Blender 5.2.3 workflow is staged at `.github/workflows/nvp-usd-film02mh-real-actor-district-render.yml`. It is NOT triggered by every source commit; run **once** when the preceding queued acceptance backlog has cleared enough to get actual runner evidence. Do not mark native or Cycles PASS before inspecting exact-head logs, PNGs and independent saved-scene receipts. Repair demonstrated failures and rerun the group once, not for every edit.

## Remaining after source implementation

1. **Native OS execution:** Collect real Windows/Linux Python 3.11/3.13 `usd-core==26.11` results and official Blender 5.2.3 Linux Cycles pair. Fix actual reported differences in USD path mapping, Blender material imports or camera source readback.
2. **Artistic framing/occlusion:** inspect rendered pixels, source-visible walls/windows, actor framing and near-LOD mesh, shadow and depth of field. The present host does not guarantee human-composed camera framing or visually excellent lighting just because native meshes and image bytes exist.
3. **Installed original film editor:** expose a bounded, preview-first 02M-H actual-render request through the existing trusted NVP WebView2/WO6 desktop bridge; require separate operation-specific Windows OS confirmation and verify interruption/restart recovery from an installed NSIS exe. A source-only preview/shot binding **cannot claim real installed picture review**.
4. **Camera rails/shot FX:** implement planned CAM-FX-01/02 deterministic director-editable virtual rails in a separate stronger OpenUSD layer; CAM-FX-03/04 installed director controls and typed AI suggestions; CAM-FX-05 native render and selected-view 01Q/01S/01T final-film acceptance. Original ActorID performances, source Takes and PCM remain immutable.

**Sequential status:** F/G/H native run #42650335958 queued; P0-F-01 installed real GGUF/NSIS run #42664870777 queued at the last inspection. Those are **distinct earlier acceptance groups**; no source status should be promoted from their queued state.
