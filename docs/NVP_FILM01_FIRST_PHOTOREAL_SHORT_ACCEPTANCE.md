# NVP-FILM-01 — First complete photorealistic 30–60-second short-film acceptance

**Type:** Future end-to-end film-production acceptance gate (NOT yet passed).
**Dependency:** Complete and verify the B13/B14 edit reimport and conform foundations, native creator-approved render/export, source-linear color-managed edited video, synchronized audio, and independently audited playable master.
**Scope:** NVP only. Lu–DLC interface remains deferred until after Lu v1.0.

## Outcome

Produce an original narrative or visual short film of **30–60 seconds** from NVP's world/scene/performance/camera/lighting/material data and frozen Digital Takes. Deliver a coherent, **photorealistic-looking** presentation (not merely high bit depth), with **actual persistent, non-destructive picture edits**, **sample-accurate synchronized sound**, and **a playable, technically auditable high-quality master**. The human reviewer, not an automated file-format check, determines whether the images look genuinely convincing.

This milestone does not demand full feature-film scale, advanced VFX, DCP, or complete Lu integration. It does demand one real start-to-finish film rather than a stitched test-only synthetic video or renamed low-quality proxies.

## Mandatory film content

- 24 fps, 30–60 seconds: **720–1,440 actual final output frames**. Existing B12/B13/B14 small-fixture limits (120 original and 480 edited frames) MUST be extended through a separately engineered bounded, streaming production path; never silently bypass resource protections.
- At least three visually distinct shots and two visible, motivated editorial cuts; persistent editable cut list and two non-destructive revisions. Exact source ranges/camera identity preserved.
- Physically plausible materials, lighting and shadows, stable scene geometry, temporal continuity and camera motion; any humans/creatures/props must remain consistent across cuts. Visual evidence must come from generated render content, not reference stills substituted into a video container.
- At least one time-critical visible action with an associated synchronized sound effect, with optional dialogue or musical score licensed/original as appropriate. Silence alone does not count.
- A creator-review playback format and a professional high-quality **video+audio** master (e.g. proper ProRes 422 HQ MOV with PCM audio, appropriately tagged; additional mezzanine or H.264 preview optional). Frame rate, dimensions, bit depth/chroma, sound sample rate/channels and correct color transfer/primaries recorded and independently checked.

## Foundational processing rule: data-addressed, batched or streamed

**The full Digital Take and production package are persistent indexed data, not a requirement to load the whole film into RAM, VRAM, or one worker.** NVP shall materialize only the active working set needed for a step, using streaming or independently scheduled chunks as appropriate. Length limits in B12/B13/B14 are *temporary fixture/worker-policy bounds*, not architectural maximum film lengths.

- **Data-first:** FilmIndex owns source identities, temporal ranges, revision dependencies, media hashes and output receipts. Producers read exact needed ranges rather than deserializing the entire package into process memory.
- **Adaptive batches:** choose batch size based on measured free resources, frame resolution, renderer/codec needs and worker admission; 24/48/96 frames are examples, not fixed limits. Work can be processed out of order when independent, then conformed in timeline order.
- **Streaming:** use backpressure-aware bounded queues for successive render/color/encode/audio stages; write completed products to durable storage as needed. Streaming should not force redundant full-disk copies, but a partially emitted master is never called complete.
- **Durability:** each completed chunk records project/take/edit revision, source interval, presentation interval, pipeline version/color transform, output hash, committed receipt and dependency inputs. Atomically publish committed batches; restart skips only those that reverify.
- **Continuity:** effects that depend on adjacent frames (motion blur, denoise, interpolation, particle/simulation history, crossfades) request overlap/halo windows or persist validated state between batches. Never stitch independent chunks with incorrect temporal boundaries.
- **Audio:** keep a rational timeline and 48 kHz sample positions, aligning audio chunks to exact edit frame/sample boundaries, not accumulated floating-point timestamps. Preserve lookahead/crossfade state where required.
- **Revision invalidation:** changes to one shot or audio segment invalidate only dependent chunks and downstream conform/master outputs. Immutable original takes and unrelated rendered assets are reused.
- **Resource safety:** bound RAM/VRAM, disk occupancy, open files and parallel workers. Apply backpressure, cancellation, checkpoint/recovery and disk-budget checks. The final deliverable can be much longer than the active in-memory window.
- **Verification:** independently check all chunk manifests, ordering, overlap policies, continuity edges, decoded full master and entire duration. No arbitrary cap on film duration is inferred from a per-worker chunk limit.

