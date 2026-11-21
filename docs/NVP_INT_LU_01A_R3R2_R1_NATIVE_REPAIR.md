# NVP-INT-LU-01A-R3-R2-R1 — original native compiler failure repairs (2026-11-21)

**Source and scope:** NVP only, existing PR #161. The original source publication `f59d91bc5007adc38d355ae50b3a51c6b874d3e5` is a single fast-forward from the accepted predecessor. Its new native [GitHub Actions run #44919663798](https://github.com/vjmichael/nvp_offline_film/actions/runs/44919663798) produced two **FAILED** jobs. Do not claim native Windows/Linux PASS. Other original film CI at this SHA remains separately active and must finish before a new source update.

## Confirmed original native failures (not simulated)

1. **Ubuntu 24.04 Rust/prost:** the exact Lu workspace.proto was compiled and the NVP crate reached native test compilation, but `rustc` E0716 at `src/lib.rs:282,296,307,318` rejected four references to `&key_and_package()` held across `tokio::join!`. **Source bug, not a Lu Core incompatibility.** Repair: bind each `VerifiedEnrollment` to a local variable whose lifetime covers the join; add static regression. There is no evidence yet that the Rust tests execute successfully after that compile repair.
2. **Windows 2022 Rust/prost:** first-pass Cargo dependency resolution worked, but `build.rs` computed the Git blob hash over checked-out **CRLF** bytes. It observed `7f94d8fa48322b361d399b8b182ff6c4a629f5fa` instead of Lu's canonical Git blob `4e01d921197fb1c58c99958479b1cede36e13c9a`, although the exact Lu Git commit was pinned and the source contract itself had not changed. Repair: canonicalize CRLF→LF **only for Git blob verification**, keeping exact committed SHA and schema blob pin plus worktree-diff check. **No hash-pinning relaxation or unsigned fallback.** Windows never reached the NVP native Rust test compiler nor actual Win32 pipe fixture in this original run.

## Dependency lock provenance

Both native runners generated and uploaded separate first-pass `Cargo.lock` artifacts before failure. Their full lockfiles were fetched and independently compared bytewise: **identical 15,171 bytes; SHA-256 `6bf5cfc5c6e2403002bb020fa296e8bb677b0f3091d0989f3cb03da6e914bf73`**. Review of the resolved lock: format 4, one local NVP crate, 65 registry packages, each with a 64-hex checksum, zero Git or unknown package sources. Important direct versions: prost/prost-build 0.14.6, Tokio 1.54.1, protoc-bin-vendored 3.3.0, getrandom 0.2.17 and sha2 0.10.9. The exact bytewise-matched lock is now included in NVP's source; the successor workflow no longer calls `cargo generate-lockfile`, instead it fetches and tests **only locked dependencies**. This is a source reproducibility measure, **not** production release signing or a security audit of all upstream dependency source.

## Local negative + source qualifications after repair

- Debian GNU/Linux 13: **84 Python tests executed, 83 PASS, one Windows-native test SKIPPED**, zero failure. Actual separate-process Linux SO_PEERCRED fixture Health/denials still pass.
- Native C++ `protoc` independently compiled NVP domain schema 16 messages/one enum/no services; no genuine Rust toolchain exists locally.
- Rust source correction is based on original compiler logs, **not** a successful post-fix Rust compiler run. Windows `build.rs` correction is source-tested, **not** a native post-fix run. No genuine installed signed NVP↔Lu Health, no tool/effect grants, no Core modification.

## Next acceptance and repository guard

Keep the corrected source in a **prepared unreferenced single-child successor** until all original CI workflows at `f59d91bc` are terminal. Then perform one reviewed non-forced update on existing draft PR #161 and inspect the native original Windows + Linux run at that exact successor SHA, including actual `cargo test --locked --offline --all-targets` and genuine Windows OS named-pipe fixture. Debian Rust qualification still needs a native Rust toolchain and approved pinned Lu checkout on Debian, not merely Ubuntu. Upstream Lu issues #245 (Health), #246 (NVP effect/reference bridge), #247 (signed NVP enrollment) remain blocked for installed positive acceptance.
