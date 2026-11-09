# NVP USD-FILM — Data-first performance, virtual viewpoints, selective-quality film rendering
**Director architecture decision · November 8, 2026 · supersedes mandatory full-roll capture assumption**

## Principle

A Digital Take records an **authoritative, persistent, time-indexed scene performance**: canonical ActorIDs, animation and pose, geometry/rigs, physics/effects results or reproducible deterministic simulation, materials and lighting source, environment changes, audio/dialogue sources, and original Film Time. It does **not** record nine separate camera videos as the primary asset.

A director's "camera" is an **editable virtual viewpoint** into that one scene: projection/lens, transform/path, framing, exposure, view-dependent visibility and render settings. Any number of such views may be evaluated from the same captured state. One can introduce a tenth camera **after** the acting/performance is frozen, without repeating the actors or recreating the source Take.

The primary source deliverable is *scene data and performance*. The primary final deliverable is an *edited, sound-synchronized presentation* of chosen scene states.

## Normal production pipeline

1. **Record/performance freeze:** capture and verify one complete authoritative performance, including time-sampled source state sufficient to reconstruct its motion/physics/secondary effects. Non-deterministic simulations must be baked or stored with verifiable seeds/cache/versioning; merely having initial conditions is not equivalent to a captured performance. Original world and events remain source-immutable.
2. **Explore:** allow the director to pause, scrub, orbit, fly, create/revise/delete virtual viewpoints, change focal lengths, add rear/OTS/low/aerial/far viewpoints and select camera-only wall/occlusion overrides. Geometry, actors, light and soundtrack remain shared. Camera placement itself has no geometry/collision.
3. **Low-fi editorial:** display affordable previews from the *same* authoritative world/timeline using device-adaptive LOD, frustum culling, lower resolution/samples, cached proxy geometry, simplified shading and optional deferred preview jobs. Multiple preview thumbnails do not mandate nine high-quality encoded video rolls.
4. **Non-destructive edit:** save an edit decision list (EDL), naming approved viewpoint revision, source Film Time in/out, target timeline range, and shot-specific view/render overrides. No source performance reshoot is required to switch a camera, even after freeze.
5. **Hi-fi conform:** evaluate source state and selected view **only for frames used by the edit**, render them at film quality using protected/resumable workers, apply independent final-quality lighting/material/visibility controls, then mux the original soundtrack once. A change to the edit invalidates only affected picture views and presentation caches; original actor/physics source hashes stay unchanged.
6. **Verify/approve:** independently verify selected source state/ticks, original actor/world and viewpoint revisions, output frame hashes, true renderer execution, continuous edit timing, source PCM sync, image/audio playback and the director's cinematic judgment.

At 30s and 24fps, the normal selected-view film has **720 final output frames** (plus optional test/preview/cached rerenders), regardless of whether the director explored 9, 16 or 96 virtual viewpoints. The older *nine full 30s source videos = 6,480 images* is an **optional full-coverage export / stress and comparative-render acceptance**, not a prerequisite to finish the normal 30s edited film.

## Low-fi → hi-fi is two renderings of the same data

The image does not magically become hi-fi by enlarging a low-fi preview. The affordable viewport and high-quality offline renderer both consume the **same authoritative performance, time and shot state**. High-quality pixels still require actual visibility, shading, reflections, simulation/effects and lighting evaluations; if expensive effects are view-dependent they are recomputed for selected views. LOD, texture/shader and lighting upgrades must preserve geometric and acting continuity, not silently invent different performance data.

For low-powered PCs, previews and edit decisions should remain responsive while slow final renders run in bounded recoverable chunks. The system must not require rendering all available viewpoints at final quality before the editor can make a cut.

## USD-FILM workgroup correction / implementation gaps

- **01I / 01L:** one shared 30s actor performance and native multicamera proof stay useful as source/viewpoint tests. The nine-camera preset is an example only.
- **01M / 01N:** revisioned virtual camera source, nonphysical viewpoints and per-view ray exclusions are first-class and should eventually drive live low-fi preview as well as final hi-fi render.
- **01O:** its bounded eight-frame source-locked Cycles job and restart/custody guarantees remain essential. Its *mandatory 90-job-per-camera full-roll collection* is now **optional export mode**, not the only valid editor input.
- **01P:** current `verify_source_camera_rolls(...)` and `conform_original_30s_multicam_short(...)` **require every 720-frame camera roll** and thus do *not yet implement* the normal selective-data-first workflow. Add a separate **selected-shot render plan** and conform that accepts independently authenticated **only selected camera/time ranges** and creates exactly 720 final pictures with the shared source 48k PCM. Do not fake acceptance by relabeling existing full-roll code.
- **Next workgroup: USD-FILM-01Q** — freeze source-scoped EDL and viewpoint-revision contract; create selected-view low-fi/hi-fi render-plan and per-shot cache keys; reuse 01O's protected renderer and 01P's single original-audio mux. **01R** — installed non-destructive multiview editorial UI; adjustable-quality preview and edit-to-final-quality pixel parity.
- **GPU-accelerated nine-roll test** remains a useful *optional* performance/stress test on qualified hardware. Minimal real-source Blender smoke checks remain mandatory; finished 720-frame selected-view 30s film and actual visual/audio review remain mandatory before longer film acceptance. No claim that current native CI has passed.