This rule is a design requirement for scaling NVP, not a claim that every stage already implements streaming or crash-safe chunk scheduling.

## Hardware-adaptive workload scheduling: home PC to data center

**Design requirement:** one NVP production graph, from local single-machine execution to distributed multi-node rendering. Neither film length nor the number of shots determines how much of the film must reside in memory. Scale *workers and chunk sizes* to observed resources; preserve source assets, deterministic edit order, FilmIndex identity and deliverable semantics.

### Resource discovery and host protection

At admission and periodically during processing, measure usable CPU cores/load, physical RAM available after OS/user reserve, GPU backend(s) and usable VRAM, available scratch disk/capacity/throughput, worker liveness, and thermal/power constraints where exposed. For distributed operation additionally measure link throughput/latency and per-node asset locality. Never equate installed RAM/VRAM with fully available memory. Reserve headroom for the operating system and the user; on desktop, responsiveness outranks render throughput. If GPU constraints prohibit safe execution, choose CPU fallback or refuse with a clear recoverable reason, never exhaust the machine.

### Work unit and controller

The authoritative work unit is a hash-addressed `(production revision, shot/asset dependency set, operation, frame/sample range, transform version, quality policy)` with immutable inputs, expected outputs, resource estimates and durable journal state. The scheduler uses measured peak RAM/VRAM and throughput to refine forecasts per operation and device. It admits only work that fits all relevant limits, with bounded queues and I/O backpressure; dynamically chooses chunk duration and worker concurrency. An operation may use a full shot, one frame, tile, subframe or audio window as its minimal unit.

Support local CPU-only, one-GPU, multiple-GPU and remote workers using the same operation contracts. Data-center executors must fetch exact versioned inputs, attest hashes and return verified output manifests; the authoritative FilmIndex/controller commits accepted outputs. Node failures or stale worker results cannot claim completion. Network and shared-storage overhead may make local execution preferable for small jobs.

### Correctness across boundaries

Chunk partitioning must not alter the creative result: account for simulation history, temporal sampling, denoise/optical-flow halo frames, audio lookahead, color pipelines, codec GOP/state and edit cut boundaries. Record overlap/state, enforce exact time/sample mapping and reunite outputs in deterministic timeline order. If an operation cannot safely chunk, admit its minimal indivisible state requirement or report that the current device cannot run that particular operation; do not promise universal feasibility or identical floating-point bits across heterogeneous devices.

### Checkpoints, retry and graceful degradation

Atomically checkpoint validated results and provenance after each committed unit. A restart verifies inputs/receipts before reuse, reschedules only missing or invalid units, and releases resource reservations only after worker exit/cleanup is proven. Respond to resource pressure by reducing parallelism/chunk size, pausing with a durable checkpoint or using an explicitly supported alternative backend. Never silently change final resolution, color management, frame rate, simulation accuracy or requested render quality to fit a weaker PC; any draft-quality mode is explicit and separately labeled.

### Resource monitor + resource guard implementation status

NVP already includes `nvp_resource_guard.py` (OS RAM telemetry, GPU budgets, emergency pressure rules), `nvp_resource_ledger.py` (SQLite-serialized task admission, durable reservations, queue and activity snapshots), and `nvp_worker_containment.py` (OS-owned worker containment). B14 adds `nvp_resource_supervisor.py` to continuously sample existing ledger pressure for an ACTIVE contained worker. It requires two consecutive critical observations before invoking the contained worker's own terminate-tree operation; isolated spikes reset. It also stops timed-out workers. The host, not the monitor, must independently establish OS cleanup before releasing durable reservations.

B13's native OTIO import has been wired into this watchdog; other long-running producer hosts and B14's future authorized conform host must adopt it separately. CI unit tests cover success, intermittent/continuous pressure, timeout and invalid worker interface. This is **not** a guarantee that external applications are protected against every GPU-driver fault or that every NVP worker already has active monitoring. CI and real pressure-fault acceptance remain necessary.

