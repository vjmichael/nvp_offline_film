# ADR-2026-11-03: Data-First Digital Filmmaking

**ID:** NVP-ADR-DATA-FIRST-001  
**Date:** 2026-11-03  
**Status:** ACCEPTED CREATOR PRODUCT DIRECTION [C]. Engineering contracts [B] and end-to-end implementation [D] remain subject to validation.  
**Authority:** Creator's November 3 design clarification; reconciled with [NVP MASTER DESIGN](NVP_MASTER_DESIGN.md).  
**Companion technical specification:** [Digital Film Packages and Selective Regeneration](NVP_DIGITAL_FILM_PACKAGES_AND_REGENERATION.md).

## Decision in one paragraph

**NVP must excel at constructing, capturing, indexing, editing, and transforming the structured information from which a film can be produced.** NVP is not fundamentally a video-prompt generator. The creator builds a persistent digital 3D film world, uses inexpensive visualizations to direct a performance and camera capture, freezes the relevant authored data into a Digital Take Package, produces one or more high-fidelity Presentation Packages from that take, then selects and masters those presentations as a final, flat 2D film with sound. Each layer is durably indexed with typed lineage and revisions, allowing targeted changes and regeneration without losing unaffected work.

**Governing phrase:** Define the world. Direct the performance. Capture the take. Produce the presentation. Edit and master the film.

## Four connected production layers

| Layer | What it is | Authority and editability |
| --- | --- | --- |
| **Digital Film World** | The living production source: narrative, screenplay, chronology, sets, spatial geometry, cast identity, asset revisions, props, physics/collision rules, costumes, style profiles, lights, microphones, performance intentions and shot plans. | Creator-directed and editable through reviewed, versioned changes. The original source of film facts and physical scene state. |
| **Digital Take Package** | A frozen, versioned capture of a specific scene/shot interval: exact world revision and asset references, camera transforms, timed poses and actions, dialogue/speaker references, lighting, prop states, microphone/audio timing, director approvals and source hashes. | **Immutable after approval.** A correction creates a branch or a new take, never silently modifies the original. It can reference shared, immutable data rather than copying an entire world. |
| **Presentation Package** | Rendered interpretation of an approved take: image/video frames, sound/voice stems, style and model choices, conditioning passes, render configuration, quality checks, output digests and provenance. | Derived and replaceable. The same take can yield photorealistic, anime, stylized 3D, or conventionally rendered presentations; no generator silently changes world authority. |
| **Editorial Sequence / Final 2D Film** | The selected presentation versions placed on a shot timeline with cuts, transitions, grading and audio mixing, followed by encoded audience-facing video. | Non-destructive edits refer to exact immutable presentation/audio versions. The final movie is a flat output, not the only editable source. |

The world defines **what exists and happens**; the take defines **what was performed and captured**; the presentation defines **what the audience sees/hears**; the edit/master defines **which finished views are shown, in what order and with what sound**.

**Important distinction:** The authoritative scene is not required to be stored as a single huge file or loaded at high fidelity in RAM/VRAM. It is a versioned production graph whose visual 3D preview can be cheap, while higher-resolution representations and source assets remain on disk.

## Indexing and ownership

All layers belong to **one persistent film project index**, with stable project-scoped IDs, immutable revision IDs, source-asset digests, approval receipts, typed dependency edges, and reversible or append-only change history.

Example: Scene 12 Revision 9 -> Take 04 -> Presentation A (noir) and Presentation B (anime) -> Edit 03 -> Master 02.

A world revision can produce multiple takes; an approved take can produce multiple presentations; a presentation can participate in multiple edits; an edit can produce multiple mastering formats. The editor must navigate in both directions: from source to finished media, and from a bad frame all the way back to the world state, selected take, production job, model and approved choices that produced it.

**Do not destroy prior approvals.** A current scene revision can be different from the one referenced by a previously approved take. That old take is valid for its original world revision; a new change may require a new take or presentation but does not overwrite its history.

## Low-spec filmmaking is deliberate, not an afterthought

**The interactive film set is a low-fidelity visualization of the authoritative world, not the final render.** Stage and direct with proxy/LOD meshes, limited lighting, cached draft audio, low-memory materials and on-demand active-scene loading. Capture timed 3D information, camera/microphone motion, performance, dialogue and approved world state—not merely screenshots of the lo-fi preview.

After a take is approved, NVP loads detailed assets only for the selected production scope and applies conventional rendering or optional selected generative video/voice workers. Hi-fi asset data and model weights may exist on disk without consuming foreground VRAM. Rendering and media generation can take longer than real time, be scheduled separately, and be retried after restart without blocking interactive editing.

**Qualification:** Simplifying preview geometry must not silently change the physical contact/identity/camera semantics of the saved take. Model minimum VRAM/RAM limits remain real. Low-spec preview is the product goal; rendering times and minimum specs require measured acceptance.

## Model-agnostic production

**The filmmaker chooses video AI, voice AI, renderer, finishing engines and visual style.** No one provider owns NVP's project schema or production decisions.

NVP translates the Digital Take Package into **model-specific digital instructions and conditioning assets**: approved prompt/script, actor identity references, style, timed poses, camera path, depth/normal passes, segmentation, masks, keyframes, audio, speaker IDs, emotional direction and dialogue alignment. Each adapter must declare which controls it actually supports. A generic AI model does not magically understand arbitrary scene JSON or guarantee a consistent interpretation.

