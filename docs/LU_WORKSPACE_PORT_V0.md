# NVP ↔ Lu host interface: first executable seam

**Milestone:** NVP-HOST-00 (initial port and contract fixture), 2026-11-02.
**Status:** NVP Python integration tested with fake Lu broker; Lu Rust
workspace fixture committed but not compiled; **no real Lu-to-NVP IPC**.

## Scope of this slice

The film-specific adapter backend/nvp_lu_workspace.py has no independently
configured model server, model file path, GPU runtime, network requests or
self-issued permission tokens.

The adapter receives a **trusted Lu host port** plus an opaque host-issued
scope. A call to propose a screenplay/stage must go through exactly three
Lu-owned operations:
1. read_project(scope): the host authorizes this active workspace instance
   and returns only its approved project's data;
2. generate_story(scope, system, user, max_new_tokens): the host requests a
   completion from its already-loaded model, with cancellation and budget
   admission owned by Lu;
3. save_proposal(scope, stage, content, instructions, expected_revision):
   the host rechecks the scope and edit revision, uses its durable write
   effect journal / project broker, and commits only status=proposed.

The adapter only constructs film-specific prompts and validates the returned
text. It cannot grant Lu permissions, approve a screenplay, or run a worker.
The host port is an **interface to be implemented by Lu**, not an exposed
Python API endpoint that the WebView is permitted to call.

The existing backend/nvp_api.py, backend/nvp_model_service.py and
backend/nvp_idea_pipeline.py remain available to the temporary standalone
dev harness; they are not the production DLC execution path.

## LU SOURCE COMPATIBILITY

Lu contract version 1 (currently in branch
work/lu-generic-dlc-containment-20261101):

- ModuleKind::Workspace in src-tauri/lu-core/src/contracts.rs
- WorkspaceHost lifecycle and instance dispatch in workspace.rs
- Protobuf ToolCall.workspace_id and InferenceFrame in proto/lu/v1/core.proto
- Host authority, effect journal, worker containment, revocation per Lu DLC
  containment gate docs.

Lu feature branch lu/nvp-workspace-contract-smoke-20261102 contains a
**test-only Rust fixture** (nvp.film) for the real WorkspaceHost with a
harmless read-only mock. It does not register an executable DLC, cannot
load GGUF or prove Windows signed-worker containment. No Lu alpha files
have been modified.

## Evidence and limits

NVP local tests:
    PYTHONPATH=. python -m unittest discover -s tests -v

32 Python regression tests passed, including ten new
tests/test_lu_workspace.py cases exercising fake host refusal, suspension,
revocation, stale revisions, output validation and no direct NVP model server.

Lu Rust test to run on a host with Rust:
    cd src-tauri/lu-core
    cargo test --test nvp_workspace_boundary

No Rust toolchain exists in this authoring environment. Mark the Rust test
**not executed**, not passed. This branch is not a signed/installed DLC.

## Follow-up integration work

- Implement a real Lu trusted project broker and scope binding, *not* a
  WebView-provided project ID or a Python-created authorization object.
- Define host-vetted typed Protobuf schema for film proposal read/infer/commit,
  with bounded payloads, cancellation and serializable host result receipts.
- Use Lu's existing inference session, not an NVP-owned model process or
  unauthenticated localhost HTTP API.
- Adapt NVP writing panels into Lu Workspace loader once its UI contract is
  implemented. Do not hook the current independent FastAPI server into Lu.
- Test real Windows worker containment + Broker + revocation before enabling
  untrusted media-render workers, then first actual film render.
