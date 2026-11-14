# NVP STACK-02C3B2 — Native approved work and explicitly owned model instances

**Bounded code acceptance:** [CI 41777307929](https://github.com/vjmichael/nvp_offline_film/actions/runs/41777307929), 3/3 jobs GREEN at source SHA 89c828103912030256e227d1c76a5a1c5060be2d. Windows and Linux each passed 33 backend contracts and an official pinned lmstudio==1.5.0 import; actual Ubuntu Blender passed creator-approved queue, forced RAM denial, native render, independent source/output reopen and zero residual RAM reservations. Does not prove real LM Studio model load/unload, GPU pressure or full authoring UI.

**Development date:** 2026-11-03. **Parent:** STACK-02C3B1. This is an opt-in native integration slice. No browser route or model-exposed tool was added; retail GPU acceptance is NOT implied.

## Immutable creator-approved operations

ApprovedTaskBindings writes the exact JSON document, SHA-256, creator approval reference, and queued resource request in a single SQLite BEGIN IMMEDIATE transaction. It uses an injected trusted NVP host approval verifier, which must check the authoritative approved project revision, source and specification. An owner key or approval ID alone is NOT an authorization capability.

The approval verifier runs before queue registration and again before execution, to reject changed/revoked consent. Tampering with the sealed document fails SHA verification. The ApprovedBlenderDispatcher stores the full BlenderOperation (script/input hashes, outputs, memory demands, GPU device, job ID and timeout), rechecks it, and invokes the EXISTING OS-contained BlenderWorkerSupervisor. Worker output is independently audited before release; ambiguous containment or changed source leaves the resource reservation retained for recovery.

This is a native adapter. Creator-facing approval settings, a fully wired project-domain approval verifier and a cross-engine automatic dispatcher remain open gates.

## Owned CPU-only LM Studio instance

Ordinary model lookup might attach to a model another application loaded. NVP therefore uses the official Python SDK's load_new_instance(model_key, unique_identifier, config) instead of model(), specifying a fresh nvp-prefixed UUID. It requires that the returned handle get_info().identifier exactly match the intended identity. A duplicate identifier is rejected by the provider.

A creator-verified load and SHA-identified conservative memory estimate is required before resource admission. This first SDK adapter forces GPU offload ratio zero, because Windows AMD GPU identity and VRAM estimation remain unverified; GPU-enabled model loading is not activated.

Before SDK loading, a FULL-sync durable record stores the intended instance ID. Only the same still-live verified SDK handle may unload its own model. Lost requests or unload acknowledgements, wrong provider identity, and restarts retain memory reservation and forbid automatically unloading other models. No unload-all, no attaching preexisting models, no fabricated load percentages.

The SDK client must be provided by a trusted host configured for the local server. The Python SDK is not installed or bundled by this change. Native live-model behavior is NOT proven by mocked contract tests.

## Tests and remaining gates

New contracts cover creator revocation, immutable digest tamper detection, atomically queued records, resource denial, actual two-phase SDK calls through fake verified handles, wrong-instance rejection, lost load/unload acknowledgements, restart refusal, exact Blender audit and uncertain native process cleanup. Linux and Windows CI also rerun the previous scheduler, memory governor and guarded Blender-admission suites.

The next steps are: connect approval verification to authoritative approved scene/take revisions; pin and run the real LM Studio SDK/real model on an actual machine; obtain and validate conservative lms estimate-only RAM usage; add provider-backed liveness/progress; test Windows Radeon memory pressure before any GPU offload; integrate native dispatcher queues across all production routes; perform OS cleanup and provider recovery reconciliation before releasing retained reservations. Licensing and a one-installer build remain separate.

Official SDK documentation:
- https://lmstudio.ai/docs/python/manage-models/loading
- https://lmstudio.ai/docs/python/model-info/get-model-info
- https://lmstudio.ai/docs/cli/local-models/load

## Final native acceptance evidence

The genuine Blender fixture in tools/nvp_stack02c3b2_approved_blender_fixture.py created a SHA-pinned source and a creator-verified immutable operation, refused to launch under injected unsafe RAM, then admitted after measuring actual host headroom. The established contained Blender executable built a real native blend, rendered a real PNG, wrote an original audit, and re-opened all outputs independently; all checks passed. The final resource ledger reported zero outstanding RAM reservations. The test does not imply GPU offload or real SDK model-server acceptance. Official Python SDK 1.5.0 import was independently exercised on both operating systems, while actual SDK runtime lifecycle uses fake provider handles in the 11 B2 contract tests.