### Test matrix and actual acceptance

Test on (1) constrained CPU-only home hardware, (2) consumer single-GPU PC, (3) high-memory multi-GPU workstation and (4) distributed workers with deliberately injected worker/network failures. Compare final frame/time/source lineage, audio sync, output decode and quality-policy adherence across environments. Measure maximum memory, VRAM, storage, throughput, host responsiveness, restart recovery and scaling efficiency. Passing one CI runner does not prove the full hardware range. Data-center support is a future execution mode, not an already implemented capability.

## Source-of-truth production workflow

1. Author and freeze world, shots, performances and production instructions into indexed Digital Take(s).
2. Render real scene-linear high-bit-depth image frames from the authored world. Record source frame SHA, timing and camera shot.
3. Make color-managed editorial review pictures, retaining immutable source and look policy.
4. Edit the actual shots through supported OpenTimelineIO cut revisions. Import and persist at least two versions; old versions remain reopenable.
5. Conform **the approved edit version only** into the actual final sequence, preserving full frame lineage. The technical master path works from scene-linear original source and explicit color transform; do not relabel sRGB PNG codes as Rec.709 mastering.
6. Compose/synchronize audio to editorial frame/sample timeline. Specify the frame↔sample mapping rationally (24 fps and 48 kHz => 2,000 samples per frame), avoid cumulative clock drift, and enforce clip boundaries and trim behavior.
7. Render professional picture+audio deliverable under native creator consent and OS-contained, resource-admitted workers. Persist FilmIndex master record with exact take/edit/audio/grade dependencies and media hashes.
8. Reopen after NVP restart and independently decode/verify the *actual* output master: expected frame count, duration, audio presence and duration, A/V sync event timings, color tags, picture/frame lineage, full content SHA, no missing assets, no leaked resource reservations.

## Two independent acceptance tracks

**Technical (automated, required):**
- Real on-disk source/render/edit/sound/conform/delivery; not mocked image or soundtrack tests.
- Full 720–1,440 frames at actual chosen resolution and source bit depth, with CI/local resource budgets stated; bounded work chunks and no full-film RAM residency.
- No source rewrite across edits; SHA-based FilmIndex provenance; restart persistence and approved revision exactly matches delivered master.
- Video decode checks, stream probing, A/V timebase and sample-frame sync checks, deliberate failure/recovery/cancellation/retry paths, worker containment and disk/RAM accounting.
- Honest codec/color/audio claims verified by probe and decode; master is truly playable.

**Creative/visual (human review, required):**
- Photoreal quality plausible to a viewer: coherent lighting, shading, texture, temporal stability and motion, with no distracting render artifacts.
- Editing enhances the miniature film rather than merely demonstrating cuts.
- Audio causally matches onscreen events and levels are listenable; no conspicuous synchronization drift.
- Story or action conveys a clear intended beat within 30–60 seconds.
- Human creator approves the actual viewed output. Automated metrics assist but cannot certify photorealism.

## Gate policy

- A 120-frame fixture or picture-only conform proves **component functionality**, NOT FILM-01.
- Real 30–60 s photoreal cinematic quality is an **aspirational, measurable acceptance target**, not an already-proven capability.
- Do not mark FILM-01 PASSED without independent technical evidence and explicit human creator viewing/approval. Keep technical pass and visual approval separate.
- No fake audio, no 8-bit proxies called scene-linear 32-bit assets, no silent omission of unsupported film operations, no unverified exported master.
- Production costs/latency and hardware limits must be reported with actual measured runs, not estimates presented as results.

## Implementation sequence after B14

1. Finish native-approved B14 conform and exact-source real edited output acceptance.
2. B14 professional edited picture mastering from source-linear frames, with independently verified video decode.
3. Film-audio authoring/edit-conform, 48 kHz sample-accurate sync, audio lineage and inspection.
4. High-quality picture+audio mux/master with immutable FilmIndex delivery and restart audit.
5. Extend short test frame/raster budgets to bounded streaming **720–1,440-frame** workload; photoreal visual-production pipeline and creator review.
6. Execute FILM-01 and record technical proofs plus separate human creative verdict.

**Status:** Specification only; not an implementation or acceptance claim.
