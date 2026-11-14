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

## DA-BATCH-3C closeout — native material/ACEScg source interchange, recovery, readiness (2026-11-06)

**Implementation:** draft PR #85 `nvp/datafirst-batch3c-color-render-delivery-closeout-20261107`, stacked on #84. Continue development without waiting on unrelated historical GitHub operations.

**Batch 3 implementation now committed:**

- Real original SHA-addressed reusable `UsdShade.Material`/`UsdPreviewSurface` authored for geometry assets, with exactly scoped RGB/roughness/metallic input. Old asset and frozen-Take revisions remain unchanged when materials are revised. Native `visual_state` and live Three.js viewport honor real source shader parameters for ordinary meshes and skinned characters. The CPU source-linear renderer applies a bounded GGX/Smith/Schlick microfacet preview from actual USD material scalars with explicit **uncalibrated** receipt; this is not full Hydra light transport/texture-network equivalence. New native Windows/Linux regression `test_nvp_native_usd_material_fidelity.py`.
- Native official OpenEXR 3.4.17 (BSD-3-Clause; CPython Windows/Linux 3.11/3.13 binary wheel) for source-authoritative **FLOAT32 ACEScg RGB** images. `NativeSceneLinearEXR.write` computes the verified frozen USD source scene at original Film Time and real authored camera, applies the SHA-pinned saved grade in declared linear source RGB and pinned OpenColorIO source→ACEScg colorspace transform; metadata contains original Take/scene/snapshot/grade/OCIO SHA. Actual OpenEXR is read back to verify every FLOAT32 pixel. No external executable or FFmpeg. `Approved2DPackage.export(...linear_exr_grade=...)` creates a complete distinct EXR + native PCM WAV sequence; explicit camera gaps are black native RGB32 EXR rather than made-up scene frames. It is a **separate unmastered float scene-linear intermediate**, not an HDR10 or cinema master.
- Trusted `data_av_export_native_acescg_exr` uses the native OS destination folder picker and exact creator Take/grade/config/cadence approval, never a browser-requested path. `NativeColorGradePanel` now offers the independent output alongside existing source-verified ACES2 SDR RGB16 PNG/PCM output. The old BGR24 AVI path is blocked from handling high-bit-depth color packages.
- Durable host-crash/cancellation support for both approved ACES2 PNG16 and ACEScg EXR32 exporter paths: bounded per-picture SHA-fsynced source checkpoint journal, exclusive cross-process Windows/Linux OS lock, exact Take/grade/OCIO/cadence identity on resume, previous original snapshot re-evaluation at each retained Film Time, cleanup only of orphaned **derived** images, atomic same-filesystem no-overwrite publication, explicit in-process cancellation hook without auto-mastering. On publication, commit an immutable FilmIndex `presentation` receipt depending on the original frozen Take and color decision; manifest SHA and exact color profile are held in durable project SQLite for restart-authenticated preflight. A forged self-consistent JSON manifest cannot substitute for this registry proof.
- Strict no-FFmpeg `assess_unmastered_source_package` validates every picture and PCM SHA and exact authored ticks, refuses misleading DCP/HDR10 claims, and enumerates missing SMPTE 2K JPEG2000 XYZ12 MXF / PCM24 sound / CPL PKL ASSETMAP / independent QC / calibrated reference + projector ingest or HDR10 PQ Rec.2020 mastering gates. Native `data_av_cinema_readiness` uses OS folder selection **and original producer FilmIndex receipt**; React displays source proof and missing delivery requirements. It creates **NO fake DCP, calibrated HDR master or unlicensed conversion**.
- Installed Windows NSIS acceptance commands fixed to launch the GUI-subsystem app with PowerShell `Start-Process -Wait -PassThru` and read exact Python-entry startup diagnostics instead of checking stale `$LASTEXITCODE`. Installed A/V smoke now additionally exercises real OpenUSD authored surface, the pinned native ACES2 16-bit RGB PNG, and actual native OpenEXR FLOAT32 ACEScg conversion. Exact-head native Win/Linux 3.11/3.13, React, no-FFmpeg, original USD tests and installed-app smoke all run in CI; committed tests include `test_nvp_native_acescg_exr.py`, `test_nvp_native_color_export_recovery.py`, `test_nvp_native_cinema_master_gate.py`, and the updated live UI tests.

**Explicit outstanding release/hardware gates (DO NOT mark as implemented/accepted):** independent installed Windows GPU/physical reference display color measurements; actual camera/sensor input transform and source light spectral/texture fidelity; complete Hydra/PBR/UV texture-network parity; licensed true 2K/4K production-grade animation/geometry and native physical color calibration; fully functional FFmpeg-free **native JPEG2000 XYZ12/MXF/SMPTE DCP encoder**, independent no-FFmpeg strict DCP validator, 24-bit sound mix, audio channel/channel-order QC and real theater projector ingest; HDR10 Rec.2100 PQ 10-bit mastering metadata and display QC; 60-second production throughput on the minimum installed workstation. Old `nvp_audio01k3_dcp.py` uses DCP-o-matic, which has FFmpeg-based conversions; old `nvp_cinema_essence.py` explicitly invokes FFmpeg/FFprobe. **These remain quarantined** by creator directive, not candidates for silent resurrection. A new DCP backend can use an audited all-native OpenJPEG/asdcplib/libdcp chain or suitable verified FFmpeg-free tool only after binary provenance, license and actual JPEG2000/MXF cinema acceptance. Current output is an accurately characterized source-linear/SDR finishing intermediate, not a theater-ready DCP.

**Status:** Implementation committed in #85; exact-head CI pending and may require native repairs. Do not call Batch 3 theatrical mastering production-complete until physical and DCP gates pass.


## NVP-15 work orders — verification to production delivery (2026-11-06)

The creator converted the remaining Batch 3 release gates into five ordered work orders. **Continue sequentially and do not mark native or physical acceptance from implementation alone.**

1. **WO1 Native verification and repair.** Prove exact-head Linux/Windows Python 3.11/3.13, frontend, packaging and installed Windows NVP.exe; repair actual failures; document the acceptance commit and any unsupported physical gates.
2. **WO2 Renderer fidelity.** Original USD UV/textures, shader networks and rigged-character presentation with source revision checks; no replacement actor placeholders.
3. **WO3 Cinema output.** Functional JPEG2000/XYZ12/MXF/SMPTE DCP generation and independent validation, verifying codec licensing and output provenance.
4. **WO4 Color and sound mastering.** Calibrated cinema/HDR targets, output transfers, native channel/24-bit PCM mapping and QC; hardware evidence stays a separate gate.
5. **WO5 Production acceptance.** Real 60-second workload throughput and cancellation/recovery, installed Windows app, physical reference/projector ingest and production receipts.

**Revised boundary decision:** NVP's authoritative Digital Takes, USD/PCM capture, timeline/assembly, editing, playback, grading decisions and native intermediate generation remain data-first, immutable-source and FFmpeg-independent. The creator permits **investigating optional FFmpeg solely as an explicitly selected final-delivery boundary adapter**, not as a dependency for the primary NVP workflow. Such a future adapter must accept only approved, independently hash-verified derived packages, never mutate source material, be separately packaged/opt-in with audited licensing/provenance, and issue its own deterministic output/validation receipt. No permission is given to reactivate legacy embedded FFmpeg pipelines, and no FFmpeg-based delivery is currently implemented or accepted by this decision. Prefer a genuinely working verified FFmpeg-free exporter where achievable. Do not loosen current CI's zero-FFmpeg primary-workflow gate.

**WO1 snapshot at head `cd900dbcfb9b5794ce9e3f800e2cfe018270dd12`:** DA-00 no-FFmpeg audit, Linux 3.11/3.13 and React passed, while Windows 3.11/3.13 and installed-app smoke were still running on DATA-AV-01 run 42334034757. All five separately triggered USD/E2E workflows passed. Await exact-head Windows results and repair concrete failures before WO1 acceptance.


### WO2 implementation — source-owned UV mesh pathway (2026-11-06)

**Development branch:** `nvp/wo2-usd-uv-verified-20261107`, stacked on WO1 PR #85. Native development proceeds without blocking on unrelated queued GitHub jobs.

Implemented and committed **source-authored, per-vertex USD `primvars:st` UVs for bounded reusable triangle meshes**. The native asset publisher accepts `mesh_uvs` only for actual authored meshes, validates finite bounded pairs and exact vertex count, writes an authentic `UsdGeom.PrimvarsAPI` vertex-interpolated `st` primvar into the original USD layer, and pins its values in the SHA-addressed FilmIndex asset revision. Reopening a source asset independently compares actual USD primvar values and interpolation with the immutable FilmIndex UV manifest, failing closed on mismatch or an unindexed rogue `st` primvar. A later revision cannot silently modify old stored UVs or prior scene references.

`visual_state` carries these verified UVs only with the original mesh, and the live React/Three.js viewport validates topology and UV bounds before constructing disposable GPU `uv` attributes. Neither the browser nor the renderer creates new source UV authority. Windows/Linux native regression `test_nvp_wo2_mesh_uv.py` and React viewport UV negative tests were added to DATA-AV CI. **No claim of verified native CI or physical texture display yet.** No external texture/file path, arbitrary resolver, image decode, or FFmpeg added.

**WO2 remaining:** source-verified image texture blobs and original `UsdUVTexture` / shader graph connections; protected image decode, sampling and color-space semantics; consistent texture sampling in source-linear CPU output and live Three.js; original skinned-actor material/UV parity and UV seams; richer material network coverage, independent fixture-based render comparisons and installed-app acceptance. This commit is UV transport/authority infrastructure, **not full WO2 renderer completion**.


### WO2 continuation — authentic PNG/UsdUVTexture and skinned UV transport (2026-11-06)

This implementation follows the previously completed authentic USD `primvars:st` mesh transport on draft PR #87. **Native editing and FFmpeg-independent playback remain data-first.** Implementation is committed without declaring native CI acceptance.

- **Original image authority:** `backend/nvp_native_usd_texture.py` validates native-approved bounded PNG RGB or opaque RGBA bytes (single image, at most 512×512 / 2 MiB; translucent alpha fails closed pending compositor support), indexes the unchanged original bytes by SHA-256 in the project FilmIndex, and reopens them with digest/size/format checks. No resolver accepts filesystem, browser, project URL, or network texture paths.
- **Original USD shader graph:** reusable UV meshes now accept original PNG source bytes, author genuine `UsdUVTexture` (file, sRGB, repeat wrap), `UsdPrimvarReader_float2(st)` and `UsdPreviewSurface.diffuseColor` connections in the immutable source USD layer. The file input is a non-resolving `nvp-blob://texture/<sha>` symbolic identity, **not a filesystem path**. Reopen verifies the actual graph nodes, connections, texel digest, UV primvar, and unchanged material values before presenting pixels.
- **Native source-linear review:** the bounded CPU raster uses the original indexed PNG, reopens and decodes after SHA verification, samples authored UVs with perspective-correct repeat wrapping and native sRGB-to-linear conversion, and records textured triangle count plus its explicitly uncalibrated shading status. Original source is unchanged.
- **Live 3D viewport:** native `visual_state` passes the verified original PNG transport and frozen UVs to the ephemeral Three.js `MeshStandardMaterial.map` via a **local in-memory data URI only**, with sRGB color space, repeat wrapping, nearest texel sampling, and texture disposal. The JS side checks descriptor/digest identity but trusts the native host for the actual content hash; never grants original image authority to browser controls.
- **UsdcSkel actors:** original skin authoring now permits bounded per-vertex `st` UVs, source evaluation returns actual skin mesh primvars rather than invented UVs, and the live viewport accepts these source UVs with deforming vertices. Missing skinned geometry remains an explicit missing-source condition, not a substitute character.
- **Source-version regressions:** real USD shader graph/FilmIndex blob and frozen Take tests, unsafe PNG and forged descriptor rejections, UV shape and invalid actor UV tests, and native rendered pixel comparison across changed source revisions are added to Windows/Linux CI. The old frozen Take is explicitly re-rendered to verify the same original RGB data after a new source revision.

**WO2 limitations / further gates:** independent physical native GPU pixel capture and a tolerance-based CPU/WebGL reference-render comparison are unverified; current CPU microfacet texture tint is an **uncalibrated approximation**, not Hydra/PBR shader parity or calibrated HDR. Skinned actors now also author an actual source-verified `UsdUVTexture` / `UsdPrimvarReader_float2(st)` / `UsdPreviewSurface` graph with a project-owned SHA-indexed PNG descriptor. The same existing native texture decode/transport/CPU sampling path is reused across static and deforming meshes, preserving original pose, authored UVs, and material. Rig source acceptance validates the registered image and original on-stage shader connections; no fake actor proxies or file resolvers are permitted. Full UV seam/face-varying interpolation, multi-material rigs and native GPU pixel acceptance remain open. A creator-facing trusted native texture-import UI is not yet connected. MaterialX/full USD node graphs, production UV seam support, HDR texture color spaces, larger textures, multi-material assignments, and installed Windows acceptance remain future implementation/acceptance gates. These limitations must not be silently rebranded as complete renderer fidelity.


### WO2 continuation — trusted creator import, UV seams and renderer acceptance fixtures (2026-11-06)

Continues **WO2 on PR #87**, without blocking on WO1 GitHub verification and without activating FFmpeg in NVP's primary workflow.

**Implemented source/UI code:**
- Native desktop WebView2 `data_av_import_original_texture(project_id)`: chooses exactly one PNG through the OS file picker (no browser-supplied path), bounds source reads to 2 MiB, rejects symlink/nonregular files and mid-read changes, verifies actual PNG/RGB data, then asks native creator approval showing the independently computed source SHA and dimensions. A denied import does not publish a FilmIndex texture. The original PNG remains immutable and project scoped.
- `data_av_texture_mesh_catalog` lists only current original UV mesh revisions with verified FilmIndex assets. `data_av_apply_original_texture` independently checks the chosen original mesh revision/SHA and approved imported PNG SHA, asks a second OS confirmation, rechecks the current mesh head and publishes **one NEW mesh revision** preserving geometry, source UVs and scalar material. Existing source scenes, actors and frozen Takes retain their old SHA-pinned asset revision. React now exposes source selection and the separate apply action without accepting filesystem/URL paths.
- Added genuinely authored `faceVarying` USD `st` primvars for static meshes and UsdSkel polygon meshes; required finite bounded UVs and exact corner count, mutually exclusive with per-vertex `st`. Native reopening verifies exact original primvar interpolation, topology and source SHA. Original skin polygon face corners are triangulated with the same exact fan topology as positions; live Three.js uses disposable unindexed GPU vertices when seam corners disagree while updating actual skinned poses at Film Time, and refuses changed UV seams without a new source revision.
- Native float32 scene-linear raster samples the actual verified source PNG from both vertex and face-varying UVs; installed-app smoke now also creates a genuine original PNG textured face-varying mesh/scene/frozen Take and checks nonzero native texture output, FilmIndex re-open and no FFmpeg or source mutation. The Windows NSIS PyInstaller bundle explicitly includes the native PNG verifier.
- Added native picker/revision approval/denial and symlink tests, real USD seam topology and skinned pose tests, React picker/revision and face-varying seam tests, and deterministic CPU 2×2 PNG row-orientation / UV repeat pixel fixture. The native Win/Linux and React CI matrix contains these tests.

**Acceptance distinction:** This records implementation and wired native test coverage, **not** verified CI passes, independent Windows installed/GPU pixel readback, calibrated display measurements, or projector delivery. Render parity is bounded to source-verified texture coordinates, sRGB→linear decode, and approximate material preview; it does **not** claim Hydra/MaterialX shader equivalence. Further WO2 production hardening requires supported MaterialX graph/multi-material evaluation, physically calibrated color/lighting, texture resource streaming/performance budgets and genuine calibrated GPU/CPU screenshot comparison on the installed app. Those tasks remain open and must not be reported complete from successful source-authority tests.


### WO2 software hardening — OpenPBR, multi-material, GPU evidence and bounded LOD (2026-11-06)

**Committed on WO2 PR #87** and stacked on WO1. This phase extends source-authoritative material fidelity without adding FFmpeg or reclassifying pending Windows acceptance as passed.

1. **Authentic non-overlapping material subsets:** `backend/nvp_wo2_material_slots.py` validates 1–8 source material slots, finite bounded RGB/roughness/metallic, and disjoint triangle-face assignments. Actual `UsdGeom.Subset` prims use the official `UsdShade.MaterialBindingAPI.CreateMaterialBindSubset` interface and genuine `UsdPreviewSurface` binding. Reopening verifies the complete subset set, original face indices, bound shader values and material paths; fabricated material slots fail closed. Native CPU scene-linear raster chooses the correct face material (and does not apply a default texture to an untextured override). Live Three.js groups original materials into no more than 9 **derived** draw groups, reordering ephemeral GPU triangles/UVs only; original USD and frozen Takes stay immutable. All GPU material/texture resources are disposed, including failures during partial construction.
2. **Bounded dual-context OpenPBR:** Added a genuine `UsdShade` `ND_open_pbr_surface_surfaceshader` node and `outputs:mtlx:surface` for new **scalar-only** original base materials, subset materials and skinned actor materials, retaining universal `UsdPreviewSurface` fallback. Reopen verifies exact node identity, terminal connection and RGB/metalness/roughness values. Textured graph nodes continue using verified universal `UsdPreviewSurface` and **must not** imply unimplemented MaterialX image graph equivalence. This is a bounded OpenPBR graph authoring subset, **not** arbitrary MaterialX node authoring, shader-generation admission, or independently calibrated Hydra output.
3. **Source PNG throughput and derived LOD:** Original immutable PNG source acceptance is bounded to 2048×2048 pixels and 8 MiB compressed, with explicit image/color/opacity validation. Every original remains indexed by its own SHA and can be sampled at full resolution by the trusted native CPU renderer. Live WebGL uses a **separately SHA-addressed, explicitly labeled derived preview** at most 512 pixels on its largest edge. The derived preview cannot replace/modify original source bytes, FilmIndex identity or historic Takes. Per-scene data-transfer budget is 8 MiB. The GPU viewer deduplicates identical textures by source SHA, reference-counts their disposal and bounds cache to 16 textures / 16 MiB decoded GPU RGBA estimate. This is bounded derived LOD/caching; full production streaming and arbitrary 4K/8K source textures are NOT implemented.
4. **Evidence:** Added a voluntary real-WebGL framebuffer texture-readback fixture with explicit per-corner expected colors, measured channel errors, and fail-closed unavailable-GPU status; unit tests refuse invented/malformed byte buffers. CPU fixture checks the corresponding original USD bottom-origin UV/PNG texture convention. This is an independent **texture fixture**, not a true end-to-end matching CPU and installed GPU rendering of the same source-authored scene, and not calibrated camera/display or Hydra parity.
5. **Acceptance:** Tests cover original USD face subset authoring/verification, OpenPBR nodes, rig shader context, frozen asset revisions, GPU input policy and trust boundaries. CI and Windows NSIS hidden imports include the new modules; installed native NVP A/V smoke includes a face-subset textured USD Take. **Exact-head GitHub native run results and installed WebView2/GPU measurements remain unverified at this ledger entry**. Do not mark release-grade parity or physical installation complete without real evidence.

**WO2 outstanding production scope despite implementation progress:** renderer-supported comprehensive MaterialX image/normal/roughness/metallic/emission graph evaluation; full Hydra/OpenPBR and calibrated source-light/color parity; direct same-scene CPU↔installed Windows GPU image comparison with numeric tolerances and screenshots; high-resolution progressive texture streaming, real installed minimum-spec performance, and physical display quality assessment. The accepted implementation is a *bounded source-owned rendering subset*, not a complete production film renderer. These hardware/renderer-dependent checks remain explicit follow-up gates rather than hidden completion claims.


### WO2 renderer gap-close continuation — material images, approved tile streaming and source-pixel evidence (2026-11-07)

**Branch:** `nvp/wo2-usd-uv-verified-20261107`, draft PR #87. Development proceeds independently of WO1's queued/cancelled CI. The primary NVP recording/assembly/playback workflow remains FFmpeg-free and data-first.

**Concrete additional software implementation:**

1. **MaterialX image networks:** On real SHA-verified original PNG textured static meshes and UsdSkel actors, author a bounded `ND_image_color3` → `ND_open_pbr_surface_surfaceshader.base_color` graph with `ND_texcoord_vector2`, explicit `srgb_texture` file colorspace and periodic/nearest addressing, while retaining the universally compatible genuine `UsdUVTexture` / `UsdPreviewSurface` graph. The native reopened USD stage verifies the exact authorized symbolic source URI, node IDs, UV and image connections and scalar input values. This is *not* arbitrary MaterialX document execution or a production renderer shader-generator acceptance.
2. **Renderer-resolver sandbox:** `backend/nvp_wo2_materialx_resolver.py` offers an internal, operation-scoped probe context only. It SHA-verifies each original project FilmIndex PNG and creates tightly scoped temporary image files; an anonymous flattened copy of the approved USD stage uses those paths for independent renderer trials. The canonical USD source layers and Take revisions are unchanged and the temporary files are destroyed on scope exit. Unexpected texture source paths are rejected. The installed native acceptance fixture checks immutable stage identity and cleanup. No general-purpose external resolver, network source or permanent flattened media copy exists.
3. **Corrected CPU material shading:** Scene-linear CPU raster now evaluates source sRGB→linear texture colors as base reflectance **before** the existing GGX/Smith/Schlick material/light calculation, instead of incorrectly tinting the already-lit result, including dielectric specular. Constant-white-texture equivalence and dielectric specular regressions were added. This remains an uncalibrated scene-preview lighting approximation, not full Hydra equivalence.
4. **Independent source CPU↔GPU texel comparison:** The approved native source PNG transport carries actual CPU-decoded expected RGB at four fixed UV coordinates, SHA-addressed separately from its original and derived LOD. The installed React WebGL probe renders the same verified source PNG in an unlit nearest-neighbor test plane and reads back 4×4 GPU pixels, comparing each against those native CPU values. Malformed/fabricated data fails closed; results explicitly do not claim full-scene MaterialX/Hydra, hardware acceleration or physical projector calibration. The installed `--smoke-window` workload now creates an authentic frozen textured mesh and drives the real WebView2 probe via a narrowly scoped **smoke-only** native bridge method; ordinary desktop IPC has no such test-only method.
5. **Approved 2K progressive texture tiles:** Native `texture_tile_transport` serves bounded 256px PNG tiles and 0–3 display mip levels from the unchanged SHA-verified full-resolution original. Actual desktop IPC requires the **currently authorized native Take ticket**, exact original project scene asset ID/revision/document SHA and matching original texture SHA; it refuses unbound assets, old ticket/revision and out-of-range tile requests. The React inspector requests tiles sequentially, validates every source and Take identity, assembles one disposable canvas and supports cancellation/progress. The Three.js viewer optionally swaps in this full-resolution canvas as a bounded sRGB GPU derivative; the original USD texture/Take never mutates. A one-image-at-a-time decoded source cache belongs to the native Take session and is discarded upon stop, avoiding up to 64 repeated 2K PNG decodes. These are bounded on-demand source previews for **reusable USD asset-bound meshes**; skinned actor textures remain source-verified in both renderers, but their separate full-resolution tile endpoint is not yet authorized. This is *not* unrestricted 8K streaming or a global movie-image cache.
6. **Actual failure repair:** In DATA-AV-01 Linux native CI, a skinned `faceVarying` UV regression failed solely because a USD float32 primvar was compared to decimal expected values with exact Python list equality (0.10000000149011612 versus 0.1). Changed it to 1e-5 approximate comparison, without reducing source topology or SHA validation. The next exact-head CI run must independently accept the repair.
7. **Added verification:** Source MaterialX graph and colorspace assertions; trusted temporary resolver/cleanup; original PNG CPU/GPU four-corner SHA comparison with tamper refusal; 2K tile seek/mip/out-of-bounds tests; approved Take IPC membership, stop/revocation and re-decoding cache tests; React tile assembly/abort tests; installed native tile authorization and actual WebView2 GPU readback checks. Native test and Windows NSIS packaging definitions were updated.

