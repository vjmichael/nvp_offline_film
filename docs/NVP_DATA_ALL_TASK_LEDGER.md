# NVP-DATA-ALL — Per-task migration closeout ledger

**Creator directives (2026-11-06):** All NVP production, capture, authoring,
editing, playback, media import and final mastering must be DATA-FIRST;
**FFmpeg is not used anywhere in the resulting application.** Do not
reintroduce FFmpeg as an optional fallback, packaged dependency, PATH
discovery, executable, CLI, decoder, exporter or test prerequisite. Old
source code may remain in historical commits, but **must not be an active
product path**. Reusable third-party components are welcome provided they
are independently licensed and do not require/invoke FFmpeg.

**Source authority:** immutable Digital Film World + OpenUSD scene,
performance and exact signed-64-bit Film Time events (7,056,000,000
ticks/second), Digital Take hashes, source-signal references and
non-destructive assembly manifests. Hardware renders ephemeral samples
and visuals as requested. Only an explicit final 2D presentation freezes
output raster/video/audio; samples/frames never define a Digital Take.

## Ordered implementation and acceptance tasks

| ID | Task | Evidence required | Implementation | Native acceptance |
| --- | --- | --- | --- | --- |
| DA-00 | Supersede any FFmpeg anywhere; permanent dependency guard | Core/export/import paths cannot spawn FFmpeg; CI enforces no active dependency; no stale automatic CI | IN PROGRESS | OPEN |
| DA-01 | Replace FPS-based shot planning with tick-addressed camera/event editor | Creator can author/edit/revise shots/cuts/gaps in integer Film Time; no 24-fps authority | IMPLEMENTED (source editor) | OPEN |
| DA-02 | Migrate legacy capture and motion controls | New frozen take ties source OpenUSD pose/actor/mic/sound references and exact time; old fixed-frame proxy cannot be a native Take | PARTIAL (original-PCM live microphone capture; full motion pending) | OPEN |
| DA-03 | Connect filming sound producer and spatial evaluator | Immutable sample chunks and source events recorded at filming; two listeners from same Take yield different data-native audio | PARTIAL (live capture + orientation/coarse obstruction) | OPEN |
| DA-04 | Native 3D live picture/audio evaluation | Time-synchronized interactive OpenUSD picture and spatial sound without pre-rendered 2D movie, bounded RAM; renderer device failures contained | PARTIAL (authored USD camera, device-clock scene, GPU loss fallback) | OPEN |
| DA-05 | Non-FFmpeg import and non-FFmpeg final 2D export adapters | Trusted decode/import with source hash; approved 3D→2D image/audio render, independent encoder/mux, no FFmpeg | PARTIAL (native PNG/WAV + uncompressed AVI; cinema export open) | OPEN |
| DA-06 | Quarantine frame/proxy/media legacy entrypoints | No accessible editor, API, or native tool path routes to old frame-based authoring/decoding/execution; legacy data readable as explicitly labeled historical formats | PARTIAL (ASGI pre-dispatch quarantine; broader audit open) | OPEN |
| DA-07 | Native acceptance and installer | Win/Linux tests; installed Windows user interactions; long seek/playback/audio and picture sync; restart/crash/recovery; no FFmpeg present | OPEN | OPEN |

Definitions: **OPEN**=not coded/accepted; **PARTIAL**=substantial code
but missing required behavior; **IMPLEMENTED**=code landed without
independent acceptance; **ACCEPTED**=exact-head native tests including
relevant installed-app evidence passed. Do not collapse these statuses.

## Migration rules

- No claim of complete migration while an active UI/API path still
  produces an authoritative `frame_count`/`start_frame` or generates
  a legacy proxy for native filming or review.
- No deletion of immutable existing source data or silent rewriting of
  previously captured projects. Old formats can be inspected/imported
  only through a separately marked migration reader.
- Prefer one shared evaluator for the same Film Time/scene function.
  Preserve first-party authorization, opaque bounded windows, SHA
  provenance and recovery; tests cannot be waived merely because
  GitHub runs are delayed.
- All work and repair receipts go into
  `docs/NVP_ENGINEERING_STATE.md` and this checklist. The live branch
  is PR #74, `nvp/data-av01-native-scene-playback-20261106`.

## Work performed and outstanding defects

