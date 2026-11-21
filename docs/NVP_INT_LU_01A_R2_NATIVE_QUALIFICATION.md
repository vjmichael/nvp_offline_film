# NVP-INT-LU-01A-R2 — Native descriptor qualification and guarded read-only IPC candidate

**2026-11-21 • Local source-only development; not installed/runtime acceptance.**

## Exact external source and scope

- NVP: existing draft PR #161, `nvp/mainline-convergence-20261113` at `efb6ed67e5511879a9138315577842dce65f9151`. Previous roadmap/01A draft candidate `15b821803a05d59f7cc8e4e2dffad926f728fd1c` remains unreferenced while 45-workflow CI batch completes. This standalone R2 package has **not** been merged or pushed to that branch.
- Lu: `vjmichael/Lu-AI-GUI` draft PR #244 at `6932ace156ddaae728a2967660fc37aa986471ae`. This new head contains more Lu Core host authorization work than the R1 snapshot. `workspace.proto` blob `4e01d921197fb1c58c99958479b1cede36e13c9a`, validator `workspace_ipc.rs` blob `06c47e8e83ad835711dca3ed0dc9851bcf8aae05` remain unchanged; transport at this head is `95df0bbba2000457c1a9725c6446609c5ba4191e`, and `workspace_ipc_core_host.rs` blob `d2c45ed1a19834f4a3284bd65dd22a670c0acc2d`.
- Full Lu source/compiled Rust bindings were **not** reproduced in this environment. Reinspect current Lu PR before future implementation/acceptance and never copy source-only evidence into an installed claim.

## Native compiler and runtime evidence

`/opt/pyvenv/lib/python3.13/site-packages/torch/bin/protoc` — native executable `libprotoc 3.13.0` — compiled `contracts/nvp/film/v1/nvp_film_v1.proto` into `receipts/native_contract.pb` (a real `FileDescriptorSet`). The independent Python runtime parsed the compiler's descriptor, found exactly 16 messages, one enum and zero RPC services, cross-compared all fields/tag numbers/types against the R1 restrictive source parser, and executed deterministic Protobuf wire roundtrips. `tools/nvp_native_protoc_qualification.py` reproduces the native compiler invocation and machine-readable receipt.

**Real limitation:** Protoc 3.13-generated Python `*_pb2.py` files are incompatible with this environment's newer Protobuf Python runtime (direct descriptor construction was refused). Therefore the working R2 runtime exercises the *native-compiled descriptor set* through the standard `DescriptorPool`/`message_factory`, not old generated Python bindings. The full, original **Lu** `workspace.proto` has **not** been compiled here; Rust prost/Cargo compilation and cross-language wire compatibility remain open.

## Capability registration reconciliation — new blockers found

Lu `NativeToolRegistry`'s `ToolDescriptor` currently contains **one** `ToolEffect`, not multiple. In the draft `CapabilityDescriptor` there can be a declared `repeated EffectClass`, but the original/native registry bridge does not thereby gain multi-effect enforcement. The two candidates `nvp.film.render.shot` and `nvp.film.edit.export` declare `EXECUTE` plus `WRITE_WORKSPACE`; these remain **BLOCKED_EFFECT_BRIDGE_APPROVAL**. The proposed single native `ExecuteCode` effect must also require separately verified NVP write/creator/worker custody; it is **not** approved by this design. This is documented explicitly in `native_effect_alignment.json` rather than hiding the missing Lu effect semantics.

The newer Lu `CoreDlcHostGate` (same inspected head) binds `OriginRefs` to the original `BoundCallOrigin` and actual workspace, requires `capability_version==1`, uses a max 4 in-flight calls, rejects deadlines over 5 minutes, requires a trusted exact-input verifier and existing registered typed tool, and **currently rejects any incoming `input_refs`** until a host-owned object-reference resolver exists. NVP must not enable large media refs/remote paths or represent unsupported reference handling as accepted. Only native installed signed Windows peer sessions can create production Core DLC ingress; Linux has source-only inner gates. No NVP registration was performed.

## Native Windows IPC foundation — intentionally fail closed

- `backend/nvp_lu_windows_pipe_probe.py` validates a strictly local `\\.\pipe\lu-ipc-<32 lowercase hex>` endpoint; on actual Windows it can open the *existing* pipe without sending any Protobuf, observe the server PID with the kernel's `GetNamedPipeServerProcessId`, then close it. This PID is **not** a signer, valid package, credential or authority. Native Windows execution of the probe was not available here.
- The authentic Windows named-pipe client **cannot yet connect, authenticate or send a read-only Health request**: `open_authenticated_read_only_session` refuses all callers until actual native signed Lu/Core server process-image/publisher/credential/epoch checks and installer enrollment exist. No unsafe PID-only admission or HMAC test key bypass is introduced.
- `backend/nvp_lu_ipc_v0.py` adds Lu wire-26 `HealthReport` to the existing test-only Protobuf projection and checks a matched request/session plus exact Lu host module, connected status and epoch after a verified fixture HMAC handshake. **This is a controlled socketpair fixture; it is not Windows named-pipe or installed Lu positive acceptance.** Generic read-only Health is not permission to call effectful tools or models.

## Local test and installation limitations

- R1 baseline 32 tests retained. R2 adds 13 tests: native `protoc` against the schema and a duplicate-tag negative, exact native-tool-effect gap assertions, Windows path/unqualified peer refusal, fixture-only mutual HMAC + matched Health (positive and five denials).
- All source modules compile with Python; no actual Rust compiler, Windows SDK/MSVC, physical installed NVP/Lu app, trusted signed package or production credential broker was available.
- One original NVP CI cohort was still active: previous snapshot 44 success, 1 running CONV-12, 0 failures. No new PR, branch, CI run, service launch, film content, keys, user approvals or `main` merge from this local R2 work.

## Next tasks

1. Compile **exact Lu** `workspace.proto` and NVP schema in the approved Rust/prost workspace and compare both generated type URLs and wire bytes; reconcile old-protoc Python generator separately or use a newer pinned compiler.
2. Resolve the `ExecuteCode`+write native registry effect gap and NVP source-scoped original-user grant, and implement genuine host-owned scoped `ObjectRef` resolver before enabling references.
3. Implement installed native Windows named-pipe signed Lu server attestor (process image/publisher pinned independent of untrusted handshake), protected secret broker and per-message OS peer check; then permit **Health only** with approved test receipt. No model/effectful IPC before security acceptance.
4. Reconcile original CI batch, then publish one independently reviewed source successor to existing PR #161 without stacking CI. Update the central task ledger with these blockers and follow NVP-INT-LU-01B/01C; complete full-product STAB-01A–F before final security and installed acceptance.
