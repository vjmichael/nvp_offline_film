# V-LIGHT-FX — Independent effect clocks, cop strobes, fireworks, and silver/gold bounce

**Date:** 2026-11-08. **Status:** approved creator requirements/design backlog, NOT installed implementation or independently verified rendered light transport.
**Parent:** `docs/NVP_VLIGHT_VIRTUAL_PRODUCTION_LIGHTING.md`.
**Architecture:** reuse native OpenUSD `UsdLux` for authored light source attributes, USD mesh/materials for passive reflectors, NVP's original Film Time for deterministic final rendering, and existing director preview / two native approval controls. No arbitrary shell/plugin/MCP or second scene database.

## The creator's desired behavior

A virtual light is a placeable fixture. Move or rotate freely; snap/attach to a moving object, or lock in world space. Choose omni, directional/ray-like spotlight, area/softbox and emitter shape; brightness, RGB and Kelvin, soft/hard cone, and optional changing intensity. The light can also run on **its own clock** to simulate practical effects: cop-car red/blue strobes, intermittent street light, flashing beacon, lightning, fireworks, animated fire. The timer must be reproducible, or its live execution recorded and synchronized with picture and sound. Silver/gold bounce reflectors are movable **passive** scene objects that change the physically simulated reflected light.

## V-LIGHT-FX-01 — Three deliberately distinguished clock modes

1. **Timeline-synced** (repeatable default for filmed shots): a deterministic frequency/phase/amplitude waveform is evaluated at the original authoritative Film Time (exact rational tick or frame/subframe). A car siren strobe can continue even when the user seeks; re-rendering any frame reproduces exactly the same light without relying on computer clock speed. Optional cue starts from an original TemporalLedger event (e.g., a fireworks launch with a recorded sound event).
2. **Independent/free-running** (live interaction): an individual light uses a monotonic oscillator, not the desktop wall clock that can jump because of NTP or user time changes. Save `origin_monotonic_timestamp`, relative phase, oscillator settings, source revision, cycle count/jitter seed and clock mode while active. A free-running preview may drift relative to footage until mapped/baked; it must not be treated as a stable film source without capture.
3. **Record/synchronize independent clock**: at record start, capture a pair of host-monotonic and NVP Film Time timestamps and any later resync/discontinuity receipts. Convert the oscillator to an indexed **light FX track** by sampling/recording change events with exact Film Time, original source SHA, waveform version, phase and random seed. When reopened, the final render uses the recorded/baked timeline (not re-running uncontrolled live wall-clock effects). Clock start/stop and resume after crash require explicit policy; no silent phase jump.

A source light's state can be evaluated by a pure function:
`state = evaluate(light_revision, fx_revision, film_tick, captured_clock_mapping)`.
Store the waveform and anchor, not a huge event list when an analytic repeatable function suffices. For genuinely chaotic or interactive events, store actual event trigger times and deterministic RNG seed plus sampled overrides. For physically simulated effect geometry (fireworks smoke, embers), keep the light emission and particle simulation linked by shared event/time identity; do not fake the visuals by a flashing light alone.

**Pause and scrub:** timeline-synced effects freeze/seek to the corresponding original Film Time; free-running lights can keep flashing during preview if explicitly enabled; pressing Record captures the phase link. No scenario can accidentally replace the movie's audio clock or affect DCP timing.

## V-LIGHT-FX-02 — Usable director controls and presets

- **Light rig:** ID, type/shape, 3D transform, size, position, snap target, world lock, attach offset, visibility, power/intensity, exposure, Kelvin/enableTemperature, RGB color, beam direction/cone angle, cone softness, source size/shadow quality.
- **FX:** Off, Pulse, Strobe, Alternate, Flicker, Lightning, FireworkFlash, EventDriven. Speed Hz / period, duty cycle, rise/fall, brightness minimum/maximum, phase, deterministic jitter/seed, optional multiple lights linked as one rig.
- **Police lights:** two or more red/blue fixtures with separately controllable grouped flash schedules; real light beams cast illumination on vehicle, ground, actors, and bounce cards. Optional fog/volumetric scattering requires a suitable renderer; not implied by UsdLux schema.
- **Fireworks:** burst triggered on a recorded Film Time event, fast peak and decay tail, color/position, source-linked particle/smoke simulation and time-linked sound cue. This is lighting **simulation** in film production, not a real pyrotechnics controller.
- **Sync/read-back:** one source-revision/timeline SHA and explicit `clock_mode`, `anchor_film_tick`, `relative_phase`, optional `monotonic_capture`/jitter seed; edit preview shows the exact evaluated light state at scrubbed time. Renderer checksum/provenance is required for acceptance.
- **Safety / artistic controls:** warn on frequent high-contrast flicker when reviewing/previewing; allow reduced-flash preview. Do not silently alter director-authored final waveforms or assume a universally safe frequency threshold.

## V-LIGHT-FX-03 — DIGITAL cheats first, physical bounce as optional realism

**Creator clarification:** Do NOT force a real or simulated bounce card into a
digital scene. Physical silver/gold reflectors are only ONE optional style.
The default artist workflow is a `virtual_fill` effect: the renderer
applies a colored/neutral directional contribution to selected actors,
objects or surfaces, without an actual physical board or path-traced
light bounce. The result can be deliberately nonphysical.