The existing USD/TemporalLedger and DATA-AV-01 source chunk reader,
dry spatial PCM mixer, native sound bridge and audio-clock-linked
world-state inspector establish the data-first foundation, **not**
complete acceptance. The most recent independently observed native
CI at commit `06546564941b319ccea436be59427d213db480ab`
failed: spatial USD time-code type, native consent test assumptions,
one existing React test; Windows installed acceptance was skipped.
These are tasks to repair, not releases to approve.

**Zero-FFmpeg clarification:** prior statements that FFmpeg could
remain for external media or final export are explicitly withdrawn.
A decoder/encoder must come from another suitable library or a native
format adapter; where none exists, the operation remains unavailable
until implemented instead of silently invoking FFmpeg.

## DA-05B — Protected final 2D derived-package integrity (2026-11-06)

**Implementation: committed on isolated draft branch** `nvp/da05b-2d-package-integrity-20261106`, stacked on PR #74 at `d2e81ea2`. **Native acceptance: OPEN.** This hardening is intentionally independent of the continuing DA-00–DA-07 migration job.

The trusted renderer's PNG response must now pass complete Pillow chunk/CRC validation and bounded pixel decoding, not only IHDR signature checks. Reject missing IEND, extra bytes after IEND, malformed IDAT/CRC, unsupported pixel modes and over-limit dimensions; export failure cleans the staged presentation without changing its frozen Take SHA. A complete package is published with OS-native no-replace directory rename: Windows `os.rename`; Linux `renameat2(RENAME_NOREPLACE)`. A concurrent empty output directory must never be silently overwritten. If atomic no-replace cannot be provided, fail closed.

Regression cases are added to `tests/test_nvp_final_2d_native.py` for corrupted PNGs and a destination-creation race. A separate local Pillow/Linux syscall contract exercise passed, **not** a repository regression or Windows-installed acceptance. Exact-head CI, real original-scene 2D raster acceptance, crash orphan reconciliation, and real approved presentation remain open. No FFmpeg dependency was introduced.

## 2026-11-06 — Creator-ordered DA-05/06 batch, then DA-02/03/04/06B

Development branch `nvp/da05-06-native-sequential-closeout-20261106` stacks on PR #75 and the migrating native PR #74. Committed, subject to native verification: creator-approved FFmpeg-free one-file uncompressed AVI from derived PNG+PCM; FastAPI ASGI legacy frame/EXR/proxy quarantine; native miniaudio microphone source recording and freeze/cancel lifecycle; listener-rotated spatial stereo and coarse SHA-bound USD obstruction; real authored camera mode and WebGL-loss recovery; preview-only source-bound saved color decisions applied to derivative picture bytes. Regression tests and Win/Linux CI paths added. **These are implementation receipts, NOT real hardware/installed-app or cinema acceptance.** Full ordered write-up: [NVP_DATA_AV_SEQUENTIAL_CLOSEOUT_20261106.md](NVP_DATA_AV_SEQUENTIAL_CLOSEOUT_20261106.md).

## DA-BATCH-1 — Native 2D delivery, retired executor quarantine, exact source edit cursor (2026-11-06)

On `nvp/datafirst-batch1-2d-quarantine-editorial-20261107` stacked on PR #76, the independent AVI writer now binds the actual PNG bytes read during mux to the manifest's SHA-256, and rechecks the unchanged WAV/manifest after streaming, before publication. Retired SLATE-08B Blender still/proxy CI workflows have been moved to manual-only historical evidence; the live DATA-AV matrix now verifies that the still IPC fails closed rather than expecting prohibited legacy processing. ASGI quarantine permits safe read-only historical sequence/motion records but refuses mutations, codec/color routes and legacy render artifacts. The original `SlateSequenceAssembly` is reused (no parallel rewrite), with a new SHA-pinned `source_at` exact-tick projection from committed assembly output to its frozen Take/shot; no transient review selection changes a committed cut, and no frame materializes. Regression tests were added. **CI and installed output acceptance remain OPEN.** Full professional encoding/mux formats and complete old executable path audit remain outstanding.

## DA-BATCH-2 — Live capture containment, spatial geometry and original USD mesh presentation (2026-11-06)

