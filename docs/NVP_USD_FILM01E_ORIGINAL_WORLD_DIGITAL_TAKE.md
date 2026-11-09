# USD-FILM-01E — original persistent world → immutable cinematic Digital Takes

**Status:** Implementation committed in stacked draft branch `nvp/usd-film01e-world-digital-take-20261108`; **current-head native Windows/Linux execution and independent JSON artifacts OPEN**. Builds on USD-FILM-01D's camera-selected working sets and original USD-FILM-01A–01C FilmIndex-backed source layers. All earlier technical and installed-app acceptance gates remain separately open.

## The actual film capability

A film Take is **not** just the world mesh. A replayable original performance needs the correct camera, time, performing actor identity, actor movement/rig state, original sound, and source-selected dialogue. 01E uses existing authoritative NVP systems:

- `FilmIndex` owns projects, original immutable source revisions, source SHA and dependencies.
- `OpenUSDWorldComposer` provides a source-locked multi-set spatial USD stage.
- `FilmWorldShotPlanner` holds an exact original native `UsdGeom.Camera`, selected source scene and authored camera sample ticks. All director-required sets stay selected.
- `OpenUSDTakeCapture` owns each **existing verified scene+TemporalLedger Digital Take**. It is NOT replaced or given a new incompatible interpretation.
- `ProductionBibleActors` maps the source Take's actor prim paths to canonical StoryBible ActorIDs. It refuses uncast or ambiguous performing actors; USD prim labels do not become identity.
- `ProductionBibleVoiceIdentity` preserves independent versioned VoiceIDs; a current VoiceID is NOT automatically a recorded delivery.
- `ActorDialogueManager.route` approves exactly an existing, director-selected actor/script/performance/recorded audio route; no scene model may guess speaker identity.
- `RecordedSoundSources` preserves original 48 kHz mono PCM16 and original TemporalLedger sound events; film time uses **7,056,000,000 ticks per second**, i.e., **147,000 ticks per 48 kHz PCM sample**. No time stretch, voice synthesis, soundtrack mastering or imaginary audio is added.

`backend/nvp_usd_film01e_world_take.py` adds the distinct, immutable FilmIndex **`take` format `nvp.usd_film01e.immutable_composed_world_take.v1`**. It references a pinned original world and a pinned 01D camera-shot record, plus exact **existing frozen scene Takes** for all actor-bearing director-required world sets and the camera's own set. An actor-free environment set may join a required shot without a fabricated acting Take. The **same original scene Take may not be duplicated as if two separately performing actors**, and the world Take cannot use a scene Take for the wrong set, project, revision or clock range.

The world Take contains source IDs, revisions and hashes—not user paths or a destructive baked scene. Publication validates every original scene Take with the existing `OpenUSDTakeCapture.verify_take`, independently checks each original sound event against its original 48 kHz PCM source, and **rehashes all registered audio chunks in bounded one-chunk reads** (max 512 chunks / 256 MiB per source for this stage). It stores original audio event identity, original PCM source SHA, sample count and tick/sample mapping. Separately selected dialogue lines are revalidated via `ActorDialogueManager.route`; no unrecorded line becomes audible just because its ActorID has a VoiceID.

The first-world-Take freeze samples at the exact 01D camera shot ticks. For each checkpoint it:
1. Opens the actual source-locked film world, loads all director-required original sets, and applies only source-authored look variants in an in-memory USD session layer;
2. Reads the real original native composed camera transform from USD and checks it against the saved director shot's exact camera samples;
3. Reopens the original source Take's scene+temporal performance at that tick, samples original authored actor transforms, performance channels, native camera/light schemas and skeletal data as present;
4. Checks that each canonical StoryBible ActorID still addresses the expected native composed prim and that its original scene transform agrees with the composed world;
5. Seals the aggregate checkpoint digest in the new immutable world Take.

**No picture pixels are rendered and no audio is mixed.** The new format is a source contract for subsequent original renderer ingestion under 01F, **not yet compatible with consumers that expect the old `nvp.digital_take.openusd_temporal.v1` scene-only format**. A new 01F adapter must explicitly teach the actual renderer/film-review/scene-audio workers to consume this world Take; silently passing the new format to old `FrozenSceneAV` is not an implemented feature.

## Non-destructive editing, multiple versions and original voice continuity

The director's creative freeze event is authenticated against one exact world/shot/source Take/ActorID/checkpoint digest. This is a creative operation only, **not a legal/performer consent system**.

FilmIndex's own single-commit `take` identity rules prevent rewriting an old world Take. A later camera change, new actor performance, look revision, new selected dialogue, or new world arrangement produces new source revisions and a distinct Take ID. Original scene Takes and PCM remain unchanged.

An ActorID may be renamed and a VoiceID may later be recast for future performances. Reopening the old Take deliberately uses the **historical original cast/VoiceID evidence**, not the newest current voice or screenplay selection. Historical cast links and voice-cast versions are checked in their existing production-bible tables. Already selected recorded performances are reverified by original performance/script/selection/PCM hashes and historical voice-cast row, **without re-routing through a later, changed screenplay or current voice**. All original audio chunks are verified rather than relying on an attractive filename or the first sample.

FilmIndex's `register_revision` precommit guard additionally rechecks original source document SHA, exact ActorID-to-source-Take cast links and current VoiceID at the freeze boundary. Later creative source changes remain allowed but cannot race into an unreviewed freeze.

## Claude's second OpenUSD assessment — accepted film-only improvements

