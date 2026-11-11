# G02 — Lu-owned inference and NVP Film Workspace integration evidence

**November 10, 2026 · Implementation underway · NOT physical release acceptance**

## Source heads and no-overwrite rule

- NVP G02 isolated branch: `nvp/g02-lu-shared-model-boundary-20261110`, based on filmmaker documentation draft PR #153. Keep PR #74's moving native Film Time/OpenUSD production branch unchanged.
- Lu Core G02 isolated branch: `lu/g02-generic-workspace-inference-gate-20261110`, forked from Lu PLAN-04 draft PR #210 commit `34dab0993284d22020656cd27fae84b7dcf13dda`. Lu IDE work is unrelated and must not be touched.
- Older `vjmichael/jan_alt` Workspace/DLC proposal and its native bridge are **historical**, not proof that the current `Lu-AI-GUI` Windows desktop mounts NVP.
- G01 independent physical NVP approvals/cancellation and Qwen3.8-27B Radeon acceptance remain open. No PR #151 → #74 integration or inherited acceptance.

## Actual source findings

1. The current Lu Core has `src-tauri/lu-core/src/workspace.rs` with module registration, active/suspended/closed instance checks and typed native tool dispatch via policy; it does **not** install or mount external NVP content by registering a manifest.
2. `TrustedInferenceSupervisor` owns the model, session, generation, typed event stream, generation reservation and cancellation; its `model_ids()` observes the host model catalog. `InferenceFrame` is an internal Protobuf message, **not** a public network contract.
3. The present Lu desktop's `workspace_desktop.rs` is a chat-scoped folder picker/read-only tool flow, **not** NVP's Film Workspace. None of these existing components authorize independently choosing Lu's llama.cpp localhost port or loading a second model.
4. NVP already has `backend/nvp_lu_workspace.py`, a film-specific proposal engine using an injected `LuFilmHostPort`. Its old test suite uses a simulated trusted host, not genuine Lu inference.

## Source changes in this group

### NVP adapter

`backend/nvp_lu_g02_port.py` implements NVP's existing read_project/generate_story/save_proposal port and adds conservative readiness and cancellation. It requires a separately **trusted** Lu host implementation of:
- verify_scope(opaque_scope, operation), host-owned project/instance/epoch/task validation **on each call**;
- read_runtime and catalog_count, distinguishing no catalog, available/unloaded, loading, ready, busy, unloading, failed, timed-out, disconnected;
- generate_events with bounded, monotonic generation event frames bound to the exact instance/project/session/model/epoch, plus a mandatory noncancelled terminal completion;
- record_generation of the exact request/generated SHA-256 in the Lu durable journal **before** saving any creative proposal;
- read_project/save_proposal with CAS on the project revision and only the `proposed` status;
- cancel_active with a request result **never** represented as verified worker termination.

**No direct TCP/socket, GGUF loading, filesystem, FFmpeg or execution API exists in this NVP adapter.** It cannot self-issue a host scope. The source tests inject a host double and must never be called an installed bridge.

### Lu Core generic admission

`src-tauri/lu-core/src/workspace_inference.rs` adds a reusable host-only boundary. It validates an active, correctly owned Workspace instance and exact human task/project policy **before** model status, generation reservation, run and cancel. It uses the same `TrustedInferenceSupervisor` instead of making another model process. It denies stale/suspended/foreign workspaces, wrong model sessions, wrong generation IDs and late-stream policy revocation. Cancellation remains a request, not a terminal proof. This is not NVP-specific code.

## Acceptance classification

| Gate | Current status | Evidence required |
| --- | --- | --- |
| G02-A generic Lu Workspace ownership + native policy check | Source implemented; native CI in dedicated Lu branch | Windows/Linux Rust `workspace_inference::tests` and existing `workspace::tests` exact head |
| G02-B model status mapping | NVP contract implemented; host-double tests | Physically installed Lu model catalog + real supervisor status bound to active NVP Workspace, including unloaded/busy/failure |
| G02-C source-bound proposals and cancellation | NVP contract implemented; host-double tests | Real Lu `InferenceFrame` stream, bounded hosted request, terminal and durable host receipt; revoked/timeout/stale source evidence |
| G02-D resource and worker custody | Existing Lu/NVP components, not wired for Film Workspace | Shared GPU budget and one loaded GGUF; per-task authorization, host resource queue, cancellation and native recovery |
| G02-E installed NVP Film Workspace | **Not implemented / unaccepted** | Trusted signed/verified package lifecycle (or equivalently vetted built-in workspace), Tauri mount, native IPC, project grants, physical Windows Qwen3.8-27B/R9700 |
| G01 independent physical closeout | **Open** | Human approve/refuse/cancel/restart, worker journal, RAM/VRAM and source integrity; selective PR #74 integration after acceptance |

## Remaining G02 integration work (do not silently skip)

1. **Lu host-supplied real adapter:** Implement typed host-side Session/Project/Task binding, actual model status/inference event delivery, journaled proposal save and native cancellation through a controlled Lu Workspace mount. Keep browser and model text out of credential / model file / tool path decisions.
2. **Transport and UI acceptance:** Have Lu mount NVP as a vetted Film Workspace. Maintain its own specialist UI without an external development model server. Show only human readiness/next action, not technical model internals. No duplicate model catalog/weights load.
3. **Native resource and recovery:** Share host CPU/GPU/VRAM admission; cancellation before worker start, during streaming and after completion; deny stale epoch, cross-project response and grant replay through restart. Record genuine effects in Lu's durable journal.
4. **Exact-head verification:** Run host/native Windows/Linux tests and real Qwen (not mock) end-to-end. Test physical Windows Windows/GPU memory consumption on Radeon AI Pro R9700 and uninstall/project data retention. Lu itself must continue working with NVP disabled.
5. **Canonical reconciliation:** Only after compatible source/ABI/Film Time checks and physical evidence, selectively integrate NVP G02 with PR #74. Do not wholesale merge donor histories.

**Overall:** G02 has begun with real cross-repository source changes and native test gates, but G02 is **not complete** while the current Lu desktop lacks a physically installed NVP Workspace host binding.