Branch `nvp/datafirst-batch2-live-spatial-world-20261107` stacks on DA-BATCH-1 PR #77. No FFmpeg; no source video frames. The native microphone recorder now refuses to publish a Take after sample overrun or disk writer failures and protects any spool whose worker cannot be proven terminated; new tests cover failure/cancellation. The spatial PCM mixer now interpolates geometry-based occlusion as source/listener/wall transforms change within each bounded sample window, rather than keeping one abrupt constant attenuation. `OpenUSDAssetRegistry` now accepts strictly bounded original source triangle meshes (max 2,048 vertices / 4,096 triangles), persists the exact topology in SHA-bound FilmIndex and OpenUSD, independently revalidates the original USD layer, and passes the bounded mesh to both the live Three.js renderer and restricted native 2D picture projector. It does **not** claim animated/skinned character parity, physical acoustics, HDR material fidelity, or installed app acceptance. Native Win/Linux OpenUSD tests were added, but **native test results are pending**. Professional actor rigs, HRTF/room simulation, continuous full-length synchronized playback and physical microphone acceptance remain OPEN.

## DA-BATCH-3 — Non-destructive color, pinned real OCIO ACES 2.0 (2026-11-06)

Branch `nvp/datafirst-batch3-native-aces-color-20261107` stacks on DA-BATCH-2 PR #78. New `backend/nvp_native_aces_color.py` implements pinned OpenColorIO 2.5.2 with its built-in ACES 2 CG config, CPU display/view processor, exact config SHA approval input, untouched original Take/grade SHAs, clipped-channel audit and a first-party **true 16-bit RGB PNG** writer; no FFmpeg, media subprocess, image proxy, or source mutation. Pinned `opencolorio==2.5.2` and native NumPy are packaged via foundation requirements and PyInstaller options (BSD-3-Clause license compliance still requires release-notice verification). Test coverage requires **real** OpenColorIO on Win/Linux and refuses absent/past-version/config mismatches. This native route requires **genuine 32-bit FLOAT scene-linear RGBA** from a future verified HDR renderer; our existing 8-bit CPU primitive renderer is NOT automatically fed through ACES or falsely called a cinema master.

The existing preview-only non-destructive grade output also now properly decodes the sRGB transfer, performs exposure/contrast/saturation in linearized light, encodes sRGB again, and records exact highlight clipping counts/fractions in its derived-output manifest. This is marked SDR review-only and cannot substitute for calibrated ACES/HDR mastering. Color-grade revisions, USD world data, original performances and sound remain immutable. **Actual native CI, calibrated display, professional scene-linear render, high-dynamic-range output, final MOV/DCP packaging and cinema acceptance remain OPEN.**

## DA-BATCH-2B — Live UsdSkel actor playback + original mesh acoustic rays (2026-11-06)

