# NVP-INT-LU-01A — exact-source Lu protocol pin and NVP film type mapping (2026-11-21)

**Status: SOURCE-ONLY DRAFT / NOT COMPILED / NOT INSTALLED.** This milestone begins contract alignment; it does **not** enable an endpoint, register tools, authorize a movie edit, or pass a cross-process acceptance gate. This is a successor to the owner-approved NVP Lu IPC + stabilization roadmap.

## Exact upstream source and dependency

- Source: [Lu-AI-GUI draft PR #244](https://github.com/vjmichael/Lu-AI-GUI/pull/244), head `ab3b207bcafda9b6517ca6d928dfd6be3565bcf7` on `lu/ipc01d-r2-r1-native-20261120`; **not a Lu release or stable SDK**. Re-check before any implementation/rebase.
- `src-tauri/lu-core/proto/lu/workspace/v0/workspace.proto`: Git blob **`4e01d921197fb1c58c99958479b1cede36e13c9a`**.
- `src-tauri/lu-core/src/workspace_ipc.rs`: Git blob **`06c47e8e83ad835711dca3ed0dc9851bcf8aae05`**; declares `WIRE_MAJOR=1`, `WIRE_MINOR=0`, `MAX_FRAME_BYTES=262144`, `MAX_TYPED_BYTES=65536`, `MAX_CAPABILITIES=64`, `MAX_OBJECT_REFS=16`, `MAX_STREAM_CREDIT=64`.
- `src-tauri/lu-core/src/workspace_ipc_transport.rs`: Git blob **`c596530884c4d994dda19995bb0cc4b85690cf95`**; big-endian u32 size, Protobuf and 3-second framed I/O timeout.
- `src-tauri/lu-win-worker-job/src/ipc_pipe_peer.rs`: Git blob **`7b7b456cb3068fd145d89309a587140ad3dc5780`**; installed peer identity and signed enrollment additionally depend on installer/credential-broker modules, NOT a generic named-pipe connection.

## Contract binding

| Inherited Lu contract | NVP decision | Current disposition |
|---|---|---|
| `lu.workspace.v0.WorkspaceFrame`, major/minor **1.0** | Reuse exactly; no NVP envelope, guessed external `lu.v1` channel or JSON-on-socket transport | Source pinned; no native client |
| `Hello` / `AuthChallenge` / `AuthProof` / `Welcome` | Lu-owned enrolled package, OS account/process/image, protected HMAC and epoch; claims alone are untrusted | Installed positive enrollment **BLOCKED upstream** |
| `ModuleRole.MODULE_ROLE_WORKSPACE` | `nvp.film` is proposed Workspace/provider; actual manifest must be separately approved | Proposed ID, not registered |
| `RegisterWorkspace` / `CapabilityDescriptor` / `TypedValue` | Map exact `nvp.film.*` capability IDs and `type.googleapis.com/nvp.film.v1.*` payload types in [candidate schema](../contracts/nvp/film/v1/nvp_film_v1.proto) | Proposed schema; protoc/prost and NVP handler compilation open |
| `OriginRefs` / `ObjectRef` | Lu host binds original workspace, conversation, user turn, task, operation; domain rechecks source scope; object hash/size/expiry is a locator, never bearer authorization | Semantics recorded; live binding open |
| `CoreInferenceRequest` / `CoreInferenceEvent` | Optional Lu model reasoning/streaming; no duplicate GGUF model or private localhost endpoint | Await enrolled Lu runtime |
| `SharedModelStatusReport`, `ModelLease*`, `ResourceTransition*` | Lu owns model and lease lifecycle; NVP requests cooperative scheduling and reports only measured usage | Await runtime and resource evidence |
| `CancelAcknowledged`, `ReconcileOperation`, `TERMINAL_STATE_UNCERTAIN` | Cancel-ack is not worker stop; durably reconcile NVP TaskLedger/FilmIndex before any replay | Handoff work open |
| `StreamCredit` | Explicit 1–64 event credit, contiguous stream sequence and bounded cancellation/backpressure | Handler/consumer open |

`WorkspaceFrame` source acceptance additionally requires canonical encoded bytes, exact version, max 64 capability descriptors, <=16 object refs, max 64-KiB typed payloads, each code/ref bounded, legal effect class, no mixed PURE effects, no unknown/duplicate registration IDs, no forged host owner. The external Lu transport limits payload to 256 KiB including Protobuf (not just JSON).

## NVP capability/effect mapping — proposed, not currently admitted

Lu `CapabilityDescriptor` requires a fully qualified type URL and real effect classes. **Pure compute must not be misreported as ReadWorkspace** because Lu's current original native ToolEffect bridge does not accept pure computation yet.

| Capability ID | Input message | Output message | Lu-declared effects | Domain obligations |
|---|---|---|---|---|
| `nvp.film.project.read` | ProjectReadRequest | ProjectReadResult | READ_WORKSPACE | Source-bound project/FilmIndex snapshot only |
| `nvp.film.scene.read` | SceneReadRequest | SceneReadResult | READ_WORKSPACE | Return stable scene/Take references, no full media in IPC |
| `nvp.film.story.propose` | StoryProposalRequest | StoryProposalResult | WRITE_WORKSPACE | Save an unapproved **proposal only**, not implicit screenplay approval |
| `nvp.film.project.commit` | ProjectCommitRequest | ProjectCommitResult | WRITE_WORKSPACE | Explicit original user-turn grant **and** NVP creator/revision approval |
| `nvp.film.render.shot` | RenderShotRequest | RenderShotResult | EXECUTE + WRITE_WORKSPACE | NVP protected native worker, resource admission, picture-derived only |
| `nvp.film.picture.review.read` | PictureReviewReadRequest | PictureReviewReadResult | READ_WORKSPACE | Source hash and pending metadata; decrypted picture in trusted UI only |
| `nvp.film.picture.review.decide` | PictureReviewDecisionRequest | PictureReviewDecisionResult | WRITE_WORKSPACE | **Native authenticated filmmaker event**; never a model-authored approve/reject |
| `nvp.film.edit.export` | FilmExportRequest | FilmExportResult | EXECUTE + WRITE_WORKSPACE | Source-locked edit, original PCM, approved export profile, host journal |

For each input/output message above, full `type_url` is `type.googleapis.com/nvp.film.v1.<MessageName>`. All eight descriptors are provisional and inert until source-registered in Lu's existing NativeToolRegistry/effect bridge. Large Story Bible, USD, footage, picture, timeline and PCM are passed via host-resolved scoped `ObjectRef` separately; no raw filesystem/media/executable/token in `TypedValue`.

## Existing NVP source and migration findings

- `backend/nvp_lu_workspace.py` is a **development-only fake-host film prompting seam**. Its historical `jan_alt` bridge reference is not current Lu source evidence. Reuse film-specific logic only behind the new Lu registration and handler.
- `backend/nvp_lu_alpha_contract.py` pins historical internal Lu alpha `lu.v1` inference status; it does **not** prove an external IPC model-control API.
- `backend/nvp_lu_status_socket.py` and `backend/nvp_lu_status_wire.py` carry bounded **custom JSON/HMAC** over a test AF_UNIX path, not Lu's `lu.workspace.v0` Protobuf. Keep them isolated and never silently treat them as production or a fallback when enrollment fails.
- `backend/nvp_post01f_installed_receipt_transport.py` and NVP filmmaker review host bridges concern NVP's **separate SCM signing/creator authority**. Lu gateway enrollment never substitutes for creator signoff or original-Take/PCM immutability.
- The Windows NVP alpha must remain usable without Lu. Lu-connected mode is optional and **default-off** pending installed authentication. Existing NVP OS-native production worker custody remains distinct from Lu's model/tool custody.

## Next 01A acceptance gates and blockers

1. **Source pin gate:** independently fetch/review the exact five Lu modules and verify their SHA, plus 1.0 wire contract; no blind import of Lu beta/master or historical Jan IPC.
2. **Schema gate:** run actual `protoc`/prost compile for NVP-owned messages with Lu source pinned, reflect their descriptors, validate URLs/effects/field bounds and source ownership, unknown fields and version mismatch; **not yet executed**.
3. **Registry gate:** get Lu Core's reviewed registration and native `ToolEffect` mapping for each capability. Split effect classes rather than bypass or label execution as read. Production endpoint disabled until then.
4. **Security gate:** independent protected installed Windows NVP publisher/manifest/credential broker and Lu Core positive peer session. Lu draft PR #244 and a signed PowerShell surrogate do not qualify an installed NVP app. Linux UDS source design preserved; physical Linux acceptance deferred by owner.
5. **Integration gate:** approved project read, creator-gated proposal commit, render request/receipt, encrypted filmmaker read/decision, original audio and crash/replay evidence using actual user-origin and exact source revisions.
6. **Roadmap:** finish `NVP-INT-LU-01A`, continue **01B–01H** while avoiding overlapping CI, then complete mandatory **NVP-STAB-01A–F** before final security, installed acceptance and installer release gates.

**Execution policy:** one existing PR #161, branch `nvp/mainline-convergence-20261113`. Roadmap commit `8e122669809df9ac912cfe053dcf4e08d28d023c` was staged off NVP `efb6ed67e551` while its CI remained active. This 01A candidate must remain unreferenced until the current CI cohort finishes; then perform at most one independently reviewed **non-forced** fast-forward of the single branch. This source-only document and candidate schema are NOT native acceptance.