## Revised decisive acceptance

1. One persistent original 30-second ActorID/source-performance Take, real source timeline and soundtrack.
2. At least 9 synchronized cheap virtual viewpoints shown/sampled in the director workspace; add a **new** viewpoint after freezing the original performance; verify original world/ActorID/PCM source SHA unchanged.
3. Edit across multiple camera viewpoints with reversible revisions, cuts and time-synchronized low-fi previews, without rendering 9 complete encoded videos.
4. Execute **only the selected shot-frame intervals** through a real, authorization-scoped, restart-resumable Blender/Cycles high-quality render path; independently check all 720 selected final frames.
5. Conform 720-picture original-source film with *one* 48k PCM soundtrack, independent picture/audio essence decoding and director shot/lighting/sound continuity approval.
6. Repeat optionally as a 9×720 source-roll stress test on an adequate GPU host; do not block ordinary low-power filmmaking or higher-level scene design on this optional workload.

**Architecture status:** director decision captured. The selective-shot path, preview interface, real native pixel tests and final film evidence remain **OPEN**. Historical full-roll tests are preserved as optional capabilities, not deleted.

### NVP RES-01 / USD-FILM-01S — hardware-aware camera batches and own-worker usage for Lu (SOURCE IMPLEMENTED; NATIVE/INSTALLED GATES OPEN)

Director clarified: NVP must autodetect available PC resources and scale preview/final virtual camera jobs to low/high-end machines; it must let users set **how many shots per batch** (Auto or 1–64) **independently from the number of simultaneous render processes** (Auto or bounded cap). Nine camera viewpoints are only a preset. All preview viewpoints may be evaluated low-fi, while ONLY selected final shots should receive hi-fi rendering. Lu may read NVP's **own** host/managed-worker CPU/RAM/IO usage and queue progress but has NO implicit process, approval, or scheduling authority over NVP.

**Existing foundations reused**: `nvp_resource_guard.py` system RAM/VRAM/pressure admission; `nvp_resource_ledger.py` TaskLedger and in-app ResourceActivityPanel; existing pinned, journaled, contained BlenderWorkerSupervisor. **New code:** `nvp_resource_process_monitor.py` measures only source-registered NVP worker child tree and host CPU/RSS/IO via psutil (unknown GPU per worker stays NULL; process-tree observation NOT kernel custody); BlenderWorkerSupervisor now automatically registers and samples managed workers and exposes read-only resource status. NVP API `GET /api/system/activity` includes these own-process measurements alongside existing system telemetry. `nvp_usd_film01s_adaptive_batch.py` plans source-SHA-bounded low-fi/selected hi-fi queues, auto-detects RAM/CPU capacity and vetted GPU eligibility, groups camera shots into editable Auto/manual batches and bounds simultaneous worker admission with fresh resource checks. SQLite/FULL durable shot queue stores source/ticket hashes, per-shot fresh authorization, independent result verification and interrupted-worker non-replay without custody proof. `nvp_usd_film01s_resource_service.py` composes autodetection, queue progress and read-only `nvp.film01s.lu_read_only_resource_and_batch_report.v1` status. New local API `POST /api/system/shot-batch-estimate` and director tab **21 · Batch camera shots** expose editable viewpoint/selected-final counts, batch size, concurrency and CPU/GPU preference, with honest read-only estimate (no render approval or invented source identity). psutil is added to offline installer foundation requirements.

**Explicit limitations:** NVP now monitors the Blender process path; other native/third-party workers still require individual trusted registration. Per-process GPU attribution, actual vetted Blender GPU backend/device integration, Lu-side connector consumer and real installed NVP worker/desktop acceptance are OPEN. The browser sizing form estimates, it does NOT yet admit an actual FilmIndex source/edit or launch an approved Blender job; 01Q selected-shot worker/EDL and 01R installed editor remain next. Existing full-roll 6,480-frame coverage is optional, while selected 720-frame edited 30s picture/audio film stays mandatory. New Windows/Linux Py3.11/3.13 real own-child/queue unit matrix and actual React resource UI/build CI are committed, not accepted until completed exact-head results are inspected. More in `docs/NVP_RES01_USD_FILM01S_ADAPTIVE_RESOURCE_MONITOR_SHOT_BATCHES.md`.
