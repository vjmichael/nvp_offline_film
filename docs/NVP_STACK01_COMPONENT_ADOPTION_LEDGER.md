# NVP-STACK-01 — Existing component evaluation ledger

> **Tracking notice (2026-11-13/14):** This is a historical/technical reference, **not an active task ledger or backlog**. The sole current NVP task journal, priorities, statuses, acceptance gates and branch/PR dispositions are maintained in [NVP_DATA_ALL_TASK_LEDGER.md](NVP_DATA_ALL_TASK_LEDGER.md), through draft convergence [PR #161](https://github.com/vjmichael/nvp_offline_film/pull/161). Older branch/PR claims below are source snapshots; preserve technical evidence but do not use them to decide current task priority.


**Status:** Candidate identification only; no new external engine is considered integrated or redistributable by creating this ledger.  
**Owner:** NVP production engineering  
**Policy:** [ADR STACK-001](NVP_ADR_STACK01_REUSE_FIRST_AND_ONE_INSTALLER.md)

Use this sheet as a **decision gate** for every planned substantial custom implementation. Do not write a new DSP, pixel math, editor, effects engine, physics system, asset importer, or animation solver while an approved candidate can perform the operation.

| Priority | Required NVP capability | Proven software worth testing | NVP state | Reuse adoption test / outcome |
| --- | --- | --- | --- | --- |
| P0 | Scene-linear grading curves, primaries, ASC CDL, standard LUTs | OpenColorIO | Pinned ACES color management used; **custom grading math remains** | **STACK-01A:** Test OCIO built-in grading and LUT transforms on same original two-shot NVP EXR; freeze new custom math |
| P0 | Efficient OpenEXR/HDR image reads, tiles/cache | OpenImageIO, OpenEXR | Current code includes custom EXR metadata parsing and FFmpeg decode | **STACK-01A:** Test OIIO file caching, HDR channel handling and independent readback; replace bespoke I/O as applicable |
| P0 | Editorial interchange, timecodes and clip metadata | OpenTimelineIO | NVP has original FilmIndex timeline contracts | **STACK-01B:** Export/import exact source identities and test EDL/OTIO round-trip without losing source/take link |
| P0 | Real editing/rendering/playback/effects | MLT, compare libopenshot | Current adapters and FFmpeg can export technical clips | **STACK-01B:** Test 2+ clips, multi-track preview, transitions, time range and independent decode |
| P1 | Masks, roto, tracking, node effects | Natron, OpenFX; mature OpenFX plugins | NVP has early global/shot grading controls | **STACK-01C:** Independently test a mask/tracked composite; inventory licenses of whole app and plugins |
| P1 | Camera rig, constraints, 3D scene, character animation, renderer | **Blender standalone worker selected**; USD import/export optional | Creator-approved Blender-first architecture; current native Cycles test accepted | **STACK-02/01E:** Harden external CLI/job adapter, GPL script notices and binary packaging; **defer standalone OpenUSD** until real multi-app reference/variant/layer requirement |
| P1 | Room layout and collisions | OR-Tools CP-SAT, trimesh, Blender BVH | Custom bounded solver has production fixtures | **STACK-01D:** Same frozen fixtures, solve quality, timeouts, complexity and stability; remove duplicate solver only after parity |
| P1 | Sound design, spatial acoustics, loudness | Ardour, pyroomacoustics, pedalboard, FFmpeg loudnorm | DCP technical silence only; real soundtrack unapproved | **STACK-01D:** Real dialogue/music/FX stem and 5.1 mix proof, consent/licensing |
| P2 | Characters, mocap, faces, TTS/lip sync | Blender rigs/NLA, CMU/etc licensed mocap, Rhubarb, proven speech/aligners | Early actor proxy and motion retarget tests | **STACK-01D:** Evaluate authentic licensed character/motion performance and fidelity |
| P2 | Finish/deliver movie/DCP | FFmpeg, DCP-o-matic | Technical DCP and ProRes/DNxHR native proofs passed | Preserve independent bit-depth/sample/raster and manifest validation; audit actual codec licensing |

## OS worker containment adoption — STACK-02B

The external Blender worker adopts **standard Windows Job Objects through maintained pywin32**, and Linux `prctl(PR_SET_PDEATHSIG)` + `resource.RLIMIT_AS`, not a homegrown alternative. [STACK-02B technical gate](NVP_STACK02B_OS_WORKER_CONTAINMENT.md) has independently passed code-level Windows/Linux kernel crash tests and native Linux Blender acceptance. This is an *engine integration result*, not a complete installer or GPL clearance.

**Pending:** Windows native Blender/Job Object scene acceptance, Linux whole-tree cgroup or guardian containment, NVP runtime multi-instance lock/lease, RAM/VRAM preflight, full existing Blender path migration and retail bundle source/notices. Preserve these as explicit unresolved tasks; never silently mark source/film release readiness.

## STACK-02C completed and follow-up production tasks

**Adopted established OS facilities rather than inventing a new distributed lock:** `fcntl.flock(LOCK_EX|LOCK_NB)` (Linux) and `msvcrt.locking(LK_NBLCK)` (Windows) now own a Blender worker journal for an entire execution or journal crash-recovery operation. Real independent processes proved lease contention, automatic release after actual `os._exit`, and prevention of false second-host recovery. These are **local-filesystem** guarantees, not a distributed service.

**Real Blender on Windows:** the official portable Blender 5.2.3 ZIP was verified against its published SHA-256 manifest and run under a Windows Job Object, using native Cycles CPU on the headless runner. Full original NVP approved-scene build and independent Blender geometry audit passed **nine checks**, including source hashes. [Run 41767354797](https://github.com/vjmichael/nvp_offline_film/actions/runs/41767354797) completed **4/4 jobs** (Windows 14 worker/kernel/lease tests, Linux 13 plus one Windows-only skip, genuine Windows and Linux Blender scene/audit). [Detailed acceptance report](NVP_STACK02C_HOST_LEASE_AND_WINDOWS_BLENDER_ACCEPTANCE.md).

**Next tasks, do not mark complete:** `STACK-02C2` Linux **whole detached-grandchild process-tree** cleanup through delegated cgroup v2 or equivalent OS-managed guardian with a real hard-host-exit test; `STACK-02C3` conservative RAM/VRAM render-admission guardrails and actual Windows GPU device acceptance; `STACK-02D` migrate all direct Blender/Cycles/animation/retarget paths through the same supervisor; `STACK-01E` one signed, GPL-compliant offline Windows installer with verified install/uninstall lifecycle. Multi-machine network shares need a different distributed locking model.

## STACK-02C2 kernel-containment adoption and next gates

**Technically accepted on Linux (opt-in):** NVP uses the existing **systemd `Delegate=yes`/ `DelegateSubgroup` policy and kernel cgroup v2 `cgroup.kill`** for Blender worker-tree custody. The independent out-of-tree guardian watches host death via a kernel pipe; the worker joins a cgroup *before exec*, and the guardian destroys detached descendants through `cgroup.kill`. Strict tasks without delegation cannot silently revert to a process group. Full provenance and earlier durable worker/creator custody remain intact.

**Measured:** [GitHub CI run 41770547351](https://github.com/vjmichael/nvp_offline_film/actions/runs/41770547351), **5/5 jobs passing**: 4 real delegated Linux kernel contract tests without skips (worker plus detached grandchild killed on actual host crash), original Blender 5.2.3 native render + nine independently audited scene-identity checks under strict cgroup, a **real Blender 5.2.3 hard NVP host exit with separately-sessioned grandchild killed and the journal recovered as INTERRUPTED**, the same combined proof using distro Blender 4.0.2, Windows Job Object regressions, and previous Linux worker tests. Full [STACK-02C2 evidence](NVP_STACK02C2_LINUX_CGROUP_WHOLE_TREE.md). The strict worker's short Blender version probe is also kernel-contained.

**Do not mark commercial/production ready:** `STACK-02C2B` **COMPLETED** real Blender-spawned descendant + abrupt host kill proof; `STACK-02C3` cross-platform RAM/VRAM preflight/limits (Linux `memory.max` and Windows job memory **do not cap GPU VRAM**); `STACK-02D` migrate remaining film-render/retarget/animation paths to the same supervisor; `STACK-01E` one offline single installer including systemd user-worker delegation on Linux (when built), Blender GPL license/source notices, NSIS on Windows and install/uninstall acceptance. The cgroup feature is deliberately opt-in until delegated desktop service architecture is accepted.

## STACK-02C3 PC resource governor, progress UX and full integration plan

**Implemented and measured as an opt-in development foundation:** standard Windows GlobalMemoryStatusEx / DXGI, Linux MemAvailable/PSI/amdgpu DRM and optional driver NVML; conservative per-task RAM/VRAM admission; SQLite FULL-sync cross-process memory reservations and honest phase/percent task journal; native Blender supervisor integrates with a guarded reservation and critical-pressure cancellation path; NVP's sidebar has live, accessible RAM/VRAM meters, current reservations and phase progress. An external AI server is **observed only**, with no uncontrolled model unload. Final code CI [41774472490](https://github.com/vjmichael/nvp_offline_film/actions/runs/41774472490) **4/4 successful** (28 Linux and 28 Windows contracts, React 2/2 and Vite build, actual distro Blender queue-admit-render). The kernel journal now passed real multi-process simultaneous RAM-budget competition, after fixing a genuine SQLite WAL reconfiguration race. [Detailed evidence](NVP_STACK02C3_RESOURCE_GOVERNOR_PROGRESS_AND_PC_SAFETY.md).

**Outstanding engineering tasks and proposed order:**
1. **02C3B — managed AI provider and priority queue:** use documented LM Studio native v1 model load/unload and progress events, explicit creator ownership, provider memory estimates and context/KV-cache budgets. Implement actual priority scheduling so short interactive AI edits don't silently start alongside a high-VRAM GPU render; queue all under the shared resource governor. Do not unload a model owned by another application.
2. **02C3C — device-specific protective admission:** real AMD Radeon AI Pro R9700 physical Windows GPU telemetry, DXGI adapter identity, multi-GPU correctness, measured GPU driver budget changes and RAM/VRAM exhausting-workload stress; effective Linux cgroup memory.max in admission and safe CPU fallback profiles. Maintain non-negotiable reserve floors.
3. **02C3D — UX controls and verified end-to-end progress:** user safe-cancel/pause/quality profile without forbidden unsafe toggle; frame/samples progress from Blender and provider model events, accurate source-linked percentages and actual measured ETA when statistically justified; persistent activity center and recovery UX.
4. **02D — full engine-path migration and crash reconciliation:** default-on governor for all render/animation/retarget/composite/encode paths, OS-verified reservation release and native process cleanup after crash, bounded background work. Current guarded Blender supervisor is opt-in; API's existing local AI writer is not a model manager.
5. **01E — commercial install/redistribution:** one-click Windows installer, packaged Blender workers, license/SBOM notice/source offers, signed binaries, and install→render→restart→uninstall acceptance. This technical result is not retail readiness.

## Decision record for every adopted component

Copy the template to `docs/stack-decisions/STACK-DECISION-<ID>.md`:

```markdown
# STACK-DECISION-<ID>: <specific operation>
Status: PROPOSED | ACCEPTED | BLOCKED | REJECTED | CUSTOM-GAP-APPROVED
NVP source fixture and sha256:
Required input/output, objective numerical quality:
Candidates (at least two, if available):
Candidate versions / tagged commits / download source / SHA-256:
Supported API/CLI/protocol, side effects and limitations:
Test commands and independent acceptance evidence:
Latency / CPU / RAM / VRAM / disk footprint / startup:
Windows x64 and Linux x64 packaging support:
Licenses of exact binary, linked libs, plugins and media assets:
Corresponding source, notices, build configuration, attribution:
Security model, worker permissions, cancellation and recovery:
Offline support, update/patch path:
NVP source/take/provenance integration:
Decision and creator approval:
For custom exception: exact unserved function and re-evaluation deadline:
```

## NVP single-installer release ledger

No product release until each selected redistributable third-party package has a machine-readable record:

- `name`, `vendor`, `version`, `build_hash`, `origin_url`, `artifact_sha256`, `signature_status`, `license_expression`, `source_offer_or_location`, `copyright_notice_path`, `dependency_chain`, `platform`, `architecture`, `codecs_and_compile_flags`, `redistribution_review`, `runtime_worker_policy`, `security_update_owner`.
- Every native worker must be part of a reproducible, offline test: install → launch → process frozen NVP take → verify outputs/permissions → restart/recover → uninstall, including **source and snapshot preservation**.
- LGPL/GPL-sensitive dependencies need **actual component-by-component review**; linking dynamically or running out of process is neither blanket permission nor blanket prohibition.
- No silent download/installation at first launch. One NVP installer can optionally select built-in feature packs, with no required manual external installation.
- Pin and sign the exact dependency bill of materials. Track codecs and plugin assets individually; do not infer licensing from the umbrella product name.

## First change-management decision

**Custom GRADE-UI-02B2 LUT implementation is held pending STACK-01A.** Use OCIO's supported `FileTransform`/grading APIs, standard `.cube` etc. **through OCIO itself**, with strict input/output-space contract, checksum, file sandbox and creator consent. Retain legacy custom NVP curve math as comparison fixtures until a correct adoption decision is accepted. Any custom parser/math must identify a genuinely unserved, reproducibly demonstrated function.

**No new engine has been selected by this file alone.** STACK-01A and subsequent native benchmarks will produce measured decisions, not assumptions.

## Accepted decision — Blender-first, standalone OpenUSD deferred

The creator explicitly approved an independent external production-worker architecture and Blender as sufficient for NVP's present 3D pipeline. This is recorded in [ADR STACK-002](NVP_ADR_STACK02_BLENDER_WORKER_USD_DEFERRED.md). **Selection of Blender as the primary external tool does not constitute permission to redistribute a particular GPL binary without audit**. The native `bpy` scripts and all Blender-dependent adapters require licensing review. Keep USD support through Blender when the supported interchange suffices; do not bundle a separate OpenUSD SDK to satisfy hypothetical future requirements.

## STACK-02C3B1 priority queue adoption (2026-11-03)

A native-producer-only scheduler slice is now CI accepted on [run 41775842472](https://github.com/vjmichael/nvp_offline_film/actions/runs/41775842472): 3/3 green. Rather than reinvent a queue service, the same SQLite FULL-sync task ledger serializes priority-ordered per-owner admission, FIFO within lane, safe queued-only cancellation, and durable reservations. Both Windows and Linux passed 9 new scheduler plus 10 existing governor tests; React passed 2 tests and built successfully. It is not a universal cross-engine dispatcher, managed AI model owner, preemption mechanism, GPU stress proof, or license/installer gate. [Scope and outstanding work](NVP_STACK02C3B1_PRIORITY_ADMISSION.md).

## STACK-02C3B2 approved dispatch and CPU-owned instance integration (2026-11-03)

Opt-in native adapters implement creator-authorized immutable task binding (exact SHA), an approved Blender dispatcher using the existing contained worker, and a CPU-only LM Studio Python SDK fresh-instance owner that never attaches to or unloads other apps' models. Missing: real production-domain approval wiring, SDK distribution and real LM Studio native acceptance, actual provider memory estimate, live GPU resource stress, host-side heartbeat/recovery, global autonomous dispatcher, and retail licenses/installer. [Design](NVP_STACK02C3B2_IMMUTABLE_JOBS_AND_OWNED_CPU_MODELS.md).

**B2 independent native acceptance:** [GitHub CI run 41777307929](https://github.com/vjmichael/nvp_offline_film/actions/runs/41777307929) 3/3 green at code SHA 89c828103912030256e227d1c76a5a1c5060be2d. The Windows and Linux jobs each passed 11 newly added approval/model/native-dispatch contracts, 9 scheduler contracts, 10 resource governor contracts and 3 guarded Blender admission contracts. Official pinned LM Studio Python SDK 1.5.0 imported on both runners. The separate Linux Blender job proved real approved immutable source-to-output execution, low-RAM queue refusal without spawning, subsequent native render, independently reopened output, and released RAM reservation. Live LM Studio model loading and GPU pressure remain untested.

## STACK-02C3B3 estimate/admission and restart recovery (2026-11-03)

Adopted the provider's own LM Studio estimate-only facility instead of inventing a GGUF/VRAM predictor. Source-pinned native CLI produces a model/context/GPU-off receipt plus conservative RAM contingency, verified in the existing SQLite resource ledger before admission. New CPU-only model owner persists identifier, modelKey and unique provider instanceReference; no resumed handle can unload an external model. Revocable native-only task consent and read-only loopback provider observation are recorded. Real downloaded model runtime, genuine CLI estimator, provider-epoch cleanup, user-facing approval and Windows physical GPU stress are still pending. [B3 design](NVP_STACK02C3B3_MODEL_ESTIMATION_AND_RECONCILIATION.md).

## STACK-02C3B4 Lu alpha provider reconnaissance and passive integration

`vjmichael/Lu-AI-GUI` independent desktop source was reconciled against its canonical Protobuf, internal Tauri status/load/unload commands, supervised pinned llama-server implementation and two-turn real-GGUF smoke example. The AF_UNIX carrier found in `jan_alt/lu/ipc-common-af-unix-20261031` is an isolated tool IPC prototype and is not an accepted external inference service. NVP added a source-locked read-only compatibility probe plus non-owning Lu status observation under the existing activity ledger, without executing any model or acquiring private API credentials. An isolated Lu CI branch independently runs native Rust inference/core contract tests. [B4 gate document](NVP_STACK02C3B4_LU_ALPHA_INFERENCE_INTEGRATION.md). Live Windows installed alpha/real GGUF and cross-app authorization are separate release gates.

**B4 CI acceptance / cross-project blocker:** [NVP run 41781810609](https://github.com/vjmichael/nvp_offline_film/actions/runs/41781810609) 2/2 green, 37 tests each OS including six-process native SQLite first-open WAL races. [Lu run 41781449832](https://github.com/vjmichael/Lu-AI-GUI/actions/runs/41781449832) Linux Lu Core 8/8 Rust tests green, Windows source compiler E0599 missing `assign_and_resume_suspended` in checked-in Job FFI crate (no unsafe fallback, Lu separate draft PR). Installed alpha and real GGUF NVP acceptance are still OPEN.

## B5 — authenticated Lu read-only AF_UNIX status lane

Native Windows/Linux true AF_UNIX tests exercise the NVP client with a test-only simulated Lu host using canonical framed status, a host-injected project/epoch-bound 256-bit HMAC grant, expiring one-use requests, SQLite replay/revocation and independent reply correlation. No model-control functions, no borrowed private llama.cpp token, and no assumed alpha integration. [B5 gate](NVP_STACK02C3B5_LU_AUTHENTICATED_STATUS_WIRE.md); [Lu Windows missing method issue #7](https://github.com/vjmichael/Lu-AI-GUI/issues/7). A real Lu-owned host adapter and real GGUF remain OPEN.

## B6 — Native-ready approved proxy scene source preflight (NVP-only)

The Film authoring UI previews exact project/world/script revisions and SHA-256. Internal native-ready staging fsyncs immutable approved source/script files under a pinned Blender worker root, builds typed BlenderOperation and verifies hashes/staleness again; it cannot grant creator consent, reserve memory or execute. Native Windows/Linux + React tests under B6. [B6 source and acceptance](NVP_STACK02C3B6_SOURCE_BOUND_RENDER_PREFLIGHT.md).

**Scheduling decision:** Lu–DLC interop postponed until after Lu v1.0; no Lu service is a prerequisite for NVP production.

## B7 — native authorized Blender execution and independent output readback

NVP now binds a director-approved, versioned proxy scene and its hash-pinned Blender script to a bounded, revocable, SQLite-durable **native-only** creator event authorization. The existing dispatcher revalidates the exact operation before/after resource admission, and a second resource-admitted Blender worker reopens the `.blend` to audit real geometry and director visibility plus render a PNG proof. Linux real Blender and Windows/Linux native contract gates are tracked in [B7 native build/reopen acceptance](NVP_STACK02C3B7_NATIVE_APPROVED_SCENE_AND_REOPEN.md). The installed creator-authenticated native desktop approval handler, real Windows GPU physical acceptance, animated Digital Takes, scene-linear EXR and professional output remain OPEN. **No Lu–DLC dependency until after Lu v1.0.**

## B8 — Frozen Digital Take original source → native timed Blender scene

Native FilmIndex capture renderer stages the *original* immutable world and timed performance revisions, even after live WorldState changes. The trusted NVP desktop consent contract pins take/capture identity, original scene and 24fps frame count, pinned generated script, actor marks, camera cut markers and exact RAM/GPU/worker operation. Existing resource-admitted Blender processes build the scene and independently reopen it to audit camera lens/pose/cuts and sampled actor-frame XY; real Linux Blender CI also creates a technical PNG when complete. Full-frame EXR and native installed creator UI acceptance remain OPEN. See [B8 source-native contract](NVP_STACK02C3B8_FROZEN_TAKE_NATIVE_ANIMATION.md). Lu/DLC remains deferred until after Lu v1.0.

### B8B derived technical presentation indexing

Native `publish_verified_preview` requires an already-complete original frozen-take Blender build and separately audited actual camera/actor timeline. It streams the `.blend` to a project-scoped content-addressed FilmIndex media blob, indexes the original native audit JSON and technical PNG as separately checked blobs, and registers a **new `presentation` object** with a typed revision-1 `source_take` dependency. `verify_presentation` reopens the original immutable capture and hashes all published bytes after restart; no presentation result modifies the frozen DTP. A single technical frame is not a full film image sequence. [B8 contract](NVP_STACK02C3B8_FROZEN_TAKE_NATIVE_ANIMATION.md).

## B9 — Full frozen Digital Take to real Float32 OpenEXR image sequence

NVP's host-only production renderer now supports the original frozen 24fps DTP via B8's verified indexed `.blend` source, with separate creator consent for the complete sequence. It batches up to eight frames per native task, requires measured RAM admission, writes actual Blender RGBA 32-bit OpenEXR with Raw scene-linear transform, independently verifies header channel type (FLOAT, not HALF) and decompresses float pixels in a separate contained Blender worker. Only a complete uninterrupted 1..N frame set may be streamed as content-addressed `image/x-exr` assets into a new derived FilmIndex `presentation` with revision-1 `source_take` ancestry. CI 160×90 is a *format and persistence* gate, not resolution/quality mastering. Exact OCIO/ACES primaries and full film mastering remain OPEN. [B9 contract](NVP_STACK02C3B9_FULL_FLOAT_EXR_FILM_SEQUENCE.md).

## B10 — Original frozen take, higher-resolution Float32 imaging and official ACES 2.0 OCIO

B9's full original 120-frame 24fps Float32 EXR sequence remains the source of truth. B10 adds explicit 720p/Full HD/UHD render RAM/batch/disk admission and a real single-frame high-resolution Blender native acceptance. It separately stages an original indexed Float32 frame into an OS-contained CPU OpenColorIO worker with authenticated creator consent and a **fixed** ACES 2.0 CG config. The processor converts actual linear Rec.709 RGB pixels into new ACEScg/AP1 Float32 channels with independently verified output pixels, alpha, OCIO version/config SHA and a new FilmIndex presentation linked to the original DTP. It does not replace immutable original takes. Final 120-frame Full HD/UHD render, complete custom input OCIO attestation, display Output Transform, graded master/audio/DCP and installed native consent UI remain OPEN. [B10 details](NVP_STACK02C3B10_OCIO_ACES_HIGHRES.md).

## B11 — Established ACES2 SDR review for original frozen B9 FLOAT32 image sequences

Bridged B9's complete original 24fps 32-bit floating OpenEXR FilmIndex media directly to NVP's already implemented `nvp_color_ocio` **COLOR-01B** display-view, true-float FFmpeg decoder, 16-bit RGB PNG quantizer, and per-file full RGB48 decode. Added native user-approval/TaskLedger containment for full reviews, original camera-cut mapping, independently re-opened indexed output, and typed dependency to immutable original Digital Take. Full 120-frame real Blender-to-SDR16 acceptance is CI-gated and must not be claimed until verified. No reimplemented competing OCIO maths and no Lu interface. [B11 details](NVP_STACK02C3B11_SDR_EDITORIAL_BRIDGE.md).

## B12 — Portable editorial interchange, exact camera-cut OTIO, verified technical picture delivery

Use **OpenTimelineIO 0.18.1** native `Timeline`/`Track`/`Clip`/`ImageSequenceReference`, not a custom timeline JSON format. Package B11's full creator-declared ACES2 sRGB SDR16 RGB review media as indexed relative `media/review_*.png`, bind each original camera shot in the frozen Digital Take to exact 24fps clip source ranges, verify the complete OTIO and image package independently, and index the immutable delivery as a FilmIndex presentation with take/float EXR/SDR typed dependencies. Reuse established COLOR-01B2 FFmpeg/FFprobe 10-bit ProRes HQ and DNxHR HQX codec auditing for optional *silent technical picture candidates* under its existing raster limits. The native host binds exact source/profiles/disclosure to creator consent, RAM admission, and OS containment. Real 120-frame Blender→ACES2 SDR16→OTIO/ProRes acceptance pending CI; no claim of NLE import, audio, approved picture lock, finished grading or theatrical DCP. [B12 details](NVP_STACK02C3B12_EDITORIAL_INTERCHANGE_DELIVERY.md).

## B13 — Reimport edited OTIO picture changes as non-destructive FilmIndex edit revisions

Official ASWF OpenTimelineIO 0.18.1 parses actual edited B12 package timelines, allowing only exact source-bound shot trim/reorder/split/repeat, integer 24fps frame ranges, bounded clip count, source-image URI and original image SHA. Unauthorized foreign media, nested composites, transitions, gaps, effects, speed/time warps and audio are refused. Stores exact edited OTIO bytes and an entire output→original shot/frame hash mapping as typed, optimistic-CAS `edit` FilmIndex revisions. The original frozen Digital Take and every earlier edit revision persist. Creator approval binds source, edit bytes and expected revision to a short-lived shared TaskLedger native RAM admission and OS-contained import parser. Real B12→B13 two-edit revision acceptance is CI-gated; this is not yet a conformed/rendered movie or sound mix. [B13 details](NVP_STACK02C3B13_EDIT_ROUNDTRIP.md).