The user supplied a detailed two-part Claude proposal: **(A) a cached two-tier "compile" stage** and **(B) a bounded AI/OpenUSD tool layer**. Both contain valuable architectural patterns, but most examples target standalone VR headsets and games. We will apply the useful patterns to **filmmaking** without silently expanding NVP.

| Claude proposal | NVP decision | Where it belongs |
| --- | --- | --- |
| Cache an asset preparation result by original file SHA + target/profile version | **Adopt for film assets**, preserving pristine source and perceptual-quality settings; on any shader/geometry/provenance change invalidate affected derived cache | USD-FILM-02 / 08 |
| Native USD variant, payload, precise scene/time resolution before flattening | **Adopt only on disposable shot/render build**; source world remains rich and revisable | Existing USD-FILM-01A–01E, later 08 |
| `usdchecker` + typed schema/units/relative-asset validation | **Adopt after verifying actual installed native checker and renderer support**. Use original meters/Z-up and an asymmetric +X/+Y/+Z calibration asset before any necessary renderer coordinate conversion | USD-FILM-00 / 08 |
| Geometry/texture optimization, LOD choices and PBR material mapping | **Use only when demonstrably useful for renderer quality/performance**. Never blindly downsample hero skin/eyes, flatten required displacement, or bake away editable source for VR budgets | USD-FILM-02 / 05 / 08 |
| Per-camera visible triangles, shader/texture/worker-budget reporting | **Adopt measured per-shot budget reports and compare estimates to actual renderer pixels/performance**; headset FPS/draw-call targets do NOT apply to 24-fps cinema | USD-FILM-08 / 09 |
| Typed AI `place_asset`, `move_prim`, `set_variant`, `set_property`, `add_light`, `inspect_prim`, paginated reads | **Adopt a small native host-verified verb registry** using project asset IDs, original ActorIDs, dry runs, bounded argument/geometry checks, structured errors and 50-result bounded queries | USD-FILM-07 |
| AI writes to proposal-only stronger USD layer; review diff, undo, commit or discard | **Adopt** using NVP's existing authoring/admission infrastructure and correct USD stage session-layer precedence; no untrusted free-form Python or raw USDA mutation | USD-FILM-07, 01D's existing look layer |
| Relational positioning (beside, atop, centered, facing), placement bounds and collision | **Adopt physical placement checks only insofar as needed to author plausible film sets**, not game or grabbable-object physics | USD-FILM-02 / 07 |
| Golden stage replay, malformed argument fuzzing and 25–30 plain-English scene instructions scored across models | **Adopt model/worker benchmarks** with verified results, source SHA, latency and separate failure attribution | USD-FILM-07 / 09 |
| Mandatory MCP stdio server | **Not required**; native first-party tools already exist; optional MCP interop can be explored separately if requested | Not an 01E task |
| XR output profiles, headset-specific LOD/draw-call/FPS, player spawn, grab/collider logic, teleport behavior, game engine import | **Out of NVP filmmaking scope**. No VR engine, runtime collision rules, headset compilation or device-specific FPS contract added | Not authorized |

Claude's proposed JSONL edit logs and source/compiled separation map naturally to NVP's existing durable FilmIndex revision/dependency journal and typed host operations; we should **reuse the ledger instead of creating another global actor/asset catalog**. For model-facing tools, page results and provide units, source hashes and useful alternatives in structured errors. A model's tool-call/preview success is never a director-approved source edit.

## Native acceptance, actual evidence and remaining gates

**Source implementation and tests present:**
- `backend/nvp_usd_film01e_world_take.py` — true source-bound multi-set world Take, original camera and actor checkpoints, all original PCM chunk verification, historically pinned VoiceID, exact creative freeze scope, SHA-fenced FilmIndex commit, independent restart verification and sampled replay.
- `tests/test_nvp_usd_film01e_world_take.py` — first-party project/world/Takes with real native source USD, StoryBible ActorID, unaltered original room PCM, strict no-fabricated actor, cross-project and wrong time refusal, new-world revision preserving the old Take, later VoiceID recast, and **existing FILM03 four-actor Donut/Box/Sphere/ServiceCraft original selected dialogue + source VoiceID/PCM route** (the voice PCM in the fixture is synthetic TEST data, not natural-film voice).
- `tools/nvp_usd_film01e_benchmark.py` — creates the existing real authored 30-second, three-shot Donut/Box/Sphere original film sources in a disposable project, casts four object-actors into an original verified scene Take, creates one composed world shot Take, independently reopens it under a fresh Studio/FilmIndex and produces JSON for source hashes, original audio, actor count and checkpoint/reopen timing. It does NOT render the film.
- `.github/workflows/nvp-usd-film01e-original-world-take.yml` — Windows2025 and Ubuntu24.04 × Python3.11/3.13 (four genuine USD cells) + real original film-world Take benchmark on each OS (two cells). Source world parent CI gates USD-FILM-01A–01D are not waived by 01E.

**Pending native evidence:** Inspect exact-current-head Windows/Linux test logs and actual JSON artifacts. Repair all genuine code/API/scene/voice failures and rerun on final commit. No source-only PASS, no queued/canceled-result credit. Keep original voice sound realism, real actor facial/mouth sync, fully installed Windows/Linux source→render app, CPU/GPU resource measurements, native Blender/Cycles multi-shot pictures, and sound master/perceptual photorealism separately OPEN.

**Next:** USD-FILM-01F renderer ingestion of the new immutable world Take and **real multi-shot** visual and audible filmed world, plus prior FILM03-09E verified synchronized acting and UHD photorealism benchmarks under USD-FILM-05/08/09. Don't misrepresent a verified USD data checkpoint as finished filmmaking.
