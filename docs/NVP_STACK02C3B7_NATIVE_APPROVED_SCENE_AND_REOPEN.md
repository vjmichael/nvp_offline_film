# NVP-STACK-02C3B7 — Native creator-bound Blender build and independent source audit

**Scope:** NVP native filmmaking only. Lu–DLC Workspace integration is deferred until after Lu v1.0 and is not used by this pipeline.

## Film workflow

1. NVP Studio, ProductionScene and WorldState hold the filmmaker-approved proxy geometry and director's visibility and staging choices. B6 returns a revision-bound, deterministic world + Blender script hash receipt.
2. A **trusted native host** uses `stage_proxy_render_source` to fsync exact `approved_manifest.json` and `trusted_scene_build.py` into a unique, private existing Blender worker directory. No arbitrary model/browser script or executable is accepted.
3. `NativeApprovedProxyRender.consent_from_trusted_native_action` invokes an injected **authenticated creator-action verifier** with exact project/scene ID, source/script SHA-256, current revisions, requested RAM/GPU budget, native job digest and complete build + independent review output contract. Only an explicit positive result from that trusted local host can create a short-lived, durable, revocable consent in the shared SQLite ledger.
4. `enqueue_approved` submits the pinned existing `BlenderOperation` to the existing `ApprovedBlenderDispatcher`. Its `ApprovedTaskBindings` verifies the exact canonical operation SHA-256 and grant at enqueue and immediately before and after memory admission. A final host-only `pre_worker_check` verifies current creator permission and source again directly before native launch.
5. `run_next` uses existing TaskLedger headroom policy, reservation journal, pinned Blender executable, OS containment, fail-closed process cleanup and input/output SHA-256 checks. Under inadequate RAM it queues without launching Blender. Under allowed RAM it runs the actual scene build; it does not invent percent-complete.
6. `NativeProxySceneAuditor.reopen_and_verify` accepts only a durable original build success and exact valid consent. It copies the verified original `.blend` by bounded streaming and the approved manifest into a **different** native worker directory, pins the unchanged standard `AUDIT_SCRIPT`, and launches another host-controlled, memory-admitted Blender process which actually reopens the scene, validates scene/layout/instance/pose/rotation/spatial anchors/visibility, and renders a PNG technical preview.
7. The audit is accepted only after `verify_completed` independently rehashes both inputs and outputs, the audit JSON contains nonempty all-passed checks for the exact scene ID, source preflight still matches and RAM reservations are released. Repeat calls reverify completed output without re-executing a worker. Interrupted, pending, wrong, expired, revoked or tampered work is never accepted as success.

## Authorization boundary

The new `NativeApprovedProxyRender` and `NativeProxySceneAuditor` modules are **host-only**; no new FastAPI endpoint, browser-callable load/execute method, model-exposed tool, or Lu dependency is introduced. The `verify_creator_action` callback **must** be supplied by an installed host component capable of validating actual human presence, current local creator identity and a clear approval of the exact context. It is intentionally not a `True` boolean supplied by the web UI. The B7 unit tests and real Linux Blender CI use a **test-only simulated native creator signal** for repeatability. Consequently, a consumer-native desktop UI consent flow remains an open product integration gate.

The code never grants a project edit, model unload or arbitrary filesystem effect. Releasing a resource reservation after an uncertain OS worker cleanup is forbidden. A last-moment approval/source failure after admission is conservatively left ACTIVE with reservation pending host reconciliation, even when the subprocess is not launched. A revoked QUEUED task is cancelled without launching; an ACTIVE task is not killed or marked complete just because consent was revoked.

## Evidence and important limits

- Native Windows and Linux CI run project/scene source, immutable staging, policy, approval, restart, revocation, expiry, RAM admission, worker-spawn denial, audit-denial and legacy worker tests.
- Linux CI additionally installs **real native Blender** with a headless display and runs `tools/nvp_stack02c3b7_native_approved_scene_fixture.py`; on success its evidence contains the true Blender executable hash/version, actual build `.blend`, separate actual Blender reopen, independent geometry/visibility checks, PNG preview SHA-256 and no leaked RAM reservation.
- React UI regression remains unchanged: B6's Inspect preflight is read-only. An installed native approval interface has **not** been delivered; no production UI render button is enabled.
- The accepted output is **procedural-proxy previs**, NOT a fully rigged digital character, actual frozen Digital Take Package, scene-linear high-bit-depth EXR sequence, final color grade, professional finishing master or DCP.
- Linux headless real-process success does **not** prove installed Windows Blender/AMD GPU VRAM safety. A later Windows physical acceptance and Blender/Cycles workload-admission stress remain open.

## Remaining NVP-only gates

- **B7C**: bind an actual trusted installed NVP desktop creator UI event to the above native-only verifier and audit/approval receipts. Do not provide a web-only authorization shortcut.
- **B7D**: host restart/worker death, in-flight audit-queued reconciliation, expired-in-progress consent policy, cancellation and rigorous OS cleanup/cgroup/Windows Job Object proofs under concurrent tasks.
- **B8**: frozen Digital Take Package as the render source (not merely approved static proxy world), verified timed character motion, camera/cut/audio provenance; preserve immutable original take identities.
- **B9**: real high-bit-depth scene-linear EXR and color-managed image sequences, independently verify pixel/channel fidelity; then timeline/editorial mastering, IMF/ProRes/DCP as appropriate.

**GitHub review:** NVP draft PR #37, stacked on B6. No modifications to Lu or Cognitum.
