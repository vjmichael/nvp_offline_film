# NVP-PROD-SCALE-01 — Studio-scale, piecewise film production architecture

**Date:** 2026-11-05  
**Authority:** Creator-directed production design requirement.  
**Status:** Adopted architecture requirement; implementation and studio-scale acceptance remain open.  
**Priority:** Core standalone film production before any further AI Assistance Layer work.

## Decision

NVP uses ONE film-production architecture for a one-minute short, a three-hour feature and even larger productions. A 3-hour film is a **minimum long-form test**, not a hard maximum. Expect multi-gigabyte, multi-terabyte and potentially distributed source libraries, extensive unused takes and alternate edits.

An individual film need not fit in main memory, video memory, a single database JSON document, a single process, a single intermediate disk volume, or even one machine. The authoritative source is a versioned **production graph**, not a flattened movie. All operations target independently verifiable portions of that graph.

At 24 fps, 1 minute = 1,440 frames and 3 hours = 259,200 frames. Audio at 48 kHz for three hours is 518,400,000 samples **per channel**. Time and sample identities require checked signed 64-bit coordinates and rational timebases. Do not assume every imported source runs at 24 fps.

## Authoritative production objects

- **Project:** ownership, storage policy, production context and final editorial lineage.
- **Sequence:** logical chapter/reel/segment and its editable source references.
- **Scene:** narrative and physical-world planning identity; not necessarily one file.
- **Shot:** selected camera/view and its own production/lighting/performance references.
- **Take:** frozen creator-approved simulation/performance/camera state with original identity; revisions never rewrite an original.
- **Source asset:** file-backed or chunk-backed media, geometry, textures, sound, motion, reference or other source; includes real location/volume, sizes, hashes, codec/timebase/metadata and availability.
- **Editorial version:** compact ordered clip references and rational input/output intervals, with explicit transitions, retimes and compositing dependencies.
- **Work unit:** immutable exact input revisions, required temporal/spatial region, versioned transform/worker, expected outputs, resource estimates, dependencies and durable lifecycle identity.
- **Artifact:** verified output chunks, frames, proxy, soundtrack, preview, versioned master or distribution copy with full provenance.

FilmIndex is the foundation for durable source and output revision identity; native TaskLedger and existing worker supervisors remain authoritative for execution. Do not introduce a competing film authority or second scheduler. Any new tables must extend the current SQLite-backed index with indexed queries and paged access rather than replace its existing objects.

## Non-negotiable constraints

1. **Bounded working sets:** RAM/VRAM consumption follows the active task budget, not total film or library size. Frames, clips and assets are paged or streamed. Avoid full-film per-frame lists or monolithic JSON.
2. **Piecewise operations:** ingest, procedural generation, production, acting, retargeting, simulation, rendering, denoising, grading, edit, sound, conform, QC and archive are independently schedulable by relevant ranges/tiles/shot/asset. Chunk size is measured and adaptable, not a global frame cap.
3. **Continuity:** model simulation state, shutter/motion blur, physics, denoise, cuts, retime, crossfades, color and audio lookahead as explicit halo windows/state dependencies. Merely splitting frames is insufficient for film continuity.
4. **Versioned partial invalidation:** edit or regenerate one shot, asset or scene without overwriting unrelated source data. Invalidation follows proven dependency edges and intervals, not a global rebuild by default.
5. **Durable publication:** checkpointed outputs bind exact source revisions and hashes; an independent verifier checks actual bytes before promoting a work unit. Crash uncertainty requires OS-stop and journal reconciliation, never optimistic retry.
6. **Storage lifecycle:** originals are immutable; caches/proxies are explicitly expendable only after checking provenance and recreation eligibility. Real media may reside on internal volumes, external drives, NAS and eventually content-addressed remote storage. Missing/offline media is not silently replaced by invented success.
7. **Distributed execution:** the same typed work spec runs locally or, in future, on authenticated remote workers. Remote nodes fetch hash-pinned inputs and return independently checked products; network and worker identity do not grant publication authority.
8. **Scale-aware UI:** opening/editing one sequence must not traverse or materialize entire archives. Use indexes, paginated queries, thumbnails, waveforms, proxies and selective previews. A one-person filmmaker should not see distributed infrastructure complexity unless useful.
9. **Truthful output:** final master and DCP have independent whole-duration decode/QC, exact rational time/audio mapping, missing-frame/gap detection and verification. No segment is accepted as a finished film merely because a codec process exited zero.
10. **Preserve creator authority:** approval of a film/sequence/take/master is a scoped human decision. Independent native production must work without Lu or any AI model.

## Existing source audit (2026-11-05)

- `backend/nvp_film_index.py` stores project-scoped revisioned objects, dependency edges and hashed disk blobs but currently restricts JSON documents to 1 MiB, individual blobs to 32 MiB and individual revision dependencies to 128. These are valid bounded-object protections, NOT suitable whole-source-media limits. Add separate indexed large-media records and paged reference manifests rather than lifting them arbitrarily.
- `backend/nvp_resource_ledger.py` already provides durable resource admission, native reservations and phase events. Extend scheduling contracts instead of building a second worker queue.
- `backend/nvp_frame_batches.py` now has `iter_batches`, a lazy bounded frame-plan iterator. It does not yet implement compact source-catalog lookup, native worker integration or feature-length media mastering.
- Current B12/B13/B14 120/480-frame caps are narrow implementation/fixture limits and must not become schema limits.
- The first 30–60-second film remains the near-term creative proof using the same future long-form architecture; it must not force a new short-only processing path.

