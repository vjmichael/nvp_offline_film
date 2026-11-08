# USD-FILM-01C — true on-demand film-set source caching and scoped texture resolution

**Development:** Native project-owned source cache, lazy world-open integration, original PNG/MaterialX image resolution, source/restart tests and OS matrices **committed**. Actual exact-head Windows/Linux results **OPEN**. New draft PR stacked on USD-FILM-01 #129.

## Why 01C exists

USD-FILM-01A created genuine references, scene payloads, variants and PointInstancers, but still opened and flattened EVERY referenced source scene while constructing a world—even with `Usd.Stage.LoadNone`. That made the USD payloads unloaded but not the source preparation. 01C explicitly removes the expensive original-scene reconstruction from the **world-open** path, without weakening NVP's source identity or frozen Take guarantees.

## Architecture and source integrity

**Filmmaking sources stay authoritative:** FilmIndex / SQLite, existing `OpenUSDSceneBridge`, `OpenUSDAssetRegistry`, the actor/story source and original Takes. The new code extends `backend/nvp_usd_film01_world.py` and adds `backend/nvp_usd_film01c_texture.py`. It does NOT create a second asset database or a global OpenUSD asset resolver.

**01C world publication:** When a new world is authored, the original USD source scenes/assets are first reopened and verified through the existing FilmIndex interfaces. Any source scene is flattened as a **derived, non-authoritative snapshot** to close its original in-memory reference graph. NVP registers the actual resulting bytes as an immutable content-addressed layer blob **in the same project FilmIndex**. It binds the derived layer SHA, original source document SHA, original USD layout-layer SHA, exact source ID and revision in the world manifest. NVP's original scene, asset, texture and Take objects are not modified. Retakes or world variations create new FilmIndex revisions, not silent changes.

**01C world reopen (the important change):** The session reopens only sealed source identity/metadata for currently unloaded sets. It does **not** call `OpenUSDSceneBridge.open()`, flatten the original scene, decode its textures or stage its USD bytes while opening the world. It authorizes and materializes the small set of currently-needed non-payload asset references and selected/available look variants. The composed root opens with native `Usd.Stage.LoadNone`; no set source files are written until an explicit `WorldSession.load(["SetName"])`.

**01C set load:** For a newly published 01C world, the selected layer is retrieved from the same FilmIndex project by its SHA, independently rehashed, written into an ephemeral private SHA-named `scenes/*.usda` staging path, and loaded using the original OpenUSD payload arc. This avoids an original scene flatten on **every load**, not just during world open. No remote URLs, arbitrary filesystem paths, untrusted model-supplied aliases or network asset fetches. A set's child prims are independently checked after load: `UsdPrim.IsLoaded()` alone cannot prove geometry actually resolved. Unload removes its contribution from native USD composition; the private staged files are retained until session close so reloading remains inexpensive. **This is a bounded source cache, not yet adaptive GPU paging or a city-scale renderer.**

**Legacy migration:** Older 01A worlds did not register sealed derived layers. For them, the 01C lazy session still defers original scene reopening until the director loads a named set, and reconstructs the original legacy USD layer bytes for its exact old SHA. Older source hashes must not be rewritten to pretend they came from the new cache.

## Texture and MaterialX/PBR handling

Existing `nvp_native_usd_texture.verified_texture()` and original `OpenUSDAssetRegistry.open()` remain the source authority. NVP resolves only the approved `nvp-blob://texture/<sha256>` URIs that are already bound to original asset source descriptors. It validates original PNG essence and recorded image dimensions and colorspace, and refuses absolute paths, unknown original texture URIs, foreign-project texture blobs, unexpected/upstream file connections and unregistered or altered bytes.

A **derived, temporary USD stage** maps exactly those approved UsdUVTexture and MaterialX ND_image `file` inputs to relative `../textures/<sha>.png` source files under private staging. Original source shader graphs, MaterialX/PBR bindings and FilmIndex document hashes remain unchanged. Each temporary PNG is individually SHA-verified and files are read-only. Image bytes count toward the private stage working-set budget; identical SHA files are deduplicated.

The first implementation stages required non-payload asset sources and their verified images when opening the world, while **scene payload images are deferred until the named set is loaded**. This solves the originally identified eager scene-flatten bottleneck, but it is not yet optimal demand paging of every prop, texture mip, MaterialX cache or camera-visible tile. That is partly USD-FILM-01D/08.

## Honest runtime measurements

`WorldSession.receipt()` records: initial authored source count, original world SHA, **zero eagerly flattened scene sets on session open**, actually materialized named sets, exact FilmIndex sealed layer-cache hits, stage source-file/byte counts, initial native `Stage.LoadNone` time, per-set load/unload time, and current whole-process RSS. The 1,200-instance `tools/nvp_usd_film01_benchmark.py` now rejects eager original set staging and verifies two actual cache hits after loading two different original scenes. Process RSS is not USD-only allocated memory, VRAM was not measured, no renderer pixels were produced.

## Regression and CI

**Native tests:** `tests/test_nvp_usd_film01c_lazy_resolver.py` publishes genuine first-party scene/asset revisions, makes the real original scene opener raise during *world-open and load*, proves only the selected set materializes, reopens after SQLite restart and rejects source substitution. It also tests a real 16×16 original PNG and a separately verified grayscale MaterialX roughness map in original source USD, requiring their temporary relative SHA-addressed image paths in both a reusable prop and a loaded scene. It asserts original `nvp-blob://` source URI and source SHA survive. A hostile absolute texture path and staged symlink are rejected where the OS permits symlink creation.

**CI:** `.github/workflows/nvp-usd-film01c-native-lazy-resolver.yml`, genuine native `usd-core==26.11` and Pillow, Windows 2025/Ubuntu 24.04 with Python 3.11/3.13 (4 matrix jobs), plus 1,200-instance World working-set evidence on both operating systems (2 jobs). Existing USD-FILM-01 and original reusable-asset regression tests are included. JSON is retained when jobs execute.

**Gate status:** Code authored; **not accepted** until full final exact-head Windows/Linux jobs return PASS and the actual JSON, source hashes, correct set/payload behavior, original texture files, startup latency and RAM measurements have been inspected. An actual rendered original film, installed UI camera-based streaming, photoreal materials, shader-color parity, GPU VRAM figures and 09E dialogue/actor acceptance remain separate.

## Next engineering tasks

- **01C remaining:** inspect exact-head OS logs; repair actual native source/API/runtime failures; verify real source images on both OS; establish cache-hit vs cache-miss benchmark and avoid a silent broken payload resolver. Reconcile old world legacy reopening.
- **USD-FILM-01D:** camera/shot-aware loaded working set and actual editor responsiveness, bounded CPU/GPU resources and recovery under failure/cancellation.
- **USD-FILM-01E:** source-bound world-to-shot and Digital Take integration with original ActorID/VoiceID/film-time continuity.
- **USD-FILM-01F:** independent real Blender/Cycles rendered multi-shot original film set and visual/audible creator review.

NVP remains **pure filmmaking**; no digital-twin, historical-world database, game engine, unrelated scientific simulator or legal performer administration is introduced.