**Still requiring independent proof:** the newest exact-head Python 3.11/3.13 Linux/Windows and React CI, actual installed WebView2 GPU acceptance; 60-second performance under real textures and actors; calibrated HDR/ACES/source camera lighting/image parity against a supported Hydra render delegate and color-managed display; broader physically meaningful normal/metallic/roughness/emission/opacity MaterialX textures and material variants; larger-than-2K streaming and real minimum-spec memory/thermal budgets. The staged source-authority implementation is not a certification of physically calibrated full film rendering. Other legacy SLATE-06 Blender/preview worker failures should be separately triaged rather than used to weaken WO2's original-material security or resurrect the retired media workflow.


### WO2 skinned full-resolution tiles, transport integrity and native continuity gates (2026-11-07)

**Development committed to PR #87. WO1 CI operations remain independent.**

- **Rigged full-resolution image delivery implemented as a separate authorization path.** A skinned actor is not a reusable asset and must not be authorized with an asset revision request. New `TrustedDataAVController.read_original_rig_texture_tile` and desktop `data_av_original_rig_texture_tile` bind each request to the current approved exact-SHA Digital Take, current original scene revision, `skeleton_layer_sha256`, authored actor `/World/...` path, weighted skin manifest PNG SHA and the actual preserved MaterialX image shader graph. The exact project-owned PNG is verified before tiles can be returned; wrong paths/SHAs/tickets and revoked sessions fail closed. This uses the same 256px tile/mip format and a separate one-rig-at-a-time native session source cache. Native/JS tests cover accepted rig tiles, hostile metadata and cancellation. A separate source rig binding is now emitted by `visual_state` and the React editor offers both asset and rig source selection.
- **WebView2 tile byte integrity:** The browser independently recomputes SHA-256 over the authorized tile's actual decoded PNG bytes using native browser cryptography, refusing altered tile contents or unavailable digest support *before* drawing a tile on the temporary canvas. 2K original source and the derived mip remain separate identities; neither changes frozen takes.
- **Measured continuity harness:** `backend/nvp_wo2_continuity.py` measures native source preview samples at explicit Film Time with source SHA checks, p95/max actual render latency, actual wall time, Python peak traced allocations and cancellation. A second entrypoint uses an actual pinned `FrozenSceneAV` and `NativeSceneLinearRaster` for source-owned camera frames. Tests exercise a 60-second, 600-tick synthetic callback **only to test measurement/control flow** plus a real native OpenUSD one-frame raster. **This does not constitute measured 60s production acceptance**; that requires an exact frozen 60-second source take, actual native CPU scene raster at selected cadence, real installed WebView2/GPU frames, minimum-spec device/resource readings and preserved receipt hashes. The harness never labels synthetic callbacks as proven native rendering.
- **Remaining material/physical gates:** comprehensive source-owned roughness/metallic/normal/emission/opacity image graph handling with physically correct sampling, verified renderer-independent MaterialX/Hydra output, calibrated source lighting/camera/color/physical display, longer-than-2K or mixed scene memory/thermal acceptance, actual installed Windows GPU/NSIS evidence, and exact-head CI repair. These gates remain OPEN; previous pending and cancellation results do not count as passes. No FFmpeg fallback or blanket resolver permissions were introduced.

**WO2 implementation vs evidence:** The skinned and asset texture tile paths are **implemented with regression tests**, not independently native-accepted. The continuity harness is **implemented** but full 60-second real installed benchmark remains unproven. Production renderer parity, physical Windows GPU/display and complete MaterialX/PBR texture channels must not be claimed complete from this ledger.


### WO2 broad PBR material channels and independent renderer / Windows hardware evidence (2026-11-07)

**Repository implementation on draft WO2 PR #87; no FFmpeg added to NVP's source-first workflow.**

**Material-channel implementation:** `backend/nvp_wo2_pbr_channels.py` now accepts exactly five source-owned, SHA-verified original PNG channels: `roughness`, `metallic`, `emission`, `normal`, and `opacity`. Roughness/metallic require true grayscale RGB to prevent CPU red-channel versus Three.js green/blue-channel discrepancies. Emission uses sRGB color; scalar and normal data use raw/linear decoding. The normal source is explicitly rescaled and biased to tangent-space [-1,1]. Opacity is strictly **binary black-or-white cutout**, with 0.5 USD/Three.js threshold and no unsupported alpha blending. These channels are authored to real `UsdUVTexture` and bounded typed `ND_image_float` / `ND_image_color3` / `ND_normalmap_vector3` nodes connected to the genuine OpenPBR surface. Every channel's file SHA, UV connection, source color-space, scalar type, output path and original FilmIndex blob is reverified. No arbitrary MaterialX XML, user shader code, local file path or network resolver is admitted.

**Actual preview evaluation:** The native CPU float32 scene-linear raster now samples the original PNGs by source UV with perspective-correct interpolation and per-pixel GGX response for roughness/metallic, linear emission, and a bounded normal-map tangent basis. Binary opacity discards hidden pixels before writing the depth buffer. Three.js uses the same source-owned channel descriptors as roughnessMap, metalnessMap, emissiveMap, normalMap and alphaMap, with SHA-keyed bounded GPU texture caching, correct raw versus sRGB texture sampling, and scalar fallback override behavior. These remain uncalibrated native preview responses; independent Hydra/PBR physical equivalence has **not** been asserted.

**Characters and authoring UI:** The same five map descriptors are retained in authored UsdSkel manifests and checked against genuine actor USD shader graphs when producing live poses. The trusted desktop PNG picker now lets the creator choose a PBR channel for a separately OS-approved **new immutable reusable mesh material revision**. Existing base-color images, earlier channel maps, original geometry, historical scenes and frozen Digital Takes are preserved. Untrusted grayscale/opacity map inputs are refused rather than silently recoded.

**Independent verification machinery:** `backend/nvp_wo2_hydra_probe.py` creates a tightly scoped derived USD stage, resolves only SHA-approved original image files in a temporary directory, and invokes the actual installed Hydra `usdrecord` executable with a bounded render width/timeout. The receipt distinguishes `HYDRA_BINARY_UNAVAILABLE`, `HYDRA_RENDER_FAILED`, `HYDRA_RENDER_TIMEOUT`, and `HYDRA_FRAME_RENDERED`. Even a real image does not by itself prove parity with native CPU, WebGL or calibrated display. Tests require a genuine independent Hydra image **when usdrecord is actually installed**; missing tools cannot become false render passes. Real calibrated pixel-color comparisons remain a separate gate.

**Windows hardware evidence:** `backend/nvp_wo2_hardware_evidence.py` uses native Win32 `EnumDisplayDevicesW` to enumerate actual Windows adapter names and recognize common software devices. Real installed WebView2 acceptance emits this evidence **after** its source-PNG GPU readback; the WebGL receipt independently records claimed renderer/vendor and flags software renderers. Enumeration, strings and a WebGL texture test are each insufficient to certify a physical GPU, Hydra rendering, camera response or projector color calibration, and all such flags remain explicitly false.

**Regression and packaging:** Added source-PBR static mesh, real skinned USD source, scalar/normal/opacity raster behavior, original film-index revision preservation, hostile channel contracts, native creator approval, independent Hydra unavailable/refusal, Windows adapter evidence and installed multi-channel USD scene smoke. Updated Windows/Linux Python 3.11/3.13 native CI and NSIS PyInstaller imports. Also repaired a preexisting CPU material-subset framebuffer-variable collision and corrected OpenPBR fallback inspection of connected roughness/metallic inputs.

**Verification evidence at authoring time:** The current local Linux tool container has neither the `pxr` bindings, `usdrecord` executable, nor `/dev/dri` device; it therefore cannot run independent Hydra or physical Windows GPU acceptance. Exact-head PR #87 native CI and installed-Windows jobs were queued on the latest commit checked, not passed. Prior USD 01/02 workflows passed on an **older** head; those results cannot clear new PBR gates. **Still outstanding**: successful latest-head native test logs; actual independent Hydra rendered material image and comparison metrics; real installed Windows GPU-classified pixel capture, 60s production throughput and calibrated HDR/ACES/display checks; physical projector/reference display acceptance; and unrestricted advanced MaterialX surface/opacity blending semantics. Production WO2 cannot be marked accepted until these external gates are substantiated.


### WO2 exact-head repair and paired Hydra comparator (2026-11-07)

Implementation on draft PR #87 continues independently of WO1 GitHub operations. **Do not close physical acceptance from implementation-only evidence.**

- **Actual shading failure repair:** Source roughness map pixels turn the microfacet alpha into an array. The previous CPU native shader still used Python scalar `max` and scalar face-normal lighting, so five-channel raster tests could fail or incorrectly ignore normal-map perturbations. Replaced alpha clamp and light/halfway-vector cosine terms with NumPy per-pixel operations, maintaining finite bounded output. The source-native regression now verifies metallic-map changes and a genuine tangent-normal lighting difference.
- **Actual immutable MaterialX validation repair:** A binary opacity image was authored as `ND_image_float` but verified against `ND_image_color3`; verified node identities now agree. Exact original file, source color space, UV graph, and binary cutout remain required.
- **Paired independent renderer evidence:** Added bounded source-authoritative numeric RGB8 comparison (`backend/nvp_wo2_renderer_comparison.py`): exact image dimensions/source and renderer receipt hashes, mean absolute/p95/max error and RMSE, explicit numeric-tolerance result, explicit `physical_display_calibrated=false` and `scene_linear_hydra_parity_proven=false`. The real `usdrecord` Hydra probe can optionally request a frozen Digital Take and native raster at Film Time zero; the comparison runs **only** if source scene SHA and actual pixel dimensions match. It reports dimension mismatch rather than resizing away physical differences. Native float linear Rec.709 preview is converted to RGB8 sRGB for the numeric probe; it does not claim equivalent camera/renderer lighting, display transfer functions, scene-linear equality or film-grade ACES.
- **Independent renderer invocation repair:** Current OpenUSD documents that `--disableGpu` restricts Hydra to CPU-capable plugins, while `usdrecord --imageWidth` derives image height from authored USD camera aspect. The probe defaults to CPU Embree, allows Storm only with explicit GPU admission, and refuses contradictory settings. It records unavailable or failed external renderer outcomes instead of inventing frames. Real renderer installation and GPU-run acceptance are still required.
- **Coverage and CI:** Added numeric image comparison/provenance tests, Hydra paired-Take trust tests, native raster map-response tests, and explicit renderer-admission tests to the Windows/Linux matrix and packaged dependencies. These additions are source changes, not confirmed exact-head green native runs.

**Remaining WO2 release gates:** latest exact-head Win/Linux native CI and installed Windows NSIS/WebView2 outcomes; confirmed full-source Hydra image vs native same-camera image numerical results using an available independent renderer; characterization of mismatched camera aspect/lighting/shader output; calibrated HDR/ACES reference display and physical GPU/projection measurements; representative real 60s loaded-scene performance, cancellation and recovery. Historical cancelled runs and synthetic test passes cannot satisfy these gates. Do not reintroduce FFmpeg into the primary NVP workflow.


### WO2 acceptance hardening — complete channel admission, genuine 60s render and independent reference (2026-11-07)

**Scope and branch:** WO2 draft PR #87, `nvp/wo2-usd-uv-verified-20261107`, stacked on WO1. Work proceeds while older queued GitHub workflows remain separate. The primary NVP workflow stays source-immutable and FFmpeg-free.

**Implemented repairs:**
- Source five-channel PBR publication now validates *every* original PNG and scalar/binary pixel contract before publishing any channel blobs. An invalid later map cannot cause the earlier maps to be partially admitted. Original source geometry and old asset revision SHA are unchanged.
- `backend/nvp_native_scene_linear_raster.py` uses per-pixel NumPy operations for roughness and normal-map GGX lighting; `backend/nvp_wo2_pbr_channels.py` verifies `ND_image_float` for opacity (same type the authoring code creates). Normal and metallic response tests require measurable render differences, not merely successful shader-node construction.
- Corrected `.github/workflows/nvp-data-av01-native.yml`: removed malformed combined YAML path filter, added numeric renderer-comparison module to compilation, and runs **all** new native UI, texture-tile, GPU reference, and installed-probe React tests rather than omitting them from the explicit file list. This repairs missing verification coverage, not an already-proven green CI run.

**Real native 60-second Film Time acceptance:** Added `tests/test_nvp_wo2_real_60s.py` and a dedicated `wo2-real-sixty-second-cpu` GitHub Linux job. It authors a real OpenUSD actor/camera/light scene, exact 60-second shot assembly and frozen Digital Take, then renders 60 *actual native float32 CPU frames* at 1 Hz across 60 seconds of Film Time. Receipts report real wall-clock time, p95/max render latency, peak Python allocations, original Take SHA and per-frame digest. The exact-head result is uploaded as `wo2-native-60s-receipt.json`, never fabricated if the job fails. This tests actual native source continuity at 1 Hz, **not** installed WebView2 GPU at 60 fps, min-spec memory/thermal performance or cinema display quality.

**Paired independent shader-renderer verification:** `backend/nvp_wo2_renderer_comparison.py` requires actual same-resolution native and independent RGB planes, frozen scene/renderer SHA evidence and records MAE/p95/RMSE/max channel differences, without promoting low numeric error into physical parity. The `usdrecord` Hydra probe can compare native frame and independent frame for one real frozen Take at exact Film Time zero; USD-authored 16:9 camera defaults match the native 640×360 target. Added a five-channel texture fixture requiring an actual Embree Hydra frame and same-scene native comparison **when** `usdrecord` exists. If absent, the test skips and release parity remains unaccepted. Renderer error, absence, timeout or dimension mismatch cannot count as a pass.

**Outstanding external acceptance gates:** New exact-head Linux/Windows native regressions and installed Windows NSIS/WebView2 acceptance still need completed passing runs. The local work container has no `pxr`/Hydra binary or device GPU; physical acceleration, calibrated HDR/ACES and projector/display measurements cannot be manufactured there. An installed real 60-second scene with mixed textures, animated rigs, cancellation/recovery and GPU readback must still be measured at target hardware specification. Multi-renderer photographic comparison and MaterialX/Hydra handling of the five-channel source, including shade semantics, must be reviewed against real evidence. Do not mark WO2 fully released from green source-authority tests alone.


### WO2-A–E production-film look implementation and creator/AI admission (2026-11-07)

**Decision:** WO2 must deliver filmmaker-usable presentation excellence for novices, including first-party lighting, environment reflections, camera/lens appearance, texture authoring, translucency and safe AI assistance. A thin minimum/demo renderer is not a production acceptance target. All work reuses the original OpenUSD scene and separate immutable presentation revisions; no second competing scene engine, arbitrary shader programs or FFmpeg active dependency.

**Architecture implemented:** `backend/nvp_wo2_presentation_look.py` defines a bounded first-party `presentation` revision referencing an exact original `scene` id, revision and SHA. Source actors/prop paths and original material channel SHA identities are independently rechecked. A real desktop OS confirmation precedes each new revision; source files, earlier versions, PNGs, rigs and frozen Takes remain untouched. Source-scoped catalog/reload work after application restart. `backend/nvp_wo2_derived_usd_look.py` produces disposable independently inspectable OpenUSD-derived stages, not rewritten originals. `frontend/src/WO2PresentationLook.js` provides matching typed controls and non-authoritative novice-friendly presets. The WebView2 editor and installed binary use the same native look service, not an HTTP source-mutating API.

**WO2-A — shadow/light implementation:** WebGL shadow mapping uses PCF soft shadows with bounded 512/1024/2048 resolutions and filmmaker-facing softness controls. Verified authored `UsdLux.SphereLight` instances are read from the source scene and presented as bounded positioned source lights; the optional creator look provides its own explicitly derived direct key light. Actual USD geometry casts and receives shadows. The independent source-safe USD renderer-look stage authors `UsdLux.DistantLight` and `UsdLux.DomeLight` for deterministic look lighting, without moving captured lights. This is not yet a validated global-illumination equivalence result.

**WO2-B — environment/reflection implementation:** Bundled renderer `RoomEnvironment` is converted to a bounded PMREM environment for physically based surface reflections in `MeshPhysicalMaterial`. First-party neutral studio/daylight/golden-hour/moonlight controls adjust environment light, reflection intensity and source-neutral look rig; the derived USD lighting stage encodes independent dome/key light decisions. Reflection fidelity and artist-grade external HDRI source import are **not yet accepted**. A generated studio map cannot be mislabeled as a captured HDRI.

**WO2-C — source camera/color implementation:** The live viewport uses real authored `UsdGeom.Camera` focal length and meter-aware source lens, independent exposure in stops, opt-in depth-of-field via BokehPass, focus distance and f-stop controls, and an explicitly labeled working filmic (Three.js ACESFilmic) or neutral preview transfer. Derived USD stage authors focus distance and f-stop, and retains view-curve/exposure metadata without mutating source camera. This is **not** a validated OpenColorIO/ACES master, spectral model, or physical projector/camera/lens parity gate.

**WO2-D — texture authoring implementation:** Original FilmIndex PNGs remain SHA-bound with full-resolution tile transport. WebGL now offers per-channel UV repeat/offset/rotation, bounded trilinear mipmapping, bilinear/nearest and 1–16× anisotropy with proper raw/sRGB color-space contracts, memory budgets, resource disposal and immutable image provenance. The derived USD layer authors standard `UsdTransform2d` with parallel MaterialX `ND_UsdTransform2d` nodes and bounded `ND_image_*` filtering; source texture authority is independently checked. Changes are presentation-only. Cross-delegate exact UV appearance still needs native parity evidence.

**WO2-E — transparency/physical material implementation:** Source-bound actor/prop materials use `THREE.MeshPhysicalMaterial` with actual alpha blending, transmission, thickness and index-of-refraction controls. The derived USD PreviewSurface/OpenPBR graph authors opacity, IOR and transmission weight and retains geometric thickness metadata without confusing it with absorption depth. Binary original opacity cutouts remain supported; attempts to combine a fractionally transparent look with a binary source opacity map **fail closed** until a physically valid compositing network exists. Actual multiple-bounce refraction/spectral attenuation require independent high-fidelity verification.

**Creator usability and AI tool boundary:** Nontechnical users can pick meaningful scene moods, select a real original actor or prop, edit its appearance and UV mapping, inspect changes live, publish an OS-approved new source-scoped look and later reopen it. The NVP native bridge can provide a verified, bounded scene/actor/camera/light/material brief to an AI planner and validate an external model's typed look recommendation and explanation without executing code, touching sources, persisting, or granting approval. **This is an AI integration contract and safe first-party guided presets, not a working generative filmmaking agent or local LLM.** Connecting a real model to these tools, iterative shot direction and full script-to-film assistance remain dedicated later AI-layer implementation/acceptance work.

**Tests and packaging:** New native tests cover look versioning, exact source SHA, rejection of unsupported paths/UV channels, AI non-authority, derived USD lighting, look material transmission and matching USD/MaterialX UV transformations. React tests cover look presets, material authoring, source Kelvin bounds and UV/scope refusal. The packaged Windows native smoke additionally approves, catalogs, reopens and derives a real source look, with SHA and original-layer checks. DATA-AV-01 CI includes Python 3.11/3.13 native tests and actual React build/test and PyInstaller imports. No green latest-head acceptance is inferred solely from commits.

**Remaining production work, not waived:** exact-head native Win/Linux regression repair and installed WebView2/NSIS acceptance; real GPU shadow/PMREM/DOF/transmission acceptance across varying hardware; source-owned captured HDRI/environment lighting where applicable; native Hydra/MaterialX look parity and color-managed ACES/OpenColorIO monitoring; representative production complexity over real 60-second playback and memory/cancellation; true AI director integration instead of presets, and clearly documented default studio material libraries for cost-free novice filmmaking. The earlier unrelated SLATE-06 approved-worker and stale UI assertions remain separate CI failures and cannot be relaxed to greenwash WO2. WO2-A through E are **implemented in source but not independently production-accepted**.


#### WO2-A–E final source-admission and accessibility follow-up

A creator or future AI model cannot publish a look with UV controls for a source actor that lacks that original SHA-verified PNG channel. The native look publisher, saved-look reader and AI proposal verifier independently inspect the pinned mesh/rig material source; absent channels and fractional alpha over original binary cutouts are refused. The live WebGL editor checks the same invariants before presenting a change. Existing original PNGs and FilmIndex revisions remain immutable.

For lower-budget systems, the WebGL renderer requests a high-performance device but degrades to valid geometry, direct lighting and source inspection when the PMREM reflection environment is unavailable. Depth-of-field postprocessing also fails to a readable working 3D view with a warning, never claims optical acceptance. The native installed-app acceptance exercises actual OS-approved source-look creation, saved-look catalog/reopen, and a disposable derived OpenUSD stage; CI separately runs native A–E and React tests on the same PR. These paths are implemented, but exact-head Windows GPU/Hydra pass and genuine integrated local generative AI filmmaker remain outstanding.


### WO2 closeout — native failure repairs and constrained production acceptance (2026-11-07)

**Scope decision from creator:** WO2 finishes the deterministic **OpenUSD source/presentation rendering** pipeline. Actor blocking/direction, generative video insertion, the AI filmmaking assistant, and final theatrical mastering are **separate work orders**, not WO2 release requirements. The future AI can propose scene/look specifications; creator-approved deterministic components execute them. Do not expand WO2 merely to emulate general-purpose video generation.

**Actual exact-head evidence inspected:** PR #87 source head `110b2b5` contained four **successful** USD-01/USD-02/USD-02C/USD-02D native workflows; SLATE-06 and DATA-AV-01 were **failed** (not merely queued). In DATA-AV-01, native Linux 60-second OpenUSD CPU continuity and React source audition **passed**. Real source `wo2-native-60s-receipt.json` reported 60 distinct actual native 640×360 renders over 60 seconds of source Film Time at 1 Hz, 3.646 s wall time, p95 58.02 ms, peak Python memory 22,085,012 bytes, matching Take SHA, and explicitly **no GPU or calibrated-display proof**. These are hosted Linux runner numbers, not min-spec physical desktop claims.

**Confirmed native repairs committed after inspection:**
- `backend/nvp_native_usd_texture.py`: trusted OS-picked `pathlib.PosixPath`/`WindowsPath` is a concrete `Path` subclass; the prior exact `type(path) in (str,Path)` incorrectly rejected legal absolute paths. Use `isinstance` while retaining absolute-path, no-symlink, regular-file, descriptor/FSTAT, SHA/OS approval and read-race defenses.
- `backend/nvp_slate_preview_host.py`: approved source manifest does not contain invented `source_cache_key`. The real SHA-bound original ticket `cache_key` is checked separately against freshly reopened FilmIndex source; removed the always-failing imaginary-field comparison without bypassing revocation, TTL, task spec, worker script SHA, actual source Take/SHOT, or cache checks.
- `frontend/src/SlateBranchTimelinePane.test.jsx`: stale test expected no rigged deformation although application now truthfully supports source-bound weighted skinning; assertion now matches current capability while still verifying no final/master approval.
- `backend/nvp_native_scene_linear_raster.py`: scalar-only GGX path restored after previous accidental NumPy replacement; genuine native 60s and source-color regression can run again.
- `backend/nvp_wo2_derived_usd_look.py`: replaced nonexistent `ND_UsdTransform2d` shader ID with real MaterialX `ND_place2d_vector2`; inverse scale and negative offset match USD's scale/rotate/translate UV semantics, with independent assertions covering the same source authoring.
- **Packaged Windows native fault:** Windows PyInstaller package reached the `native_usd_publish_begin` checkpoint then exited via a native process failure, not Python exception. The bundle previously used only `--collect-submodules pxr` and might omit plugin metadata. Updated to `--collect-all pxr` (copies OpenUSD plugin metadata, data and native libraries) and instrumented small opt-in, fsynced exact native USD publication checkpoints so the next installed CI run can identify crash boundaries. This is a **candidate repair**, not a confirmed Windows acceptance pass.

