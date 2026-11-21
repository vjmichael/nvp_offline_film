# NVP-INT-LU-01A-R3 — NVP-owned IPC client source and Lu Core handoff

**Date:** 2026-11-21. **Status: NVP SOURCE-ONLY / LOCAL TESTED, NOT native Rust-built, signed, installed or enrolled.** No Lu Core file, branch or PR was edited for this NVP task. NVP's draft PR #161 remains subject to the previous exact-SHA CI batch and non-forced promotion rule.

## Exact upstream inspection

Lu `vjmichael/Lu-AI-GUI`, draft IPC PR #244 head `6932ace156ddaae728a2967660fc37aa986471ae` when reviewed:

- `src-tauri/lu-core/proto/lu/workspace/v0/workspace.proto` Git blob `4e01d921197fb1c58c99958479b1cede36e13c9a`. `lu.workspace.v0`, wire major/minor 1.0. Protobuf frame <=256 KiB; typed data <=64 KiB; <=16 object refs; stream credit <=64.
- `src-tauri/lu-core/src/workspace_ipc.rs` Git blob `06c47e8e83ad835711dca3ed0dc9851bcf8aae05`; strict validation/source-only, no authority from Protobuf itself.
- `src-tauri/lu-core/src/workspace_ipc_transport.rs` Git blob `95df0bbba2000457c1a9725c6446609c5ba4191e`; 4-byte big-endian length, HMAC challenge/response, host-enrolled OS peer lifetime, native Windows pipe and Linux UDS.
- `src-tauri/lu-core/src/workspace_ipc_core_host.rs` Git blob `d2c45ed1a19834f4a3284bd65dd22a670c0acc2d`; real host native tool dispatch checks exact original user turn, `NativeToolRegistry`, `TrustedCoreInputVerifier`, `ConversationAuthority`, `EffectJournal`, one capability version (1) and 4 concurrent slots. **Current `input_refs` with any entries are refused** because Core's scoped ObjectRef resolver is not yet implemented. Current `ToolDescriptor` has one `ToolEffect` per tool, not compound EXECUTE+WRITE.
- Lu signed installed NVP publisher, credential distribution, Core health server and post-handshake native signer verification have **not** been witnessed in this local project environment. Lu's CI outcomes do not substitute for NVP installed acceptance.
- **Later refresh:** Lu PR #244 advanced to `9f43d078aa5e979de0ff72ca4c19e8c5829572af`; independent re-fetch confirms the **workspace.proto and workspace_ipc.rs Git blobs are unchanged**. The host gate gained Windows Job/journal work (`workspace_ipc_core_host.rs` now blob `3214635a20825e0d7fc8e0a78c81180358b0d217`), but the current gate still rejects nonempty `input_refs`. This does not clear #245 or #246. R3 remains pinned to reviewed source; re-pin before installed acceptance.

## NVP-only changes

1. `native/nvp_lu_ipc_client/` — NVP Rust `prost` consumer using upstream `workspace.proto` from an independently checked out Lu source, with Git-blob pin in `build.rs`. It uses Lu's versioned Protobuf, framed read-only Health request/response and domain-separated HMAC transcript; it cannot start an endpoint, register tools or load models. The only public production entry **returns MissingInstaller** until an accepted signed native broker binds the exact pipe handle and enrolled secret. Rust/prost build and native Windows tests are **OPEN** because neither Rust toolchain nor an installed signed Core endpoint was available in this environment. `Cargo.toml` aligns `prost`/`prost-build` 0.14 with Lu's source; Rust code is uncompiled and not an acceptance receipt.
2. `backend/nvp_lu_win32_client.py` — NVP Win32 named-pipe source for fixed HKLM installer-owned endpoint/pinned image and service SID observation; actual native `GetNamedPipeServerProcessId`, process creation time, OS token SID and preliminary image SHA; bounded overlapped Win32 `ReadFile`/`WriteFile` with cancellation/draining; local/identification-only SQOS and no generic TCP/HTTP/JSON fallback. **Observation is not signed Windows admission**: Authenticode signer/revocation/file identity/ACL and protected credential provision must be verified by a separately approved native broker. No bytes are sent by the observer, and `connect_authenticated_read_only()` always refuses. The HKLM path is a provisional NVP-side installer schema, not a currently provisioned Lu registry record.
3. `backend/nvp_lu_readonly_policy.py` and `contracts/nvp/film/v1/capabilities.json` — strict 8-capability v1 scope, explicit version 1, 3 eligible read-only candidates, 2 blocked compound-effect render/export operations, no claimed registration or user-turn grant. Any `input_refs` is refused while Lu's resolver is absent; a caller's `installed_enrollment_proven=True` is not trust.
4. Retain existing R2 NVP `nvp_lu_ipc_v0.py` synthetic HMAC Health fixture, native NVP Protobuf compilation and test-only Linux `SO_PEERCRED`; never activate the historical `nvp_lu_status_socket.py` JSON source as a Lu Protobuf fallback.

## Direct Lu Core issues, not code edits

- [#245 — LU-IPC-CORE-HEALTH-01](https://github.com/vjmichael/Lu-AI-GUI/issues/245): already-open Core health dispatcher and supported installed endpoint/enrollment contract, originally filed for IDE; NVP reuses the same Core capability and must not duplicate it.
- [#246 — LU-IPC-NVP-01](https://github.com/vjmichael/Lu-AI-GUI/issues/246): NVP-specific ObjectRef host resolver and multi-effect registration/effect enforcement; concrete input and negative acceptance provided.
- Until both are resolved and independently accepted, **NVP Core-provided film capabilities and positive installed Health remain blocked**. NVP can finish its read-only client and source tests independently.

## Local qualification and limits

- Native Protobuf compiler: `/opt/pyvenv/lib/python3.13/site-packages/torch/bin/protoc` (`libprotoc 3.13.0`) successfully compiled NVP's film schema. **16 messages, 1 enum, 8 candidate capabilities, 0 services**, no unauthorized extra service. Descriptor SHA-256 in `receipts/NATIVE_PROTOC_R3.json`.
- Focused NVP source/fixtures: `PYTHONPATH=. python -m unittest discover -s tests -p 'test_nvp_int_lu_01a_r*.py' -v` — **63 PASS / 0 FAIL** after fixing the explicit capability-version omission and correcting a false-positive source assertion. Real Linux `SO_PEERCRED` tests from earlier R1 and mocked Windows negative tests are included; Windows native APIs were **not executed on Windows**.
- Python `compileall` passes for backend/tools/tests. Original whole NVP regressions, exact NVP source checkout, native Windows MSVC, Rust/prost executable build and genuine installed Windows Lu Health session **not run**.

## Next NVP-only tasks

- **R3-R1:** compile/qualify NVP Rust prost client on genuine Windows + Linux native toolchains against pinned Lu checkout; repair only confirmed source errors; independently compile Win32 pipe module, test user/package negative and cancellation/deadlines. Keep installed admission fail-closed until actual broker and issue #245 Core Health completion.
- **01B:** integrate one read-only Health session in the first-party native NVP host with true signed Lu process pin, independently audited installed NVP credential acquisition, per-frame process lease, restart/revoke; no caller-selected endpoint, no UI/model-controlled keys.
- **01D:** keep three read-only NVP film catalog declarations inert pending Lu Core registered decoder and original-user-turn authority. Render/export cannot be relabeled as READ to pass registry restrictions. Lu Core object refs need #246.
- Continue mandatory whole-NVP STAB-01A–F later. Never merge, start another CI batch, or claim installed success while the original PR #161 exact-SHA cohort remains active.
