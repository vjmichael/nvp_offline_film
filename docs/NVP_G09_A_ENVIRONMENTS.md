# G09-A — Environments and production scene finishing

**Development source branch:** `nvp/g09-production-environments-20261111`, stacked on G08 native film export and G07 source-based editing. This is **a source-implementation milestone, not a tested production-quality release**. No GitHub Actions, PR verification, compiler, physical GPU, owner GUI, native rendering, or full-picture acceptance was executed under the creator's build-first priority.

## Filmmaker experience

In **Post-Production → select a shot → Finish the scene's look**, the filmmaker sees creative choices instead of USD, PBR, shader paths, asset resolvers, worker commands or model protocol:

- Choose **Interior, City, Mountains, Coast, Forest, Desert, Farmland, Space, Open Landscape, or Original Setting**.
- Each location now authors real scene-relative, independent 3D objects (building/road/street-lamps, room walls/doors/furniture, trees/soil, dunes/rocks, field crops/fences, shore/water, mountain ridges, asteroids) rather than a label or static background. All set objects are individual editable geometric entities with stable Take-bound identities. Changing the preset removes prior generated entities but keeps director-added custom set pieces.
- Choose sun direction/height, intensity, ambient fill, temperature, sky, ground, fog color and density; select physical surface parameters for actual filmed objects (roughness, metallic finish, color and glow).
- Dress the set with bounded position/size/shape/material controls, move or remove derived set objects, and preview the actual OpenUSD scene from a saved frozen Take.
- **Approve This Scene Look** explicitly before it can affect a finished movie. An unapproved revision is shown in the editor but does **not** silently replace the last approved exported look. Save an approved scene look as a reusable set, and clone its pieces into another Take under fresh object identities. No hidden command/approval machinery is exposed in the UI.

## Source-of-truth and production data flow

1. `backend/nvp_g09_environment.py` creates immutable `g09_environment_versions` in the existing ordinary SQLite or encrypted G03 in-memory SQLite movie store. `g09_environment_heads` retains **distinct latest draft and last approved revision**, with exact frozen G06 Take SHA. `g09_environment_kits` persists reusable, hash-verified environment descriptions without arbitrary external asset paths. Source ActorID/geometry, performance USD and PCM never change.
2. `backend/nvp_g09_production_usd.py` authors a new, separate OpenUSD production layer based on a **copy** of the frozen performance USDA. It adds real USD scene geometry and UsdLux distant/fill lights, binds UsdShade PBR previews and portable MaterialX standard-surface inputs, records the original USD and Take provenance, and independently reopens the derived USD to verify all approved set pieces. Original USD bytes remain untouched.
3. `backend/nvp_g09_render.py` evaluates the immutable OpenUSD world at exact G07 frame times, lighting and weather, then paints a bounded CPU low-poly geometry pass with per-face GGX/Smith/Schlick metallic/roughness highlights, color/temperature, fog depth, 3D culling, distance LOD and director-added set pieces. **This does not claim physically accurate global illumination, shadows, true material textures, or production-quality Cycles images.** The approved look is shown in a disposable JPEG scene preview.
4. `backend/nvp_g07_edit.py` includes only **approved** G09 look snapshots by original Take ID plus an exact canonical `production_looks_sha256` digest, separate from the G07 edit digest. No editable/unapproved draft leaks into a final assembly.
5. `backend/nvp_g08_native_avi.py` validates the look set, authors and independently reopens the derived production USD per Take, then applies the approved look to actual picture frames. The real movie stream remains first-party MJPEG/PCM, with the existing unstyled G08 picture path available for Takes lacking approved looks.
6. `backend/nvp_g08_export.py` and `tools/nvp_g08_export_worker.py` bind **both** exact edit SHA and approved look SHA to the native supervised render request, durable job record and completion receipt. A changed look after the director starts an export causes refusal. `backend/nvp_g08_sealed_export.py` similarly stores the approved look SHA inside the protected export job and renders the immutable selected look snapshot in memory.
7. `backend/nvp_g09_routes.py` + `backend/nvp_api.py` expose only the existing director/locked-project-guarded look editing, approval, reusable-set and disposable-picture preview routes (ordinary and protected film), with no raw USD bytes, native executable paths or unauthorized worker commands.
8. `frontend/src/DirectorEnvironmentLook.jsx`, `director-environment-look.css` and `DirectorFilmEditor.jsx` present the choices inside the separate filmmaker editing room, not a developer application.

## Incomplete work

- **G09-A2 — Genuine native production rendering:** connect approved G09 derived OpenUSD/MaterialX to the existing protected real Blender/Cycles/Hydra render supervisors (not a new reimplemented image application). Real high-resolution EXR/shadow/reflection/material fidelity, renderer equivalence and Radeon hardware execution are still required. The present output is a lower-fidelity, 640×360 low-poly software rendering with improved lighting/material/set geometry and no photorealism claim.
- **G09-A3 — Larger scene libraries and real asset references:** the built-in presets are made from NVP-controlled basic meshes. Detailed licensed environments, arbitrarily imported mesh topology, asset repair, mesh/material interchange, texture custody and fully editable architecture asset collections remain future work. The conservative geometry/LOD/visibility budgets currently protect memory.
- **G09-B — Actors:** actual UsdSkel gait/facial performance, meaningful emotional voice, phoneme/viseme lip sync, hair/cloth and original ActorID performer continuity beyond basic translations/semantic cues.
- **G09-C — Native production A/V:** real capture device and time sync, continuous multichannel spatial sound, acoustic occlusion/HRTF and playback/recording recovery.
- **G09-D — Finishing:** verified OCIO/ACES look conversion, professional picture codec, cinema sound mastering, SMPTE DCP Bv2.1 independent checks and cinema playback only for actually qualifying assets.
- **G09-E — Sustained scale:** 30-minute film, then feature length, sustained memory/cgroup/job custody, true checkpoint-resume of expensive render, output/worker capacity and independent recovery evidence.
- **G09-F — Distribution:** installed Windows/Linux signed/unsigned policies, protected library/source preservation and deferred Lu integration. The creator has explicitly deferred G02 and routine CI/PR checks until full application implementation.

**Next engineering subgroup:** **G09-B — Actors and performance quality** can advance independently. G09-A still has open production renderer/asset fidelity and physical acceptance gates; record them rather than claiming they passed.

## Acceptance

No native compilation, independent Blender/Cycles, source USD pixel comparisons, installed NSIS, owner Radeon R9700, playback or film quality acceptance has been run. Code changes are real repository writes, but runtime claims remain unverified until the later consolidated pass.