**Expanded representative proof:** Added `tests/test_nvp_wo2_mixed_60s.py`: another full 60-second frozen original OpenUSD scene with a genuinely skinned/animated UsdSkel actor, original five-channel PBR textured mesh, real camera, dual authored lights and time-varying actor motion. The dedicated CPU job now runs this **in addition** to the completed simple scene and uploads both actual source-sha/latency/memory receipts if successful. This is representative deterministic rendering evidence, not installed GPU/hardware quality certification.

**WO2 closeout remains OPEN until:** new exact-head native Windows/Linux and React suites pass without security relaxations; Windows packaged NVP.exe creates and reads an actual native USD scene and completes installed smoke; genuine Hydra/MaterialX full-scene shader comparison has external renderer evidence (not a skipped test); and source camera/shadow/reflection/transparency rendering is tested on a real GPU with documented acceptable quality, cancellation and failure behavior. Physical theatrical projection/color mastering belongs elsewhere. Do not mark WO2 production-closed based only on available CPU or skipped external tests. After those gates, lock WO2-A–E scope, record actual release SHA, move on to next work order.


## WO3 — Native SMPTE cinema packaging, JPEG2000 and MXF (2026-11-07)

**Scope:** Cinema *package construction and independent essence verification* only. WO4 owns calibrated cinema/HDR picture and final PCM mastering. WO5 owns production throughput, installed Windows hardware, external reference/projector ingestion and formal acceptance. Actor direction, video generation, and AI filmmaking assistant remain separate areas. Original OpenUSD scenes, Digital Takes, original textures and source PCM are authoritative and never overwritten. FFmpeg is not used in the core or native cinema pipeline.

**Current development branch and PR:** `nvp/wo3-native-dcp-complete-20261107`, draft PR #89, stacked on WO2 draft #87. The older WO3 #88 branch preceded WO2 cleanup and was closed *without merge* after checkout omitted WO3 source files. PR #89 contains the full current implementation.

**WO3-01 — real SMPTE metadata/file auditing:** `backend/nvp_wo3_dcp_structure.py` reopens an explicitly selected local single-volume DCP and checks AssetMap/PKL/CPL namespace and UUID identity, bounded XML/DTD/XXE, relative plain filenames without symlinks or traversal, complete mapped files, PKL SHA-1 plus SHA-256 receipts, correct picture/sound Reel references, no aliasing or missing files. No arbitrary subprocess or automatic conversion. Synthetic MXF bytes with valid metadata may pass *structure* but always return `mxf_essence_verified=False`, `production_dcp_accepted=False`, `independent_dci_compliance_verified=False`. Native Win 2025/Linux 24.04 Python 3.11/3.13 structural suites passed on preceding exact heads, later repeated on current PR #89.

**WO3-02 — native 12-bit XYZ JPEG2000:** `backend/nvp_wo3_native_codecs.py` packages actual original-approved XYZ12 big-endian 2K PPM into a privately staged input, runs a SHA-verified reviewed OpenJPEG binary with bounded `-cinema2K 24 -p CPRL -mct 0 -I` arguments and no shell, hashes output and independently checks raw JPEG2000 SOC/SIZ/COD markers. `backend/nvp_wo3_j2k_audit.py` checks three unsigned 12-bit components, real 2K shape, one tile, cinema RSIZ, CPRL one-layer coding; **not full decoded visual fidelity or DCI certification**. Actual Ubuntu OpenJPEG native job **passed** and generated a real 1998×1080 12-bit J2K (389 bytes for constant XYZ frame; SHA-256 `126d46035c2ef117571e9dcd0f0eb298723ac014b8729d4eb8955b4b38986752` on that exact runner). Release still needs packaged binaries and independent decoded pixel/image quality tests for representative film rather than flat-constant source.

**WO3-03 — native SMPTE MXF wrapping:** `backend/nvp_wo3_mxf_native.py` sends source-SHA-verified JPEG2000 sequences and real PCM24 48 kHz WAV to SHA-pinned CineCert `asdcp-wrap -L`, demands matching 24 fps MXF identity/frame count, uses an independent native `asdcp-info -i -d` readback and binds returned SHA to original frozen Take. Source approval and binary identity are not supplied by browser/LLM. Actual MXF success awaits native test. CineCert `asdcplib` source pinned at commit `905d6047f67c8211c2d22f29fb0e2e44c142b59b`, BSD-3-Clause; OpenJPEG license and OpenSSL/Xerces built dependencies require binary documentation before release. No FFmpeg dependency.

**WO3-04 — actual native SMPTE package author:** `backend/nvp_wo3_dcp_package.py` writes new CPL/PKL/ASSETMAP/VOLINDEX XML with distinct UUIDv4 track/Reel/CPL/PKL IDs, authoritative 24 fps duration, independent SHA-1 file hashes required for PKL, and SHA-256 source receipts. Requires real frozen OpenUSD Take and temporal checkpoint verification **before and after native creator approval**, a trusted OS-selected output directory, hashes of the native MXF bytes and no overwriting of existing original Take. Builds in disposable staging, independently reopens package, publishes a new non-destructive FilmIndex `presentation` revision depending on exact `source_take`. Report explicitly calls the result `STRUCTURAL_DCP_CANDIDATE_PUBLISHED`, with `production_dcp_accepted=False` until full external evidence exists. True OS-level atomic no-replace across process crashes and cleanup/recovery need installed acceptance.

**WO3-05 — actual essence round-trip verifier:** `backend/nvp_wo3_independent_essence.py` strictly rechecks package SHA/UUID, runs reviewed SHA-bound `asdcp-unwrap`, verifies *every* extracted original JPEG2000 source frame against its source-approved SHA, uses native OpenJPEG decode to inspect all XYZ12 picture data and a WAV reader to compare unwrapped PCM24 samples exactly with the approved source sound SHA. It records exact native source and binary SHA and keeps `formal_independent_dci_validator_passed=False`, `physical_projection_accepted=False`, `production_dcp_accepted=False`. A second process running the same codec family is not equivalent to an independent DCPDoctor/DCI laboratory result.

**Cross-platform and real native CI:** `.github/workflows/nvp-wo3-dcp-native.yml` has Win/Linux Python 3.11/3.13 with official OpenUSD 26.11, real full 2K OpenJPEG CI encode, and a separate real 2-frame OpenUSD→J2K→CineCert SMPTE picture/PCM MXF→CPL/PKL/AssetMap→full JPEG2000/PCM24 unwrapping job. CineCert is checked out at an exact reviewed commit and compiled in that job without optional encryption/XML dependencies. Independent tests reject damaged PKL/MXF, DTD, symlink, SHA, incorrect timestamps, non-XYZ source, non-pinned tools, unapproved source and forged receipt identity. **Do not infer final native production acceptance from passing metadata tests.**

**Outstanding gates:** get an exact-head green native CineCert build/wrap/unwrapped-pixel and sound result; repair real native errors without weakening source checks; production 2K Flat/Scope and 4K profile, rate-limit and color/output validated on varied frames; external DCPDoctor or other genuinely independent MXF/JPEG2000 validator and formal SMPTE XML-schema proof; bundle reviewed codec binaries into Windows/ Linux single installer with all license notices, signed provenance; crash/restart output reconciliation and true no-overwrite native destination handling; WO4 exact cinema XYZ/PCM mastering; WO5 independent cinema server/projector ingest and physically calibrated exhibition. Keep WO3 open for these actual release gates.


### WO3 exact-head native all-green acceptance — three-frame SMPTE picture/sound (2026-11-07)

**Actual independent job evidence:** exact WO3 commit `05c58b6b5658c3689930047eb46182374a244683`, native GitHub run `42348314654`, completed **all six CI jobs SUCCESS**: Windows 2025 Python 3.11/3.13 and Linux 24.04 Python 3.11/3.13 DCP structure/real-source admission; genuine Linux OpenJPEG 2K/4K 12-bit cinema codestream creation; and genuinely compiled CineCert `asdcp-wrap`/`asdcp-info`/`asdcp-unwrap` real OpenUSD→three 2K XYZ12 JPEG2000 frames→SMPTE picture MXF and native PCM24 48 kHz sound MXF→CPL/PKL/ASSETMAP/VOLINDEX→exact original J2K codestream SHA readback→three independent OpenJPEG frame decodes→extracted PCM byte-for-byte source SHA verification. This is the first verified genuine executable codec/MXF/DCP pipeline (not an XML fixture). Actual 3-frame test native picture MXF SHA-256 `c81ee0cda74a727f4b20d02aba5a87c4960eec235924674916aa78842014b607`; sound MXF SHA-256 `f2e53ddd665860d70ac3250103bed9c51bab88c4492398d05908b0255590c49f`; frozen original Take SHA-256 `db8188de072fd4aab5d6d0cb8b4d461e38e9419df3cb37f123d2737465d6ce2e`. Real J2K 4K standalone test also passed; this is NOT full 4K MXF acceptance.

**Failure repairs proven:** early incomplete WO3 PR #88 was closed; #89 correct ancestry. Initial exact-head tests caught independent DCP checksum ordering and canonical Windows temp directory aliasing, repaired. Actual CineCert short-reel `asdcp-info` crashed with SIGFPE due to averaging by `ContainerDuration - 2`; NVP now refuses fewer than three frames before invoking it. The integrated test now uses three real picture/sound frames. Official OpenJPEG PPM decoder prefixes a version comment and CineCert sound unwrap writes the selected prefix without `.wav`; the source reader was repaired for both actual native formats. Full real 3-frame pipeline is now green, with independent codestream and sound SHA reconciliation.

**Production acceptance intentionally OPEN (WO3 next gates):** This exact 3-frame source uses a nearly constant image and short sound, not representative long-form quality, rate/bandwidth and failure recovery. Independently schema-validate all SMPTE XML plus a second, separate implementer's J2K/MXF decoder and strict DCP Doctor; verify realistic varying frames at both 2K Flat/Scope and 4K, codec bitrate and chromatic XYZ12 accuracy; confirm audio label mapping and mix once WO4 PCM mastering is present; package the reviewed BSD-2 OpenJPEG and BSD-3 CineCert binaries and license notices in the real installed NVP Windows/Linux app; prove secure destination selection, cross-process atomic no-overwrite, crash-resume reconciliation; WO5 projector/server ingest and physical calibrated acceptance. No claims of genuine cinema projection, SMPTE/DCI compliance certification, installed application acceptance, or 60-second full cinematic mastering. WO3 native code is **implemented with a genuine green 3-frame codec/MXF acceptance test**, not fully production-closed.


### WO3 export restart reconnaissance (2026-11-07; implementation, not acceptance)

Added `backend/nvp_wo3_export_recovery.py` and `tests/test_nvp_wo3_export_recovery.py` to provide **read-only** enumeration of bounded NVP staging directories and published DCP UUID directories after a crash. An independently validated SMPTE structure and SHA-256 hashes of **all** XML and MXF files are compared against explicitly host-supplied trusted FilmIndex presentation receipts. The result separates (1) staged/uncommitted candidates, (2) packages published without a corresponding ledger receipt, (3) exact ledger-and-filesystem matches, (4) tampered/hash-mismatched or incomplete packages, and (5) ledger entries whose directories are missing. Symlinks are never followed, no files are deleted or automatically promoted, and even full ledger+structure parity never claims cinema compliance. The native Windows/Linux 3.11/3.13 workflow now compiles and executes the regression suite.

**Still open:** the production author must integrate a host-controlled reconciliation UI; enforce true cross-process atomic no-replace at final destination; fsync parent/commit transition and prove crash injection at each boundary; source receipt input must come from the actual trusted FilmIndex API rather than user/browser JSON. New exact-head CI remains unverified until jobs finish. This increment is not a crash-safe transactional publisher, and it does not close WO3 or WO5.


### WO3 sequential production-gap implementation (2026-11-07)

**WO3-06 kernel-backed atomic no-replace publish — IMPLEMENTED, native acceptance OPEN.**
`backend/nvp_wo3_atomic_publish.py` uses Linux `renameat2(RENAME_NOREPLACE)` or Windows `MoveFileExW` without replacement; unsupported systems fail closed, not back to check-then-rename. `nvp_wo3_dcp_package.py` fsyncs the staged directory after fsyncing staged files, then uses the no-replace primitive before writing FilmIndex revision. Cross-process collision, existing user directories, same-parent restrictions and symlink refusal are covered by `test_nvp_wo3_atomic_publish.py` on native Windows/Linux. Staged orphan exports remain read-only review items on startup. Production true end-to-end crash injection, Windows power-loss durability, installed-app restart, and trusted host presentation-ledger UI remain OPEN. A crash after publishing and before FilmIndex commit must never be called a committed presentation.

**WO3-07 additional independent SMPTE structural invariants — IMPLEMENTED, schema evidence OPEN.**
`backend/nvp_wo3_dcp_structure.py` now checks AssetMap per-file Chunk Length against actual PKL/CPL/MXF sizes, requires canonical Reel UUID, explicit 24/1 picture/sound edit rates, bounded intrinsic/entry/duration and identical picture/sound reel durations. Hostile fixtures intentionally rehash/rebind altered XML so semantic checks, rather than only PKL SHA, must fail. This is independent local semantic validation, NOT official SMPTE XML XSD validation, a second developer's MXF checker, or a DCPDoctor external acceptance receipt; all three remain separate release requirements.

**WO3-08 variable original XYZ12 codestream quality — IMPLEMENTED test, real result OPEN.**
`tests/test_nvp_wo3_real_variable_quality.py` produces a nonconstant 16-patch 2K Scope XYZ12 picture, genuinely runs approved OpenJPEG cinema encoder and decoder, checks raster dimensions/12-bit XYZ, numerical sampled-channel differences, preserved contrast and compressed bytes, and leaves certification false. Added to genuine Linux OpenJPEG job beside existing 2K Flat and 4K Full codestream fixtures. Extended varied full 4K MXF with representative temporal motion, bit-rate envelopes, independent decoder and WO4 color-quality acceptance remain OPEN.

**WO3-09 codec bundle provenance/license gate — IMPLEMENTED validator, actual installer OPEN.**
`backend/nvp_wo3_codec_bundle_provenance.py` requires all five exact native tool roles, SHA-256-pinned binary files and the corresponding full OpenJPEG BSD-2 / asdcplib BSD-3 license-notice files, rejects symlinks, missing entries, path traversal and modified bytes. `tests/test_nvp_wo3_codec_bundle_provenance.py` checks negative cases across native OS matrices. The manifest must be supplied from a trusted vetted release process; its signature and transitive native DLL dependency audit are **not** implemented, and the production Windows/Linux installer does not yet stage these real reviewed binaries or license texts.

**Important acceptance:** These code changes and CI jobs do not complete independent DCPDoctor/external cinema ingest, full 4K MXF, formal XML schema verification, distributor packaging, installed Windows user interaction or physical projector acceptance. Keep WO3 in verification/production-hardening status until actual exact-head native receipts and external evidence are obtained. No FFmpeg runtime.


### WO3 licensing disposition (creator decision, 2026-11-07)

**Decision: APPROVED IN PRINCIPLE.** OpenJPEG BSD-2-Clause and CineCert asdcplib BSD-3-Clause are sufficiently permissive for NVP's native cinematic pipeline. NVP will not modify or remove upstream copyright attribution. Do not block WO3 implementation on further licensing discussion. Preserve each required copyright/license notice and BSD-3-Clause non-endorsement provision in distributable packages, document third-party runtime/build dependencies, and keep reproducible SHA-pinned release artifacts. Exact native binary bundle inclusion, notices, and dependency inventory are packaging/acceptance tasks, **not unresolved permission to use the licenses**. No FFmpeg.


### WO3 trusted FilmIndex restart integration (2026-11-07)

Added `backend/nvp_wo3_project_recovery.py` to retrieve historical presentation revisions from the native project's real local FilmIndex, validate single source-Take dependency and no-original-mutation custody, and feed those trusted durable records into the read-only export scanner. This closes the earlier untrusted caller-supplied receipt interface at the **host adapter** level: UI/browser/LLM cannot invent accepted receipt hashes for this entrypoint. Regression fixtures in `tests/test_nvp_wo3_native_delivery.py` now publish a genuine structural export, reload from persisted FilmIndex, and detect modified exported VOLINDEX metadata without updating the original source or approving cinema readiness. Native CI compile/test includes the adapter.

**Current observed CI:** native WO3 run `42349957081` at prior commit `b526cfd8` completed SUCCESS; previous run `42349929367` also completed SUCCESS. The present FilmIndex adapter commit still requires a fresh exact-head run; do not infer its pass from earlier heads.

**Remaining:** crash-kill injected at real staging/fsync/publish/database boundaries and restart reconciliation across processes; real installed Windows host/UI admission and packaging; standards-sourced SMPTE XML-schema validator and separate vendor DCP checker; varying multi-frame full 4K MXF and independent pixel/rate evidence; physical projection in WO5. Reconciliation identifies inconsistencies but never automatically deletes or repairs user packages.


### WO3 abrupt process termination at publish boundary (2026-11-07)

`tests/test_nvp_wo3_crash_publish_process.py` now executes the real OS-specific `atomic_publish_directory` primitive in a separate native Python process and forces `os._exit(91)` immediately after publication. Parent inspection verifies the complete published directory and bytes survive the child process's abrupt exit; a separate conflicting existing destination exercise confirms the creator's previous files are not replaced and staged bytes remain. Included in native Windows/Linux Python 3.11/3.13 CI. This tests a **real process exit** rather than only exception-based cleanup. It does **not** simulate kill during each write/fsync, actual power loss, or source FilmIndex database commit failure, and does not constitute installed-app acceptance. Those gates remain outstanding. No FFmpeg used.


## Distribution-wide third-party license custody — creator directive (2026-11-07)

**MANDATORY FOR EVERY NVP RELEASE, INCLUDING COMMERCIAL DISTRIBUTION:** Inventory all third-party code, tools, binaries, DLLs/shared libraries, assets and other redistributables actually shipped with NVP. For every dependency whose license requires an accompanying copy, copyright notice, attribution, disclaimer or other distribution notice, retrieve and retain the actual applicable upstream LICENSE/COPYING/NOTICE text at the exact version/source revision being packaged. Include it in the installed application distribution and any appropriate consolidated Third-Party Notices/License directory, preserving the copyright holders' text rather than paraphrasing it. Verify the files are packaged for Windows/Linux and that installer/uninstaller tests preserve the notices while NVP is installed. Do not distribute a component if required notices or redistribution permission cannot be verified; check transitive binary and asset licenses too. Maintain a provenance manifest containing package identity, upstream URL/revision, license identifier, notice source/hash and bundled installed path. This requirement applies beyond WO3 and must be checked by the release/package pipeline.

**BSD-2-Clause and BSD-3-Clause:** permissive commercial, modification and redistribution are acceptable; publishing changes upstream is not mandatory. Retain upstream copyright/license/disclaimer text, and respect BSD-3's non-endorsement restriction. This decision is resolved: further licensing debates do not block WO4 development. Actual notice collection/package validation remains a release task.

## WO3 → WO4 handoff (2026-11-07)

Proceed with WO4 cinema picture and audio mastering on a branch stacked on the current WO3 work. WO3 remains **implemented with acceptance gaps**, not formally production-closed. Keep outstanding exact-head native tests, independent SMPTE XSD/second implementation DCP review, variable-content 4K MXF, installed Windows/Linux codec package evidence, full crash-boundary and cinema projection gates visible; do not misrepresent their status. WO4 owns explicit reference image color transform/XYZ12 decision provenance and approved 48 kHz PCM24 film mastering and channel layout. Digital Takes, camera/scenes, original sound and 7,056,000,000-tick Film Time remain immutable. No FFmpeg paths.


## WO4 — Cinema picture and final PCM mastering (started 2026-11-07)

**Development branch:** `nvp/wo4-cinema-mastering-20261107`, stacked on WO3 PR #89. No FFmpeg. Input source Take, PCM and approved OpenUSD records remain authoritative. WO4 owns picture color mastering including explicit scene-linear-to-cinema XYZ12 transforms, validated display/color intent, and accurate final audio PCM24; WO5 owns external cinema/projector acceptance.

**WO4-01 PCM24 mastering candidate — IMPLEMENTED, native acceptance OPEN:** `backend/nvp_wo4_pcm_master.py` accepts only explicit creator approval, SHA-256-verified original PCM data and frozen Take identity, exact 24 fps / 48 kHz sample duration, declared stereo/5.1/7.1 channel order, and a bounded rational mastering gain. Uses deterministic signed 24-bit integer math, fails closed on clipping instead of silently normalizing, emits genuine RIFF/WAV PCM24 and immutable source/master SHA receipts and keeps production loudness certification false. `tests/test_nvp_wo4_pcm_master.py` covers bit-exact identity, negative-value rounding, clipping refusal, consent/source SHA rejection, 2/6/8 channels and WAV readback. `.github/workflows/nvp-wo4-native-mastering.yml` adds real Windows/Linux Python 3.11/3.13 CI; **no latest-head result verified yet.** Note that channel labels are explicit in the receipt, not yet an independently verified DCI theater channel mapping.

**Next WO4 implementation order:** WO4-02 explicit source-linear RGB→XYZ12 color transform with fixed verified color-space decision provenance and out-of-gamut policy; WO4-03 calibrated reference image and waveform/loudness measurements; WO4-04 NVP immutable Take/Frozen Assembly UI approvals and source-bound presentation records; WO4-05 integrate WO3 native J2K/MXF pipeline with the mastered audio/picture and independent picture/sound master QC. Do not claim theatrical sound/color quality from a deterministic PCM conversion alone. Native Windows installer and physical projector acceptance still open.


### WO4-02–05 sequential implementation (2026-11-07)

**WO4-02 — IMPLEMENTED code, exact-head native CI OPEN:** `backend/nvp_wo4_xyz12_master.py` converts explicitly graded *linear sRGB D65* (little-endian float32, 3 channels) to CIE XYZ and then quantizes SMPTE ST 428-1 DCDM XYZ12 using 48 cd/m² mastering reference, 52.37 cd/m² normalization, inverse gamma 2.6, and nearest integer. Records exact source SHA, untouched Take SHA, input color contract, D65 white intent, no chromatic adaptation, code range and derived SHA. Rejects NaN, infinity, out-of-range/gamut values and unapproved input; **does not claim DCI projector-white adaptation, independent calibrator precision, output-quality verification or completed HDR/ACES/OCIO color management.** Standards references: SMPTE ST 428-1:2019 and SMPTE RP 431-2:2011. `tests/test_nvp_wo4_xyz12_master.py` checks output encoding, source immutability and invalid colors.

**WO4-03 — IMPLEMENTED code, exact-head native CI OPEN:** `backend/nvp_wo4_master_qc.py` verifies actual XYZ12 and native WAV/PCM24 SHA and count, measures per-component XYZ code extrema/mean, actual signed PCM24 peak, fractional RMS and sample peak dBFS. Deliberately leaves integrated loudness LUFS, true-peak/oversampling, calibrated color, screen HDR/SDR measurements and production/master acceptance false. `tests/test_nvp_wo4_master_qc.py` covers real samples and tamper rejection.

**WO4-04 — NATIVE LEDGER BACKEND IMPLEMENTED, installed creator UI OPEN:** `backend/nvp_wo4_mastering_decision.py` authenticates exact frozen original OpenUSD Take, compares its source/derived picture/audio QC SHA receipts, obtains native creator approval over the precise scope, re-verifies after approval and writes only a new immutable FilmIndex `presentation` dependency on source Take. The master is a disposable derivative; never changes original Digital Takes or film-time events. `tests/test_nvp_wo4_mastering_decision.py` uses a genuine FilmIndex frozen USD Take fixture to prove approval, refusal and tampered source denial. The real installed creator mastering panel is not yet implemented or accepted.

**WO4-05 — NATIVE DELIVERY ADAPTER IMPLEMENTED, real integrated acceptance OPEN:** `backend/nvp_wo4_master_delivery.py` requires prior trusted WO4 mastering decision, matching picture/audio Take SHA, exact PCM24 WAV frame timing/channel depth and sample SHA, and actual approved XYZ12 SHA; then invokes existing reviewed OpenJPEG encoder, CineCert MXF picture/sound wrappers and strict WO3 native SMPTE publisher. Initial scope is only an approved single image held for a three-or-more-frame short reel. Motion picture sequence requires a separate ordered frame-identity decision, not fabricated authorization by repeating one SHA. `tests/test_nvp_wo4_mastering_decision.py` verifies rejection when decision missing or sound/image SHA changed. Production DCP/color/loudness acceptance remains FALSE.

