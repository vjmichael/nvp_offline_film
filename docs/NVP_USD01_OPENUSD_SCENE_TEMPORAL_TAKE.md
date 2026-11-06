# NVP USD-01 — OpenUSD scene composition and authored-time evaluation → frozen Digital Take

**Creator decision:** OpenUSD is the initial native scene composition/time-sampling substrate for NVP's data-first film world. The authoritative index and semantic event timeline remain FilmIndex + Temporal Ledger. Output pictures are not the source of film truth.

**Implementation state:** Initial scoped adapter and real native integration tests committed. Windows/Linux matrix, installed desktop delivery, artist acceptance and production-quality asset composition are OPEN until verified. No claim of film mastering or AI video generation.

## Responsibilities

- `backend/nvp_openusd_scene.py`: first native OpenUSD `pxr.Usd` + `UsdGeom` + `Sdf` bridge. A trusted host sends strictly typed `/World/...` prims with semantic roles and bounded translation curves. NVP creates an immutable layout USD layer and a stronger motion USD layer. They are composed as `motion → layout` with native `Sdf.Layer.subLayerPaths` and `Usd.Stage.Open`. Authored motion is evaluated using `Usd.TimeCode` and `UsdGeom.Xformable.ComputeLocalToWorldTransform`. No image frame is rendered.
- Layers are stored using `FilmIndex.put_blob`, scoped to the exact project, with SHA-256 content identities; a single immutable `scene` FilmIndex revision records both layer digests, layer strength, roles and animated paths. Opening after restart reimports the real USD bytes, reconstructs composition, checks source blob integrity and observed semantic role.
- **No external OpenUSD layer references, payloads, arbitrary paths, shaders, models or plugin-invented codecs are accepted in USD-01.** The initial bridge deliberately authors only NVP-typed objects and animation. We will later add an authorized asset resolver, payload working-set controls, arbitrary scene properties, rig/character animation, materials, cameras, lights, variants and constrained file import with native worker containment.
- `backend/nvp_openusd_take.py`: connects exact `scene` and `temporal` FilmIndex revisions. It verifies the authoritative timeline's ordered event digest and rejects semantic event paths not present in the composed scene. A trusted host-supplied creator-action callback must approve the **exact scene/timeline/checkpoint scope** before a Digital Take is published.
- `FilmIndex.register_revision(...kind="take")` freezes the source scene and temporal revision references, exact document SHA values, source USD layer SHA values, the authored duration, and bounded checkpoint-state SHA within a **single-commit** Digital Take ID. The existing FilmIndex take one-commit restriction means subsequent changes require a new Take ID. A new scene revision cannot mutate earlier takes.
- `verify_take` reopens source layers and event ledger and independently recomputes checkpoint-state evidence from exact authored time ticks; it returns `VERIFIED_FROZEN_DATA_TAKE`, **not** a rendered image, creator-approved final picture or finished film.
- Sample times are exact NVP integer ticks. USD's time ordinates are `double`; NVP rejects ticks above `2^53-1` and authors `timeCodesPerSecond=7,056,000,000`, making tick-to-UsdTimeCode conversion integer-exact over ordinary features (roughly 14.8 days). It does **not** mean a project has committed to a specific video FPS. The renderer still chooses its own output cadence and optical/temporal policy.

## Example

A scene has two USD layers: a layout defining `/World/Actor`, `/World/Camera` and `/World/Prop`, and a stronger motion layer moving the actor from x=0 at tick 0 to x=10 at tick 14,112,000,000. OpenUSD calculates the actor's authored intermediate transform at tick 7,056,000,000 as x≈5, without any requirement to render frame 24 or frame 60. A timeline event saying that the actor walks references the exact performance revision and `usd_prim_path`. The frozen take captures both source revisions and digest evidence. Two separate presentation plans may sample the same performance at 24 or 60 frames per second.

## Testing and acceptance

`.github/workflows/nvp-usd01-native.yml` installs pinned `usd-core==26.11` native Python wheels and verifies actual scene composition on Ubuntu 24.04 and Windows 2025, Python 3.11/3.13. `tests/test_nvp_openusd_take_native.py` covers true sublayer composition, interpolated transforms, timecode fidelity, blob-backed scene reopen, creator freeze permission, immutable FilmIndex take dependencies, new-scene-revision isolation, bad prim target refusal, cross-project isolation, and two-output-rate planning.

Native package `usd-core` is the OpenUSD **core**, not its full imaging, rendering or plugins. Native tests cannot be replaced by a mocked `pxr`. A CI compile-only or queued run does not establish native acceptance.

## Remaining engineering gates

1. **OpenUSD-native verification** against real exact-head Windows/Linux runs, dependency version pinning, installer packaging/runtime and native linked-library/license review. The current PyPI metadata uses a `LicenseRef`; inspect upstream OpenUSD distribution license and wheel contents, do not infer the complete installer license from the package label.
2. **Authorized source asset loading:** deterministic asset resolver and referenced/payload layers with verified project scope, rights metadata and reloadable offline assets, plus full geom/camera/lighting/material/rig composition. No blind recursive external-reference loading.
3. **Performance state evaluator:** joint and facial curves, quaternion/motion interpolation, prop constraints, acoustic events, camera projection, collision/contact and temporal resets; semantically meaningful events may require a dedicated state machine beyond USD transforms.
4. **Frozen Take coverage:** all upstream source assets/rights, approval evidence, exact host authorization/worker fencing, frozen stage layer dependencies, durable managed crash recovery and end-to-end authoring integration. The first take is an immutable *metadata and sampled-world-state capture*, not a complete commercial acting capture.
5. **Multiple visual presentations:** build actual conventional low-fi and alternative hi-fi/stylized rendering adapters against one take. Test unchanged source hashes while presentation-specific outputs vary; no assumption that generative models preserve identity perfectly.
6. **NVP desktop/UI:** human editor staging, scene tree, time scrubber, performance curves and creator checkpoint approval. The AI Assistance Layer remains deferred.

**Architecture rule:** Preserve the performance as data; request a presentation at an exact time; render only at the selected backend's boundary.