- **Silver bounce (virtual):** linked neutral-to-cool fill or eye/face
  highlight, brightness/direction/size/soft wrap and surface/actor mask,
  recorded as authored USD/NVP effect parameters. Board geometry optional.
- **Gold bounce (virtual):** linked warm-gold color fill on a face/scene
  target with independent intensity and feathered mask, not a gold
  light fixture or an actual reflecting surface. Multiple bounces can
  be artistically faked by separate independent virtual lights.
- **Physical bounce mode (optional):** place a real silver/gold material
  board when the director wants visible set dressing and physically
  accurate light transport. In this mode renderer BSDF/light-path tests
  must prove reflected energy; the CPU preview cannot.
- **Renderer adapter:** define exact priority between `physical`,
  `virtual_fill`, and `hybrid` mode and label nonphysical overrides
  clearly so the director can choose realistic or artistic output.
  Link FX to object IDs, not arbitrary screen coordinates, unless the
  user explicitly selects a camera-space filter. A target may be
  an actor face, costume, ground, camera view, or whole shot.
- **Preserve data-first custody:** effect ID, target original prim
  identity/SHA, source camera/scene, RGB/Kelvin, intensity, falloff,
  direction, mask, softness, timestamp/FX schedule and compositing
  order are first-class authored source data. The renderer must evaluate
  them at the same exact frame/Film Time as picture and sound.

**Acceptance:** verify a face gets a warmer *artificial* fill without any
gold object or indirect GI. A separate physically rendered bounce
comparison proves optional `physical` mode. Do not claim the initial
CPU raster currently implements these fills; pure effect evaluation and
SHA receipts are a preparatory step only.

## V-LIGHT-FX-03B — Impossible light, sky and creative filters

- **"Always summer 3 PM" sun:** set a named, locked
  `cinematic_sun_direction` (explicit azimuth, elevation and warm
  spectrum) independent of the story's wall-clock date/time. Keep it
  fixed across hours of film, or parent it to the camera or another
  moving object. "3 PM" is an artist's *look* unless a latitude/season
  and real solar model are explicitly requested. No astronomical
  location data is needed to author the look.
- **Impossible direction/target:** spotlight follows only the hero's
  face, gold bounce ignores all other objects, shadows come from
  an intentionally different virtual source, a rainbow falls only
  on a selected costume, or a moonlight source pulses in sync with
  a musical cue. Artistic reality may differ per camera/shot.
- **Filters:** composited film looks (prismatic, gold/silver glow,
  light wrap, stylized gradient, silhouette/negative fill, cartoon
  or luminous edge) should be independent, reorderable, maskable
  source operations rather than permanent baked pixels. They can
  be layered with truly simulated lights. The final 2K color-managed
  rendering path must preserve their scene-linear/color-space intent.
- **Time:** some effects use authoritative Film Time; some run
  independent clocks live and are captured/replayed as immutable
  event/phase tracks. Freeze/scrub/retake must yield the same pixel
  values for the same approved source. The film must never change
  unpredictably between offline render attempts.
- **Designer UX:** a simple `Light FX` section offers presets and
  immediate before/after/solo/bypass, per-object targeting and
  copy/paste to new shots. A realistic/virtual/hybrid toggle
  keeps these choices accessible. There is no need to recreate
  a practical studio set just to add an artistic fill.

## V-LIGHT-FX-04 — Film and DCP timing contracts

The fixture FX simulation, camera, original authored editorial cut and PCM must share a **single exact scene/source Film Time for final rendering**. Audio may remain a hardware clock for interactive preview, but the final picture frame timestamp, flash envelope and mastered audio sample positions must come from the committed source timeline. Offline frames may render faster or slower than real time; the output must be the same every time for the same source revision.

At 24fps and 48kHz, the normal nominal interval is 2,000 audio samples per output picture frame. The exact-time representation remains authoritative, including cross-cut source identity, sample-level cues and any intentionally subframe light changes. DCI package authoring is downstream from this, and must not inherit preview frame skipping, live oscillator drift or uncalibrated 640×360 display transforms.

## Gates and implementation order

- **FX-P0:** original immutable schema/timer reference/effect-source receipts, deterministic oscillator evaluation, negative tests for seek, restart and arbitrary source revision. This does not require a full GI renderer.
- **FX-P1:** simple place/snap/attach/lock UI + police strobe, event-triggered firework flash, manual capture/free-running clock → recorded Film Time effects; creator-approved changes only.
- **FX-P2:** native UsdLux emitted color/temperature/beam/emitter behavior in real renderer (Hydra/MaterialX or measured independent path tracer), deterministic moving/flash source proof. The existing CPU raster is only limited neutral-light preview.
- **FX-P3:** real passive silver and gold bounce geometry, BSDF/reflectance modeling and independently measured one-bounce illumination, area shadows and render acceptance.
- **FX-P4:** full editorial cut and original sound synchronization, installed Windows/Linux preview, captured effect retiming, DCI-intended image pipeline QC. Physical installed screen/flash warnings and theater ingest are separate gates.

**No completion claim:** No source implementation, path-traced bounce verification, true live clock capture or cinema-compliant light render is asserted by this design document.
