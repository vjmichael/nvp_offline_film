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

## V-LIGHT-FX-03 — Movable passive silver/gold reflector boards

These are **physical reflecting surfaces**, NOT extra direct light emitters or post-process color overlays.

- Place a plane/card (single- or double-sided per user selection) with size, shape, bend/curvature (later), orientation, position and a pivot/stand. Support free move, snap, attach to rig/actor and lock as for light fixtures.
- **Silver bounce preset:** high but finite neutral spectral/RGB reflectance with a choice of diffuse/matte or directional/specular metallic-coated response, controlled roughness and reflectance. It can yield stronger, relatively neutral bounce subject to source and geometry.
- **Gold bounce preset:** warm/yellow-gold wavelength-dependent reflectance (or calibrated material approximation) that warms the **reflected** light and highlight/shadow fill; maintain physically bounded energy. Gold is NOT just a gold light source.
- Also useful future presets: white diffuse foamcore, black negative-fill flag, mirror/foil, silk/diffusion screen, grid/flag, and mixed silver/gold reflector. These are possible follow-ups, not yet required by the user's two specified bounce cards.
- Author as immutable OpenUSD geometric meshes + bound compatible `UsdShade`/`MaterialX` material parameters with original-source SHA, not synthetic in-process UI sprites. A render delegate must actually calculate at least one bounce/indirect transport or an explicitly labeled physically informed approximation. **The current NVP first-party CPU raster has no demonstrated multi-bounce GI; displaying a reflector in that preview does NOT verify reflected illumination.**
- Acceptance requires comparative real rendered pixels: same scene/card off vs silver vs gold, neutral vs warmer reflected illumination on an actor/object, shadows/reflections and multi-bounce energy tests against a suitable path-tracing renderer. Also validate USD/MaterialX translation and license/NOTICE requirements.

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