**Verification:** Prior WO4-01 native CI `42350799668` SUCCESS. Added Windows 2025/Linux 24.04 Python 3.11/3.13 source approval, picture conversion and QC suites to `.github/workflows/nvp-wo4-native-mastering.yml`. Results at latest code head have not yet been inspected, therefore do not label WO4-02–05 accepted.

**Remaining critical WO4:** run/repair latest native CI; add representative full real integrated WO4→WO3 2K/4K picture+PCM J2K/MXF/DCP roundtrip; approve source-authentic *ordered motion frame* sequences; actual installed native creator color/audio mastering UI and OS consent; standardized 5.1/7.1 channel assignment, K-weighted loudness/true-peak and mix QC; physically measured, display-calibrated color, DCI reference white/chromatic adaptation and independent mastering assessment. WO5 projector/server ingest and external distribution continue separately. No FFmpeg.


### WO4 regression and bridge tightening (2026-11-07)

WO4-05 now independently opens real candidate WAV and verifies exact signed PCM24 sample SHA, 48 kHz rate, declared channel count and 2,000 samples/channel for each 24 fps picture before calling native MXF wrapper. The new positive adapter regression uses actual approved FilmIndex metadata and mocked codec boundaries to prove the exact candidate picture bytes/PCM WAV are passed onward; hostile tests reject missing decision and altered picture/sound SHA. The adapter test **does not claim native full J2K/MXF execution**. WO4-03 QC's 12-bit big-endian test fixture was corrected. The earlier WO4-01 full native matrix passed (run `42350799668`), while the newer WO4-02 through WO4-05 native workflow was queued at last inspection. Keep acceptance OPEN until the new exact-head result and repairs. Physical color/loudness mastering, real animated ordered-frame master, native installed creator UI, and real WO4→WO3 full DCP pipeline remain outstanding.


### WO4 ordered-motion, standards QC and real DCP integration increment (2026-11-07)

**Implemented and committed:**
- WO4-02 now supports separately authorized *D65 unadapted* or *Bradford D65→cinema reference x=.314/y=.351* white intent; both preserve immutable original picture source, explicit color metadata and uncalibrated projector status. SMPTE ST 428-1 quantization remains source-controlled, no silent tone mapping or clipping. Physical measurements are OPEN.
- WO4-03 now includes a native 48 kHz BS.1770-style K-weighted gated 400 ms / 75% overlap loudness diagnostic (`backend/nvp_wo4_loudness.py`), ignoring LFE, applying channel weights, -70 absolute and -10 relative gates. It does not fabricate a loudness result for reels shorter than 400 ms, and its reference accuracy/true peak remain OPEN. `evaluate_master_candidates` records available real metrics; the creator mastering decision remeasures QC rather than trusting model/browser statistics. Source SHA, picture-code statistics, WAV timing and PCM sample SHA are revalidated.
- WO4-04 permits **distinct ordered source-verified XYZ12 motion frames**, records their exact SHA sequence and 294,000,000 Film Time ticks per 24 fps sample inside the frozen Take's actual temporal duration. Each approval scope is deep-copied before invoking the native creator callback, all source picture/audio bytes are rechecked after consent, and a mastering ID may not silently be reused/revised (FilmIndex commit uses expected_revision=0). Original Take never changes.
- WO4-05 now accepts the ordered-frame manifest instead of requiring one repeated frame SHA, but requires exact matching picture bytes/PCM samples before calling native OpenJPEG/CineCert/SMPTE publisher. Added real end-to-end native test `tests/test_nvp_wo4_real_delivery.py`, using **three different** full 1998×1080 WO4 linear-RGB-derived XYZ12 frames and a real frozen OpenUSD Take; it invokes actual native OpenJPEG/cinema J2K, asdcplib picture/sound MXF and SMPTE DCP production and unwraps/decodes each picture/audio source. Dedicated `.github/workflows/nvp-wo4-real-cinema.yml` compiles CineCert from reviewed SHA and runs this test, not a mocked codec. **The workflow has been queued and has not returned a verified passing receipt.**
- Added cross-platform regression tests for separate Film Time range, source tampering, forged QC, approval callback mutations, distinct frame sequence SHA, immutable decision ID reuse, true source sound and LFE metering. All code is committed; native test acceptance is not falsely inferred.
- Formal requirement matrix: `docs/NVP_WO4_ACCEPTANCE_MATRIX.md`. This documents exactly which native, installed hardware, third-party license, reference white and external physical receipts are still missing.

**Observed actual CI:** WO4-01 baseline run `42350799668` previously passed. Latest WO4 native and real-cinema pipelines at commit `27fa3111`, runs `42352444909` and `42352444923`, were **QUEUED** at inspection, not independently accepted; later commits are unverified.

**Outstanding, cannot be marked finished from current environment:** real new-head CI pass/failure repair; independent calibrated projector/reference image assessment; independently calibrated programme loudness plus oversampled true-peak proof; native installed Windows/Linux mastering controls and approved OS picker; long variable-content 2K/4K memory-bounded streaming J2K/MXF (the current WO3 wrappers still keep whole short reels in RAM); full integrated longer 4K and failure-recovery testing; independent SMPTE DCP schema/checker and projector ingest in WO3/WO5. Do not mark WO4 cinema production-complete, or silently relax those gates. No FFmpeg anywhere in the native WO4 pipeline.


### WO4 disk-streamed native audio and MXF implementation (2026-11-07)

**WO4-06 — File-streamed source PCM24 master, IMPLEMENTED; native CI acceptance pending.**
`backend/nvp_wo4_pcm_stream.py` opens only a host-selected, SHA-256-verified original raw interleaved signed PCM24 file; validates sample count at 48 kHz and 24 cinema frames/s, channel declaration, frozen Take digest and exact source SHA *before and after* native approval. It processes 4,096 audio frames per block (not a whole file), deterministically applies the same rational gain/clipping policy as WO4-01, fsyncs an output WAV and atomically publishes a new uniquely named file via filesystem hard-link creation (never replacement). It returns source/master SHA, published WAV SHA, sample-channel/timing/peak evidence, and explicitly retains `production_audio_accepted=False`. It rejects classic RIFF payloads that would exceed its 4 GiB limit rather than silently producing invalid files; RF64/reel partitioning is still open. `tests/test_nvp_wo4_pcm_stream.py` exercises exact existing WO4 PCM byte parity, half-gain rounding, clipping/no output, denial and SHA refusal, symlink refusal and protection of existing creator exports on native Win/Linux.

**WO4-07 — Disk-backed native CineCert sound MXF, IMPLEMENTED; actual codec run pending.**
`backend/nvp_wo4_mxf_stream.py` consumes the file-backed WO4-06 WAV receipt, rehashes the complete WAV and native PCM samples, requires actual reviewed SHA-pinned CineCert asdcp-wrap/info tools, uses a separately staged, streamed private WAV copy (bounded RAM but additional disk), wraps SMPTE 24 fps sound MXF, verifies the real MXF edit-rate/asset UUID/frame count, rechecks original WAV after execution, fsyncs the MXF file and publishes with cross-process no-replace hardlink. Returns MXF file path/hash/bytes rather than the full MXF bytes. `tests/test_nvp_wo4_real_stream_mxf.py` exercises real native WAV→MXF→asdcp-unwrap and exact unwrapped PCM SHA in a new step of `.github/workflows/nvp-wo4-real-cinema.yml`. Do **not** claim pass until this current exact-head CI job actually finishes. Current WO3 picture track / DCP package author still uses in-memory MXF blobs, so complete full-length DCP is **not** yet memory-bounded.

**WO4-08 — File-streamed native gated loudness, IMPLEMENTED; native CI pending.**
`backend/nvp_wo4_loudness_stream.py` performs SHA-bound WAV QC by reading audio in small packets with a 19,200-sample (400 ms) rolling window, at most one derived energy result per 4,800-sample step, instead of materializing the full PCM track and energy arrays. It uses the existing K-weighting/relative and absolute gates and ignores LFE, with true-peak and external standards calibration still `False`. `tests/test_nvp_wo4_loudness_stream.py` checks genuine stereo sine-wave agreement with WO4's in-memory reference diagnostic, short/silent samples, LFE-only signals and corrupted file refusal. Added to Win/Linux Python 3.11/3.13 CI.

**Scope boundary:** The disk-streamed WAV/MXF sound track is an incremental step toward feature-length mastering. Final SMPTE DCP authoring, picture JPEG2000 frame streaming/long-term source custody, feature-sized archive constraints, RF64 and external DCP/visual/audio calibration are not completed by these modules. Native installed creator approvals remain required. No FFmpeg reintroduced. Latest submitted commit and runs must be checked before any acceptance update.


### WO4 streamed-audio closeout checkpoint (2026-11-07)

**Current implementation head before this ledger update:** `1afbc98d5e8f9779f18d3b36347c86c2e0429740`. A further native Windows/Linux file-stream test now forces the creator-consent callback to delete the approved source path or replace its bytes. The source deletion case proves the staged WAV handle is closed and the partial stage is cleaned without publishing a bogus master; replacing the source keeps the approved SHA check as a hard stop before publication. The stream's resource-acquisition order was repaired for Windows cleanup. Existing user files are not replaced. These tests have **not** yet returned native CI pass results.

**Exact observed CI:** WO4 native mastering run `42353332506` and WO4 real native cinema run `42353332623` were both `QUEUED` at inspection; no failure logs or pass receipts were available. All WO4-06/07/08 capabilities are code-implemented with tests submitted, not independently accepted. The previous WO4-01 baseline success is not proof for this new head.

**Next work still required:** native test failure repair once jobs execute; long-form disk-backed picture codestream/MXF and source-bound final DCP author (the in-memory picture/DCP path remains), true on-disk feature-duration throughput/crash/cancellation tests; RF64 or explicit split for audio beyond classic RIFF; installed desktop creator grant/OS picker; exact third-party notices in installers and independent color/audio/cinema compliance. WO3 and WO5 external acceptance remain separate.


### WO4 source-isolated MXF worker security repair (2026-11-07)

Replaced the initial hardlink of the approved WAV into the CineCert staging area. A hardlink shares the underlying inode, so a codec process accidentally or maliciously opening its source file for writing could modify the creator-approved WAV even though a post-run SHA check would detect it. **Current WO4-07 code streams a separate private WAV copy** under the temporary codec directory, fsyncs and re-hashes that copy, and gives the external MXF process access only to the disposable private file. The original approved WAV is never hardlinked into the worker's directory. Any private-copy mutation, original SHA mismatch or failure remains a hard stop before MXF publication; the only hardlink used after codec completion is from the newly generated MXF stage to its final unique filename, so no approved source inode is exposed. The memory bound remains small; extra temporary disk capacity is now a stated requirement.

`tests/test_nvp_wo4_mxf_stream.py` uses a hostile mocked native writer that intentionally modifies `master.wav` inside the worker's staging area and proves the approved original WAV remains unchanged, no MXF becomes published, and the staging directory is removed. A separate pre-execution test rejects WAV tampering before starting the worker. This is a security behavior test, **not real CineCert acceptance**; the real native unwrap test is separate. New exact-head native CI remains OPEN until observed pass evidence.


### WO4-LF01/LF03 creator decision — one durable supervisor and manual NVP lock (2026-11-07)

**Approved architecture:** One persistent, independently hosted NVP Production Supervisor owns all long-running rendering, picture/color and PCM mastering, J2K/MXF/DCP, job leases, checkpoints and recovery; the editor is a client and may be minimized, closed/reopened or locked without implicitly cancelling supervisor jobs. This supervisor service is **specified but not yet implemented or verified**; the new frontend lock is not its substitute. Full contract, states, failure boundaries and acceptance: `docs/NVP_PRODUCTION_SUPERVISOR_AND_LOCK.md`.

**Manual NVP lock, FIRST UI IMPLEMENTATION COMMITTED:** `frontend/src/WorkspaceLock.jsx` and its CSS now offer a deliberate **Lock NVP** action in the main studio header. The workspace stays mounted but inert/hidden from interaction behind a dedicated accessible app lock screen. Unlock by pressing **Home · Open NVP** or sliding the explicit slider fully to OPEN; no credentials, automatic timeout, forced window/system lock, background-job mutation or worker cancel. Per-webview session storage keeps a manual lock across an accidental refresh. This is a **convenience/accidental-interaction guard, not authentication, filesystem security or a worker cancellation permission check**. Native OS session lock is separate, optional, manual and not yet wired to a verified desktop bridge; it must never run automatically from NVP lock.

**Tests and current acceptance:** `frontend/src/WorkspaceLock.test.jsx` covers unlocked invisibility, manual Home and slide, partial-slide refusal, and absence of auto-lock/system lock/cancel controls. `.github/workflows/nvp-workspace-lock-ui.yml` installs frontend deps, runs Vitest interactions and builds the desktop webview UI on native Windows/Linux. These are submitted for CI; no physical installed-app acceptance or operational supervisor has yet been demonstrated.

**Next implementation order:** WO4-LF01 genuinely native independent supervisor and SQLite durable export journal with time/revision/source SHA manifests; WO4-LF02 memory-bounded long-form picture→J2K/MXF→DCP author; WO4-LF03-B optional native OS lock/active-work sleep policy; WO4-LF04 unified crash recovery; WO4-LF05 native Windows/Linux installed AFK/cancellation/restart acceptance. The app-level lock must never be implemented by invoking the OS lock or disabling authorized host-level recovery.


**Manual-lock native CI evidence update:** Workflow run `42354746851` shows the Ubuntu 24.04 job completed SUCCESS, including exact manual Home/slider Vitest interactions and Vite desktop frontend production build. Its Windows 2025 sibling had not completed at last observation. This verifies the frontend build and behavior in CI, **not** the installed desktop app, native optional OS lock, or a standalone production supervisor process.


### WO4-LF01 standalone production supervisor implementation (2026-11-07)

**CREATOR DIRECTION:** one durable supervisor, distinct from the manual NVP Home/slide lock and optional OS session lock. The independent process keeps job ownership and source assembly evidence outside React/webview state.

**IMPLEMENTED, native CI OPEN:** `backend/nvp_production_journal.py` persists immutable approved assembly SHA/revision, dependency manifest and contiguous Film Time job segments in SQLite WAL (FULL synchronous writes). Job submission validates a real native `FilmIndex` and creator callback, never a frontend consent flag. Rows contain process owner tokens/PID, source path/SHA/size, verified segment digest and byte count, cancellation request, bounded events and review-required states. Restart rehashes verified segments, flags tampered source data without deletion, and only requeues interrupted **read-only** verification segments; a reviewed/mismatched segment can retry only with explicit native host authorization and restored SHA. POSIX state roots require owner-only permissions. This is not a DCP publisher.

**IMPLEMENTED, native CI OPEN:** `backend/nvp_production_supervisor.py` is an executable **separate Python process** with an exclusive Windows/Linux OS-held file lock, no network port or arbitrary shell, a single admitted `VERIFY_APPROVED_MEDIA_V1` streaming verifier, heartbeat checks and protected cancellation. It keeps running when no editor/webview exists if launched as an independent host process. It does **not yet own a native codec subprocess process-tree**, ship an installed service or bind actual render→J2K→MXF workers.

**CI tests submitted:** `tests/test_nvp_production_journal.py` and `tests/test_nvp_production_supervisor_process.py` cover host approval, exact FilmIndex assembly SHA, owner constraints, multi-segment SQLite recovery, source tamper/review/restoration, authorized cancel, OS singleton, three-hour Film Time planning with no 3-hour RAM load, and a genuine `os._exit(79)` worker claimant followed by separate-process restart and exact source verification. Workflow `.github/workflows/nvp-production-supervisor-native.yml` runs on native Windows 2025 and Ubuntu 24.04 with Python 3.11 and 3.13. New exact-head results **not yet received**.

**Separate prior failure repaired:** WO4 master motion fixture at previous commit was corrected (doubly escaped bytes); subsequent native run identified another test-fixture error: source replacement test wrote escaped zero-text bytes rather than an equal-length zero-byte buffer. Fixed `tests/test_nvp_wo4_pcm_stream.py` to use `bytes(len(self.raw))` so the intended digest-tamper branch is exercised. Four-platform exact-head acceptance is pending; do not call this passed.

**Remaining LF01/next phases:** actual native CI result inspection/repairs; installed standalone worker launcher/reconnect, Windows ACL and Linux service manager integration; OS-contained codec subprocesses and durable output checkpoint journal; feature-length picture frame/MXF/file-backed DCP; system sleep inhibition and separately optional native OS lock; real installed app/forced shutdown/power-loss verification. The NVP manual convenience lock never creates any job/cancel permissions. See `docs/NVP_PRODUCTION_SUPERVISOR_AND_LOCK.md`.


### WO4-LF01 native matrix acceptance and host reconnect hardening (2026-11-07)

**Verified native LF01 baseline PASS:** commit `d9e1c5dd95a953874b344f069b9079931fdbdaae`, GitHub Actions run `42355702884`, all 4 jobs Ubuntu 24.04 / Windows 2025 × Python 3.11 / 3.13 completed SUCCESS. The jobs compiled the standalone supervisor and exercised real OS process separation, single-owner file lock, `os._exit(79)` after a segment claim, durable journal restart, source SHA verification, approved cancel and restored-source review. This certifies only the **first native read-only worker/job-journal behavior at that head**, not cinema encoding, an installed app or physical master.

**New implementation since that PASS:** `backend/nvp_production_monitor.py` is a trusted project-scoped read-only job status/segment-progress interface suitable for reconnect after a desktop UI restart, with exact native FilmIndex project validation and separate authorization callback. It never exposes source filesystem paths, worker tokens, native cancellation or other projects' jobs. `tests/test_nvp_production_monitor.py` includes independent project isolation and durable-status reopening. The journal now serves status/catalog/event queries via read-only SQLite WAL snapshots without holding the production writer lock, and long restored-source SHA checks run outside the writer transaction followed by an exact manifest/segment identity recheck. Host-only retry is still required. These additional head changes require a NEW successful native matrix before accepted.

**Remaining LF01:** installed native service helper/launcher and automatically reconnecting real NVP windows, OS containment and process-tree cancellation for real codec workers, authenticated native UI host exposure and complete source-root permission enforcement; true long-form picture/DCP output-staging checkpoint contract in WO4-LF02/LF04. NVP's manual slide/Home screen remains an unrelated convenience lock, never an authority to stop/pause/cancel jobs.


### WO4-LF02/LF04 — real file-spooled OpenJPEG picture/MXF workers (2026-11-07)

**Implemented, committed, latest native CI pending:** The one existing `ProductionSupervisor` now dispatches approved `ENCODE_APPROVED_XYZ12_PICTURE_REEL_V1` jobs from the same `ProductionJournal` SQLite database, via `CinemaJournal` (schema extension, NOT another scheduler). `CinemaJournal.submit_reel` uses a real frozen, independently verified OpenUSD/temporal Take and an existing immutable WO4 mastering decision with exact ordered XYZ12 SHA-256 frames and 24 fps Film Time positions; verifies the approved 2K/4K source file bytes and SHA-pinned reviewed OpenJPEG/CineCert binaries, and requires a native creator approval callback over the canonical manifest hash. Only 3–7200 frames per reel are currently admitted; feature-length multireel assembly has not been implemented.

**Real native worker stages:** `backend/nvp_wo4_picture_spool.py` scans each original XYZ12 image in bounded buffers, emits a temporary 12-bit XYZ PPM and lets SHA-pinned actual OpenJPEG produce a real codestream in a job-private directory; it uses the WO3 JPEG2000 header constraints, flushes it and publishes it without overwrite to a deterministic indexed filename. The supervisor then commits a durable SQLite frame index→source SHA→J2K SHA/size receipt. Only after every frame checkpoint is present does the same independent supervisor dispatch SHA-pinned real CineCert MXF wrapper/info against the disk-backed J2K directory, verify SMPTE label, edit rate, duration and UUID, rehash all J2K inputs after wrapping, fsync/publish a file-backed picture MXF and commit a separate MXF SHA/size checkpoint. No whole-reel JPEG2000 list or MXF bytes need be loaded into Python memory. **This is a verified-structure picture MXF candidate, NOT a full movie DCP and not independent DCI compliance.**

**Cross-platform process cancellation:** `backend/nvp_supervised_codec_process.py` executes reviewed SHA-pinned native codec files without shell/interactive stdin, bounded logs on disk and bounded timeouts. Linux starts a new process session and terminates the process group on cancellation; Windows configures Job Object kill-on-close for native codec descendants and attempts TerminateJobObject on cancellation/timeout. Closing or sliding NVP's manual lock never calls this control. Windows child assignment is after process creation (not a suspended-start, race-free launch); full kernel containment and installed-app acceptance remain OPEN. Native tests use real interpreter child/grandchild processes to exercise cancellation, timeouts and process-group/Job Object termination.

**Crash and checkpoint behavior:** `CinemaJournal.cinema_reconcile` runs under the exclusive supervisor singleton. It rehashes original XYZ frame sources, verified codestream checkpoints, and the final MXF receipt. It may requeue an interrupted segment only if no stage/output artifacts exist; a partially written stage, output without SQLite checkpoint, altered original or missing/tampered verified frame/MXF results in `REVIEW_REQUIRED` and leaves all evidence undisturbed. A real `os._exit(79)` child process test creates an uncommitted stage and proves no automatic promotion/deletion. Explicit approved cancel during a frame refuses an output checkpoint. **This does not yet implement controlled review disposition or an output-producing job's full stage→final-DCP crash repair.**

**Tests:** `tests/test_nvp_production_cinema.py` (genuine OpenUSD FilmIndex source, mocked output codecs explicitly labeled), `tests/test_nvp_supervised_codec_process.py` (real process tree), `tests/test_nvp_production_cinema_real.py` (real full-resolution 2K original XYZ12 picture → per-frame file-backed OpenJPEG → native CineCert picture MXF → full unwrap SHA, through four separate supervisor processes). Updated Windows/Linux Python 3.11/3.13 matrix `.github/workflows/nvp-production-supervisor-native.yml` and native codec workflow `.github/workflows/nvp-wo4-real-cinema.yml`. **Submitted tests are not accepted until actual latest-head jobs pass.** Earlier LF01 baseline passed at `d9e1c5dd` (workflow `42355702884`) but cannot certify these new workers.

**Existing test repair:** Older native supervisor matrix revealed `tests/test_nvp_production_monitor.py` incorrectly searched for the substring `source_path` in the display representation of the truthful boolean field `source_paths_exposed=False`. Fixed the assertion to inspect actual segment dictionary keys and absence of literal filesystem roots; no production information leak was observed.

**Remaining:** Native exact-head failure repairs, feature-length multireel and 4K resource budgets, picture/sound MXF pairing and *file-backed* final SMPTE DCP author/FilmIndex commit, Windows race-free containment/installed OS service host, full crash recovery including pre/post fsync/publish/FilmIndex, and external cinema compliance/hardware. Continue no FFmpeg policy.


### WO4-LF04 reviewed retry and real codec evidence checkpoint (2026-11-07)

**Independent real native picture acceptance obtained:** At exact code head `3857076b3da23ba0f086327c74eed32f344edb46`, Linux workflow `42357220969` completed SUCCESS. Log explicitly shows `test_native_supervisor_frame_checkpoint_restart_mxf_and_full_unwrap ... ok` and `WO4_SUPERVISED_DISK_NATIVE_PICTURE_MXF`: 3 ordered full-resolution 2K source XYZ12 frames → 3 independent native OpenJPEG file-backed J2K checkpoints → separate supervisor process for each stage → real SHA-pinned CineCert SMPTE picture MXF → actual asdcplib unwrap verifies all 3 original codestream SHAs. All source Take and XYZ files stayed unchanged, whole reel was not held in Python RAM and `production_dcp_accepted=False`. This is a REAL native picture/MXF integration result, not a finished SMPTE DCP, 4K feature test, independent DCI approval or installed desktop acceptance.

