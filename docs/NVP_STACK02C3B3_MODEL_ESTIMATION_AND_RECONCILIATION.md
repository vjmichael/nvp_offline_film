# NVP STACK-02C3B3 — CPU-model estimates and restart recovery

**Development date:** 2026-11-03. **Parent:** STACK-02C3B2.

## Protection for the creator's desktop

The native LM Studio estimator uses a SHA-pinned local binary and an explicit numeric loopback address. It calls the official model estimation command with estimate-only, the exact model key and context, and GPU off. Never accept an arbitrary supplied estimate hash as proof of RAM usage. Output must identify the exact model, provide one total-memory measurement and one GPU measurement, and report zero GPU memory. Invalid, stale, contradictory, nonzero-GPU or over-budget readings fail closed.

The parser treats GB conservatively as GiB, reserves at least 125% of the estimated memory plus 1 GiB extra, and leaves the existing 20%-of-RAM/at-least-2-GiB free reserve intact. A new strict owner stores the output/tool provenance digest in FULL-sync SQLite, verifies freshness within five minutes before admission, and never bypasses the established resource governor. An estimate does not guarantee an OS-enforced memory cap or safety from third-party allocation spikes.

## Actual owner identity

The model is created with the official Python SDK new-instance API, with a fresh NVP identifier and GPU offload ratio zero. NVP must then verify the exact modelKey, identifier, and unique instanceReference reported by the SDK. These fields are stored durably. Before unloading, the same still-live SDK handle must return the same three fields; a reused identifier is insufficient to unload a different instance.

An in-flight load is periodically heartbeated as an active NVP request, not an invented percentage. Uncertain load/unload acknowledgements, missing identity evidence and crashes retain RAM reservations and require explicit reconciliation.

## Native consent

The new NativeModelConsent registry stores a short-lived, revocable, exact SHA-bound permission for one task, model, context and conservative memory request. A trusted native desktop handler may issue or revoke it; the AI model and web UI are never allowed to mint it. The actual human-facing approval event and project-specific host identity verification are still to be wired, so this is a backend policy component, not a finished consent UI.

## Restart safety and recovery

LocalModelObserver performs a bounded read-only GET on the numeric loopback LM Studio v1 models endpoint. No proxies or redirects are permitted. The durable observation distinguishes PRESENT_UNVERIFIED, IDENTITY_CONFLICT, NOT_OBSERVED, PROVIDER_UNAVAILABLE and UNKNOWN, with original NVP task/instance IDs. Every observation is journaled.

The observer never unloads a model, reconstructs an ownership handle, or releases a resource reservation. A missing instance in one readout does not prove an in-flight load request cannot complete later. That race must be resolved by a separate provider epoch/termination proof and explicit creator-authorized reconciliation.

## Tests and boundaries

The B3 regression suite covers exact CLI command/arguments and binary hashes, conservative memory math, revoked consent, expired estimates, tampered receipts, foreign model identity, reuse of instance identifiers, simulated provider failures and lost acknowledgements, multi-process reservations inherited from B2, and read-only restart observation. Pinned official LM Studio SDK import is exercised in CI, but provider handles and CLI responses remain simulated. Genuine Blender evidence from B2 remains valid and separate.

The next gates remain: real LM Studio + genuinely downloaded small GGUF CPU load and unload on a controlled host; actual trusted desktop consent interaction; provider-backed orphan cleanup; physical Windows Radeon RAM/VRAM pressure and Blender coexistence; complete engine dispatch, installer and license review. Never infer full hardware safety from simulated provider tests.

Official references:
- https://lmstudio.ai/docs/cli/local-models/load
- https://lmstudio.ai/docs/python/manage-models/loading
- https://lmstudio.ai/docs/python/model-info/get-model-info
- https://lmstudio.ai/docs/developer/rest/list

## Manual real-runtime acceptance

The repository includes tools/nvp_stack02c3b3_local_model_acceptance.py. It defaults to estimate-only without starting a model, requires a pinned native LM Studio CLI executable, and is intentionally developer-only. To load a new CPU instance and immediately unload only that same verified handle, the operator must supply both --execute and the literal --creator-consent I_APPROVE_NEW_CPU_MODEL_AND_OWNED_UNLOAD. The runtime records evidence in a dedicated state directory; when admission is unsafe it queues without launching. This script has not been run against a real installed LM Studio server or model on the creator's machine. Native CLI script/batch launchers are not supported by this safe no-shell fixture.
