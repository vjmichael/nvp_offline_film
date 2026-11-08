# FILM01-R2 — Native 30-second film viewing and visual/sound acceptance

Date: 2026-11-08. Branch `nvp/film01-native-visual-audio-qc-20261108`.
Stacked on V-LIGHT-R1 PR #107. State: real source/validation code
committed; complete native Windows/Linux and paired 720+720 exported
movies NOT ACCEPTED until jobs genuinely execute and a person watches.

## The goal is to watch the actual original film

The director explicitly wants to see the first original NVP 30-second
short, not just a test summary, JSON receipt, illustrative storyboard,
or promised file link. A true deliverable must include a single
picture+sound review AVI, original SHA-checked picture PNG sequence/WAV,
a contact sheet made from actual pixels and a technical QC report.
A completed NVP source rendering is necessary but NOT sufficient for
creative quality; the human can reject all aspects of the short.

`Last Light at Relay Nine: Signal Restored` is deliberately simple:
three 10s source Takes, service craft returning to a relay, an engineer
connecting an antenna and a sound cue at film time 26.0–26.5s.
It currently has **sphere / cube geometry** and linear object translation.
The story's intent is registered; no code generator can pretend those
shapes, movements or tonal audio amount to a believable film.

## Source custody problem found and resolved

The two prior independent baseline and FX CI workflows each CREATE a
fresh original project. Even with identical script and edit decisions,
their immutable scene/Take/document hashes may legitimately differ:
OpenUSD layer source identities, project IDs and creation metadata
are independently published. **A rigorous source-to-source virtual
lighting comparison cannot silently assume the same frozen Take
just because the titles match.**

New `tools/nvp_film01_render_paired_original.py` creates **ONE** fresh
original FilmIndex/USD source project and native committed edit.
It separately renders baseline and virtual-light versions FROM THAT SAME
project and same exact event/PCM source. Each gets its own complete 720
PNG/1,440,000 PCM archive, actual indexed 24fps MJPEG/48kHz PCM16
AVI, and native film quality report. Only after both original media
reopen and pass independent AVI JPEG/index/PCM decode does it generate
a paired contact image with side-by-side pixels at 0, 2.5, 9.96, 10,
15, 19.96, 20, 26, 29.96s. Original Take and sound hashes are
verified byte-for-byte equivalent and actual RGB pixel differences
are measured. No added stills, duplicated motion, random AI images,
fake PCM, or edited Take source are accepted.

The original baseline/FX PRs remain useful independent visual
individual specimens, but are not treated as cryptographically
identical source pairs until a shared-origin acceptance proves it.

## Objective picture and sound quality controls

New `tools/nvp_film01_native_visual_audio_qc.py` only opens the real
**complete** source PNG/WAV ZIP. All 720 manifest row slots must
exist in exact order and have the same source Take within each shot,
with exactly TWO source cuts at 240 and 480. All 720 source time
receipts carry true original sound event IDs. The signal chirp
must appear on frames **624 through 635** (film 26.0–26.5s) and
nowhere else; original mono 48kHz PCM must contain exactly 1,440,000
samples and match its SHA.

Image inspection samples 25 original frames including edit boundaries
and the critical sound cue. It computes authentic per-frame RGB
brightness, luminance percentiles, nearly black/white pixel ratios,
within-shot motion/pixel differences and cross-cut image differences.
An original frame never gets silently repeated or replaced by a
generated placeholder. The original geometry registry is declared,
so reviewers can identify intentional cubes and spheres instead of
guessing whether a character rig failed to load.

Audio inspection measures true PCM peak, RMS, clipping, near-silence
and three shot-level spans, plus signal audio statistics immediately
before/during/after 26 seconds. An audible cue can still have poor
creative quality, so the metrics report probable concerns without
declaring that the mix is acceptable. Dark/abstract visuals may be
intentional and are never disqualified automatically by heuristic
brightness or movement tests. Source missing/truncation/false
frame/Take/timing identity **does** fail.

