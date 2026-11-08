# WO6-07F — Real OpenUSD-rendered pixels with original PCM on one audio clock

Date: 2026-11-08. Branch `nvp/wo6-07f-rendered-source-av-20261108`.
Base: WO6-07E draft PR #103. Source implementation submitted; CI, installed
Windows WebView2 actual throughput and sustained 24 fps acceptance **OPEN**.

## Actual first-party picture and sound source

This phase advances beyond WO6-07E's native **scene-position metadata**.
`backend/nvp_wo6_07f_rendered_av.py` now calls the *existing real*
`NativeSceneLinearRaster.render` for every frame of a bounded original
digital-slate editorial window. The rasterizer reads a fully reopened frozen
OpenUSD Take/source scene, actual source-authored camera, real bound USD mesh/
cube/sphere/actor geometry, original material colors and native UsdLux
SphereLight intensity. The result is a genuine, independently depth-tested
**640 × 360, 32-bit float scene-linear RGBA rendered image**, not a visual
gizmo or serialized actor coordinates. It is converted into ephemeral
uncalibrated sRGB PNG only for WebView2 preview, then reread and pixel-hashed.
The window fails closed on missing real geometry, unrendered triangles,
wrong camera, malformed float buffer, bad PNG or original source mismatch.

Each output frame is addressed by exact **24 fps output Film Time**.
`SlateSequenceAssembly.source_at` maps it to the immutable original Take,
shot, scene, original Film Time and SHA, including source changes across
actual editorial hard cuts. The source event/PCM layer is reopened through
WO6-07E with `audio_window_frames=1`: exactly **2,000 authentic 48 kHz
PCM16 samples per output picture frame** are read from saved original
recorded sound source revisions, preserving sound-cue SHA, original
in/out source segment and human-authored gain. Deliberately silent frames
receive 2,000 explicit *silence* samples only when no verified recorded sound
source exists; this is declared, not represented as mastered mix.

Native backend returns a source-verifiable **up-to-six-frame** picture/
PCM window with each original Take SHA, output frame index and original
scene tick, actual PNG pixel SHA, float RGBA buffer SHA, source rasterized
triangle counts, original sound-source track receipts and one combined
mono 48 kHz WAV with exactly `frame_count*2000` samples. The displayed
PNG is not re-used as a source frame for later production tasks.

**Hard cut integrity:** The current source preview requires all editorial
cut start/end ticks and source in/out points to be EXACT multiples of
`7056000000/24=294000000` Film Time ticks; an arbitrary subframe hard
cut is refused instead of rounded to a different source frame. Rendering
may cross a properly frame-aligned hard cut: its next output frame
reopens the next frozen Take separately. Different source Take sound
revisions work through the original-Take soundtrack selection. A user-
selected *single derived* sound timeline is valid only for Takes whose
original event manifests it correctly extends; other Takes fail closed.
Later work can introduce a true scene/timeline-per-clip explicit mix map.

**Shot-local presentation guard:** The existing first-party raster consumes
the original frozen Take, not a stronger authored shot-local override layer.
If a selected slate branch references such a shot, WO6-07F currently
**refuses to render** rather than silently displaying unmodified Take
pixels in place of the intended actor/camera/light shot. Composed
shot-local presentation must be connected to the raster separately.
This is an intentional open functionality gate, not a playback success.

No FFmpeg, video generator, speculative source content, source overwrite,
untrusted browser path, arbitrary model/renderer subprocess or new tool
authorization appears in the window code.

## Actual audio-led editor viewer

The existing `WO6CreatorActionsPanel` includes
`WO6RenderedDirectorPlayer` beside its source-only review. The
creator chooses a committed original edit and optional source-sound
timeline and manually presses **Pre-render first two A/V windows**.
This performs *actual* native CPU 3D rasterization for the first
12 picture frames, verifies source/renderer/PCM count, decodes PNG
images before playback and caches only bounded windows.

**Play with audio clock** is a distinct user click. WebView2 WebAudio
decodes original 48 kHz mono WAV chunks and schedules each at the
corresponding absolute `AudioContext.currentTime` offset. Picture
selection uses that SAME audio device timeline at 24fps, driven by
`requestAnimationFrame` rather than a separate unreliable wall-clock
movie timer. New native bounded rendered windows are requested ahead
of playback and old images/audio references are discarded. A missing
window, late audio, unavailable renderer, skipped frame or overrun
causes a visible **UNDERRUN/STOP**; NVP does not quietly change the
active source, silently skip a picture or lie that a film was watched.
User stop/reselection invalidates in-flight preview results and stops
future audio, without claiming an actively executing in-process CPU
render was OS-process-tree canceled.

