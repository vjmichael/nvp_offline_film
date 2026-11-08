# FILM-01 — First original 30-second NVP short: "Signal Restored"

**Date:** 2026-11-08. **Implementation:** first original source, editorial and
original sound, with an optional authentic low-resolution NVP CPU rendering
export. **Not** a completed released movie, photorealistic 2K, mastered
film or DCI-accepted package. Its visible frames must be independently
reviewed and improved before film acceptance.

The original general FILM-01 acceptance remains
`docs/NVP_FILM01_FIRST_PHOTOREAL_SHORT_ACCEPTANCE.md`:
30–60 seconds, at least three visually different shots/two cuts, a
timed meaningful action and synchronized original sound, genuine
rendered photorealistic picture, editable source, fully playable
picture+sound master and independent artist review. This first 30s
technical film proof addresses only a subset.

## Original short: story and shot breakdown

**Working title:** *Last Light at Relay Nine: Signal Restored*.
A service craft returns to a dormant communications relay. An engineer
discovers the antenna is unpowered. At the end, the engineer reconnects
the beacon and a signal chirp is heard.

| Source shot | Film output | Action | Original source |
|---|---|---|---|
| **Arrival** | 0–10 s / frames 0–239 | Wide view of approaching craft, dark relay, engineer | Original OpenUSD scene revision 1, frozen Take 1; original 10s captured audio |
| **Discovery** | 10–20 s / frames 240–479 | Tighter angle as engineer approaches dead antenna | Scene revision 2, frozen Take 2; different 10s recorded source |
| **Rekindle** | 20–30 s / frames 480–719 | Engineer reaches beacon; timed original chirp at output 26.0s | Scene revision 3, frozen Take 3; original ambience plus exact 0.5s chirp |

Three **real NVP authored** scene revisions share an underlying
canonical scene/asset palette, but each Take freezes the correct
immutable revision, actor and craft transforms, camera angle, source
event ledger and PCM. All three original Takes reference OpenUSD
geometry/actor movement/camera/light and separately captured 48kHz
mono PCM16LE sources. The last scene has a discrete cue anchored at
Film Time 6s in its own Take; when played after two 10s editorial
segments, the signal event is at film 26s.

A real `DigitalSlateBranches` graph has three performance branches
and an explicitly committed `SlateSequenceAssembly` edit covering
the entire 30s with exactly two hard cuts, no silent take recreation.
This is SOURCE-ONLY editorial authoring in disposable CI, not
automatic human director approval.

## Native real-render 30-second review package

`tools/nvp_film01_original_30s.py` supports two explicit operations:
create a **fresh** original source workspace (SQLite/FilmIndex,
OpenUSD/USD geometry, original PCM, source events, frozen Takes,
committed native three-shot edit), and optionally render a complete
**720-frame** review ZIP via the existing first-party WO6-07F
`rendered_source_window`.

This is not a fake video made from reference stills. Every frame is
freshly rasterized as a true 640×360 source-authored OpenUSD PNG by
`NativeSceneLinearRaster`. The same exact source Film Time selects
2,000 original recorded PCM16 samples per 24fps frame. The native
export packs all 720 exact numbered PNG frames and one matching
48kHz mono WAV containing exactly **1,440,000** original source
samples, plus original Take/segment/scene tick and SHA for each frame.
The exporter never holds the whole RGB film in RAM: each six-frame
native window is verified and written directly to ZIP. The PCM
accumulator remains bounded by the 30-second film duration.

**Important:** The archive is a **frame sequence plus separate WAV**,
not a finished playable synchronized MOV/MP4, cinematic 2K quality
proof, Dolby-style mix, SMPTE DCP or photorealism acceptance. An
artist can import the frames as a 24fps sequence with 48kHz WAV in
a capable review/editor application. NVP still needs an approved
native reviewable audio/video movie packaging path and true cinema
mastering from its original data. A partly completed archive MUST
not be advertised as a full thirty-second film.

Run in a fresh controlled environment:

```bash
python -m tools.nvp_film01_original_30s \
  --root "/absolute/fresh/work/relay30" \
  --render-review-zip "/absolute/fresh/out/relay30-source-preview.zip" \
  --consent I_APPROVE_DISPOSABLE_ORIGINAL_30S_CI_SOURCE
```

`--render-review-zip` can be omitted to audit only the immutable
source and exact edit; `--max-frames 6` is for short native smoke
tests, not completion. CI exports the **full 720-frame** archive only
after it can prove full original source and real raster/PCM integrity.

## Virtual lighting in this short

The new `backend/nvp_virtual_light_fx.py` is a pure, deterministic
**data evaluation** component. It currently describes virtual
silver/gold targeted fills, a fixed summer 3pm sun, police
red/blue oscilliator, and a time-capturable firework flash with
source-safe hashes. Two evaluation decisions (sun lock for relay,
gold face fill for engineer) accompany the short's source receipt.

**These two digital artistic fills are NOT yet rendered.** This
is a deliberate candor safeguard: WO6-07F CPU raster only implements
its existing limited native source light. A future shader/renderer
adapter must actually use virtual light FX target masks at Film Time,
with explicit before/after artist review and color-managed 2K.
The new script cannot claim the gold fill altered an actor's pixels.

## Acceptance matrix and failure policy

Workflow: `.github/workflows/nvp-film01-original-30s-preview.yml`.

- Windows 2025 and Ubuntu 24.04 native Python 3.11 tests create the
  actual three OpenUSD Take revisions, graph and 30s edit; verify
  source hashes, three distinct cut projections, real PNG/PCM
  output samples and one time-critical sound event. Pure V-LIGHT
  tests verify deterministic silver/gold/sun, recorded independent
  police phase, firework envelope and malformed data refusal.
- A dedicated Linux job exports **all 720** actual frame windows
  (and **1,440,000** matching recorded audio samples), checks
  exact PNG count, source metadata, WAV format/duration and packaging
  SHA; only then uploads a GitHub Actions artifact. This is real
  native CPU raster work, potentially much slower than realtime.
- No CI success, downloadable artifact or physical installed
  playback is claimed until the exact-head runner actually finishes.
  The exported ZIP is eligible for manual creative review, not
  automatic film acceptance.
- Still OPEN: finished picture/sound playback as ONE movie,
  meaningful facial/actor performance quality, precise native 2K
  cinema-grade renderer/color-managed light/materials, practical
  application of digital sun/gold/other lighting cheats, 24-bit
  multichannel mastered PCM, scene-linear 12-bit XYZ DCP encoding,
  independent DCP ingest, physical installed Windows UI, 30-minute
  original finished pilot, and feature/epic endurance.

The creator's joke about a direct download link is understood:
**only a genuinely produced artifact may be linked**. GitHub's
artifact URL becomes an actual candidate after a successful render;
the PR or queued workflow is not a playable film.
