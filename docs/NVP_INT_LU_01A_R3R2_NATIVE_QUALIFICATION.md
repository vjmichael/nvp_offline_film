# NVP-INT-LU-01A-R3-R2 — NVP-only genuine native qualification handoff

**2026-11-21 · Status:** NVP source/fixtures locally verified; true **Rust/prost Windows + Debian native compilation NOT yet obtained**. This document explicitly separates actual Debian 13 kernel/OS fixtures from Rust compilation, native Windows execution, and genuine installed Lu Core. It does not modify Lu Core and does not turn on production IPC.

## Reviewed source and integration boundary

- NVP original PR #161 head at this development baseline: `efb6ed67e5511879a9138315577842dce65f9151`. Its original 45-workflow cohort has completed **45 PASS, zero failures**. The earlier reviewed roadmap+01A documentation is staged as unreferenced candidate `15b821803a05d59f7cc8e4e2dffad926f728fd1c`; merge only one reviewed non-forced successor into the existing branch, not another PR or CI stack.
- Lu Core draft PR #244 exact **source pin** `9f43d078aa5e979de0ff72ca4c19e8c5829572af`, `lu.workspace.v0` Protobuf blob `4e01d921197fb1c58c99958479b1cede36e13c9a` (wire 1.0, 256 KiB envelope, 64 KiB typed value, 16 ObjectRefs, 64 stream credits). Lu PR #244 moved forward to `ea6e35e6a10a0754e166eb4c34a794eb0c9b5551` during work; its Lu Protobuf blob remains identical. Do not re-pin protected enrollment/host logic automatically just because Lu advances.
- Lu Core still has an IDE-specific installed enrollment/credential prefix; no source-grounded installed NVP `nvp.film` enrollment or accepted host Health dispatcher. Core-side dependencies are GitHub [#245](https://github.com/vjmichael/Lu-AI-GUI/issues/245) (Health), [#246](https://github.com/vjmichael/Lu-AI-GUI/issues/246) (scoped ObjectRef and effects), [#247](https://github.com/vjmichael/Lu-AI-GUI/issues/247) (signed NVP enrollment/credential handoff). **Do not edit Core in NVP work.**

## NVP R3-R2 source work

1. **Credential secrecy:** Python test-only `EnrolledClient` excludes its 32-byte secret from `repr`; Rust `VerifiedEnrollment` no longer derives a key-printing `Debug`, and uses an explicitly redacted `Debug` plus a native Rust regression test. This repairs genuine diagnostic key-exposure risk; test-only credentials remain nonproduction.
2. **Windows trust observation:** NVP's `ObservedWindowsLuPipe` supports deterministic context-managed close; the observation refuses a server that exits or changes its observed PID/session/process generation **before returning a process lease**. Existing per-frame rescan continues to refuse changed/stale peer. This is OS-process observation only, not installed publisher/credential proof.
3. **Genuine Debian 13 OS test, fixture only:** real **separate OS subprocess** Unix-domain socket with 0700 directory, 0600 endpoint and kernel `SO_PEERCRED`; NVP sends exactly bounded Lu 1.0 Hello/proof/Health frames, verifies a source-only Core fixture's HMAC and response; wrong key, forged host MAC, mismatched health session, and forged kernel-PID policy are refused. It is **not** real Lu Core and grants no tool, model or creator effect.
4. **Windows native test prepared:** a Windows-only independently spawned test process hosts an actual OS named pipe; NVP tests the real overlapped Win32 client, process handle/PID/SID observation and byte exchange. **Not executed here** (Linux environment); its test-only injected pin does not qualify a signed installed Lu package.
5. **Native qualifier:** stricter exact Lu checkout+schema Git blob checks, offline/locked Rust dependency refusal scripts, native Windows PowerShell variant, and a scoped GitHub Actions workflow for first-pass Windows 2022 + Ubuntu 24.04 Rust/prost compilation. CI workflow explicitly uploads its newly generated Cargo.lock for independent review; an unreviewed first-pass lock is not final release custody. No Docker. Actual Debian Rust remains separate from Ubuntu runner qualification.
6. **Original domain schema:** native C++ `protoc` independently compiles NVP's 16 film messages/one enum/no services; the catalog has eight **draft unregistered** `nvp.film.*` capabilities. Multi-effect render/export and ObjectRef invoke paths stay disabled pending Lu #246.

## Local qualification on genuine Debian GNU/Linux 13

- `python -m compileall -q backend tools tests` → **PASS**.
- `python -m unittest discover -s tests -p 'test_nvp_int_lu_01a_r*.py' -q` → **82 tests run, 81 PASS, 1 Windows-only native test SKIPPED**, zero failures. Of the passing tests, five execute real kernel UDS interprocess fixtures. Linux source tests are not Windows tests and do not prove Lu's installed server.
- C++ `protoc` `libprotoc 3.13.0`: **PASS**, schema descriptor SHA-256 `efbb5fb8c835f04cabf3fe4dceb0437a403c54a075d4de04807993488d238b84`.
- Bash acceptance preflight: expected **BLOCKED 20** without an exact Lu Git checkout. `rustc` and `cargo` are absent; no complete Lu checkout or reviewed NVP Cargo.lock. Do not claim Rust/prost native PASS from Python source scans or C++ Protobuf descriptors.

## Remaining native acceptance gates

| Gate | Real evidence needed | Current state |
| --- | --- | --- |
| Debian Rust/prost | Debian x86_64, exact Lu checkout, actual cargo/rustc, reviewed Cargo.lock, `cargo test --locked --offline --all-targets` | **BLOCKED** in current Debian container (toolchain/lock/checkout unavailable) |
| Windows Rust/prost | Windows x64 MSVC native cargo/rustc, exact Lu checkout and locked dependencies, native tests | **Not run locally**; scoped runner qualification prepared |
| Actual Win32 client | Real Windows GetNamedPipeServerProcessId, server creation/session/token, overlapped I/O, close/restart, process exit and pin-mismatch negatives | **Windows-only test authored, not run here** |
| Signed NVP / Lu Core Health | Genuinely installed separate signed NVP and Lu processes, OS-attested publisher/package/credential/session, Core-owned Health dispatcher; revocation/crash/restart | **Upstream Lu #245/#247 still open.** NVP production access deliberately refuses |
| Nonread effects | Per-turn authority, NVP original-creator approval, ObjectRef rights and multieffect registry binding | **Upstream #246 / NVP integration open** |

**Conservative next task:** obtain first-pass native Windows runner and Debian Rust toolchain results, fix actual compiler or native OS defects (not fixture-only approximations), capture reviewed Cargo.lock and a same-source acceptance receipt, then integrate NVP-side host Health only after Core's accepted broker handoff. Continue existing single draft PR #161 and batch CI; no new branches/PRs, no force-push, no silent installer privilege or fake acceptance.