**Native supervisor matrix observed failure and repair:** Earlier run `42357220980` failed consistently in an older monitor *test assertion* that searched for the text `source_path` in the string representation of the truthful flag `source_paths_exposed=False`. Fixed `tests/test_nvp_production_monitor.py` to check actual returned segment dictionary keys and literal filesystem root absence. These subsequent CI runs have been queued; no unobserved current-head passing Windows/Linux process-tree result is claimed.

**Reviewed output recovery implementation:** `CinemaJournal.approve_rebuild_uncommitted` is now a native-host-only, separately approved review/retry action. It rehashes all immutable original frames and every committed J2K receipt. Uncommitted frame/MXF files and work directories are **preserved** under unique review names through no-replace hardlinks/directory promotion before their active names can be reused. SQLite resumes only missing segments, retaining all verified checkpoints. If source or prior committed checkpoint differs, it refuses recovery. Tests cover denied review, byte-preserving quarantine, unexpected output without journal commit, source modification refusal, genuine process `os._exit(79)` and direct cancellation. These reviewed-retry additions await exact-head native matrix acceptance.

**Additional native containment hardening:** POSIX whole-process-group reaping after successful codec exit; Linux and Windows cancellation/timeout process-tree tests; source stage symlink checks and post-MXF wrap rehash of every verified J2K checkpoint; complete `OUTPUT_READY` picture outputs cannot be retroactively cancelled. The codec process runner now enforces a finite scratch budget on stdout/stderr log files and fails closed if exceeded. Windows Job Object is created/assigned after `Popen`, with a documented launch-race gate for a future suspended-start host broker. No FFmpeg.

**Remaining work after this bounded production increment:** cross-platform exact-current-head native CI repair; real native 4K and long multi-reel resource/throughput budgets; a supervised disk-backed PCM sound MXF stage and final file-backed SMPTE CPL/PKL/ASSETMAP DCP publisher with recovery across staging, publish and FilmIndex commit; installed supervisor service, desktop approvals/status and Windows suspended-before-run Job Object assignment; external independent DCI validator, projector and calibrated theatrical picture/audio acceptance. Do not mark WO4/LF02 production cinema complete.


### WO4-LF02/LF04 — supervised complete file-backed DCP delivery increment (2026-11-07)

**IMPLEMENTED / NATIVE CI PENDING:** Continue from already genuine Linux picture-MXF success at commit `3857076b`, run `42357220969`. Added `backend/nvp_wo4_supervised_sound.py`, `backend/nvp_wo4_file_dcp.py`, `backend/nvp_wo4_delivery_journal.py`, and integrated these exact worker phases with the same independent `backend/nvp_production_supervisor.py`. There is still only **one production scheduler/journal/lock**. The new work takes already approved `OUTPUT_READY` picture MXF, creator-approved SHA-bound file-backed PCM24 48 kHz WAV, and the existing immutable FilmIndex mastering decision. It performs private streamed WAV copy→actual SHA-pinned CineCert sound MXF with process-tree cancellation and independent native info readback→SHA-bound no-overwrite job-private sound checkpoint. Picture and sound MXFs are copied in 1 MiB blocks (not whole-file RAM) to a new DCP stage, with genuine CPL/PKL/AssetMap/VOLINDEX and SHA-1 interchange hashes plus separate full SHA-256 receipts. The independent WO3 structural auditor must pass before OS atomic no-replace DCP directory publication. This is still `production_dcp_accepted=False`.

**Durable finalization:** Production ledger phases `SOUND_PENDING`, `SOUND_RUNNING`, `SOUND_READY`, `PACKAGE_RUNNING`, `PUBLISHED_PENDING_INDEX`, `INDEXED` / `REVIEW_REQUIRED` are persisted. Picture/audio file hash receipts and published DCP manifest are independently reopened before each commit. `commit_filmindex` reopens the original native Studio/FilmIndex and independently verifies frozen OpenUSD Take and decision, commits source-bound presentation `WO3DCP_<CPL UUID>`, and idempotently detects exact existing revisions after a crash **between FilmIndex commit and the final supervisor journal update**. A crash after OS publication but before a trusted DCP checkpoint requires creator review rather than silently indexing the orphaned folder. Existing or incomplete stage/final output is never overwritten or automatically deleted.

**Explicit cancellation:** `CinemaDeliveryJournal.request_delivery_cancel` requires a new native host authorization bound to the approved job manifest/CPL/phase. Only live sound and package operations are cancellable; an already published/indexed DCP cannot be retroactively cancelled. The native codec worker observes the durable journal request and terminates its process tree. NVP's manual Home/slide window lock still does not issue job cancels.

**Tests submitted:** `tests/test_nvp_wo4_file_dcp.py` verifies real structural SMPTE PKL, no-clobber and retained partial stages but uses intentionally fake MXF essence (NO decoder acceptance claim). `tests/test_nvp_production_delivery.py` uses real FilmIndex/SQLite, deliberately mocked native codec output, genuine final structural XML, separate sound/package/index transitions, explicit host approvals/cancellation, a final-DCP-before-SQLite crash gate and idempotent post-FilmIndex-before-journal recovery. `tests/test_nvp_production_cinema_real.py` now extends already-native full 2K picture acceptance with genuine source-bound PCM24→actual supervised CineCert sound MXF→file-backed complete SMPTE DCP→exact native FilmIndex receipt→independent decoded J2K + exact 48 kHz PCM sample checks through seven independent supervisor process invocations. Updated `.github/workflows/nvp-production-supervisor-native.yml` and `.github/workflows/nvp-wo4-real-cinema.yml` submit these to native Windows/Linux Python 3.11/3.13 and real Linux OpenJPEG/CineCert CI. New-head test results were QUEUED when submitted and are **not yet accepted**.

**Remaining release/feature gates:** inspect/repair new native CI; handle approved review disposition of final package orphans; multi-reel orchestration for 2–3-hour output, 4K full-length budgets, installed native supervisor/UI/worker lifecycle, Windows Job Object launch-race closure, independent SMPTE schema/DCI/external cinema validation, installed third-party binary license notice bundling. No FFmpeg. No claim of production theatrical acceptance from a structurally valid DCP alone. Detailed contract: `docs/NVP_PRODUCTION_SUPERVISOR_AND_LOCK.md`.


### WO4-LF04 final source-custody and terminal cancellation fixes (2026-11-07)

**Implementation-only pending new exact-head native CI:** `CinemaDeliveryJournal.commit_filmindex` now independently reopens and hashes *all* original job-authorized XYZ12 frame source files, every committed J2K codestream, both committed picture and sound MXFs and the approved PCM24 WAV before registering the finished structural DCP in FilmIndex, in addition to verifying every published DCP package asset. Therefore a structurally correct published folder cannot hide subsequent altered source media. `tests/test_nvp_production_delivery.py` injects post-package source XYZ12 and WAV mutations, asserts FilmIndex refuses registration and keeps the existing output and journal review evidence untouched.

**Cancellation gate:** the native base job journal now rejects late cancellation of `DCP_PUBLISHED` and `DCP_INDEXED` (as it already did for `VERIFY_COMPLETE` and standalone `OUTPUT_READY`). `request_delivery_cancel` still allows explicit trusted consent while native sound/package tasks run, with no external worker permission bypass. Unit test asserts no retroactive cancellation after output has been atomically published and indexed.

**Current verification note:** Latest dedicated Windows/Linux 3.11/3.13 and Linux real-native cinema jobs are QUEUED after these updates. Earlier source-bound picture-only real 2K native run `42357220969` succeeded at commit `3857076b`. No new exact-head pass has yet been observed for supervised sound, file-backed full DCP or idempotent FilmIndex commit. Remain honest: this task is substantially CODE-IMPLEMENTED, but cannot be marked release-accepted until actual latest-head CI and installed-app/independent standards gates pass.


## WO4 Seven-Package Closeout Sprint — 2026-11-07

**User directive:** Work all seven remaining WO4 tasks: native recovery CI repair; creator-approved orphan final DCP recovery; sustained multi-reel 2–3-hour architecture; long-form/4K resource admission; standalone host and read-only desktop reconnect; Windows process-tree security and license-bundle controls; installed NVP/AFK/crash-recovery acceptance.

**01 — RECOVERY MATRIX REPAIR, implemented, latest exact-head CI OPEN.** The original Linux/Windows 3.11/3.13 failure expected interrupted_requeued=[0], while the journal incorrectly included already PENDING segments [0,1,2]. Fixed cinema_reconcile to report/requeue only actually interrupted RUNNING segments with no surviving stage. No change to SHA/recovery refusal. Dedicated native 4-platform matrix submitted. Earlier pre-sprint matrix at commit dd8d04ce (run 42386494179) succeeded all four platforms; it is not evidence for newer code.

**02 — CREATOR-REVIEWED ORPHAN DCP, implemented with new tests, CI OPEN.** CinemaDeliveryJournal.approve_orphan_dcp_adoption verifies actual published package CPL/PKL/AssetMap UUIDs, frame durations, original Take, all source XYZ12/PCM24, J2K and source MXF SHA, exact picture/sound source bytes; only a full complete existing DCP can be explicitly creator-adopted after a crash between OS promotion and SQLite checkpoint. It then records PUBLISHED_PENDING_INDEX without moving/deleting/overwriting output, and existing idempotent FilmIndex commit completes. Partial/mismatched folder remains REVIEW_REQUIRED. Equivalent creator-reviewed multi-reel orphan adoption implemented in FeatureJournal, preserving original folder and verifying all approved source reels. Tests cover adoption and partial refusal, fake MXF tests labeled as structural-only.

**03 — MULTI-REEL 2–3-HOUR ASSEMBLY, implemented architectural path, native scale OPEN.** nvp_wo4_multireel.py builds a SMPTE CPL with multiple ordered exact 24fps reels and file-backed picture/sound MXFs, a single PKL/AssetMap/VOLINDEX with SHA-1 interchange digests and SHA-256 custody receipts. No whole-feature RAM bytes and no file replacements. FeatureJournal extends the SAME SQLite production journal/supervisor, requires a real FilmIndex edit/presentation whose frozen ordered_reel_job_ids and start/end Film Time agree with exact indexed original reels, re-verifies source/media hashes before approval and before final commit, persists queued/staging/published/indexed/review states and idempotent FilmIndex feature presentation. ProductionSupervisor dispatches feature package/cancel/index in its existing singleton process. Two-reel real SQLite/FilmIndex + mocked-essence structural tests submitted; this is NOT proof of feature-length real encoder throughput.

**04 — LONG-FORM / 4K RESOURCES, implementation/pilot submitted, physical stress OPEN.** nvp_wo4_resource_budget.py partitions 2-hour and 3-hour 24fps films into contiguous <=7200 frame reels, including awkward 7201-frame tails, and estimates conservative scratch memory/storage for 2K/4K and 2/6/8 audio channels. A per-stage free-disk guard with 64MiB reserve now runs before input PPM, JPEG2000, picture MXF, supervised private WAV/sound MXF, single-reel DCP and multi-reel final package stages. Low disk is rejected before the stage; unexpected ENOSPC later retains review evidence. Separate native Linux 4K Scope three-distinct-full-frame OpenJPEG/CineCert test added. Even if it passes, this is a 4K pilot, NOT a 2–3-hour actual encode or measured PC resource baseline.

**05 — GUI-INDEPENDENT NATIVE HOST, library implemented, installed Lu DLC integration OPEN.** backend/nvp_production_host.py is an explicit trusted host-side adapter: launches the independent supervised process in a detached OS session rather than tying it to React/browser lifetime, discovers the OS-held singleton, exposes project-authorized, source-path-redacted read-only progress after NVP view reopens, and requires a separate native host authorization to stop only a process (not cancel job). Tests include actual short-lived parent process exit, independent reconnect, original SHA preserved and denied admin controls. The current backend/nvp_api.py preview HTTP endpoints are NOT a trusted native consent/permission boundary and must not expose process handles or cancellation; actual Lu v1.0 DLC IPC/installer bridge remains deferred.

**06 — WINDOWS CONTAINMENT + DISTRIBUTION, implementation submitted, OS-native/release OPEN.** Replaced the Windows early-running Popen→Job assignment window with backend/nvp_win_suspended_worker.py: CreateProcessW(CREATE_SUSPENDED), then SHA-reviewed codec Job Object assignment before ResumeThread, fail closed, plus process-tree timeout/cancel. Native Windows test asks child whether it belongs to a Job Object at its FIRST instruction. Linux retains process-group kill/reap. Protected Windows service identity, restricted token and tight inherited-handle list require additional release verification. backend/nvp_wo4_native_bundle.py enforces on-disk native binary SHA, versions, full license/notice file hashes, declared transitive dependencies, no symlink/path traversal and no-overwrite BOM; it explicitly does NOT certify complete platform dependency scanning or legal approval. Real upstream binaries/notices still must be packaged by the actual installer, not fabricated.

**07 — INSTALLED AFK E2E ACCEPTANCE, protocol prepared, PHYSICAL RELEASE OPEN.** docs/NVP_WO4_INSTALLED_ACCEPTANCE.md now specifies install→approved Take/assembly→long render→manually lock NVP→use other apps/unlock/reopen→authorized pause/cancel and exact process-tree kill→fault injection at source,J2K,MXF,DCP,FilmIndex boundaries→restart/restore/uninstall. Actual installed Windows/Linux Lu NVP DLC, OS service/autostart, 2–3-hour real 2K/4K evidence, third-party dependency legal notices, physical DCI/color/audio/theater acceptance have not been provided and must not be marked green.

**Exact evidence distinction:** The earlier WO4 real native 2K picture+PCM sound+file-backed DCP and independent source decode passed Linux run 42359312665 at commit e2d4d2b. The older first four-platform supervisor/monitor test matrix passed at dd8d04ce/run 42386494179. The newer seven-package current-head multi-reel, suspended-first Windows worker, host lifecycle, disk budget, orphan recovery, license BOM, and 4K pilot CI jobs were submitted but had not completed at documentation time. Do not propagate earlier green badges to the latest head.

**Next immediate priority:** repair any actual exact-head four-platform native CI failures; obtain genuine 4K short pilot receipts and then measured sustained 2-hour/3-hour installed workload on physical Windows/Linux hardware. Independent calibrated theatrical DCI/true-peak/color compliance remains specialist acceptance. NO FFMPEG.


### WO4 seven-task native closeout repair — Nov 7, 2026 (current continuation)

**Verified real short-form evidence:** At code head `84e1f28e08dc835b7b945695cffafaa72d0d213b`, GitHub run `42387923803` **PASSED** actual native Linux OpenJPEG+asdcplib three-distinct-frame 4K Scope XYZ12→file-backed JPEG2000→CineCert MXF pilot. The log prints `WO4_NATIVE_4K_PILOT`, exact picture MXF SHA, source preserved, and `test_three_distinct_full_4k_frames_spool_and_native_mxf ... ok` in ~7.5 seconds wall-clock for that test. It also prints `WO4_SUPERVISED_FULL_FILE_DCP` for true 2K picture+PCM24 sound→real SMPTE DCP→FilmIndex and independent full picture/sound decode; those are genuine codec tests, not mocked output. This is **NOT** evidence for 2–3-hour throughput, full 4K DCP/sound, independent calibrated DCI compliance, or an installed Lu/NVP DLC.

**Native supervisor four-platform PASS after real failure repairs:** Same prior code head `84e1f28e` supervisor workflow `42387923798` failed only in the brand-new NativeProductionHost startup tests. Native logs: Linux incorrectly rejected the trusted runner's symlinked `sys.executable` before resolving it; Windows rejected ungranted `CREATE_BREAKAWAY_FROM_JOB` with `WinError 5`. Fixed both without weakening OpenJPEG/CineCert codec process-tree containment: canonicalize the trusted runtime interpreter path; don't require forbidden Job breakaway privileges for detached user-session host child; explicitly mark `survives_enclosing_job_termination_certified=False`. Exact repair commit `ff7204a7f31b1a736bf26525ad4ef25a0dc8ae54`, four-platform native supervisor run `42390002973` **PASSED all four**: Windows 2025 Python 3.11 and 3.13; Ubuntu 24.04 Python 3.11 and 3.13. Includes the genuine OS Job membership-at-first-instruction, descendant termination, timeouts, original Take/FilmIndex, crash recovery, orphan adoption, multi-reel, host/GUI-exit and source-preserving unit/structural suites. Thus the earlier supervisor CI failure is repaired, not deferred.

**Additional Windows hardening committed and verification pending:** `backend/nvp_win_suspended_worker.py` now uses Windows `STARTUPINFOEXW` and an explicit `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` of *only* three individually duplicated standard handles before `CREATE_SUSPENDED` child resumes inside its Job Object. The prior launch inherited every inheritable parent handle; this is an actual security scope reduction. New real Windows negative test `test_unlisted_inheritable_handle_cannot_reach_codec` deliberately creates an inheritable host pipe handle and proves it cannot be seen by the child. Current exact-head matrix for this further hardening remains queued; do not claim it has passed from the earlier green supervisor run.

**Stronger actual crash/installed-like acceptance submitted, pending:** `tests/test_nvp_wo4_feature_journal.py` now uses an actual separate OS process and `os._exit(79)` immediately after complete multi-reel OS atomic DCP publish but before journal receipt; an independent journal instance must mark REVIEW_REQUIRED, preserve all files, only creator-adopt exact original source/media/UUID/codestream/PKL receipts, and then commit one idempotent FilmIndex revision. `tests/test_nvp_wo4_staged_host.py` copies the backend to a fresh native-runtime-like root **outside the source checkout**, executes the genuine standalone host startup/reconnect and GUI-exit tests there on Windows/Linux, with the source checkout removed from PYTHONPATH. This is installation-like isolation smoke only, **not** an installed NSIS/Debian Lu DLC, packaged codec/legal bundle or physical workstation E2E.

**Physical and release gates still OPEN:** Actual guided Lu-hosted NVP DLC installation, independently provisioned Windows background service/broker outside the editor's Job Object, protected native IPC, exact external license/NOTICE and platform transitive dependency inventory for shipped OpenJPEG/asdcplib/USD and runtime DLLs, signed binaries, sustained 2–3-hour 2K/4K throughput/memory/disk/power budget and failure restart on Windows/Linux physical hardware, formal independent DCI validator, color/projector/audio compliance and exhibition ingest. These cannot be closed by a short hosted runner or documentation. No FFmpeg.


### WO4 sustained GitHub Actions 2h/3h at 2K/4K — submission (2026-11-07)

**Creator directive:** Run the two-/three-hour export workload on GitHub CI now, and defer actual third-party license collation until final release while keeping an exact non-optional backlog. Explain theatrical compliance and keep independent cinema/projector validation a specialist acceptance gate.

**Actual new test:** `tests/nvp_wo4_sustained_ci.py` and `.github/workflows/nvp-wo4-sustained-cinema.yml` added to draft PR #90, with PR and manual dispatch triggers. Matrix **2h 2K Flat (172,800 frame slots), 3h 2K Flat (259,200), 2h 4K Scope (172,800), 3h 4K Scope (259,200)** at 24fps. Each uses true on-disk SHA-pinned OpenJPEG to generate 3 distinct cinema XYZ12 JPEG2000 codestreams; the test intentionally hardlinks/reuses these 3 codestreams into exactly 7,200 sequential input frame names per 5-minute reel. It creates a real 5-minute 48kHz PCM24 stereo master, then makes each of the 24/36 complete reels a native CineCert picture MXF and PCM24 sound MXF. It streams them through the current real multi-reel SMPTE CPL/PKL/AssetMap publisher and independently verifies **every package asset hash** and exact full-length reel duration list. Its auditable JSON artifacts explicitly include source hashes, 24fps frame-slot count, native binary SHA, measured elapsed wall time, peak parent/codec-child RSS and disk usage; full media is *not* uploaded due hosted disk/artifact limits. All four cases fail explicitly if 14GiB runner storage is inadequate rather than silently shortening output.

**Coverage distinction (CRITICAL):** This is a **complete-duration native J2K MXF wrapping / synthetic repeated-frame SMPTE packaging stress test**, not real sustained unique-frame 2h/3h rendering, rich-footage compression, FilmIndex approval of hundreds of thousands of distinct Digital Take samples, independent full-cinema decode, calibrated audio/picture, or installed desktop acceptance. Only 3 distinct XYZ12 frames are actually encoded per case; the 5min stereo WAV is repeated per reel. Report these repeated-source limitations adjacent to every pass/fail result. A true production-quality 3h render of distinct 4K material cannot be inferred from success of this low-entropy workflow.

**GitHub operation:** On the PR head the long-form workflow registered as `42392231266`, later `42392348906` after path fix; it was marked PENDING/NO JOBS at last inspection. Do not mark this new test accepted without an actual completed CI run, job output and archived JSON receipt. Standard hosted Ubuntu Linux VMs are ~4 CPU/16 GiB RAM/14 GiB SSD; hosted job execution time capped at 6h. Current workflow timeout is 330 min/job. If storage fails at a real measured output size, repair with explicit multi-run sharding/larger runner rather than inventing a shortened DCP as success.

**Deferred licensing register:** `docs/NVP_THEATRICAL_AND_LICENSE_REGISTER.md` newly tracks exact OpenJPEG, CineCert/asdcplib pinned commit, OpenUSD, Python runtime, SQLite, native platform libraries and future Lu NVP DLC UI/installer; actual upstream LICENSE/NOTICE full texts and binary dependency scanning are **DEFERRED BUT REQUIRED before shipping**. Existing `backend/nvp_wo4_native_bundle.py` BOM admission remains compulsory when actual binaries are bundled. Do not fabricate missing licenses or claim legal clearance.

**Theatrical compliance:** DCI DCSS latest v1.5.0 approved 2026-01-29; DCI content exchange requirements involve 2K/4K 12-bit XYZ/JPEG2000, valid PCM speaker mapping/timing, CPL/PKL/ASSETMAP/SMPTE MXF, code-stream/rate and crypto requirements where used, independent DCP ingestion, cinema projection and image/audio calibration. NVP must aim for an **interoperable independently verified DCP**, not claim a DCI certification of the entire desktop film editor based only on internal hashes. Physical projector and specialist theater/validator acceptance deferred separately.

### NVP 17 handoff — exact real long-duration GitHub acceptance and next unique-frame pilot (2026-11-07)

