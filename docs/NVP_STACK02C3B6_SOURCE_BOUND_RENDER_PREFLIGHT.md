# NVP STACK-02C3B6 — Director-approved source-to-Blender preflight

**Scope:** Standalone NVP film-production engineering. No Lu, Cognitum or other repository is modified by this milestone.

## Why this gate exists

NVP already has deterministic scene staging, persistent world edits and a generated Blender scene script. It also has a separate, OS-supervised Blender job system with immutable job inputs, bounded resource admission, output hashes and verification. What was missing was a project/scene-bound **source check** connecting the current director-approved proxy world to a precise, reviewable Blender script identity before a trusted native host grants execution.

The NVP web API is not a privileged user-authenticated native control channel. This milestone therefore creates **read-only source evidence**, not an API endpoint that can issue native creator consent, run Blender or load a model.

## Implementation

- backend/nvp_render_preflight.py: reads NVP Studio's current project and current approved world from WorldState/ProductionScene; refuses unapproved, stale, missing, cross-project or unverifiable worlds; computes deterministic UTF-8 SHA-256 identities of exact compact proxy-world manifest and generated Blender script. It reads the source **twice** and fails closed if project revision, world revision, base-plan revision, layout digest, world content or script identity changes during the preflight.
- verify_scene_preflight: recomputes against the **current** NVP project/world and rejects stale receipts. A successful comparison only confirms current source equality; it never grants a worker launch. The native host must revalidate source AND its own authorization, resource and effect grant immediately before any future execution.
- backend/nvp_api.py: exposes GET /api/projects/{project_id}/production/scenes/{scene_id}/render-preflight, limited to exact source metadata; no POST, no browser-approved work dispatch, no arbitrary filesystem/script/executable selection. Existing approved world export logic remains the sole source of proxy world data.
- frontend/src/ProductionAuthoringPanel.jsx: creator can click **Inspect render preflight** to review project/world revision, object count, world SHA-256 and Blender script SHA-256. The UI expressly says Blender did not run, no native approval was granted, and resource admission was not checked. A stale world disables inspection and revision changes clear previous proof. Existing Blender source export is retained unchanged.
- tests/test_render_preflight.py: real SQLite Studio and ProductionScene solve/approve fixtures, deterministic source equality, expected scene-script digest, edit/screenplay invalidation, missing/cross-project/unsigned source denial, source mutation between reads, no worker dispatch and actual GET API behavior.
- frontend/src/ProductionAuthoringPanel.test.jsx: real React test of displayed hashes, zero native mutation and stale-world disablement.
- .github/workflows/nvp-stack02c3b6-render-preflight.yml: native Windows/Linux Python project-source/guardian regressions plus React build/UI tests.

## Evidence is not a finished film

This source currently describes *director-approved procedural proxy geometry*. A preflight does not prove a Digital Take Package is captured, a character rig is realistic, motion/occlusion are correct, high-bit-depth EXR pixels exist, or a Blender/DCP presentation passed independent technical acceptance. Those tasks retain separate NVP native output/provenance gates.

The source proof is also **not** an atomic copy of a render job. Another edit can occur after the two checks. This is why execution must recheck both source and trusted host-issued creator approval at the worker boundary and pin immutable copies of approved source/script to the job workspace, then recheck their hashes before/after rendering. An unsigned GET receipt must never be accepted by the host as user consent.

## Next NVP-only work

1. NVP B7 trusted native creator-consent event and project-scoped production job: bind exact preflight project/world revision, content hashes and selected output contract to a non-browser-issued authorization receipt. Do not pretend a FastAPI request is that trusted event.
2. Use existing ApprovedBlenderDispatcher/BlenderWorkerSupervisor to stage immutable source/script inputs, obtain real host RAM/VRAM admission, execute only an approved worker, verify original source unchanged, and accept only verified output manifests.
3. Surface signed execution receipts and genuinely measured worker progress in the Film Workspace. Cancellation/failed cleanup must retain uncertain reservations until OS-supervised worker cleanup is verified.
4. Extend from proxy scenes to *frozen Digital Take Package* source and genuine high-bit-depth EXR frame evidence, reusing NVP's film/grade/presentation pipeline rather than creating duplicate rendering code.

No external host dependency is needed to perform this NVP preflight milestone.

## B6 follow-on — immutable native-ready source staging (2026-11-03)

The trusted internal NVP host now has `backend/nvp_render_source_stage.py`. This does **not** make the browser render endpoint privileged. Given the exact B6 source proof, Studio and an existing pinned `BlenderWorkerSupervisor`, it:

1. Recomputes and revalidates the live project source receipt (no trust in caller-supplied bytes).
2. Creates an unpredictable exclusive directory under the trusted Blender worker root. Writes `approved_manifest.json` and `trusted_scene_build.py` with exclusive OS opens, fsyncs them and verifies their SHA-256 from disk.
3. Constructs the existing typed `BlenderOperation` with pinned script/manifest inputs and fixed `approved_scene.blend` output; resource estimates are bounded but not yet admitted.
4. Runs the worker's input-contract validation without launching Blender, then rechecks source revisions after staging. On failure it removes only its inert staging directory.
5. Provides `verify_staged_proxy_source` to independently recheck current approved world, staged hashes, source identity and lack of forged run/approval claims.

**No privilege escalation:** Staging does not mint creator approval, enqueue an approved job, reserve RAM/VRAM or start Blender. It is not a FastAPI execution endpoint. The next production gate must bind a genuine trusted creator action and exact staged source proof to the existing approved dispatcher, then independently reopen/audit native Blender output before claiming scene acceptance.

## Lu–DLC interface schedule

Per owner direction, **Lu ↔ DLC Workspace integration is postponed until after Lu v1.0**. No Lu IPC or Host API implementation is a prerequisite for NVP B6 or subsequent NVP film engineering. Continue NVP's standalone project/take/world source of truth, contained Blender/FFmpeg pipeline, scene-linear imagery and cinematic delivery. B5 Lu status and earlier interface RFCs are deferred experimental records only.