Lu, when installed and approved as NVP's Film Workspace host, may manage selected worker lifecycles and budgets: admit -> load chosen model -> perform scoped production job -> save/check output -> unload or hold a justified warm cache. Media models may use runtimes other than llama.cpp. Lu is optional for development and standalone execution, and no CUDA-only or cloud-only model may become a universal film authoring requirement. Cloud usage requires opt-in and explicit data/rights handling.

**Generative nondeterminism:** store exact model/adaptor versions, weights digest where available, settings, prompts, seeds, inputs and output SHA; do not promise identical pixels unless independent replay confirms it. Provenance and editable source truth are mandatory; bit-exact regeneration for every model is not.

## The editor becomes a source-aware re-production tool

The editor presents finished video, but can locate the exact scene, actors, camera, performance, audio and AI job that made it. It supports compare, branch, review, re-render, recapture, approve, revert and replace.

| Director's request | What changes | What should stay intact |
| --- | --- | --- |
| Actor's face/clothes drift in one shot | Re-run affected visual shot with stronger approved identity/style controls | Captured actor motion, camera, dialogue and unrelated shots |
| One line sounds wrong | Regenerate that dialogue performance; update dependent sync/lip passes and composites | World geometry and unrelated audio/video |
| Move or replace camera | Branch camera track/capture revision and regenerate dependent camera/visual passes | Actor performance and approved source dialogue |
| Change actor gesture | Revise timed performance and create new capture for affected interval | Prior take and unaffected scene data |
| Present same take in anime | Add independent presentation revision with new style/backend | Source take and existing photorealistic presentation |
| Wrong prop placement | Revise world/action and its actual dependent captures/presentations | Unrelated scenes and source identities |
| Replace one poor generated clip | Regenerate only the smallest valid shot/temporal window, then check boundaries | All unaffected source takes, media and edit choices |

NVP computes dependency-bounded regeneration. **Do not require re-running an entire scene or movie if only one shot is affected**, but don't claim single-frame surgery when a generator requires overlapping temporal windows or audio synchronization. Show the true impact and cost before jobs run.

An AI editorial assistant may propose visual/voice fixes, mark potential identity drift, disappearing props or continuity mismatches, and compare generated output against captured data. Measured violations and artistic opinions must be distinguished; the director decides whether to accept subjective suggestions. A new generated prop or appearance must not silently rewrite the authoritative world.

## Project-level portability and preservation

The Digital Film World and index are not necessarily one enormous archive. The live project should store metadata and dependency links in a transactionally safe index, heavy source/media blobs in verified immutable storage, and compact previews/caches separately. Portable packaging should collect the manifest and required licensed source versions, not blindly duplicate whole films or redistribute restricted weights/assets. Missing external dependencies are reported on reopen, not guessed.

Every capture, render job, edit and master has traceable input IDs, source hashes, creator approvals, versions and failure status. Cancellation, interruption or stale input must leave previously approved work available. No model worker can mark an output approved merely by writing bytes.

## Clear limits and non-goals

This ADR is **a product/architecture decision, not a claim of an implemented complete pipeline**. NVP has independently verified scoped Blender stage, camera, rig and mesh-contact components, but has not yet delivered the complete linked world -> immutable take -> multi-presentation -> selective-editor -> 2D-master acceptance.

This decision does **not** imply that an arbitrary generative video model can consume structured JSON, always preserve the actor's identity, reconstruct all angles, exactly repeat a shot, or replace independently approved source geometry. Character feet/gait detail and photorealism remain separate quality targets and should **not block the first complete proxy-capture-to-movie vertical slice**.

## Priority engineering gates

1. **NVP-DATA-01:** Typed film-world records, stable indices, versioned source blobs, typed dependency edges, provenance and project isolation.
2. **NVP-CAPTURE-01:** Low-fi 3D rehearsal -> frozen, independently reopenable and auditable real Digital Take Package, with exact camera/performance/time references.
3. **NVP-PIPE-01:** One take -> conventional deterministic hi-fi presentation and a second differently styled/rendered interpretation, with provider capability checks; optional Lu scheduled media workers.
4. **NVP-EDIT-01:** Source-aware editor can trace a defective shot, apply a scoped revision and regenerate only its actual dependencies, preserving unaffected source and output hashes.
5. **NVP-MASTER-01:** Editor chooses presentations, mixes sound and produces a decodable flat 2D film; restart/reopen proves links back to source.

**End-to-end acceptance scenario:** Build a room with two proxy actors; stage a dialogue exchange; capture at least two shots; independently reopen frozen world/take data; produce two presentation variants; intentionally alter one shot's wardrobe/voice/camera; verify unaffected take and other-shot hashes are unchanged; assemble and decode a playable movie; restart and follow its lineage to the original take and world. Record all platform, model, rights, timing and resource limitations.

## Change governance

This decision is accepted [C], with the referenced engineering obligations baseline [B] and actual integration deferred [D] until tested. It supersedes any implied requirement to keep hi-fi meshes and media models loaded throughout rehearsal. Update the NVP Master Design and relevant workspace docs together when implementation changes authority or packaging semantics.