This follow-on Batch 2 implementation is stacked on the existing DA Batch 1→3 + CI repair work (PRs #77–80). It **reuses** NVP's real `UsdSkel` bound actor mesh/animation and `evaluate_skin`, not a second character rig or synthetic geometry. A native FilmIndex source-pinned scene at an exact Film Time tick emits bounded temporary deformed actor vertices, original triangle topology, source-derived display color, and skeleton layer SHA. The Three.js viewer updates the exact actor pose in-place; stale timestamps, altered topology, forged skin authority or unbound source actors are refused. This is live 3D source data, **not** recorded picture frames or an approved final movie. The skeletal USD animation layer now authors the correct 7,056,000,000 time-codes/sec to avoid an observed native CI bug (at 1 second the old layer returned ~3.4e-9 rather than 1.0 joint position). Existing old frozen Take source layers are **never rewritten**; if a previously frozen rig had invalid source timing, the creator must publish a corrected new source revision and a new Take identity, not reinterpret the original.

For sound, verified original USD cube/mesh geometry now uses bounded source-space ray/triangle intersection for obstruction instead of inventing blocking from oversized bounding spheres; spheres remain conservatively bounded. Each native PCM window re-evaluates source obstacles at both exact source endpoints so moving/rotating geometry cannot silently reuse stale occluder positions. This is a dry stereo broadband attenuation model; **not** frequency-dependent material simulation, diffraction, HRTF, room impulse response, or a cinema-certified spatial mixer.

New native real USD/Skel geometry and source occlusion tests, an integrated original Digital Take PCM wall/no-wall mix comparison, and headless Three.js pose/topology tests are wired to the DATA-AV matrix. Live microphone finalization also preserves the last valid PCM callback flushed synchronously during device stop (formerly a possible silent tail drop); regression coverage requires exact source sample count. **CI and installed WebView2/GPU/microphone acceptance remain OPEN.** Multi-microphone sync/crash-resilient capture, full character materials/skin fidelity, true acoustic materials/occlusion, headphone HRTF and professional mixing remain separate open implementation orders.

## DA-BATCH-2C — Multi-source filming, interruption recovery, binaural IR, live actor face/materials (2026-11-06)

**Branch:** `nvp/datafirst-batch2c-full-livestage-20261107` stacked on earlier Batch 2B PR #81. **Not a release or completed native acceptance claim.** This phase specifically addresses the user-requested residual Batch 2 work while continuing to prohibit FFmpeg and keeping frozen Take data immutable.

**Live actor geometry:** Real source-bound UsdSkel actors are deformed at exact Film Time in the live Three.js viewer; old frozen rigged actors with real mesh plus `displayColor` still render rather than being discarded for lacking new materials. A rig with no USD-bound mesh is now tagged `MISSING_BOUND_USD_MESH` and reported to the creator, **never substituted with a fake actor sphere**. Invalid or stale pose data are suppressed, with explicit status. Added bounded real USD `BlendShape` offsets, `SkelAnimation.blendShapeWeights` at exact Film Time, and actual `UsdShade.Material` + `UsdPreviewSurface` diffuse/roughness/metallic source binding. The live viewport derives ephemeral GPU vertices and materials from those original USD APIs. Material textures, advanced surfaces, face rigs with hundreds of targets and full Hydra renderer parity are still OPEN.

**Native filming:** In addition to one-microphone recording, the trusted desktop can now explicitly request **two independent original mono tracks captured on one shared-clock two-channel device**, with separate scene emitter/source IDs, unflattened PCM and one authorized frozen Digital Take. The code intentionally **rejects the false premise that two independent USB microphones are hardware synchronized**; cross-device drift calibration and authoritative timestamps remain OPEN. Added durable local original PCM recovery receipts and retained unfrozen partial sources after a host crash or failed freeze; the desktop reports unapproved spools and never silently creates an approved Take or erases source after failure. Recovering and authorizing partial signal publication after crash requires a separate trusted reconciliation workflow; current catalog is read-only.

**Native spatial acoustics:** Existing original-source geometry-based cube/mesh ray blocking and time-varying source position remain. Added bounded creator-approved, SHA-pinned original 48 kHz measured `anechoic_hrir` or `room_brir` source types and deterministic causal two-ear FIR convolution, using original pre-window PCM history to preserve seek/replay parity. No generic external decoder or synthetic HRTF dataset is installed. The measured IR is an **optional trusted backend capability**, not yet exposed as a fully calibrated headphone device UI. There is no assertion of measured head-tracking correctness, material absorption, real room simulation/diffraction, binaural calibration or cinema mastering.

**Verification:** Native Windows/Linux Python 3.11 and 3.13 tests now include synchronized dual sources, crash-denial receipts, measured IR seek invariance, real USD facial deformation/shader source and dynamic Three.js actor geometry. The test implementation and workflow are committed, but **native CI/physical microphone/GPU/headphone acceptance remain OPEN** until exact-head runs pass. Windows NSIS installed smoke remained failing on an older head and requires a traceable native repair (do not claim installed acceptance or merge these draft PRs).

### DA-BATCH-2C follow-on: explicit recover + measured-profile native UI

The native window now offers creator-approved **recovery of a stopped, fsynced, SHA-verified mono source** from a crashed/denied recording; that is an unattached original `audio` FilmIndex revision, **never** a frozen Take, with no automatic approval or deletion. A new native OS consent scope covers original PCM SHA and exact sample count. The UI reports sealed candidates, requires a new source ID, obtains native approval and explicitly states that no Take was frozen. Source journal state marks `SALVAGED_SOURCE_ONLY`, retains the old PCM evidence and excludes it from further automatic offers. If the spool was modified or its hash is absent, recovery fails closed. Separate unit + desktop tests were added.

A measured source HRIR/room BRIR may now be selected through the authenticated native profile catalog; the native auditioner verifies source profile SHA, displays it in the OS consent dialog, binds the original profile to a bounded native audio session, reports the exact SHA/kind in each PCM window, and refuses stale/wrong-profile authority. It uses original sample-window history on every seek and never invents an unmeasured impulse response. This is **not calibrated/bundled headphone-HRTF data**, room simulation, material absorption, speaker calibration or final cinema master. Those are still OPEN physical and source-licensing acceptance tasks.

Installed Windows acceptance remains **OPEN**. The Windows native smoke now writes opt-in startup/exceptions/exit receipts to distinguish pre-Python bootloader/initialization failures from Python exceptions. No active FFmpeg imports or codec packages were added. Current PR #82 exact-head native Windows/Linux/Three.js verification is pending; do not treat earlier obsolete or cancelled workflow runs as acceptance.

## DA-02E — Independent audio devices and exact Film Time synchronization (2026-11-06)

**Implementation branch:** `nvp/datafirst-da02e-independent-device-clocks-20261107`; stacked atop draft PR #82. This implements a new native, **two separate device** recorder alongside earlier one-device mono and shared-clock stereo modes. It does not require FFmpeg or change any original PCM samples.

### Capture and clock authority

- Enumerate genuine input endpoints through `sounddevice==0.5.6` (PortAudio; MIT, bundled on Windows), with no arbitrary browser-provided filenames or executable paths. Native OS approval binds **two distinct device IDs**, scene/camera source SHA and event/source IDs.
- Open two `RawInputStream` inputs at signed PCM16LE/48 kHz, each with an independent callback, byte-bounded disk queue, source file, and cumulative sample count. A buffer overflow, invalid ADC timestamp, interrupted stream, sample loss, worker restart, or source SHA change prevents freeze.
- Retain PortAudio `inputBufferAdcTime` (first ADC sample) in its **own stream time base**. A dedicated calibration thread repeatedly brackets each stream's `stream.time` against the same Python `perf_counter_ns` monotonic host clock; it does not conflate independent PortAudio origins. Require multiple stable calibration samples and ADC anchors over 750 ms; fail closed on high jitter, time jumps, unexpected rates, >2,000 ppm clock drift or >2 ms ADC residual. Fit a bounded per-device affine sample-index→host-time map; the earliest captured original sample defines Film Time zero for this sound recording. No claim of hardware genlock, sound-camera genlock, or driver timestamp quality beyond evidence.
- Publish a dedicated immutable `audio` FilmIndex clock-evidence revision containing both raw sampled timestamp/calibration series, their SHA-256 digests, independent device model/offset/drift/residuals and the SHA of **each untouched mono PCM source**. Every sound event in the subsequently frozen Digital Take pins the exact evidence ID+SHA and its own measured Film Time mapping; frozen scene/camera and temporal event references cannot silently rebind. Both source files remain unchanged, byte-for-byte.
- Native audio-window review uses bounded, seek-invariant fractional sample interpolation for each independent source on the **derived output PCM only**, including correct preceding derived history for optional measured HRIR processing. It does not resample/overwrite original sources or flatten a soundtrack. Capture count, timestamp map, and evidence SHA are revalidated at review time. Creator's second native OS approval displays the clock-evidence SHA, both measured drift rates, worst residuals, and explicitly says the devices are not genlocked.
- Two-independent-input selection, status, and proof receipts are exposed in the live filming desktop UI; single microphone and shared-clock stereo are unchanged. Failed/uncertain sessions are not auto-approved. Their spool and recovery evidence remain under native host custody rather than becoming a false Take.

### Verification and limitations

Pure regression fixtures cover independent nominally 48-kHz clocks with +150/−220 ppm drift, stream-epoch offsets, bad calibration, ADC jumps, deterministic seek interpolation, and original bytes unchanged. A native two-stream fake adapter covers separate PortAudio-style callbacks, real spool writers, source SHA, FilmIndex clock-evidence revision, creator approvals, and frozen source playback on the same scene. Windows/Linux Python 3.11/3.13 and React UI matrix wiring is committed; installed NVP.exe now packages `sounddevice`. **Exact-head CI is pending; physical dual-USB-device loopback and driver timestamp quality acceptance remain OPEN.** This is **independent audio-to-audio synchronization only**; native camera capture remains its own timing source and does not yet have a proven hardware ADC/video genlock link. Two distinct OS endpoint IDs can still represent host-API aliases to one physical device; source IDs/receipts do not claim otherwise.

**Useful technical reference:** PortAudio `PaStreamCallbackTimeInfo` fields are stream-time-relative, and host APIs differ in timestamp fidelity. See https://portaudio.com/docs/v19-doxydocs-dev/structPaStreamCallbackTimeInfo.html and https://github.com/PortAudio/portaudio/wiki/BufferingLatencyAndTimingImplementationGuidelines .

## DA-BATCH-3B — Source-verified scene-linear ACES 2 and non-destructive native review (2026-11-06)

**Branch:** `nvp/datafirst-batch3b-source-linear-aces-20261107`, stacked on completed-implementation Batch 2 PR #83. This continues prior Batch 3 ACES2 PR #79, which had working in-memory OpenColorIO 2.5.2 and true PNG16 output, but explicitly lacked a real trusted source-scene-linear raster and native artist review controls.

Implemented first-party native CPU **OpenUSD geometry-to-FLOAT32 source-light review** (no Blender, video decoder, external renderer, FFmpeg, old 8-bit PNG-as-HDR trick, or film-frame authority): reopens and verifies the original frozen Digital Take at exact Film Time, samples original real USD camera focal optics, composed source mesh/cube/sphere or deforming actor skin, actual sphere-light intensities and source-authored USD PreviewSurface/displayColor, then rasterizes bounded world-space triangles through perspective-correct per-pixel depth testing into ephemeral opaque float32 RGBA. Camera source, actor/source geometry and original Take SHA stay verified; missing original actor geometry fails closed rather than inventing an actor silhouette. Neutral fallback appearance for NVP-authored unmaterialed geometric props and limited ambient/photometric-light normalization are explicitly labeled **uncalibrated visual review**, not studio HDR master. The renderer does not claim texture networks, material scattering, calibrated IES/spectral light distributions, a validated lens/sensor transfer, full Hydra parity or genuine production photorealism.

A new `NativeACESColor.process_verified_usd_scene` hands that source-evaluated float32 array to the existing SHA-pinned built-in OCIO ACES2 SDR processor and genuine 16-bit RGB PNG writer. It checks the USD scene-linear result checksum against the ACES receipt and preserves the frozen Take/grade/config/scene source SHA; source color decisions are never baked into frozen USD or recorded audio. The desktop bridge offers an exact original Film Time + active USD shot camera, matches one saved color revision to its source Take, pins the OpenColorIO configuration SHA, and asks the creator to approve one **temporary unmastered review**. Browser users cannot supply source float RGB pixels, a file or camera path. The native Color Grade panel now reopens/saves a revision, refuses to review unsaved edits, requests one approved 16-bit ACES sample at a selected exact tick and shows its clipping/source SHA and camera provenance. No movie/EXR is generated from recorded source data in this action.

New real USD/OCIO and React tests cover source and color-decision authority, deterministic float32 output/PNG16, derived preview consent and no source mutation; wired into the Windows/Linux Python 3.11/3.13 DATA-AV matrix, React test and single NSIS installed bundle. **OPEN:** exact-head CI and native installed acceptance; calibrated physical display and camera color input characterization; full production renderer texture+material fidelity; artist-controlled output gamut/HDR mastering options; true ACES16 approved 2D package integration (beyond independent unmastered native preview). Do not declare cinema-grade ACES or Batch 3 release completion from a preview implementation.

### DA-06E — Approved creator-managed native ACES2 RGB16 + PCM derivative

Implemented a second, explicit output mode in the existing trusted `Approved2DPackage`: a saved, Take-pinned `aces_color_grade` and exact OCIO config SHA authorize a full **16-bit RGB PNG sequence plus native stereo PCM WAV** built from the same verified original frozen Digital Take. This is a NEW downstream presentation, never replacement source footage. Every original authored camera sample is re-evaluated as OpenUSD geometry/light FLOAT32 at exact Film Time, graded by the saved original color decision and pinned OpenColorIO ACES2 SDR view, then hashed as authentic 16-bit RGB PNG. Camera gaps produce explicit zero RGB16 pixels rather than inventing source geometry. Separate per-picture receipts preserve original source snapshot hashes, color clipping counts, scene-linear buffer hashes, presentation sample tick and camera authority. Native output is atomically published no-replace only after trusted OS folder choice plus explicit native creator approval of original Take/grade/ACES config SHA and picture cadence. Same original frozen Take supplies the native WAV sample-addressable sound. **No flattening of color into USD, no FFmpeg, no baked source frames, and no claim of a theatrical master.**

The legacy BGR24 AVI writer now **refuses** any original ACES2 16-bit derived package rather than silently downgrading it. Existing 8-bit SDR preview and AVI remain a separate, explicitly limited path for creators who authorize that format. The React color workspace has a separate original USD camera selector and authorizes this 16-bit derivative through the existing native OS destination picker, then shows its output manifest SHA. Native Windows/Linux source-scene/ACES/bit-depth/camera/source SHA tests and React tests are committed to DATA-AV. **Remaining:** real display/sensor calibration; HDR10/P3/Rec.2020 mastering, professional texture/material/lighting parity, native installed validation, long-form throughput/cancellation, and full DCP acceptance. These are physical/production acceptance and future renderer/tooling orders, not implicit claims of this unmastered SDR presentation.
