# NVP-STACK-02C3B8 — Frozen Digital Take → real supervised Blender animation

**Scope:** NVP film production, independent of the deferred Lu ↔ DLC interface (revisit after Lu v1.0).

## Architecture and source of truth

B7 used the **current approved static world**. B8 instead consumes a **frozen Digital Take Package (DTP)** already created by `DigitalCapture.capture` and stored as versioned immutable world/performance/take revisions in `FilmIndex`. The capture contains an approved 24fps shot sequence, camera solutions, actor marks, source geometry, timed dialogue, original director decision proof and dependency hashes. A filmmaker may later edit the mutable WorldState or shot sequence: that **must not modify the earlier take**.

- `backend/nvp_frozen_take_stage.py` independently calls `DigitalCapture.reopen(project_id,take_id)` and validates captured lineage/data. Only NVP's established deterministic exporter `animated_blender_script` constructs native Blender Python code. It binds SHA-256 of frozen geometry, *derived exact sampled performance*, generated script and original indexed capture document. Audit frame samples are deterministic from the frozen paths, never proposed by an LLM.
- Exclusive private fsync-and-rehash staging writes `frozen_world.json`, `frozen_timed_take.json` and `trusted_frozen_take.py` inside the established native Blender worker root. The bounded `BlenderOperation` contains fixed relative names, pinned hashes, `frozen_take.blend` output, declared RAM/GPU/timeout, and no model-supplied executable path.
- `backend/nvp_frozen_take_render.py` accepts an **installed native host-injected verified creator action**, scoped to the original take ID, project and scene, capture SHA, exact timed source/render hashes, frame count/rate, shot count, job identity, operation SHA and memory budget. Durable consent may be revoked or expire. A caller-supplied API key, browser bool or model assertion is not a human approval.
- The existing approved task dispatcher independently checks the exact authorization at queue, before and after atomic resource admission, and immediately before native launch. Insufficient RAM queues without spawning. Native OS containment, worker journaling, cancellation and audit are unchanged; unsafe cleanup never pretends success.
- `backend/nvp_frozen_take_audit.py` requires a verified original native build with current consent; it streams the `.blend` into a **second** immutable worker directory, pins the existing `SHOTS_AUDIT_SCRIPT` and take frame samples, and actually reopens the scene with Blender. A second resource-admitted OS-contained native job checks FPS, duration, take/dependency SHA, every cut marker, camera pose and lens, and sampled XY actor positions at key frames. It also produces one genuine Blender PNG preview and verifies output bytes and full nonduplicate check set.
- The original frozen take is never revised to hold a presentation; derived Blender `.blend`/technical preview is separate production evidence. The scene and motion are procedural character proxies, not high-quality rigging, lip sync, voice recording, professional animation or a finished master.

## Trust and failure policy

- No new FastAPI execution route. Browser can inspect B6 source but **cannot** mint native user authorization, launch Blender or reserve RAM.
- The CI fixture supplies an isolated simulated creator action only to exercise these gates; an actual installed native desktop UI verifier remains a separate acceptance gate. Do not claim shipped one-click authorized NVP rendering until that exists.
- Cross-film take IDs cannot be read; corrupted original blobs, missing lineage, modified stage/script, wrong artifact hashes, expired/revoked approval or changed operation signatures fail closed.
- **Changed live WorldState is not a reason to reject previously frozen takes.** All render verification must target the original immutable indexed source revision.
- On worker crash, uncertain cleanup or resource pressure, retain conservative reservations and terminal records until proper host cleanup. A successful process exit is insufficient absent actual second-process independent audit.

## B8 acceptance

CI workflow `.github/workflows/nvp-stack02c3b8-frozen-take.yml` runs Windows/Linux native contract and capture regression tests; Linux installs real Blender and executes `tools/nvp_stack02c3b8_real_frozen_take.py` under Xvfb, including an explicit later live-scene mutation. The fixture must create an actual approved moving performer path, 2 shots and 120 frames at 24fps, submit an explicitly accepted take and perform 2 real independent Blender processes. It checks real native outputs, source hashes, full set of frame/camera/cut checks and RAM reservation release. Frontend build/UI regression remains separate.

Acceptance is **not** 120 fully rendered frames or a playable movie: the completed work establishes actual frame-addressable Blender animation in a `.blend`, plus an independently rendered technical still. Later gates must render the complete frame range to genuine scene-linear high-bit-depth EXR, encode a film presentation and separately verify color, timing, image quality and sound.

## Next NVP production steps

1. Bind trusted native installed desktop creator UI to `NativeFrozenTakeRender` without granting an unauthenticated browser execution capability.
2. Emit a **full** bounded contiguous EXR image sequence (not one PNG) from frozen take, with measured RAM/VRAM admission, OCIO/ACES provenance, channel/readback authenticity and durable sequence per-frame receipts.
3. Add timeline/editorial/audio/video mastering from authoritative original take data; downstream presentations never modify frozen DTP world/performance records.
4. Extend procedural proxy animation to genuinely rigged/retargeted actors with measured pose/contact checks and upgraded camera/lighting production standards.

**PR:** NVP B8 draft stacked on B7. No Lu or Cognitum code changes.

## B8B — Immutable derived technical presentation in FilmIndex

Once the original frozen-take build and second-process actor/camera/PNG audit are **already completed and independently verified**, `backend/nvp_frozen_take_presentation.py` publishes **a new `presentation` object**, not a revision of the take. It preserves a typed `source_take` edge to the exact original take revision 1. The verified `.blend` is copied into FilmIndex using bounded streaming media publication; audit JSON and technical PNG are stored by SHA-256 as project-scoped blobs. A small derived manifest records original capture SHA, frame rate and total frames, worker and audit SHA receipts, camera/actor check count and explicit `complete_video=False`/`genuine_scene_linear_exr_sequence=False` flags.

`verify_presentation` re-opens the immutable original Digital Take, FilmIndex's derived presentation revision and the three indexed output blobs after restart. It independently checks their exact hashes, expected source lineage, timed performance/script SHA, original 24fps frame count and the complete, nonduplicated native Blender timeline-check set. The publisher cannot launch Blender, mint consent, overwrite a frozen take or call any Lu interface. If an output is incomplete, tampered, missing or from a foreign project, it refuses to publish/verify. A second identical publication uses the same content-addressed immutable presentation ID rather than revising historical evidence.

This derived presentation is a **single-frame technical animation preview and reusable native `.blend`**. It is not a rendered 120-frame movie, not a full editorial cut and not yet high-bit-depth/ACES EXR delivery. Full-frame native rendering and professional film presentation remain the next explicit production gates.