NVP can now *attempt* continuous preview from genuine picture pixels
and authentic source PCM when rendering/buffering keeps pace. The
implementation does **not guarantee** the first-party Python CPU
raster can sustain 24 original frames/s on available hardware.
The native response records render wall time per frame and per window,
and the React viewer reports presented frames and underruns. This is
not a display instrumentation receipt: WebView2 frame scheduling and
sound-device clock still need physical, independently measured
installed-app acceptance. The user explicitly asked us to continue
development without waiting for GitHub CI.

## Native test plan

`tests/test_nvp_wo6_07f_rendered_av.py` creates **real USD** original
sphere light, authored camera and bound USD actor cube, native recorded
PCM16 sound with positive samples and a two-segment immutable source
edit through actual `DigitalSlateBranches`/`SlateSequenceAssembly`.
It verifies genuine PNG image pixels, float raster provenance and
triangle count, SHA of both source pixel representations, exact
audio WAV samples/48 kHz/2,000 samples per image, original source
Take/PCM unchanged, hard cut frame 23→24, invalid camera/hashes,
no full-film approval and subframe hard-cut refusal. This is
neither a mocked picture nor simulated WAV.

`frontend/src/WO6RenderedDirectorPlayer.test.jsx` deliberately uses
a fake WebAudio clock to verify the browser scheduler/consent boundary
while the native tests above prove genuine USD and PCM. It checks
no autoplay, two-window prebuffer, exact audio start offsets, image
display from the device clock, on-missed-frame STOP and fake native
picture/source refusal. Those JS tests alone do NOT prove installed
sound hardware or pixel quality.

Dedicated workflow `.github/workflows/nvp-wo6-07f-real-rendered-av.yml`
checks Windows 2025 / Ubuntu 24.04 × Python3.11/3.13 with real
OpenUSD 26.11, Pillow and NumPy plus React build/Vitest. These are
source/algorithmic tests, NOT an installed end-to-end runtime/24fps
throughput acceptance. Do not mark green without actual final-head
logs and receipts.

## What remains independent

- **WO6-07F physical installed acceptance:** measure original pixels
  actually displayed and PCM actually heard across cuts, real device
  cadence and sound sync using a dedicated harness, no underrun/skip,
  repeated seek/stop, CPU/GPU utilization and memory. The current
  React `requestAnimationFrame` is not a hardware light-meter,
  camera or speaker-measurement tool.
- **Performance:** native multi-process render prewarm/bounded thread
  cache and streaming render service; CPU raster speed may be far
  slower than 24fps. Host-owned cancellation of an already running
  CPU frame is not yet implemented and is not OS worker containment.
- **Hydra/MaterialX:** the existing native raster is deliberately a
  first-party UNCALIBRATED source preview, not Hydra Storm PBR parity,
  GI, accurate Kelvin/color shadows, lighting linking or an approved
  renderer. Real independent Hydra/LuxCore/Cycles renderer integration
  and V-LIGHT light rigs are separate. UsdLux is an OpenUSD schema,
  not the final image renderer.
- **Full editorial:** original authored shot-specific camera overrides,
  multi-channel mastered soundtrack, at non-frame-aligned hard cuts
  sample-accurate mixed boundary projection, external final color
  and sound mastering, cross-reel long playback, 30-minute original
  sustained film then feature/epic production durations.
- **Theatrical DCP:** independent 2K/4K rendering and color-managed
  DCI image, cinema PCM24, SMPTE Bv2.1, independent ingester/speaker/
  calibrated projection, real installed hardware, licenses/NOTICE,
  signatures and genuine human approval remain OPEN.

## Simple V-LIGHT clarification

UsdLux comes inside the existing OpenUSD library. The creator wants
a friendly physical light editor: place and move lights, shapes,
omni/directional/cone, Kelvin and RGB, softness, attach/snap/lock,
Film-Time pulse speed. This was recorded as V-LIGHT-SIMPLE-01 inside
`docs/NVP_VLIGHT_VIRTUAL_PRODUCTION_LIGHTING.md`. Attachment, lock
and pulse keyframe evaluation require first-party NVP UI logic;
OpenUSD light schema alone does not operate those controls. The
existing source CPU raster already reads source SphereLight power,
but does **not** verify full UsdLux shaping, RGB spectral appearance,
temperature, colored soft shadows or GI. Do not claim otherwise.
