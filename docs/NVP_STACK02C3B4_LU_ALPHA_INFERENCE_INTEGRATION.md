# NVP STACK-02C3B4 — Lu alpha as a verified inference reference

**Scope:** 2026-11-03 cross-project contract reconnaissance and read-only NVP observational adapter. The developer used the user's accepted Lu alpha code as a reference; it did **not** obtain or run an installed Windows alpha binary or load a real GGUF in NVP. This is not an approved Lu model-control integration.

## Sources reconciled

- Independent desktop: private vjmichael/Lu-AI-GUI source commit ac015280e4594b7cb5fb730a240b8d2a8a819975 (the main source revision inspected; its identity with a particular installed 0.1.0-alpha.2 executable is **not independently proven**).
- Lu Core canonical Protobuf: src-tauri/lu-core/proto/lu/v1/core.proto, Git blob 6495ad09b4403dd8f6c714d3358d31da2a43e63a.
- Lu Tauri desktop host: lu-desktop/src-tauri/src/lib.rs, Git blob fb93dc2be3778cddbd9b502dec3bf5bd45656095.
- Lu persistent GGUF backend: src-tauri/lu-core/src/persistent_llama_backend.rs, Git blob ea28e818b1a62538ab3f1afc10c7b588f9ff0e1a.
- Lu Core genuine two-turn smoke: src-tauri/lu-core/examples/persistent_llama_smoke.rs, Git blob 79a31fed778c6feeb1a05d717f3f942c3949af69.
- Experimental AF_UNIX transport lives in vjmichael/jan_alt at lu/ipc-common-af-unix-20261031, commit 75f79fa45ca4d7fd217ada7f1562a0ca92ff0a92. It is **not** included in the accepted independent Lu desktop source.

## What Lu actually exposes

The alpha's Tauri desktop declares lu_status, lu_list_models, lu_load_model, lu_unload_model, lu_generate and lu_cancel as internal host commands. They are not external NVP APIs. The internal llama-server HTTP endpoint uses a host-chosen ephemeral loopback port plus a host-generated 256-bit key. Connecting to the private server without a Lu host-mediated grant would defeat ownership and authorization. NVP must never scrape the key, enumerate ephemeral ports or directly call Lu's internal Tauri commands from outside the WebView.

The AF_UNIX carrier was demonstrated on real Linux and Windows x64 in a separate jan_alt prototype. It frames Lu ToolCall/ToolReply Protobuf, with native socket testing and selected host-scope/worker checks. It was not shipped in alpha. It does not expose the inference load/generate/cancel/unload host methods, and existing socket tests do not certify cross-app caller identity or production authorization. A socket path alone is never a capability.

Lu Core itself DOES expose a supported internal inference supervisor and an explicit native developer example, persistent_llama_smoke, which requires a pinned llama-server and a caller-selected real GGUF. It performs two real generations through one persistent engine process and unloads after the test. Its current Windows persistent backend requests 99 GPU layers; executing this blindly on a large model risks VRAM/host pressure. NVP must require a verified small model, native user consent, platform-specific resource estimates and actual OS containment before an independent real-model acceptance.

## What was implemented in NVP

- backend/nvp_lu_alpha_contract.py: pins the four Lu source Git blobs, rejects altered/missing/symlinked source, and produces an explicit source-only provenance report. Windows Git CRLF materialization is normalized before the canonical Git hash check. It never starts a process or opens a socket.
- Native LuRuntimeView contract: validates exact internal Tauri status fields and plausible Lu host-issued session, generation and model refs; treats unknown/malformed states as unsafe.
- PassiveLuStatusObserver: accepts only an injected, trusted native Lu host status callback; registers a read-only external activity entry in NVP's existing SQLite ledger. No model load/unload, no NVP reservation, no invented progress %, no host claim of model ownership, no automatic release after Lu disappears. The real external native host callback remains **unwired** because the alpha has no published cross-app API.
- tools/nvp_lu_alpha_source_probe.py: developer-only, source-checkout readback with JSON evidence; does not execute the alpha binary.
- Windows/Linux NVP tests cover canonical source identity, mutation and symlink refusal, read-only status updates, unknown phases and lack of memory reservations or model-control authority.
- A separate branch in the Lu repo, lu/nvp-independent-inference-contract-20261103, adds a source-evidence fixture and CI to run Lu's own Rust inference lifecycle, canonical Protobuf and host resource-authority tests. The accepted Lu main tree is unchanged. One stale test initializer lacked a newly required history field; it was repaired in the isolated CI branch.