## Implementation order

1. **SCALE-01:** Define compact media asset and editorial interval tables, indexed by project/object/time range, with paged query and overflow-safe rational timebase validation. Add invariant and migration tests.
2. **SCALE-02:** Add real large-media source ingestion using incremental checksum, external-media custody/offline status, metadata probe and proxy relationships. Do not copy terabytes into 32 MiB FilmIndex blobs.
3. **SCALE-03:** Plan work from indexed clip/shot intervals via cursors (not whole-film frame-map expansion); pin exact revision and content digests, support resume by cursor.
4. **SCALE-04:** Native authorized processing of a bounded window through the existing TaskLedger and worker containment, with per-window receipts and verified partial reuse.
5. **SCALE-05:** Whole-film assembly, source-linear color, sound, editorial and delivery using bounded I/O, temporal halo/state, independent QC and partial invalidation.
6. **SCALE-06:** Scale/load/fault tests: minute-scale film; 3h 259,200-frame compact timeline with larger source library; terabyte-scale file indexing under measured memory; then authentic render/master stress on hardware appropriate to workload. Structural synthetic tests never count as real-media acceptance.

## Acceptance principles

- Prove indexed seek/query complexity and bounded memory regardless of source-library size.
- Prove editing one scene does not materialize unrelated footage.
- Prove exactly reproducible source custody, edit revision binding and chunk identities.
- Prove correct recovery after interruption and refusal of tampered/offline originals.
- Prove equal semantics between small and large projects; resource capacity may affect throughput but not correctness.
- Do not claim any 3-hour real film or multi-terabyte ingest/render is complete until tested with actual media.

**Policy:** Pause NVP-AI work until core production features and standalone filmmaking workflows are functionally complete. Installation/packaging is a release activity, not a substitute for the film engine.


## SCALE-UX-01 — Whole-project access, bounded active working set (creator direction, 2026-11-05)

**User-facing principle:** The filmmaker remains oriented in and can navigate the **entire** film production immediately, even when it spans terabytes. Opening a project is a metadata/index operation; it is **not** a request to load every scene, timeline frame, source movie, animation, sound file or rendered image. Only the current operation has an active resource-intensive working set.

### Separation of responsiveness and readiness

1. **Project navigation READY:** show project, sequences, scenes, shots, takes, media availability, editing versions, approvals, thumbnails and metadata from paged SQLite indexes. Do not require source media to be online to show its existing indexed record. Opening a project must not schedule a render or expand every frame reference.
2. **Preview READY / PREPARING / OFFLINE:** open a cached or low-cost proxy immediately when verified; otherwise show an honest preparing indicator and continue allowing navigation. Missing/disconnected original drives are displayed as OFFLINE, never silently substituted.
3. **Full-quality operation READY / WAITING FOR RESOURCES / PROCESSING / FAILED:** only when requested, reserve RAM, VRAM and disk scratch through NVP's existing TaskLedger and measured resource guard; native host authorizes any effectful worker. Navigation does not require the full-quality worker.
4. **Cache:** bounded, disposable previews, thumbnails, waveforms, metadata and hot source windows. Eviction must respect current task dependencies and never delete immutable originals, frozen takes, approvals or results without proven reproducibility. An LRU-like policy can be selected after measured benchmarks, not prescribed as the only algorithm.
5. **Transition:** moving from Scene 42 to Scene 7 does not implicitly cancel already-authorized rendering, free reservations before OS worker termination, or overwrite unsaved editorial decisions. It swaps the foreground view/working set while ongoing jobs remain independently supervised in the production progress center.
6. **Prefetch:** modest, cancellable, lower-priority likely-next assets (adjacent clips, next shot, cached waveform) may be admitted opportunistically only after responsiveness/headroom checks. No runaway predictive loading that causes RAM/VRAM contention or hidden storage amplification.
7. **Affordability:** set RAM/VRAM/disk budgets from measured available resources and conservative headroom; expose user-adjustable cache budget. A low-memory PC may take longer to build a proxy or render a shot but should not need enough RAM to hold the project. Never promise zero-latency access to offline or uncached multi-gigabyte media.
8. **Consistency:** index queries are snapshot/revision-bound. Show a known cached preview only with its source revision and SHA, avoid stale results after edits, and preserve exact selection/viewport state through restart.

### Concrete acceptance cases

- Load a metadata-only 3+ hour/20 TB-catalog fixture without reading any large source payload; record time-to-first-navigable-project and memory peak.
- Jump to the last scene without enumerating 259,200 individual 24-fps frames; prove indexed seek/paged query.
- Keep project navigation responsive while another OS-contained render is active and the scheduler withholds memory for expensive preview preparation.
- Detach an external source drive: project navigation and metadata continue, preview/full-quality access truthfully report OFFLINE.
- Reconnect original media, verify content before accepted reuse, and resume only the required piece.
- Revise one shot: invalidated previews/derived work are not presented as current; unaffected scene navigation continues.
- Test low-memory, modest single-GPU and studio workstation profiles with the same project model and no fabricated performance guarantees.

**Implementation status:** The current compact editorial interval catalog and TaskLedger are relevant foundations. This section establishes the UX contract; an integrated working-set cache, asset availability broker, scene navigation/proxy readiness service, and measured UI performance acceptance are **not yet implemented or proven**.