- **PASS, exact tested head `0d140d1578bbc9bcf1c860adf90aab1d69d595ea`:** GitHub run [42392709339](https://github.com/vjmichael/nvp_offline_film/actions/runs/42392709339) completed **all four native long-duration jobs**; no more pending-run claim for this earlier head. Real OpenJPEG J2K, CineCert picture+48kHz PCM24 sound MXF **per five-minute reel**, 24fps full-length CPL/PKL/AssetMap, independent structural hash audit and per-job JSON artifact receipts were reported successful.
- **Measured genuine long-form packaging workloads, not unique-frame rendering:** 2h 2K: 24 reels, 172,800 slots, 94.109s, 4,819,640,320 peak bytes on disk; 3h 2K: 36 reels, 259,200 slots, 139.675s, 7,104,081,920 bytes; 2h 4K: 24 reels, 172,800 slots, 82.201s, 5,525,336,064 bytes; 3h 4K: 36 reels, 259,200 slots, 104.005s, 8,074,911,744 bytes. Runtime and free disk depended on runner; do not treat times as feature rendering throughput.
- **Explicit test limit:** Only three unique synthetic XYZ12 images were OpenJPEG-encoded per profile, repeated across all named J2K slots and reels; one five-minute synthetic stereo PCM24 source per run was repeated for sound reels. None of the four jobs performed a full independent native essence decode, a genuine all-distinct 2–3h render, a physical installed-app export or independent DCI/projector verification. The separate short-form 2K/4K native tests cover genuine decode.
- **Four-platform supervisor matrix PASS** at same exact head: [42392709385](https://github.com/vjmichael/nvp_offline_film/actions/runs/42392709385), Ubuntu 24.04 and Windows 2025 with Python 3.11/3.13.
- **New follow-on native sample:** `tests/nvp_wo4_unique_frame_pilot_ci.py` and `.github/workflows/nvp-wo4-unique-frame-pilot.yml` demand twelve genuinely distinct, source-SHA-checked patterned XYZ12 originals and twelve unique actual OpenJPEG codestreams for each 2K and 4K profile. Each source must remain intact; elapsed native codec time, RAM and bytes recorded. This is a separate bounded sample, **not** a full-feature distinct-frame performance acceptance. New workflow CI verification pending.
- **Still open:** physical installed Lu/NVP DLC, protected native project/worker bridge and background service, real diverse full-feature rendering resource acceptance, independent DCI/SMPTE specialist/cinema ingest, true-peak/loudness/color projector calibration; exact shipping licenses and transitive dependency notices intentionally deferred until installer freeze, still compulsory. NO FFMPEG.

#### NVP 17 native distinct-frame pilot — **BOTH PROFILES PASS**

GitHub Actions [42395210102](https://github.com/vjmichael/nvp_offline_film/actions/runs/42395210102) completed successfully at test code commit `58c09e1a05155dd3401f1d219740f2c57751d3c7` (later documentation-only edits do not change the tested pilot). Verified **12 different original XYZ12 samples and 12 different native OpenJPEG J2K outputs per profile**, all original hashes unchanged, with both JSON SHA custody receipts archived.

| Native genuine-source pilot | Sample result | Measured encode time (mean) | Total pilot elapsed |
| --- | --- | --- | --- |
| 2K Flat 24fps | **PASS**, 12/12 distinct | **1.0904 s/frame** | **13.806 s** |
| 4K Scope 24fps | **PASS**, 12/12 distinct | **3.9297 s/frame** | **48.968 s** |

These **specific patterned low-complexity synthetic source frames** are a short sample on Ubuntu-hosted CPU hardware, not representative full camera/image-generation scenes and not proof of 172,800/259,200 distinct-frame production throughput, GPU acceleration, long-form FilmIndex authorization, DCI theatrical acceptance, or physical installed NVP. NVP must not multiply this mean into a definitive film export forecast. The full-duration repeated-source structural packaging gate and this short distinct-frame encoding pilot are now separately verified; *real varied full-feature and installed-machine acceptance remain OPEN*. No FFmpeg.

### CREATOR DIRECTIVE — WO4 acceptance deferred; proceed to WO5 (2026-11-07)

**Production validation is categorically different from synthetic pipeline verification.** Native short samples and 2h/3h repeated-frame MXF/DCP GitHub CI only demonstrate that implementation paths run and structural output can be checked; they do **not** demonstrate that NVP makes the film the creator intended, or establish real-world scene/render/sound quality. It is forbidden to promote their green CI results to creative, production, or release acceptance.

**WO4 disposition: IMPLEMENTED INCREMENT / PRODUCTION ACCEPTANCE OPEN / DEFERRED.** Stop spending effort to force synthetic feature-length load to substitute for the near-production film test. Keep all existing native CI evidence, but do not close WO4. Reopen WO4's deferred production-validation gates when a near-production NVP can author a **new original film of no more than 30 MINUTES (at 24fps, 43,200 presentation frame slots maximum)** using authentic source-preserving scene/actor/camera/performance/audio/edit/master workflow, with varied original consecutive frames instead of repeated synthetic codestreams. This is a functional production test of whether the intended film actually emerges, not merely a collection of non-identical SHA hashes. Record the creator's intended shot/scene result, inspect actual picture+audio playback, source custody, timing, output and error recovery, and compare outcomes with creative intent. Preserve a fresh repeatable source-bound FilmIndex and Digital Take audit.

**Still separate, deferred for later specialist/near-release acceptance:** physical installed Lu/NVP DLC and protected background host, calibrated picture/loudness/true peak and external DCI/SMPTE validator, projector/server ingest, feature-length diverse-original frame throughput on representative hardware, third-party exact licenses and SBOM (mandatory at installer freeze). No FFmpeg.

**NEXT: WO5 Production Acceptance work order.** Change the prior "real 60-second throughput" initial creative proof to the creator's **at-most-30-minute original film** first, with long-form performance as a later gate. Develop useful review/evidence/acceptance infrastructure now; physical theatrical tests, installed hardware proof, and full creative signoff cannot be fabricated or marked complete before NVP itself is near production-ready.

## WO5 — Original-film production acceptance (started 2026-11-07)

**Official next work order after WO4 deferral:** WO5 Production Acceptance, originally defined as a 60-second real workload + installed Windows/projection receipts. Per creator, begin with an **original NVP-made film <=30 MINUTES at 24fps** to demonstrate whether the application actually creates the film as intended. Synthetic benchmarks are valid pipeline implementation evidence only; never treat their green checks as creative result evidence or WO4 release closure. WO4 remains **OPEN/DEFERRED** pending the near-production original-film proof, with extended diverse-feature/performance, installed hardware and external projector/color/audio/sound acceptance separately open.

**WO5-01 implemented, CI submitted:** `backend/nvp_wo5_original_short.py` adds a read-only host-side audit bound to genuine FilmIndex + one CinemaDeliveryJournal (not a user-supplied acceptance JSON), exact frozen USD Take and creator decision SHA, indexed source-linked SMPTE DCP receipt, original XYZ12/PCM/J2K/MXF re-verification, existing 24fps 24–720 frame sample-only continuity (NOT YET THE 30-MINUTE MULTI-REEL PROOF) and intentionally varied frame SHA receipts. Explicitly rejects the 3-frame repeated synthetic full-duration stress as original-film proof and refuses source or process metadata without real durable native provenance. Green returns **ELIGIBLE_FOR_LATER_CREATIVE_REVIEW_NOT_ACCEPTED**, with `production_acceptance=False`, `wo4_production_accepted=False` and `wo5_production_accepted=False`. Source identity uniqueness is a pilot filter and NEVER proves original motion, acting, storytelling or audio/visual intent. Tests `test_nvp_wo5_original_short.py` and four-platform `nvp-wo5-original-short.yml` exercise denial/contract boundaries without rendering a film. Actual CI pass/fail must be inspected before claiming native acceptance.

**WO5-02 protocol documented:** `docs/NVP_WO5_PRODUCTION_ACCEPTANCE.md` defines creator intent vs observed film, original short production, physically installed app, cinema specialist, true varied 60s/2h/3h performance and release SBOM/license gates. Outstanding WO5-03+ tasks needing near-production NVP, physical installation, calibrated hardware or specialist testing are DEFERRED, **not** marked complete. We proceed with the non-deferred native evidence/acceptance infrastructure while preserving the original source-immutable, all native, no-FFmpeg architecture.

## CREATOR'S APPROVED NVP FINAL DESTINATION — 2026-11-07

**30-MINUTE CORRECTION:** All earlier references in the WO4/WO5 original-film
acceptance plan to a "30-second" production proof were based on a mistaken
understanding. The actual intended near-production acceptance film is
**a genuinely NVP-authored original of no more than 30 MINUTES**. That
is a real workflow/creative-intent test with varied original pictures,
authored actions, camera, scene, sound, actual editing, output and human
inspection — not a synthetic benchmark. The existing
`backend/nvp_wo5_original_short.py` is **still limited to <=720
frames/one reel** and its tests are only narrow engineering admission.
It must be redesigned for creator-approved multi-reel, full-source
FilmIndex continuity and bounded checks before the authentic 30-minute
test can be run or accepted. **No code was changed by this documentation.**

**STANDARD THEATRICAL DCP EXPORT TARGET:** **SMPTE DCP Bv2.1
Application Profile as described in SMPTE RDD 52:2020**, including all
applicable underlying SMPTE standard constraints (especially ST 429-2).
RDD 52 is a Registered Disclosure Document, not itself a SMPTE Standard;
Bv2.1 is a tested interoperability application profile. Native packages
must verify MCA sound labeling, applicable CPL markers/application metadata,
timed text/accessibility where included, compliant picture/sound essence,
MXF and SMPTE XML, and security/KDM when relevant. External validators,
reference theater playback and picture/sound calibration are acceptance
gates. Currently implemented SMPTE-style structural DCP is **NOT YET
demonstrated Bv2.1 conformant**; never call NVP DCI-certified on that basis.
Use current DCI DCSS 1.5.1 (approved Oct 20, 2026) and subsequent revisions
as context rather than outdated 1.5.0 claim.

**EXCEEDING THE THEATRICAL MINIMUM:** NVP's higher-fidelity creative
scene-linear/OpenUSD/Float32/EXR/advanced-HDR/audio capabilities and
*non-DCP delivery profiles* may legitimately go beyond DCI's theatrical
interchange bit depth/resolution/rate limits. Never widen or change the
actual Bv2.1 DCP profile with arbitrary nonstandard extensions. Keep
source Takes authoritative and run each export through its own QC.

**EQUALLY IMPORTANT PRODUCT END STATE:** reliable end-to-end native
filmmaking workflows, clean non-CLI GUI accessible to novices but
controllable by professionals, seamless scene/Take/editorial/color/audio/
delivery experience, and a **NVP-aware AI execution layer** with semantic
capability discovery, scoped native tool execution, human creative approval,
reliable progress/receipts and safe crash/cancel/recover. Model-generated
language is not tool execution or evidence of a finished film. The precise
future Lu DLC/IPC ABI is still deferred; do not block NVP product capabilities
or force premature coupling to it. All active pipelines remain data-first,
source-immutable and **FFmpeg-free**.

Canonical full decision:
[docs/NVP_THEATRICAL_BV21_AND_PRODUCT_ENDSTATE.md](NVP_THEATRICAL_BV21_AND_PRODUCT_ENDSTATE.md);
[docs/NVP_WO5_PRODUCTION_ACCEPTANCE.md](NVP_WO5_PRODUCTION_ACCEPTANCE.md).
Recorded as target and implementation mismatch, **not a completed task or
passed conformance claim**.

### WO5 30-minute multi-reel audit and creator review implementation — 2026-11-07

**WO5-01 native implementation advanced:** Added
`backend/nvp_wo5_original_feature.py` extending the earlier 30-second
sample-only feature proof to an indexed native multi-reel FilmIndex/DCP
readiness audit for a genuine original film of **up to 30 MINUTES**,
43,200 ordered frames at 24fps. It reuses `FeatureJournal`'s complete
picture XYZ12/J2K, PCM24, native picture/sound MXF and published DCP
integrity rechecks, validates frozen FilmIndex feature assembly and exact
continuous Film Time, per-reel original OpenUSD Take identities, indexed
source DCP receipts, creator-approved picture SHA order and native
source/encoded frame diversity using bounded SQLite row cursors.
The return is ALWAYS
`SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED` — no
claim of director intention fulfilled, actual feature rendering, installed
app, SMPTE DCP Bv2.1, projector compliance or WO4/WO5 completion.

**WO5-01 CI evidence:** Four Windows/Linux × Python 3.11/3.13
native tests **ALL PASS** in exact source head workflow
[42401400107](https://github.com/vjmichael/nvp_offline_film/actions/runs/42401400107).
The 43,200-frame tests exercise deterministic SHA **admission-contract
fixtures** and bad-input denial. They do **not** encode or play back a
30-minute original film, test 43,200 distinct natural/author-provided
movie frames, prove independent essence decode, or assess actual
creative success. Older 30-second one-reel inspector remains a
deliberately limited sample, not the corrected acceptance target.

**WO5-02 native implementation added; new exact-head CI pending:**
`backend/nvp_wo5_director_review.py` freezes creator-authored shot
intent against the actual FilmIndex edit/assembly before review, with
bounded full-coverage Film Time, expected action/camera/sound and a
native creator approval callback. Its follow-up `record_director_review`
requires current WO5-01 indexed-feature evidence before recording the
creator's specific observed action/camera/sound per shot, whether full
picture/sound was watched/heard, and revision-needed judgments. FilmIndex
retains immutable revision-level source relationships and separates
human-reported observations from any independent production, theatrical
or AI-generated approval. Added
`tests/test_nvp_wo5_director_review.py` and native Win/Linux CI.
Installed GUI authentication/real film human review remain **OPEN**.

**Outstanding acceptance and WO5 continuation:** 
(1) independent genuine multi-reel original-film source+essence E2E,
(2) source-consistent interactive installed GUI and real creator-signed
review workflow, (3) native crash/cancellation/reconnect full application
exercise, (4) independent SMPTE Bv2.1 DCP verification and cinema ingest,
(5) actual 30-minute original creator judgment, (6) longer-feature
performance proof, and (7) release notices/SBOM and installed packaging
when due. WO4 remains **OPEN/DEFERRED**. No FFmpeg, source mutation
or fabricated acceptance.

### WO5 desktop review and production-scale tiers — 2026-11-07

**Creator clarification:** A real original film of up to 30 minutes is only the initial *does NVP work?* pilot. The principal feature-film test is a genuinely produced **60–90 minute** original (86,400–129,600 frames at 24fps). The extended epic test is **at least 3 hours** (259,200+ frames at 24fps), with distinctive original picture, story, actors/camera, editing, sound, realistic sustained performance and recovery. Repeated-source synthetic DCP packaging is not either creative test. WO4 acceptance is deferred pending original-film evidence and remains OPEN.

**WO5 native desktop work committed (not yet installed-accepted):** The existing Windows WebView2 entry now uses TrustedDesktopWO5Bridge, a subclass retaining all original data-first source camera and spatial PCM functions. Native-only wo5_review_catalog/read_intent/save_intent/inspect_feature/save_observations perform scoped FilmIndex/journal reads and real OS-dialog-confirmed creator writes; no FastAPI write route, fabricated approval or separate supervisor. App.jsx now has **19 · Watch & review film**, whose DirectorFilmReviewPanel allows shot-by-shot intended action/camera/sound authoring, native immutable approval, real indexed feature custody review, approved reel Take audition and explicit creator-only observed-results recording. Native source playback is connected by reusing the real OpenUSD world and spatial PCM DataFirstAVPanel at the selected Take and approved source sample; the panel fails closed if the Take is absent.

**Important open playback difference:** Real original **Take** A/V playback is not yet continuous, independently decoded full **finished SMPTE DCP** playback with final color, cuts and soundtrack. The full movie player, Win/Linux installed real OS-device/source review, creator's genuine original films, SMPTE DCP Bv2.1 compliance and 60–90min/3h acceptance remain OPEN. Unit tests and CI cannot stand in for the physical GUI or full feature film.

**Verification:** New six-job Win/Linux Python+React workflow nvp-wo5-desktop-review.yml submitted, with native desktop permission tests and exact Take/time frontend controls. See docs/NVP_WO5_DESKTOP_DIRECTOR_WORKFLOW.md for scope/evidence. No FFmpeg; no source Take mutation.

### WO5 final picture/sound DCP playback / coding and genuine reel test (2026-11-07)

**Implemented source code in draft PR #91:** NVP WebView2
FinishedFilmPlaybackPanel obtains native OS-granted project/feature
view permission from the same original TrustedDesktopWO5Bridge and
supervised OpenJPEG/asdcplib codec process system. It reads
SHA-audited **published DCP picture MXF and mastered sound MXF**,
decodes exact real 24fps XYZ12 picture/48kHz PCM24 at the selected
global Film Time (including across indexed reel cuts), presents bounded
uncalibrated sRGB PNG to the screen and original-master-derived 48kHz
stereo monitoring via one WebAudio hardware clock. Exact seek,
buffered playback, stop/revoke and fail-closed handling of missing
frames, audio deadline misses and device underflow implemented. Does
NOT use original Take source preview as a fake finished film and
does NOT alter any original or derived asset.

**Real codec evidence:** Native six-frame/two-reel SMPTE DCP
picture+sound encode/wrap/final publish/unwrap/decode test passed on
GitHub [42408366415](https://github.com/vjmichael/nvp_offline_film/actions/runs/42408366415),
including distinct 2K frames/PCM across reel edge frame 2->3 and
exact 48k sound sample mapping. Linux/Windows React UI jobs in this
run passed. Mock-unit tests failed only on a synthetic undersized
J2K fixture; fixed on a later commit, exact-head CI pending.

**Still OPEN (WO5 not production-ready):** measured sustained actual
24fps without picture/audio underrun, native installed NSIS executable
WebView2 playback, legally bundled/pinned native decoder tools and
notices/SBOM, real sound-device drift and full channel mapping,
real 30-minute original pilot, 60-90-minute original feature, >=3h
original epic and independent cinema-calibrated SMPTE DCP Bv2.1
validation/projector ingest. The release codec pin is intentionally
blank until a real installer build produces the vetted manifest;
unconfigured player fails closed. Three native subprocesses per
frame need optimization before assuming full realtime performance.
Previous visible WebView2 smoke failed OpenUSD MaterialX scalar map
verification; the exact-authorized-PBR-connection fix was committed
and native verification is pending. WO4 remains deferred/open,
and no production acceptance flag has been set.

### WO5 published-MXF player verified technical contract — exact CI 2026-11-07

**Source-code player/GUI integration verified on six platform-matrix
checks plus the genuine Linux codec/essence acceptance, 7/7 success:**
[42409121482](https://github.com/vjmichael/nvp_offline_film/actions/runs/42409121482).
True two-reel SMPTE DCP package, picture J2K and actual final PCM24
sound native decode passed across global frame 2->3 and native
multi-frame 4-maximum batch requests clipped at the reel boundary.
24fps/48k contiguous sample indices and exact native J2K source SHA,
OS-scoped permission, modified MXF refusal, bounded source preview,
real WebAudio scheduling and skipped-frame/no-audio-deadline fail
closed tests passed on applicable platforms.

**Status:** technical native finished-DCP decoder, batching, and
desktop review UI code: IMPLEMENTED + REGRESSION PASS. Continuous
hardware playback in the installed app, real authentic 30-minute
original, 60-90-minute feature, >=3h epic, legal codec bundle
manifest, true calibrated multichannel cinema playback, and SMPTE
DCP Bv2.1 expert/projection review: **OPEN**, not production accepted.
Old preexisting Native MaterialX source scalar failure patched with
strict exact-map source verification; installed WebView2 reenactment
remains a separate pending gate. WO4 deferred/open.

### WO5 installed native theatrical playback and original thirty-minute source (2026-11-07)

**Draft PR #92**, stacked on #91. Engineering work:
- Pinned-source **real Windows OpenJPEG/CineCert** build, verified complete
  BSD license notices and exact release SHA manifest baked into installed
  NVP.exe; binary self-pinning from runtime/browser forbidden.
- Actual NSIS install + embedded WebView2 native codec capability test,
  real published two-reel SMPTE picture and mastered PCM24 decoding from
  installed NVP.exe, and a measured >=24fps throughput gate that fails
  closed when the native codec is too slow. Source fixture contains six
  distinct synthetic test patterns and must NOT be reported as a film.
- **Original 30m source pilot** Last Light at Relay Nine: six-act creative
  experimental OpenUSD scene, 60 original timed camera cuts, moving
  3D actors, six original PCM recorded motifs, a persisted/frozen
  full-1,800s Digital Take and 6x7,200-frame reel plan, plus source
  scene-linear visual checkpoints across all acts. Verify the original
  Take/scene SHAs remain immutable if a new scene revision and new Take
  are recorded from the surviving original data.
- The actual rendered final 43,200 cinema-resolution frames, 30-minute
  mastered sound and finished DCP, uninterrupted native Windows physical
  audio/display playback, user/director creative review, 60–90min real
  feature, >=3h epic and independent DCI/SMPTE projector validation:
  **NOT IMPLEMENTED OR ACCEPTED by these source/codec tests**.
- NVP project provenance can navigate from published DCP metadata to
  FilmIndex assembled reels, mastering decision, original Take and exact
  native OpenUSD scene source. New Takes must have a new identity; DCP
  essence alone cannot reconstruct editable scenes/camera/actor actions.
  Keep this in project/archival metadata rather than proprietary DCP
  extensions. Original files stay immutable, no FFmpeg.

**Status:** implementation and native tests submitted. Do not close
installed sustained playback or original 30m finished-film acceptance
until actual GitHub test receipts and director review arrive. WO4
production deferred/open; WO5 still open.

## WO6 — Creator-guided AI production operations (opened 2026-11-07)

**Scope established from approved end-state design, not a preexisting WO6 assignment.** New draft PR #93, branch \`nvp/wo6-ai-creator-guidance-20261107\`, stacked on draft WO5 PR #92. The creator directed continuing development while earlier WO5 installed/duration/physical cinema gates remain open. These gates carry forward rather than being misreported as complete.

**WO6 goal:** Make NVP's source-immutable production data and native capabilities useful to a model-independent, human-supervised filmmaking assistant. A director should ask for revised scene/camera/actor/sound/Takes, see exact sources and likely affected film deliveries, review a proposed native task, authorize consequential operations, and inspect genuine worker receipts. Reuse existing Studio + FilmIndex, read-only AI-01/02/03 host, trusted native supervisor and creator-authority model. Avoid another planner database, unscoped HTTP actions, model self-permission, Docker, FFmpeg or an invented Lu v1.0/DLC transport ABI.

**WO6-01 source-bound retake planning IMPLEMENTED, exact-head native verification pending:** \`backend/nvp_wo6_creator_plan.py\`, \`backend/nvp_ai_read_host.py\`, \`tests/test_nvp_wo6_creator_plan.py\`, \`.github/workflows/nvp-wo6-creator-ai.yml\`.
- Exact FilmIndex presentation/edit/master/Take ID and revision; SHA re-open; bounded upstream dependency graph and exact frozen OpenUSD scene + temporal SHA. One-hop *indexed* impact only; partial/unindexed/FeatureJournal sources explicitly reported unknown; standalone flattened DCP is not a USD archive.
- Adds semantic capability \`nvp.film.plan_retake.v1\` to original trusted read host. Current actor/project/turn must be authorized for every invocation, with SHA-bound request/result receipts. Unknown fields, cross-project reads, stale/missing references, malformed source Take hashes and model approval claims rejected. Source, Digital Take and published DCP are not changed, no media is rendered and no worker is admitted.
- Native Windows/Linux Python3.11/3.13 tests + AI-01/02/03 regressions submitted to GitHub; **do not claim any WO6 passing verdict until the run completes successfully**.

**WO6-02 source audit / origin resolver IMPLEMENTED, CI pending:** `backend/nvp_wo6_feature_origins.py` + `tests/test_nvp_wo6_feature_origins.py` now conditionally extend the original `NativeAiReadHost` with a real host-owned FeatureJournal. They reuse WO5's complete native feature/Take/source verifier, return exact reel→Take→scene/event SHA and creator-unapproved status, and fail on cross-project, altered/aborted receipts and forged Take SHA. Adapter tests mock the expensive WO5 auditor; these tests are not a new genuine DCP end-to-end acceptance. **Remaining sequential WO6 phases:** WO6-03 task-aware film context + installed verified capability/license/tool readiness; WO6-04 bounded source-impact/approval preview; WO6-05 native scoped host execution+creator approvals (no AI execution by discovery); WO6-06 unified worker receipts/cancel/recovery; WO6-07 genuine installed NVP model-assisted end-to-end director workflow and novice/professional usability. Canonical plan: \`docs/NVP_WO6_AI_FIRST_FILM_ASSISTANT.md\`.

**Independent source and release gates still OPEN:** WO5 actual continuous picture/mastered-sound in installed NVP.exe, original fully rendered/seen 43,200-frame 30-minute pilot, 60–90-minute real feature, >=3-hour epic and independent calibrated Bv2.1 theater ingest; WO4 production release acceptance deferred. WO6's read-only AI source plan does not satisfy these.

### WO6-03 source-aware scene and installed native-tool context — 2026-11-07

**Implementation in draft PR #93, exact-head Windows/Linux x Python 3.11/3.13 CI PENDING.** The existing \`NativeAiReadHost\` now accepts authorized \`nvp.film.read_scene_crew_context.v1\` (always read-only) and optionally \`nvp.tools.inspect_host_pinned.v1\` (only with an authenticated native host-injected \`TrustedToolInventory\`). New \`backend/nvp_wo6_scene_context.py\` rereads real frozen OpenUSD Digital Takes and FilmIndex SHA-backed scene+temporal sources, actual world actor/camera/light transforms at the selected integer Film Time, native schema lens and lighting, indexed action/dialogue/sound events, and sampled original PCM sound bytes. Optional exact camera shot timeline identifies the director-authored active camera without AI guesses; optional current screenplay source and creator-accepted exact scene-linked Story Bible canon are bounded, never treated as an unverified identity match to USD actors. Truncation, stale scene heads, unknown sources, missing audio, pending approvals, lack of finished-picture/sound and read-only behavior are explicit.

New \`backend/nvp_wo6_tool_readiness.py\` checks current on-disk SHA pins for native binary and upstream bundled license notices, refuses symlinks, missing/broken/mutated files and arbitrary model-supplied tool paths. It never executes native programs or installs software: hash+license verified is NOT executable/workflow/GPU readiness. Missing host pins result in explicit not-configured status; no model-runner readiness claimed. Test \`tests/test_nvp_wo6_scene_tool_context.py\` uses **real OpenUSD scene, original PCM, temporal event ledger and immutable Take**, actual host-scoped dispatch, and local native binary/license tampering simulations. Its own scenarios are short source technical tests, not a completed original movie. CI YAML quoting fixed after a no-jobs parse failure.

**Next after this phase:** verify exact-head native CI and repair actual failures; WO6-04 source/derived impact preview; then separately host-approved execution/recovery and eventual installed model/UI E2E. WO5 continuous installed finished-film A/V and 30-minute real original film, 60–90 minute feature, >=3h epic and SMPTE Bv2.1 independent cinema acceptance remain OPEN.

### WO6-04 source impact, Production Bible and approval preview — 2026-11-07

**Implemented, exact-head CI verdict pending:** `backend/nvp_wo6_impact_preview.py` adds `nvp.film.preview_source_impact.v1` to existing trusted `NativeAiReadHost`. It requires per-turn actor/project read policy; exact FilmIndex source/revision/SHA; typed proposed domain (scene/actor/camera/sound/edit/color/Take/master/DCP/approved fact); optional exact screenplay scene/revision, expected creator-approved Production Bible digest, accepted fact ID, bounded graph count and explicit 2K/4K 24fps 2/6/8 channel estimate parameters. Existing `backend/nvp_bible_context.py` is reused for scene-approved canon SHA, accepted Story Bible facts, partial-order chronology and subjective character belief/continuity state. Stale scene links/approved-canon changes fail; missing initialized Bible is reported, never silently created. Typed accepted facts/links are inspected; AI proposals never become canon.

The preview traverses known original-scene → Take → edit → master → presentation FilmIndex dependencies, scaled-editorial bindings and sparse temporal references with bounded SQL reads, exact source SHA and explicit truncation. It discloses **unindexed FeatureJournal/historical output uncertainty**, old-vs-current source heads, and distinct human approvals and native supervisor/resource grants. Optional WO4 `plan_feature` is an estimate only; native tool/GPU/disk admit, actual render/mix, creator intent approval and release DCP remain separate. No worker is run and original source+derived bytes are unchanged. `tests/test_nvp_wo6_impact_preview.py` covers the full graph, normalized event edges, approved-vs-proposed Bible canon, scene binding, stale/changed SHA, cross-project deny, preview-only capacity, truncated graph, and native authorizer denial; Windows/Linux 3.11/3.13 submitted. Design/spec: `docs/NVP_WO6_PRODUCTION_BIBLE_IMPACT.md`.

**Remaining:** native exact-head verification and any failure repair; WO6-05 genuinely creator-confirmed native execution (not AI self-authorization); WO6-06 durable worker receipts; WO6-07 installed app/model-in-loop director acceptance. WO5 sustained installed final A/V, original 30m finished film, genuine feature/epic and Bv2.1 theater acceptance remain open.

### WO6-05 — first host-owned creator-approved native Take operation (2026-11-07)

**IMPLEMENTED IN DRAFT PR #93; exact-head Windows/Linux CI not yet accepted.**
Added `backend/nvp_wo6_native_take_action.py`, `tools/nvp_wo6_take_worker.py`
and real OpenUSD native test `tests/test_nvp_wo6_native_take_action.py`.
This is a host-only first-party `nvp.film.create_frozen_take.v1` operation:
a project+actor+turn scope, human creator decision, separate native host
permission, exact scene+temporal SHA/revisions, selected bounded Film Time
checkpoints, fresh WO6-04 source-impact digest, and a **new** Take ID are
required. Existing source retirement/staleness checks and approved Bible SHA
are honored where explicitly selected. No unbounded model tool execution.

An exact immutable task is committed via existing `ApprovedTaskBindings` and
`TaskLedger`; native Python/worker source SHA pins, 4 GiB default bounded
resource reservation, existing OS containment, cancellation/policy refresh,
independent `OpenUSDTakeCapture.verify_take` and durable output receipt all
gate success. Cancelled/revoked/stale operations do not auto-create new
Takes. A crash after a source commit is an **INTERRUPTED, reconciliation
required** receipt rather than an invented rollback or a blind retry. The
older frozen Takes, edit revisions, source assets and DCP deliveries are
immutable. The AI read-only catalog does not advertise this operation.

**Still OPEN:** exact-head Linux/Windows 3.11/3.13 proof and failure repair;
tested source-commit crash/restart reconciliation and installed director UI;
concrete native actor/camera/edit/sound/color/master/DCP worker operations;
WO6-06 reliable progress/cancellation/recovery report; WO6-07 model-in-loop
installed NVP filmmaker acceptance. WO5 real installed sustained picture+
mastered audio, 30-minute finished original, 60–90-minute feature, >=3-hour
epic and independent DCP Bv2.1 theatrical validation remain separate gates.

### WO6-05 extension / WO6-06 native recovery — 2026-11-07

**Implemented in draft PR #93, native exact-head verification PENDING.**
Beyond the original immutable Take operation, three additional first-party
director-authorized classes now exist in
`backend/nvp_wo6_native_shot_action.py` and
`tools/nvp_wo6_shot_worker.py`: camera optics/position; actor/prop blocking
and eyeline; shot-local native lighting. Exact authorized shot changes are
normalized against reopened real OpenUSD roles, SHA-bound to original frozen
Take, exact scene and WO6-04 approved-source impact, then committed as a NEW
`OpenUSDShotOverrides` presentation record. They do not rewrite an original
Take/scene, render frames or approve a release. The model read-only catalog
does not expose execution; creator decision and native host permission remain
separate required callbacks.

**WO6-06 initial durable implementation:** `backend/nvp_wo6_recovery.py`
persists cancellation intents and append-only reconciliation evidence within
the existing FULL-sync TaskLedger SQLite. The host checks current cancellation
during native execution; successful worker completion uses one atomic
transaction to fence cancellation. `WorkerHostLease` prevents two local
hosts from simultaneously driving or reconciling the same native work root.
After crash, reconciliation requires independently attested stopped process
tree, reopens genuine FilmIndex/OpenUSD source bytes, distinguishes missing
commit from committed source with missing receipt and verified source+receipt,
and does not auto-retry, roll back immutable source or mark film delivery.
Task events and read-only status remain available after reopening SQLite.
Additional Windows/Linux 3.11/3.13 CI tests cover positive source execution,
negative grants, stale/revoked source, late cancellation, kernel lease, crash
after native immutable commit and missing/tampered receipts.

**Still OPEN:** actual exact-head four-platform CI logs/failure repairs;
trusted installed-Windows and Linux native worker-tree attestation and
recovery proof on true process crashes; wired director UI + model-in-loop
approval flows; other creator-authorized edit/sound/color/master/DCP native
operations; WO6-07 full installed first-film assistant. WO5's sustained
installed finished-film picture/mastered audio, authentic 30-minute film,
60-90min feature, >=3h epic and independent SMPTE Bv2.1 cinema acceptance
are not completed by these source operations.

### WO6-05/06 additional implementation: data-first native color/shot edits and authenticated status — 2026-11-07

**Code committed in draft PR #93, exact-head Windows/Linux acceptance pending.**
Added creator-approved native source-bound color and authored exact Film Time
camera sequence/edit DATA workers; existing DA-06 `NativeColorDecisions`
and DA-01 `ExactTimeShotSequence` are reused, not rewritten. Native
`WO6NativeFilmDecisionHost` equivalent class `NativeFilmDecisionHost`
performs human decision confirmation and separate native host authorization,
seals task bytes, SHA-pins source revisions, enforces typed values, creates
a NEW original-derived FilmIndex decision ID, runs an OS-contained native
worker, and reopens finished decision SHA to verify its actual immutable
receipt. It neither renders picture nor issues film delivery approval.

Hardened ALL current WO6 native writer worker entrypoints (Take/shot/data)
with independent `backend/nvp_wo6_worker_admission.py`: actual ledger
ACTIVE + resource-reserved state, matching scheduler owner and task SHA,
absence of durable cancel intent. Parent host still rechecks current creator
and native policy and worker/receipt integrity. Source head is rechecked
after successful native Take/shot/timeline action where current source
identity is required. On Windows, worker readonly SQLite opens via a
proper native `Path.as_uri()` file URI.

WO6-06 read-only `nvp.film.read_native_task_status.v1` is now opt-in
on the **existing** NativeAiReadHost only if the real host injects an
existing `WO6DurableRecovery`. The per-call actor/project/turn and
request SHA policy still runs; exact creator task ownership is checked.
Results are bounded authentic event/cancel/recovery snapshots, never
worker/admission/approval/cancel tools. No new model endpoint.

**Tests submitted in the four-platform CI matrix:** real OpenUSD native
color and exact Film Time camera sequence authoring, no original Take
mutation, denied grants, stale source, queued/not-admitted task worker
denial, mismatched owner, durable cancellation, real color decision
committed before a missing worker receipt, and read-only task status
actor/project refusal.

**Unresolved:** GitHub Windows/Linux 3.11/3.13 exact-head execution not yet
confirmed (latest runs queued/pending; superseded runs cancelled). Genuine
installed source-production end to end, audio/edit/master/cinema DCP
physical workers with real media, independent OS termination attestation
after supervisor crash, existing installed-app desktop approval UX and
WO6-07 actual model-in-loop 30min film remain OPEN. WO4/WO5 sustained
installed finished A/V and cinema Bv2.1 gates are separate and OPEN.


## WO6-07 installed director-native GUI and WO5/WO6 shared acceptance — 2026-11-07

**Implementation committed and under native CI, not yet accepted by an
installed-end-user/model-in-loop test.** This update supersedes earlier notes
that said the native GUI or installed Windows process-tree attestation
implementation was entirely absent.

- The PyInstaller/NSIS NVP.exe private command
  `--nvp-wo6-worker take|shot|data` now routes the three **first-party**
  worker classes before a FastAPI server or WebView2 starts. A frozen
  NVP.exe is not a Python interpreter. Every caller SHA-pins the executable
  and sealed spec; the contained child independently reopens the actual
  FULL-sync native TaskLedger and checks current ACTIVE+reserved admission,
  host owner and absence of a durable cancellation before touching FilmIndex.
  Arbitrary worker names are rejected.
- Windows WO6 workers use the existing suspended-first Job Object
  containment with an **exact durable prelaunch named NT Job Object**.
  `backend/nvp_wo6_kernel_attestation.py` stores the task-specific Job
  identity before worker admission and, on recovery, queries the real NT
  kernel rather than trusting a PID, marker file or expired timeout.
  Only a verified absent named Job Object after kill-on-last-handle-close
  permits a stale ACTIVE task's native recovery. Windows hard
  `os._exit` and live Job Object acceptance tests were added. Linux
  without delegated cgroup-v2 whole-tree attestation still refuses such
  recovery. Windows implementation is NOT accepted without its real CI.
- `tools/nvp_wo6_installed_action_smoke.py` and
  `tests/test_nvp_wo6_installed_smoke.py` exercise six actual
  source-bound, OS-contained writes through the real FilmIndex and durable
  TaskLedger: NEW frozen Take, camera shot, actor blocking, native light
  shot, new non-destructive color, and exact Film Time editorial camera
  sequence. The source-mode regression runs on Linux/Windows/Python 3.11
  and 3.13; the actual NSIS installed Windows candidate has a **separate
  real NVP.exe executable mode** gate in its WO5/WO6 CI matrix. This
  disposable test uses test-only approval callbacks; it does **not**
  claim the director actually approved a film, provided cinematic acting,
  rendered a mastered output or delivered a DCP.
- The **actual installed desktop** entrypoint now creates
  `TrustedDesktopWO6Bridge` (subclassing the established WO5 creator
  bridge). Every source-mutating WebView2 action is preceded by the
  read-only exact FilmIndex source-impact preview; the host itself creates
  actor/project/turn identity, random decision ID and job-owner identity.
  One real OS dialog confirms the director's **exact creative scope** and
  a separate OS dialog confirms the **exact SHA-sealed first-party worker**.
  A browser boolean, model suggestion, source ID, or finding an exposed
  method is NOT authorization. Policy grants live only in this host and
  expire/revoke on restart; queued unverified work is never automatically
  continued. Native status/cancel requires the same local creator ownership
  and explicit OS cancellation confirmation.
- `frontend/src/WO6CreatorActionsPanel.jsx` adds a distinct native
  director-approval tab in the existing React NVP screen, linking real
  OpenUSD scene/Take/TemporalLedger sources to actual read-only previews,
  typed Take/shot/color/camera-sequence authoring, OS confirmation,
  immutable-result receipts and durable task status. There is **no**
  HTTP mutation endpoint or model-facing native executor. The existing
  installed WebView2 source-window smoke now must mount the actual new
  tab and read the correct FilmIndex catalog over real JS-to-native IPC.
  `tests/test_nvp_wo6_desktop_bridge.py` and React Vitest suite cover
  project isolation, untrusted origins, denied first/second OS grants,
  queued cancellation and lack of phantom finished-film status.

**WO5 integration:** On the WO6 stacked branch, latest repaired WO5
native OpenJPEG throughput, predecoded real SMPTE MXF/PCM fixture, exact
frame/reel stage diagnostics and escaped-NUL regression repair are
integrated. The WO5/WO6 combined installed NSIS acceptance workflow
preserves the actual WO5 24fps measured throughput and 720-frame
Canvas/WebAudio presentation release gates **AND** independently requires
all six genuine installed WO6 source-worker receipts. Passing one gate
does not imply another. The compiled DCP's 30-second repeated-pattern
fixture is not the authentic 30-minute original film.

**Outstanding after implementation:** actual exact-head GitHub CI,
genuine installed actor/project/approval UX/manual playback acceptance,
local model-in-the-loop assistant orchestration in the native GUI,
persisted release-safe creative decisions after user restart,
full authentic original 30-minute film with 43,200 distinct rendered 2K/4K
images and 30-minute mastered PCM, approved native export/manufacturing
operations (color/picture, sound, edit/reel and DCP write) beyond current
six data-authoring classes, guaranteed process-tree shutdown on installed
Linux cgroup host, 60–90min feature and >=3hr epic, and independent SMPTE
Bv2.1 projection/server ingest. All are still OPEN until real evidence
has been collected. CI queued/pending or cancelled runs are not passes.

## 2026-11-07 — WO5 / WO6 native-gate follow-up

- **Native CI result check:** latest exact-head WO6 multi-platform jobs
  and WO5 real installed picture/sound jobs were queued or pending,
  and earlier superseded runs were cancelled. **No newly accepted
  pass/fail native execution evidence; no acceptance gate closed.**
- **WO5 submitted:** production `FinishedFilmPlayer` now uses an at-most
  24-frame/one-second session-and-reel scoped cache of genuinely
  unwrapped DCP PCM24 for adjacent frame windows, with exact original
  2,000-sample sound slices. Every JPEG2000 picture remains separately
  verified/decoded; cross-reel seek and stop invalidate sample reuse.
  A regression checks wrapper call counts and original pixel counts.
  Installed-codec fsync diagnostics now contain real line boundaries.
- **WO6 submitted:** two independent native OS approvals remain enforced;
  source mutations now return a **QUEUED** receipt without synchronously
  blocking the director's WebView2 IPC while a serialized trusted-host
  dispatcher invokes the original OS-contained native worker. A new
  regression blocks its child and checks prompt responsiveness. Task
  status is still the only authority for SUCCEEDED/INTERRUPTED.
- **Stacking:** PR #93 merged the updated WO5 parent into its WO6
  branch, retaining the WO6-specific native operations, workflows and
  the latest WO5 product playback improvements.
- **Still open:** exact-head Windows/Linux tests; installed Windows
  native six-operation worker acceptance; real visible continuous
  720-frame/WebAudio proof and independent >=24fps codec result;
  native cancellation/crash-boundary proof; authentic original 30m
  picture+sound+director review; 60–90min and >=3h features; external
  theatrical validation. CI setup repair or source-only code review
  must never be counted as accepted native evidence.


## WO1 integrated regression closeout — 2026-11-07

Draft PR #94 (`nvp/wo1-integrated-native-regressions-20261107`) stacks on WO6 PR #93 and targets five native regressions: (1) genuine Windows handle-inheritance evidence rather than numeric HANDLE presence, (2) SLATE-05/06 failed creator admission with private stage diagnostics, (3) already-fixed narrow MaterialX mapped-scalar authorization plus tamper regression, (4) exact PCM24 24-frame cache-crossing sample custody, and (5) bounded first-party WO6 dispatch/close/failure behavior. Dedicated four-cell Windows/Linux Python 3.11/3.13 CI: `.github/workflows/nvp-wo1-integrated-regressions.yml`. See `docs/NVP_WO1_INTEGRATED_REGRESSION_CLOSEOUT.md` for exact source paths and exit criteria.

**No new acceptance gate closed at submission.** In particular, SLATE approval failures need an observed native refusal-stage trace and an actual repair; windows native pipe/write readback, as well as all other exact-head tests, must run before success can be claimed. Work on WO2+ product features is not resumed until WO1's own acceptance is honestly assessed.


## WO2 SLATE native approval consistency — 2026-11-07

- **Draft PR #95** branch `nvp/wo2-slate-native-approval-consistency-20261107`, based on WO1 PR #94; status **OPEN**. WO1 runner evidence remains an independent acceptance gate.
- Inspected prior SLATE-05/06 failure: creator-positive requests reached `ApprovedTaskBindings.enqueue` and were rejected by `approval_check`; this is a verified failure site, **not yet a verified root cause**. WO1 added categorical host-private rejection diagnostics, but native exact-head jobs were queued at WO2 start.
- Corrected an independent integrity bug: a failed immutable native approval check left a still-live consent row and staged source directory although **no** authorized task was registered. For SLATE-05 blocking preview, SLATE-06 geometry and native pre-Take camera, on binding failure the host marks orphaned consent `revoked_at`, transitions an unadmitted cache reservation `PENDING -> FAILED`, and removes only unregistered staging. It **never** deletes a worker directory after TaskLedger task registration. Source FilmIndex and frozen Takes are unchanged.
- Added negative native tests in `test_nvp_slate05_preview_native.py` and `test_nvp_slate06_geometry_native.py` covering all three denied-approval paths and durable lack of fake worker admission.
- **Still required:** actual positive approval path must pass on Windows and Linux, prove correct source-manifest/worker SHA and active unexpired creator consent, identify and repair any `_last_slate_approval_refusal` state, rerun native matrix at final SHA. WO2 cannot close until that evidence is green.


**WO2 root cause and repair update:** The original SLATE-05/06 positive creator-consent rejection is explained by `SlatePreviewCache._db` closing an explicit `BEGIN IMMEDIATE` transaction without commit. Thus `reserve()` returned PENDING but erased its cache row, so `_approval_check` saw no durable reservation and failed closed. Verified underlying SQLite rollback behavior locally; committed success-only commit/exception rollback and native multi-connection positive/negative tests, plus orphaned-consent cleanup for blocking, geometry and pre-Take camera. Dedicated four-cell workflow `.github/workflows/nvp-wo2-slate-native-approval.yml`. Draft PR #95 remains **open pending actual native results**. See `docs/NVP_WO2_SLATE_APPROVAL_CLOSEOUT.md`.


## WO3 MaterialX and independent native renderer integrity — 2026-11-07

- **Draft PR #96** `nvp/wo3-materialx-renderer-integrity-20261107`, stacked on WO2 #95/WO1 #94, **implementation submitted; exact-head native acceptance OPEN**.
- Prior **real** DATA-AV job `128474807034` (PBR five channels) and 60s mixed scene job `128474807074` hit `RuntimeError: MaterialX source scalar changed` on valid connected roughness/metallic maps. Earlier WO1 code restricted only valid mapped scalar connections, still no passing native evidence.
- WO3 requires *exact* shader output sockets, UsdShade output-kind/type, no extra/raw USD graph connections, source-bound UV selection and PBR normal/emission/opacity color contracts. Strengthened `nvp_wo2_openpbr.py`, `nvp_wo2_pbr_channels.py`, added `nvp_wo3_materialx_integrity.py`.
- Independent disposable MaterialX texture source copies are read-only and re-hashed **after** the renderer operation, avoiding false custody receipts on native mutation; Hydra probes SHA-pin their executable across the call, reject untrusted image symlinks/oversize files and do not include raw stderr private source paths.
- Added adversarial real USD tests `test_nvp_wo3_materialx_integrity.py` and Hydra-executable integrity tests; workflow `nvp-wo3-materialx-renderer-integrity.yml` runs Windows/Linux 3.11/3.13 plus 60s original USD CPU continuity. **Pending all real job results and repairs**; optional `usdrecord` is not evidence of shader parity if skipped. Installed Windows film parity remains separate.


**WO3 hardening follow-up (2026-11-07):** Added raw USD connection-list checks for dangling shader and
texture source edges, exact PreviewSurface/OpenPBR input types, untampered
normal-map scale/bias literals, and resolver refusal of shadowed `file`
inputs. Independent `usdrecord` stdout/stderr are discarded instead of
buffered in unbounded RAM. Added native adversarial regressions in
`tests/test_nvp_wo3_materialx_integrity.py` and diagnostic-cap test in
`tests/test_nvp_wo2_hydra_probe.py`. **Final-head native execution remains
OPEN**; original PR #96 workflow run `42435076173` was queued, and all
subsequent commits require fresh exact-head evidence. No shader/Hydra parity,
GPU or installed film acceptance is inferred.


**WO3 post-render RAM bound:** Scoped MaterialX source integrity now validates
regular-file type and exact original byte length and hashes in 64 KiB chunks
without `Path.read_bytes()` on native worker output; adds oversized source
adversarial regression. WO3 is still **OPEN pending latest exact-head CI**.


### WO3 independent Hydra image and color acceptance gate — 2026-11-07

- New **mandatory and non-skippable** real Hydra Storm render test and workflow
  `nvp-wo3-real-hydra-color.yml`, stacked on PR #96. Uses independent
  conda-forge OpenUSD 26.08, Mesa/Xvfb software OpenGL, genuine native
  `usdrecord`; main 26.11 authoring matrix stays separate.
- Publishes two immutable FilmIndex scenes with identical geometry/camera/
  light/five PBR maps and different red/blue original sRGB textures. Compares
  **actual decoded Storm image pixels** for center-swatch color dominance and
  between-swatch Lab ΔE76 separation; hashes native renderer, scene and pixels.
  Receipts leave theatrical color, absolute calibrated reference accuracy,
  physical GPU and MaterialX-only terminal parity **FALSE/OPEN**.
- **Do not claim accepted from code submission:** latest exact-head real native
  job must actually finish successfully with a nonempty emitted color receipt.
  Embree is explicitly unsuitable because OpenUSD's reference Embree renderer
  does not use materials. 



**WO3 continued native color audit:** Fixed duplicate PNG-SHA in real
red/blue swatch fixture. Required Storm test now runs dual and isolated
MaterialX-only contexts (four real images) and records derived USD layer SHA,
actual pixel hashes, center RGB means, ΔE76 source separation, and exact
renderer-entrypoint SHA. MaterialX-only mode strips universal fallback on
a disposable source copy only; added positive and missing-terminal native USD
regressions, and negative **synthetic verdict** contract tests kept separate
from genuine renderer acceptance. OpenUSD 26.08 imaging and 26.11 source
matrix remain distinct. **All acceptance still OPEN** pending final exact-head
native jobs; no GPU/calibrated or production rendering claim.


## WO5 — Full XYZ12 and terminal PCM24 preview cache custody (2026-11-07)

- New WO5 follow-up branch `nvp/wo5-preview-pcm-custody-closeout-20261107` stacked on WO3 PR #96; historical WO1 PCM region 23/24 repair remains inherited from PR #94.
- Native DCP XYZ12 2K/4K display conversion previously checked only decimated preview samples; an out-of-range `0x1000` original XYZ12 word at an unsampled position could be silently missed. Repair scans **every** original 12-bit word with bounded `raw.max()` before downsampling; adds negative 2K fixture at x=1,y=1 that would have been skipped.
- Adds original sample-preservation test for 4-frame window 22–25 of a 26-frame terminal 5.1 PCM24 reel, including exact 2000 samples/frame/channel, uniquely labelled six-channel samples, two unwrap regions (0–23,24–25), reuse and eviction.
- Native four-cell Ubuntu/Windows 3.11/3.13 suite: `.github/workflows/nvp-wo5-preview-pcm-custody.yml`; exact-head completion **OPEN**. See `docs/NVP_WO5_PREVIEW_PCM_CACHE_CLOSEOUT.md`.
- Genuine installed NVP.exe 24fps A/V continuous playback, full original 30-minute film, hardware, independent theater and Bv2.1 remain **OPEN**, not implied by source fixes or unit tests.


## WO6 — Exact task-notice lifecycle and native recovery (2026-11-07)

- **New WO6 follow-up branch:** `nvp/wo6-exact-dispatch-recovery-20261107`, stacked on WO5 PR #97. Previous WO6-05/06/07 source writes, durable cancel receipts, kernel worker-tree attestation, and director UI remain inherited from WO6 PR #93; no active acceptance gate is silently closed.
- **Real source-review defect:** native desktop queued a specific sealed task ID but passed only `run_next()` to its operation-family host, allowing a different scheduler-head task to be claimed. New `expected_task_id` is threaded through desktop, three first-party host types, creator binding preflight and the SQLite `BEGIN IMMEDIATE` admission transaction. A stale, canceled, or out-of-order notice fails without reservation or another task's admission; existing scheduler priority remains authoritative.
- **Adversarial regressions:** native SQLite priority and cancellation mismatch, approved spec policy preflight, exact desktop notice propagation, queue pressure, close that drops unstarted notices, and reopened SQLite task status with explicit new OS cancellation approval. Existing OS-contained OpenUSD Take, shot, color/editorial worker, crash-after-commit and Windows Job Object tests remain in the dedicated matrix.
- **Native test workflow:** `.github/workflows/nvp-wo6-exact-dispatch-recovery.yml`, Windows 2025 / Ubuntu 24.04 with Python 3.11/3.13, actual `usd-core==26.11`, native pywin32 on Windows. **Acceptance OPEN** pending exact-head job results; no installed NVP.exe, actual terminated-worker tree or 30-minute film claim.
- Closeout specification: `docs/NVP_WO6_DISPATCH_LIFECYCLE_RECOVERY.md`. A task left QUEUED after a non-admitted notice requires fresh creator choice, **never automatic restart replay**.


## WO6-07A — Native director/local-model *read-only* source proposal (2026-11-07)

- Next task group follows WO6-06 native dispatcher PR #98 and does not reopen the deferred original 30-minute film acceptance. New `backend/nvp_wo6_director_model_proposal.py` binds the selected **actual frozen OpenUSD Take** and exact Film Time to existing independently reopened WO6-03 actor/camera/light/temporal/recorded-audio context, records SHA of the bounded packet, then calls an explicitly selected existing loopback local model via the existing `nvp_model_service.writer_for`.
- Added nonblocking, single-active, bounded in-memory local-proposal lifecycle in existing `TrustedDesktopWO6Bridge`; host checks native origin and project and never accepts executable/model URLs, script, creator approval or native worker permission from model text. Proposals never auto-run, are not persisted or replayed after restart, and cannot certify cinema or sound output.
- Existing React director panel now explicitly discovers local models, requests one read-only draft from the selected frozen Take, polls native status, and displays model text literally; any real change still requires manual operation selection, new source-impact receipt and both independent OS confirmations.
- Native Windows/Linux Python3.11/3.13 source-context tests use **real OpenUSD** but a **fake model adapter** to prove admission/authority boundaries; React builds and tests HTML/script-as-text refusal and zero WO6 source worker execution from suggested text. Dedicated workflow: `.github/workflows/nvp-wo6-model-director-proposals.yml`. Details: `docs/NVP_WO6_07A_LOCAL_DIRECTOR_PROPOSAL.md`.
- **All native/UI CI results OPEN** until exact-head runs complete; genuine real GGUF inference, installed NVP.exe model-assisted directing, film quality judgement, native AI-guided rendering and authoring, 30-minute original picture+sound, reference-managed color, external independent renderer, physical display and SMPTE Bv2.1 compliance remain independent acceptance gates.


## WO6-07B — Real local GGUF inference and installed WebView2 director interaction (2026-11-07)

- **Branch:** `nvp/wo6-real-model-installed-director-20261107` stacked on WO6-07A PR #99. No previous work-order acceptance is implied.
- **Source and model:** Native director uses existing `writer_for` loopback discovery through `ProvenLocalModelWriter`; strict canonical local-only endpoint, no redirect/proxy, matching selected+returned model ID, `stop` completion, positive reported generation tokens, and hashed bounded request/response. Returned text remains untrusted and cannot grant new Take/shot/color worker authority. New concurrent scene/timeline head check discards stale AI suggestions.
- **Genuine model:** Explicit test-only acceptance tool starts an independently compiled `llama-server` with real on-disk GGUF CPU-only, pins runtime GGUF/executable SHA, creates disposable FilmIndex/OpenUSD/TemporalLedger/Take, proves positive model output with source and authority receipts and stops the acceptance-owned server. CI downloader resolves exact version/SHA of small (~105MB) SmolLM2-135M-Instruct Q4_K_M GGUF. Test model is NOT bundled in NVP installer and does not substitute for a production-quality large model.
- **Actually installed Windows:** Original PyInstaller/NSIS workflow builds one NVP.exe, SHA-checks installed payload, runs real GGUF acceptance from installed EXE, and **in the same model-server session** opens real WebView2, selects the GGUF alias through the actual React director panel, types direction, sends read-only request, polls actual native IPC and checks displayed advice, positive tokens and zero source-worker grants. Existing baseline installed window separately exercised. Mode requires an explicit opt-in command and does not auto-load on normal NVP launch.
- **Validation:** strict HTTP negative tests deliberately use synthetic server only; they are *not* genuine inference. Dedicated real Linux/Windows workflows `.github/workflows/nvp-wo6-07b-real-gguf-installed.yml` demand no-skip model runtime and native evidence. Details `docs/NVP_WO6_07B_REAL_GGUF_INSTALLED.md`.
- **Status: IMPLEMENTED / exact-head native outcome OPEN.** Real log/receipt artifact still required. Separate OPEN: representative Qwen GGUF model latency/quality, actual director-human approval and native source write in installed UI, true 30m original 24fps picture and mastered audio, physical calibrated hardware, renderer color parity, independent theatrical DCP Bv2.1 and installer license/notice/SBOM review.


## WO6-07C — Human-reviewed AI suggestion to original-source-preserving native shot (2026-11-07)

- **New stacked work group:** `nvp/wo6-reviewed-ai-to-approved-shot-20261107`, based on WO6-07B draft PR #100; do not wait for previous independent CI jobs to perform this next implementation group. WO6-07B's actual GGUF and installed Windows acceptance remains open separately.
- **Native actor/project-scoped human review:** `TrustedDesktopWO6Bridge.wo6_review_model_proposal` accepts the exact in-memory completed, untrusted local model advice and a **human-selected** camera, blocking, or lighting action. It reopens original frozen OpenUSD Take, source/timeline SHA, exact Film Time and independently verifies the same bounded context SHA and live head. This method grants **no native worker, source mutation, or creative approval** and refuses wrong-project, wrong-SHA, stale or already consumed review.
- **Manual UI:** Real React `WO6CreatorActionsPanel` adds explicit "Review advice and plan my own shot," requires the director to pick operation, type a fresh numeric/vector value, independently author a reason and new shot ID, and inspect fresh source-impact preview. No AI-produced text or JSON is parsed into action arguments; existing **two independent native OS consent dialogs** remain required before a first-party worker is queued. Denied consent leaves original unchanged; review cannot be reused for another task after successfully queueing.
- **Durable consultation provenance:** `NativeShotActionHost` seals only reviewed proposal ID, original Take SHA, model-text SHA, verified scene context SHA, Film Time and human-selected action into both current native creative approval and durable task spec. Actual contained shot worker checks it and returns identical SHA-only provenance in native receipt, with no model grant or executed AI instruction; original native host reconciles result against immutable spec before SUCCEEDED. `WO6DurableRecovery.status` now returns this actor-authorized SHA-only citation after restart. Old Take/scene/performance source never overwritten.
- **Native acceptance:** `tests/test_nvp_wo6_reviewed_director_shot.py` runs real OpenUSD frozen Take→fake-advice strict isolation→human review→separate two host approval dialogs→actual contained shot worker→immutable new shot/read-back. Also stale scene, double submit, incorrect text SHA, denial and restart. Existing genuine native shot tests additionally assert review SHA custody and refuse forged review metadata. React tests ensure no worker call until manually chosen shot values + impact. Dedicated Windows/Linux Python3.11/3.13 + React workflow `.github/workflows/nvp-wo6-07c-human-reviewed-native-shot.yml`.
- **Status: IMPLEMENTED, native results OPEN until jobs actually execute.** Full narrative `docs/NVP_WO6_07C_HUMAN_REVIEWED_NATIVE_SHOT.md`. Separate OPEN: true creator-human physically installed Windows NVP.exe approval, representative GGUF output quality, original 30-minute native film playback/mastered sound, calibrated display, second renderer, theatrical Bv2.1/independent ingest. Continue unrelated work groups without waiting for GitHub unless source acceptance is a hard dependency.


## WO6-07D — Native recorded-PCM sound cue and actual digital-slate editorial cut (2026-11-07)

- **Branch:** `nvp/wo6-reviewed-ai-sound-editorial-20261107` stacked on WO6-07C PR #101. Work proceeds while prior WO6 real-model, shot and installed acceptances remain independently OPEN.
- **Reuse original architecture:** Existing WO6 data-decision worker, approved task bindings, SQLite TaskLedger, exact-task notification, contained subprocess, host OS creator/native confirmation, no auto-replay, durable cancellation and read-back receipts. No FFmpeg, MCP, new supervisor or separate data store.
- **Native sound cue (`sound_cue`):** Director chooses an original frozen Take's source temporal timeline and an exact recorded 48 kHz PCM16LE source ID/revision/SHA. Added one finite-gain sound cue with exact Film Time-to-native-sample boundaries to a **new** immutable `TemporalLedger` event timeline. Reopens all original timed actions/dialogue/sound events (bounded max 128, refuses truncation), verifies every source SHA and original PCM bytes unchanged. This is source authoring, **not mastered audio**.
- **Original digital-slate editorial (`editorial_cut`):** Director arranges 1–64 source segments from existing true `DigitalSlateBranches` graph. Reuses `SlateSequenceAssembly.preview` and `commit` via first-party original WO6 native contained worker to create and independently reopen one new FilmIndex `edit` revision. Source Take/shot performance unmodified; no picture/master/render claim.
- **Director AI handoff:** Read-only local-model advice can be explicitly reviewed for sound/edit by creator. Native host reopens the exact AI-bound Take and live scene/time context, enforces original timeline or slate-graph membership, and reserves review against multiple uses. The human manually enters PCM offsets/gain, sound subject/event IDs or editorial branch/tick order, new immutable output identity and **their own creative reason**. Separate fresh typed payload SHA preview and original source-impact receipt must match both independent OS approval dialogs. Raw model text never becomes a worker field, authorization or automatic edit.
- **Durability:** First-party child-worker and host receipts bind source SHA, typed original revision, actual output SHA and optional SHA-only reviewed-AI consultation; `WO6DurableRecovery` authenticated status and stopped-worker reconciliation expose provenance without recreating a permission or automatically replaying tasks after restart.
- **Tests:** Native real PCM/sound timeline and slate edit/2-segment first-party worker tests, stale or forged values and declined consent, AI-reviewed explicit human sound/editorial to two native approvals and SHA-preserving derived source; React typed-payload and no-auto-apply tests. Dedicated Windows2025/Ubuntu24.04 × Python3.11/3.13 and React build `.github/workflows/nvp-wo6-07d-native-sound-editorial.yml`.
- **Detailed handoff:** `docs/NVP_WO6_07D_AI_SOUND_EDITORIAL.md`. **Status IMPLEMENTED / native execution OPEN** until exact-head GitHub runner results and genuine installed Windows acceptance. Separate OPEN: real loaded GGUF via NVP.exe (WO6-07B), artist evaluation, actual mastered sound and edit playback at original 30-minute scope, 2K/4K renderer color parity, independent theatrical DCP Bv2.1 and signing/license identity.


## V-LIGHT — 3D virtual-production lighting mechanics and dependency review (2026-11-08)

- **New required design group recorded:** NVP needs full 3D cinematographic virtual-lighting mechanics, distinct from simple color grade or light-intensity shot opinions. Source of truth remains author-owned OpenUSD/UsdLux light rigs, keyed by Film Time and immutable scene/shot revision. Candidate functions include key/fill/rim/practicals, directional/area/dome/emissive/IES if supported, HDRI, shaping/gobos, soft shadows, physically meaningful units/exposure, temperature, moving lights, light linking, reflections/GI, volumetrics, lighting rigs and source-aware AI recommendations requiring human approvals.
- **Permissively/commercially usable candidates researched:** OpenUSD UsdLux for scene representation (upstream **Tomorrow Open Source Technology License 1.0**, NOT universally Apache-2.0); LuxCoreRender C++/Python engine **Apache-2.0** for physically based independent light transport; standalone Cycles engine **Apache-2.0** versus full Blender application **GPL-2.0-or-later**; OpenShadingLanguage and OpenColorIO **BSD-3-Clause** as possible support. Check current exact-version upstream licenses, transitive notices and asset EULAs, compatibility with USD/MaterialX, installed Windows/Linux binaries and exact renderer parity before bundling.
- **V-LIGHT-01..05:** canonical photometric/scene design, native rendering evaluation, artist/director UI, independent path-traced renderer trials and native/installed/legal acceptance. Bespoke NVP **v-lighting** is the fallback if feasible permissively licensed tools cannot meet required 3D-film fidelity. This is a **development/design backlog**, not verified image quality or a newly installed dependency. See `docs/NVP_VLIGHT_VIRTUAL_PRODUCTION_LIGHTING.md`.
- Lighting work does **not** block independent WO6-07E synchronized original-source sound/editorial preview implementation; visual photometric acceptance is separate and must not be falsely attributed to ordinary CPU metadata poses.



## WO6-07E — Exact original editorial source and native PCM director audition (2026-11-08)

- **Branch:** `nvp/wo6-07e-synchronized-director-preview-20261108`, stacked on WO6-07D PR #102; previous native and installed CI results remain independently OPEN. V-LIGHT backlog/research documented above.
- **Authentic original-source/frame review:** New `backend/nvp_wo6_07e_source_review.py` reopens exact committed `SlateSequenceAssembly` edit ID/revision/SHA and maps a zero-based 24fps output frame to immutable original Take/shot source via `source_at` and Film Time. Reopens exact OpenUSD scene through `assemble_film_crew_context` and reports actor/camera/light poses and explicit historical source-head status. Original scene poses are NOT rendered images.
- **Sound/editorial synchronization by source time:** Optional derived `sound_cue` temporal source is admitted only after verifying full original event manifest unchanged (bounded) with exactly one SHA-verified recorded PCM event. Original 48kHz PCM16LE source is sample-aligned to the SAME source Film Time and assembled into at most **12 output frames / 0.5s** mono audition WAV, no spill across a committed editorial segment boundary. Each original chunk read bounded <=8192 samples and SHA-verified; no invented sound, event truncation, full sound mix or mastered output. Track provenance, omitted/exhausted source warnings, PCM WAV SHA and source review SHA included.
- **Visible source reviewer:** Existing `WO6CreatorActionsPanel` renders `WO6DirectorSourceReview`: select original committed edit/timeline, choose 24fps frame, inspect native USD scene pose and scene-source SHA plus manually play real bounded PCM WAV. Switching source invalidates stale audio, no automatic playback or model/native authoring granted. All native IPC project scoped and read-only.
- **Evidence planned:** `tests/test_nvp_wo6_07e_source_review.py` executes actual contained original-source edit/PCM authoring then proves exact second clip/frame #24 maps to same source tick and byte-audited 48k WAV, tests silent original, wrong hashes and frame bounds. React test `frontend/src/WO6DirectorSourceReview.test.jsx` asserts no auto-play, no native execute and stale source invalidation. Windows2025/Ubuntu24.04 × Python3.11/3.13 plus React build `.github/workflows/nvp-wo6-07e-exact-source-pcm-review.yml`.
- **Status: IMPLEMENTED, exact-head native / installed acceptance OPEN.** This is accurate *source-level* film time and sound, NOT continuous rendered picture/audio playback. Source scene positions are not cinematic frames. Future native rendered picture across cuts/reels, continuous 24fps sound clock, audible installed acceptance and original 30-minute film remain separate critical work. See `docs/NVP_WO6_07E_EXACT_SOURCE_PCM_REVIEW.md`.



## WO6-07F — Genuine first-party OpenUSD rendered picture and original audio-clock playback (2026-11-08)

- **Branch:** `nvp/wo6-07f-rendered-source-av-20261108`, stacked on WO6-07E PR #103; independently queued earlier CI does not stop next-stage coding and is NOT accepted until native exact-head proof.
- **Rendered original 3D pixels:** `backend/nvp_wo6_07f_rendered_av.py` uses existing verified `NativeSceneLinearRaster` (actual frozen OpenUSD original Take, scene, camera, geometric mesh and UsdLux SphereLight) to author real depth-tested 640×360 scene-linear FLOAT32 frames, then emits SHA-verified PNG sRGB display previews. Requires at least one truly rasterized source triangle; no substitution of actor coordinates, gizmos, model-generated pictures or fake frames. This is original USD CPU working-space visual, **NOT Hydra/MaterialX independent reference lighting or physical color-managed cinema**.
- **Source editorial/audio:** Reopens committed SlateSequenceAssembly edit SHA and exact output 24fps Film Time; maps every frame to original Take/shot source tick. Reuses WO6-07E source audio in **one-frame/2,000 48kHz PCM16 samples** per picture frame, with optional original-preserving WO6-07D derived sound cue and real original sound SHA. Synthesizes explicit silence only when no verified source event exists, never a fake mastered sound effect. Windows are capped at six 24fps frames and bounded IPC, output actual PNG/WAV plus source SHAs. Hard edits must be frame-aligned; subframe cuts refused rather than rounded, no original file/Take/PCM modification.
- **Audio-clock director viewer:** `WO6RenderedDirectorPlayer.jsx` in the existing WO6 React panel: manually selects committed edit/optional source sound, pre-renders first two bounded real windows, then the user explicitly starts playback. Schedules real WAV sound by `AudioContext.currentTime` and displays actual PNG frames from the SAME clock via `requestAnimationFrame`; streams bounded subsequent windows ahead with frame cache eviction. A late picture/audio buffer, skipped frame, missing image/source or final-frame leap causes explicit **UNDERRUN/STOP**, not a fake 24fps pass. Stop/reselection drops in-flight response IDs and audio. Time and frame counts recorded but physical monitor/audio playback NOT yet verified.
- **Native regression:** `tests/test_nvp_wo6_07f_rendered_av.py` authors real USD actor cube geometry/camera/SphereLight and actual native recorded 48k PCM, freezes immutable Take, commits two-segment slate cut, then checks real PNG pixels/float SHA/triangle count, 2,000 PCM samples per frame in WAV, original Take untouched, frame 23→24 exact hard cut, bad camera/hash and subframe cut rejection. React `WO6RenderedDirectorPlayer.test.jsx` checks manual start, two-window audio scheduling offsets, clock-to-image choice, explicit underrun and fake packet refusal. Dedicated Windows/Linux Python3.11/3.13 native+React workflow `.github/workflows/nvp-wo6-07f-real-rendered-av.yml`.
- **V-LIGHT simple creator controls:** `docs/NVP_VLIGHT_VIRTUAL_PRODUCTION_LIGHTING.md` updated with a deliberate *simple* UsdLux UI: place spheres/areas/distant/domes, intensity/exposure, RGB/Kelvin, beam/softness, snap/attach/lock and Film-Time pulse Hz. UsdLux included in OpenUSD; live constraints, pulsing, UI manipulation and actual render fidelity need NVP first-party logic. CPU preview currently only evaluates SphereLight scalar light and is **not** full UsdLux Kelvin/RGB/beam/soft-shadows/GI.
- **Status:** IMPLEMENTED / native and installed results OPEN. No claim of measured uninterrupted 24fps / synchronized physical playback, user approval, real offline-GGUF local AI directing, full Hydrastorm color/material, feature/epic full-length or original 30-minute film, mastered sound, calibrated projector, SMPTE DCP Bv2.1, legal license/NOTICE, or signing. New details: `docs/NVP_WO6_07F_RENDERED_SOURCE_AV.md`.


## V-LIGHT-FX and DCI theatrical mastering readiness — creator clarification (2026-11-08)

- **V-LIGHT-FX independent timer:** Light sources are not required always to run from Film Time. A light can have an independent monotonic oscillator during live interactive simulation (police red/blue strobes, fireworks, lightning, pulse/flicker). A `Capture/Sync` function records time origin, phase, waveform, event/trigger receipt, deterministic random seed and mapping to original Film Time; offline final picture always re-evaluates the recorded, SHA-bound FX state deterministically. Choose timeline-synced or free-running/captured mode explicitly; never drift silently during original cut/audio mastering. Details in `docs/NVP_VLIGHT_FX_TIMERS_REFLECTORS.md`.
- **Actual silver/gold bounce reflectors:** New V-LIGHT requirements: placeable and movable 3D passive silver-neutral and gold-warm reflective boards, area/orientation/snap/attach/lock and selectable diffuse/specular roughness, intended to bounce existing lights onto actors/objects. True reflected illumination requires renderer BSDF + one or more transport bounces; the existing NVP neutral SphereLight CPU preview CANNOT claim this. Reference rendered before/after, independent photon/energy/XYZ color audits required.
- **DCI readiness decision:** YES, existing immutable FilmIndex/OpenUSD/scene-linear frame/PCM/DCP architecture is ready for a **DCI-targeted finishing workstream now**, independent of 24fps interactive preview performance; NO, final cinema image/audio/package and DCI-compliant output have not been independently verified. DCI baseline updated to **DCSS 1.5.1 / CTP 1.6.0 (approved 2026-10-20)**, cinema SMPTE DCP and RDD 52 Bv2.1 interoperability profile. Separate DCI equipment certification from NVP-created DCP validity. See `docs/NVP_DCI_THEATRICAL_MASTERING_READINESS.md`.
- **DCI-P0..P6 gates:** lock actual source/shot/FX timeline; deterministic **offline native 2K 2048x1080/24fps** source raster including true photometric lighting/bounce; color-managed **12-bit X'Y'Z'**; mastered **24-bit/48k PCM** multichannel/cinema maps; JPEG2000/SMPTE MXF/reel/CPL/PKL/ASSETMAP + appropriate Bv2.1; independent decode/cinema ingest/projection/audio QC; then original **30-minute** completed film, eventual 60–90-minute/3-hour endurance. HDR/4K/48fps profiles are separate additions. Rendering each source frame offline may take longer than 1/24s while still producing a valid cinematic master; installed WebView2 preview and theater playback must separately prove their timebase/cadence.
- **Current status:** documentation/acceptance specification only, not new physical renderer/mix/cinema testing, not license sign-off, not closing stacked WO6-07F PR #104 or its queued CI. Continue usable live rendering/performance on a parallel track without blocking DCI-targeted offline finishing engineering.

