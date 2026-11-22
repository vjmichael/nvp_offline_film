# NVP-INT-LU-01A-R3-R1 — NVP client native qualification and Lu Core handoff

**Date:** 2026-11-21. **Current status: SOURCE-ONLY LOCAL QUALIFICATION, NATIVE RUST/PROST NOT RUN, WINDOWS INSTALLED AUTHENTICATED HEALTH NOT RUN.** NVP changes only. No Lu Core source or PR mutated; Lu-only integration gaps filed as issues.

## Reviewed source and ownership

- NVP draft PR #161 original checked head `efb6ed67e5511879a9138315577842dce65f9151` remained unchanged while its original 45-workflow CI cohort was active. Consolidated documentation/01A candidate `15b821803a05d59f7cc8e4e2dffad926f728fd1c` is an *unreferenced* single-parent commit, not published to its branch.
- Lu Core draft PR #244 latest reviewed head `9f43d078aa5e979de0ff72ca4c19e8c5829572af`, upstream `lu.workspace.v0` proto Git blob `4e01d921197fb1c58c99958479b1cede36e13c9a`; `WIRE_MAJOR=1`, `WIRE_MINOR=0`, frame 256 KiB, typed payload 64 KiB, max 16 ObjectRefs, max 64 stream credits. Protobuf schema/codec still unchanged; Core host/transport have advanced independently.
- NVP owns its own `native/nvp_lu_ipc_client` crate, Protobuf film type messages and 8-capability catalog. Lu owns Core dispatcher, signed-installed package enrollment, original-user-turn grants, model/tool registry, credential broker and effect journal. NVP does not copy Lu's installed server or weaken NVP creator consent.
- Upstream [#245](https://github.com/vjmichael/Lu-AI-GUI/issues/245) is Core Health dispatcher, [#246](https://github.com/vjmichael/Lu-AI-GUI/issues/246) ObjectRef/multi-effect admission, and NEW [#247](https://github.com/vjmichael/Lu-AI-GUI/issues/247) separately signed `nvp.film` package enrollment and protected NVP credential handoff. Current Lu source hardcodes `lu.ide` enrollment/credential paths; **do not present an NVP client as `lu.ide`**.

## NVP-only work in R3-R1

1. **Rust client:** added five Rust source-only executable test cases for the existing `exchange_health` logic (matched Lu-formatted Hello→AuthChallenge→AuthProof→Welcome→Health; forged welcome, forged Health identity, wrong HMAC, invalid session/wire version). `src/lib.rs` still returns `MissingInstaller` from its public native entrypoint. Tests were written but **NOT compiled or run by Rust** because no Rust/cargo toolchain is installed or fetchable in this authoring environment.
2. **Win32 process ownership:** the existing observation-only local-pipe client now retains the exact queried OS process handle for the lifetime of the pipe observation and checks PID, session, creation FILETIME and process-alive before any possible future broker handoff. PID-only snapshots were insufficient to prevent identity gaps across restarts. No software-generated package grant, caller-provided HMAC or network/JSON fallback was added. Existing `connect_authenticated_read_only` **still refuses all calls**.
3. **Negative regression:** added real Python tests and Windows Win32 API test doubles for process handle retention, close, PID substitution, session substitution, exited process and no observed-only Health bypass. These are **fixtures, not execution on Windows**.
4. **Native qualification scripts:** shell and PowerShell exact-source gates check complete Lu checkout SHA and require an independently generated/reviewed `Cargo.lock` before `cargo test --locked --offline`. This R3-R1 candidate intentionally contains **no invented Cargo.lock**. They fail with explicit BLOCKED on absent toolchain/lock and never infer Windows installed acceptance from a source compile.
5. **Domain Protobuf:** independently invoked the installed C++ `protoc` (`3.13.0`) on NVP's 16-message schema with zero services, with runtime descriptor verification; not a Rust/prost or Lu native compilation substitute.

## Current blocking gates

- **Native Rust/prost source compilation**: no `cargo` / `rustc`, no independently reviewed offline dependency lock and no complete native Lu source checkout in this environment. **Cannot report it as PASS.** Use a complete locally pinned Lu checkout and approved Cargo toolchain, generate/review a lockfile, then run the included exact-source scripts on Debian and Windows.
- **Actual Windows named-pipe test**: no Windows toolchain, installed Lu Core server/broker, signed NVP package or real Win32 test runner here. Mocked Win32 tests can only support preliminary design scrutiny.
- **Actual read-only Health**: Core #245 and signed NVP enrollment #247 remain required. NVP client's public entry deliberately refuses before a Hello. NVP must prove host user/credential/package/process per-session; even a passing Health reply does not authorize a model or filmmaking effect.
- **Other film capability integration**: Core #246 must resolve ObjectRef and multiple effect safeguards; NVP's existing catalog remains UNREGISTERED. No render/export/creator-review API enabled over IPC.

**Next NVP-only task:** R3-R2 native unchanged-source Rust/prost qualification on a real complete Windows and/or Debian checkout; correct actual compile faults; incorporate the Core-approved NVP credential/Health handoff when available, while keeping installed production disabled otherwise. Once PR #161's current original CI batch is fully terminal, only one reviewed non-forced NVP branch update and one consolidated acceptance batch may proceed. Full-codebase NVP-STAB-01 remains downstream of integration.
