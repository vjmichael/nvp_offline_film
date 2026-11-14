# NVP-AI-03 — Trusted read operation host

**Status:** Implemented in source on the active PR #45 branch; regression tests added, native integration and exact-head CI acceptance **not yet verified**.

## Purpose

NVP-AI-03 adds a *trusted desktop internal* dispatch boundary over the revision-bound read-only screenplay adapter and context assembler:

- `backend/nvp_ai_refs.py`: exact source-revision screenplay lines.
- `backend/nvp_ai_context.py`: task-based scene, screenplay and shot context.
- `backend/nvp_ai_read_host.py`: per-request trusted-policy callback, strict project-scope comparison, canonical request digest and result receipt.
- `tests/test_nvp_ai_refs.py`, `tests/test_nvp_ai_context.py`, `tests/test_nvp_ai_read_host.py`: read and refusal contracts.

`NativeAiReadHost` has no HTTP route, user-authentication implementation, token issuance, persistent journal or model invocation. A concrete embedding host must obtain the real authenticated actor, active turn and project from native session state. It must supply `authorize_read(scope, capability_id, request_sha256, exact_request)` from its own trusted policy context. It may **not** delegate that callback to screenplay text, generated code, WebView JavaScript, a model, a CLI or an untrusted network client. Merely constructing a `TrustedReadScope` never grants access.

The operation host supports only:

1. `nvp.screenplay.read_lines.v1` (with current-revision enforcement).
2. `nvp.context.assemble.v1` (screenplay review, scene coverage and shot review).

Any other capability is refused. An unexpected request field is refused. A project mismatch is refused before the policy callback. A literal `True` from the host's current policy is required before content is read. The read handler re-checks the current screenplay revision and rejects stale source. The returned receipt contains the canonical request SHA and a result SHA, and explicitly indicates that neither model authority nor creator approval has been granted. These receipts are **ephemeral response metadata, not durable execution evidence**.

## Integration boundaries

The approved native job path remains owned by `ApprovedTaskBindings`, `TaskLedger`, the native FilmIndex hosts and their existing verification. Do **not** route native writes, Blender jobs, media encodes, approval changes or publication through the read dispatcher. For effectful work, add a separately designed and attested adapter that captures the exact immutable source, creator policy, preflight and existing journal IDs; never reinterpret a read receipt as a native grant.

## Still outstanding

- Native session/desktop wiring to a real host-owned identity and policy callback.
- Full typed JSON Schema (the initial capability catalog is descriptive, not a schema validator).
- Provenance-rich, byte-budgeted cross-domain AI context (Bible, FilmIndex and media).
- Current dependency inventory, operation impact preview and consolidated recovery status.
- Exact-head regression and native end-to-end verification for these changes.
- Independent Windows/Linux film-delivery, installed alpha, cinema compliance and crash gates under PR #45.

**No creative or cinema acceptance is implied by these source commits.**
