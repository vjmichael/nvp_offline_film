# W1-G first-party compiled native workers — exact-source engineering receipt

**Status: engineering source committed; real Linux/Windows compiled artifact acceptance remains OPEN until native runner logs and binaries are inspected.** No release, license grant, EFS recovery, NSIS mutation, or production-role equivalence is implied.

## 1. Real compiled first-party binaries

Five distinct C++17 executables have source entrypoints under `native/` and are compiled directly from `native/w1g_first_party_worker.cpp`, without Python child scripts, shell launch or model-selected executable paths:

| Binary/role | Real bounded operation | Does **not** yet implement |
|---|---|---|
| `original_capture` | Examine finite, immutable PCM16LE source, verify alignment, sample count, peak and SHA-256 | Device recording, native film clock and capture into immutable Take |
| `scene_render` | Render finite mathematical RGB PPM picture with actual computed lighting | Real OpenUSD/Hydra/Blender Cycles full scene rendering |
| `editorial` | Non-destructively slice an exact PCM sample interval to a derivative | NVP native scene timeline and immutable original Takes editorial |
| `audio` | Apply bounded rational PCM gain with signed sample saturation | Spatial sound, dialogue/ActorID, BWF/PCM mastering |
| `delivery` | Assemble exact picture/PCM bytes into a deterministic bounded derivative bundle | Cinema projection DCP, flattened production master or theatrical certification |

The development output explicitly returns `full_film_pipeline_accepted:false`. These workers must **not** be misrepresented as feature-complete production workers. A future production rollout needs original domain-specific implementations, independent domain verifiers and source coverage beyond these slices.

## 2. Native compilation and functional evidence

