# FILM02-01 — Original 30-second film to real Blender: exact source handoff

Date: 2026-11-08
Status: **IMPLEMENTED / native Windows+Linux acceptance SUBMITTED, not yet established**

## Why this group follows FILM01

FILM01 real Blender/Cycles accepted the 72-frame donut/box/sphere
three-second diagnostic in [run 42490015508](https://github.com/vjmichael/nvp_offline_film/actions/runs/42490015508).
That proved authentic external Cycles rendering, separate-process Blender
readback, and source/worker SHA custody. The director retake with
revised lighting/material/motion remains a separate visual/native gate.

The next step is **not** to write another rendering engine. It is to map
NVP's existing original 30-second three-shot story to the SAME
external-Blender worker boundary, while preserving real editing and audio.

The original story is "Last Light at Relay Nine: Signal Restored":
arrival, discovery, rekindle. It contains three 10-second frozen source
Takes, exact FilmIndex cut boundaries at output frames **240 and 480**,
an engineer object-actor rendered as a genuine torus, a green box
crossing behind it, a blue sphere passing through its hole, a practical
light, and a beacon signal at frames **624..635** (26.0–26.5 seconds).

## FILM02-01 delivered source-only bridge

- tools/nvp_film02_blender_handoff.py reads an **existing frozen**
  write_original_30s_source fixture, verifies the editor-committed
  Relay30Edit SHA through SlateSequenceAssembly.open_edit, and
  checks both original in/out moments through source_at for every cut.
- All **720** output frame slots are independently evaluated at 24fps
  using FrozenSceneAV.snapshot on their proper frozen Take.
  Each output includes source and output Film Time, source Take
  and segment SHA, exact scene SHA, original snapshot SHA, authored
  seven camera/light/object/prop 4×4 matrices, and original sound
  event identities. It never interpolates across an editorial cut.
- OpenUSDAssetRegistry.open reopens and validates the source USD
  geometry layers and material bounds; five bound objects are
  represented by original asset document SHA and authoritative typed
  geometry/material data, not arbitrary Blender scripts or paths.
- Original 48kHz PCM source documents are pinned by their native
  FilmIndex SHA. **No new audio samples are generated here**, and no
  invented finished soundtrack is declared.
- The full manifest is canonical SHA-256 digested; validate_handoff
  independently rejects edited cut pointers, missing frames, actor
  or camera gaps, wrong Take SHA, mistimed chirp and bad matrices.
  The source report and Takes are checked again after construction.
- A derived output may be written **once** to a separate trusted path.
  It must never overwrite the source fixture. The test fixture consent
  is specifically CI-only, not actual creator permission to render.
- .github/workflows/nvp-film02-blender-30s-handoff.yml requests
  **real Windows 2025 and Ubuntu 24.04 OpenUSD execution**, the
  original native Blender worker authorization/cancellation/journal
  regression tests, and a separate Linux source-handoff artifact.
  The artifact is explicitly labeled **NOT A MOVIE**. CI green cannot
  be called real Blender picture or physical installed-app acceptance.

## Next work groups and explicit gates

**FILM02-02 — Real three-shot supervised Blender/Cycles picture.**
Adapt the proven fixed-trusted Blender worker, using approved finite
source data only. Honor actual camera transforms and 5 NVP primitive
geometry assets; make one true render for each 720 Film Time slots,
without an invented shot transition or implicit model tool permission.
Output original full-frame PNGs/EXR and per-frame source hashes.
Use chunked worker/checkpoint policy; do not assume a single
600-second CPU job can render an entire film.

**FILM02-03 — Source audio and continuous director review.**
Preserve the true 48kHz original WAV/PCM sound, and mux only verified
picture plus source sound at exactly 2,000 mono samples per 24fps
frame. Preserve the two cuts, the 26s beacon cue, 30s duration and
frame-exact audio sync. Generate a genuinely playable file for
creator visual/audio assessment, not a silent diagnostic GIF.
Use the existing trusted playback architecture and no FFmpeg runtime.

**FILM02-04 — Director visual, performance and edit approval.**
Watch actual output; assess lighting, composition, camera, actors,
material and sound. Store observations and creator-approved retakes as
new linked versions, not silent mutation of frozen takes. No production
creator grant is implied by the CI fixture.

**Larger project targets remain:** original up-to-30-minute creative
pilot, 60–90-minute genuine feature, 3-hour-plus endurance, installed
Windows/Linux playback, legal notice/Blender GPL review and independent
calibrated DCP/SMPTE Bv2.1 verification. Passing a preflight 720-frame
source manifest is *not* any of these outcomes.