## Next actual integration gates

1. Create a **Lu-owned, opt-in host adapter** that can expose verified, authenticated and versioned status/AI inference to the NVP Film DLC. Prefer a native host-provided capability over a scrapeable loopback key or a guessed AF_UNIX path. The adapter must independently bind an active user-approved NVP project/turn and model/session.
2. Align the Lu host's source/model identity and resource claims with NVP's immutable approved task record and RAM/VRAM resource guardian; account for a model that Lu already owns as external usage, not an NVP-owned model.
3. Run a **real GGUF** with the Lu smoke example on an appropriately contained, resource-bounded host; publish the exact engine/source/model hashes, two-generation same-PID proof, latency/peak memory and independent OS cleanup evidence. An existing user installation is not accessible from GitHub CI without an explicit artifact/runner.
4. Do not promote Windows GPU support until the physical AMD Radeon simultaneous Blender+Lu+NVP headroom and failure tests are accepted.
5. Keep the experimental AF_UNIX carrier separate until native Windows endpoint ACL, caller authentication, host-bridge dispatch, cancellation, process-tree cleanup and source promotion gates pass.

The user accepted 0.1.0-alpha.2 as a **functional development baseline** following physical Windows testing. None of the new NVP interoperability code is part of that installer.

## Related evidence

- Accepted Lu functional alpha design: Lu-AI-GUI docs/LU_ALPHA_01_ACCEPTED_BASELINE_20261103.md.
- AF_UNIX prototype design/limits: jan_alt docs/lu/ipc/native-af-unix-implementation-2026-10-31.md and docs/lu/ipc/ipc-lcx-acceptance-ledger-2026-10-31.md.
- Lu isolated native source-contract workflow: lu/nvp-independent-inference-contract-20261103.


## B4 independent CI and SQLite initialization hardening

NVP B4 contract acceptance [GitHub run 41781810609](https://github.com/vjmichael/nvp_offline_film/actions/runs/41781810609): 2/2 native Windows/Linux jobs passed, each executing 8 Lu source/passive-status tests, 2 new resource-ledger first-open contention tests, 10 existing resource-governor tests, and 17 B3 estimate/recovery tests (37 per OS). The new concurrency fixture started SIX independent processes against one fresh profile database and verified journal mode WAL, schema completeness, and that reopening cannot silently release an ACTIVE model reservation.

A preceding Linux run independently exposed an actual intermittent database is locked error during competing resource-ledger construction. The ledger now checks its existing journal mode before modifying WAL, then executes all CREATE TABLE/INDEX statements under one serialized BEGIN IMMEDIATE writer transaction, with a bounded retry exclusively for SQLITE_BUSY. It no longer uses executescript, which would implicitly commit and release the initialization writer lease. This is a real resource-guardian reliability fix, separate from Lu IPC authorization.

Lu independent inference CI [run 41781449832](https://github.com/vjmichael/Lu-AI-GUI/actions/runs/41781449832) passed 8/8 real Rust Core tests on Linux (1 lifecycle, 4 Protobuf, 3 host resource authority). Native Windows source hash checks passed but Lu's checked-in Core did NOT compile: persistent_llama_backend.rs calls Job::assign_and_resume_suspended, while the checked-in lu-win-worker-job crate defines only Job::assign. This is a SOURCE SYNC / containment API blocker in the Lu repo, not a failed installed 0.1.0-alpha.2 physical test. NVP must NOT repair it by unsuspended process launch. The Lu repo has an isolated draft PR documenting the blocker and leaving the stable baseline unchanged.

## Cross-project issue tracking (2026-11-03)

**Open Lu defect: [Lu-AI-GUI issue #7 — missing Windows `Job::assign_and_resume_suspended`](https://github.com/vjmichael/Lu-AI-GUI/issues/7).** The checked-in Rust `PersistentLlamaBackend` requests suspended creation and invokes a worker-job method that does not exist in the checked-in library. Native Windows Lu Core CI fails E0599; Linux passes. This is a source-to-artifact reconciliation and process-containment blocker, **not** evidence that the owner's accepted installed 0.1.0-alpha.2 failed. Do not replace with unsuspended startup: preserve assignment to the Job before the child can execute, and independently prove cleanup. Acceptance and reproduction are recorded in the issue. NVP's interop bridge must remain read-only/no-control until this Windows boundary is fixed and tested.