Dedicated [native compilation workflow](https://github.com/vjmichael/nvp_offline_film/actions/workflows/nvp-w1g-compiled-workers.yml) builds Linux amd64 ELF64 with GNU C++17/OS libcrypto and Windows amd64 PE32+ with actual MSVC and native Windows BCrypt. This is a genuine compiler, not a PE header fixture.

The same workflow runs `tools/nvp_w1g_native_worker_functional_acceptance.py` against the real binaries, independently checks actual output bytes and SHA-256, verifies the host-sealed `job_id`, `project_id`, `role` and plan SHA, refuses a foreign role, and verifies input immutability. On Windows these executions use original suspended/Job-assigned kernel process custody and require the actual Job to report zero live descendants. Linux builds are functional process execution only; delegated cgroup-v2 production custody remains separately unaccepted.

The acceptance fixture also copies the exact source-head native binary bytes into a **test-only** private worker bundle through the original `provision_native_workers` path and verifies unchanged SHA-256. This is not signed redistribution approval or a valid production installer.

Native build outputs include five binaries and an unsigned `build-candidate.json`; actual execution results are retained in `w1g-*-native-functional.json`. Their exact hashes must be inspected from the completed workflows; no fixed or invented digest is asserted by this document.

## 3. Physical build and independent reviews

The candidate binaries remain unapproved until an independent reviewer supplies the complete first-party worker implementation review, toolchain provenance, redistribution rights, native dynamic-library dependency inventory, and a genuine externally signed exact-byte NVP release review.

On Linux the native SHA implementation currently links to OS `libcrypto`; its runtime and legal redistribution status must be reviewed independently of the Python wheelhouse. Windows links to Windows BCrypt. No build tool may silently treat this external native dependency as one of the independently reviewed Python wheels.

The production wheelhouse must separately have its exact transitive lock, every actual wheel SHA/size and **independently signed** license/redistribution review. Current development code cannot create that real legal sign-off.

`tools/nvp_w1g_reconcile_compiled_release.py` provides a **read-only** signed-byte join between the five compiled Windows PE images, staged NSIS private worker directory, external audited installed-bundle receipt, signed exact installed-byte inventory, and separately signed exact offline wheelhouse. A missing or changed byte causes denial. Even if those signatures later pass, the tool leaves `full_native_film_role_completeness_proven:false`, `physical_efs_recovery_verified:false` and `creator_authorization_obtained:false` until separately proven.

## 4. Acceptance classification

- Five native role-specific sources and build/test harness: **IMPLEMENTED**.
- Original head Windows/Linux compiled binaries, native functional outputs and actual Job receipts: **AWAITING EXACT-HEAD RUNNER RESULTS**.
- Complete original film capability in all five native workers: **NOT IMPLEMENTED** by the bounded capability slices.
- Signed/external supply chain and wheelhouse reviews: **UNPROVISIONED**.
- Physical Windows EFS key-recovery and owner-approved NSIS upgrade/rollback: **OPEN**; do not execute a production mutation.

No creator's original films are read by this functional fixture, no artificial signing credential or license is supplied, and no feature-complete worker or full-film acceptance is fabricated.

## 5. Original native evidence and demonstrated failures (12 November owner-local)

- Exact Windows/Linux native build commit `787dab646fe77d62134fbde220cedc986ae6fb16`, run [43350923981](https://github.com/vjmichael/nvp_offline_film/actions/runs/43350923981): **Linux five genuine ELF64 executable compilation, independent functional outputs and private-bundle SHA roundtrip passed**. Linux specifically does **not** prove delegated cgroup-v2 whole-tree custody.
- Windows on the same exact head **compiled all five genuine PE64 MSVC executables** (audio, delivery, editorial, original_capture, scene_render). Functional execution failed on original_capture exit 12. A later diagnostic run [43352064980](https://github.com/vjmichael/nvp_offline_film/actions/runs/43352064980) preserved original native stderr: `Worker plan must be in the current private supervised workspace`. Source repair at `a7dcea14` uses `std::filesystem::equivalent` to compare actual OS directory identity rather than path-string spelling. **Original Windows rerun remains necessary**; do not report acceptance before the native result.
- Independent PE import examination on the original Windows candidate showed `bcrypt.dll`, `MSVCP140.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`, kernel32 and Windows UCRT/API-set imports. Independent ELF dynamic-section examination confirmed `libcrypto.so.3`, `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1`, and `libc.so.6`. These **native runtime dependencies are not Python wheels** and require separate version, provenance, physical availability and redistribution review. The original `tools/nvp_w1g_native_link_audit.py` and native workflow now preserve exact candidate manifests rather than pretending approvals.
- Original protected host previously created only `plan.json` and lacked worker input staging. It now requires the exact finite role-specific `sealed_inputs`, hashes them before authorization, writes a durable PREPARED receipt **before** source files, requires genuine Windows EFS on the dedicated job directory before storing any original bytes, pins input SHA in the sealed plan and scope, checks all input hashes after execution, and explicitly reconciles interrupted INPUTS_STAGED jobs. That integration requires separate genuine installed-host OS testing before acceptance.
- The protected host now calls a mandatory independent Python verifier for all five bounded output semantics *after* original process tree custody and *before* any caller-provided verification callback. The mathematical picture verifier recomputes every pixel; an actual GNU/Linux scene_render ELF output matched every byte of the independent 9,229-byte 64×48 pixel oracle. The Linux ELF also refused a foreign existing `plan.json` (exit 12, no result) and accepted the nested input-hash plan format (exact job+plan tied result).
- **Functional gaps still open:** a device-recording original capture, ActorID/SceneID/exact Film Time, true OpenUSD/Cycles scene rendering, non-destructive native timeline and source-reference edits, spatial production sound, sustained editing and SMPTE/DCP delivery, genuine protected-host installed integration, and external signed native import/wheelhouse review. Bounded capability-slice tests do not certify any of these.

## 6. Production gate

These receipts and source fixes do not constitute authorized full native role functionality, redistribution license permission, physical Windows EFS recovery, installer approval, or a creator-authorized NSIS upgrade. Independent signed review and original host-based domain acceptance remain required.