New `tools/nvp_film01_compare_rendered_light.py` accepts ONLY
two 720-frame **same source** archives with identical original
film cut, original Takes, Film Time and recorded sound. It measures
real RGB image deltas for baseline vs deliberately nonphysical gold
fill / fixed summer 3PM sun, then creates one genuine paired
contact sheet for the director to review. It refuses incomplete
or mismatched versions. The output remains uncalibrated 640x360
preview, never cinema-quality PBR/color.

## Native acceptance and delivered artifacts

`.github/workflows/nvp-film01-native-visual-qc.yml`:
- Windows 2025 and Ubuntu 24.04 actual OpenUSD native tests reject a
  real six-frame original source masquerading as 720 frames, and
  reject a fake complete baseline vs FX comparison.
- An independent Ubuntu real-original job renders 720 + 720 frames
  from ONE pinned scene/Takes/PCM, then independently reads both
  AVI container indexes, every JPEG picture and PCM block, performs
  source film and 26s sound event QC, and compares both lighting
  treatments. The real output artifact is uploaded **only on
  overall job success**, not for partial rendering or failure.
- Expected director artifact:
  `nvp-relay30-two-real-30s-film-looks-plus-visual-sound-QC`,
  containing two ordinary 30s AVI review files with original sound,
  two 720-PNG/WAV source ZIPs, two quality reports, a side-by-side
  gold/sun comparison contact sheet and an exact source/edit receipt.

The job allows offline rendering to run slower than 24fps.
Only **actual** movie playback on a visible native Windows screen
and audible speakers can independently demonstrate viewer timing,
codec support and smooth presentation. These are still OPEN.

## Visual inspection rubric: what to improve after watching

| Area | Current authored source / expectation | Judgment to make from actual pixels/sound | Likely next development |
|---|---|---|---|
| Geometry | RelayCore sphere, Engineer sphere, ServiceCraft cube; true USD asset bindings | Is each silhouette legible, recognizable, properly proportioned? | Replace proxies with scene-authored detailed mesh/character skeleton/ship and textures |
| Animation | Actor/craft transform keys with 2 samples/10s | Movement readable, plausible, varied? Any slipping, robotic movement, penetration? | Motion paths, easing, skeleton rig poses, contact/interaction animation |
| Camera | Three authored translated camera positions; native perspective only | Does each shot communicate new information? Is the subject framed and visible throughout? | Per-shot aiming/look-at, orientation/track/dolly/zoom and camera preview composition controls |
| Lighting | Source SphereLight, virtual engineer gold fill / fixed summer sun in optional preview | Can the engineer and relay be seen? Does gold treatment read clearly without clipping? | Virtual per-object light controls, user adjust intensity/color/wrap and independent light clock controls |
| Sound | Three computer-authored 48kHz tones + 0.5s timed chirp; no mastered mix | Is the cue audible at precisely 26s? Are sound levels balanced, meaningful or grating? | Actual source recorded Foley/ambience, dialog, sound-design timing, multichannel PCM24 finishing |
| Export | 640x360 MJPEG+PCM16 AVI with source PNG/WAV, not DCI | Does a real independent Windows player open it? Is picture/audio in sync, edits clean, no glitches? | Installed playback verification; native 2K full-quality color-managed render/JPEG2000 MXF/DCI and sound master |

**Acceptance distinction:** a rigorous source and native stream test may
pass while artistic quality is judged unacceptable. No automatic test
may claim finished cinema quality. The original FILM01 photoreal
short standard and DCI 2K finishing remain separate open gates.

## Current blocker

GitHub's FILM01 PR #106 and V-LIGHT PR #107 dedicated Windows/Linux
jobs were queued/pending at this inspection. No completed original
movie/contact sheet was available to watch or supply by sandbox link.
This work group does not invent a file or treat an existing workflow
URL as a finished artifact. Inspect exact-head jobs and **only once
the real media are accessible** evaluate and show actual sample frames.
