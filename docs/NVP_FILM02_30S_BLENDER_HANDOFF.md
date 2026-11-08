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


## FILM02-02 — Native supervised real Blender/Cycles implementation (2026-11-08)

**Code and genuine GitHub OS-render workflow submitted; native full 720-frame
acceptance must still be confirmed by completed run artifacts.** Do not
treat queued or cancelled jobs as a finished film.

- Fixed, first-party GPL Blender-side adapter:
  tools/nvp_film02_blender_cycles_worker.py; imported only by the real
  independently launched Blender binary, never by NVP Core. It receives
  a SHA-bound 24-frame chunk derived from the frozen source; constructs
  the five original FilmIndex USD-bound assets (including the genuine
  torus), camera and practical light. The USD row-vector matrices are
  explicitly transposed for Blender's column-vector convention.
  Blender/Cycles CPU produces actual 640x360 PNGs with eight samples
  and secondary lighting bounces, along with a derived source .blend,
  one real verified preview and a per-frame image/SHA/time audit.
- Host adapter:
  tools/nvp_film02_blender_cycles_acceptance.py reopens the full 720-frame
  original Take handoff and actual FilmIndex source on *each* runner, then
  splits one source shot into 10 batches of 24 frames. Every batch runs
  through the preexisting ApprovedBlenderDispatcher, TaskLedger and
  BlenderWorkerSupervisor. All native resource/approval/cancellation,
  timeout, journal/restart and OS-worker-containment contracts are reused.
  Already successful chunks can be independently reverified on restart;
  interrupted/failed chunks are NOT automatically replayed or accepted.
  Three shots = 30 independently journaled real Cycles jobs.
- Blender independent readback:
  tools/nvp_film02_cycles_reopen.py is a second native Blender process
  that reopens the original .blend for first and last batch per shot,
  checks original source mesh identity, real camera/light/actors,
  first/last matrix poses and true Cycles settings. The working adapter
  cannot self-attest as an independent second process.
- Final pixel evidence:
  tools/nvp_film02_cycles_collect.py refuses any missing PNG, camera
  source, interrupted worker, absent readback, frame SHA/time mismatch,
  foreign source project or edit SHA, changed cut at 240/480, or
  incomplete 720 original frames. Only after all three shot outputs
  pass does it create a genuine 9-frame Cycles director contact and
  comprehensive source frame receipt. It explicitly does NOT claim
  a synchronized playable film or the original soundtrack.
- Real GitHub verification:
  .github/workflows/nvp-film02-real-blender-30s-render.yml
  runs native Windows/Linux source and supervisor tests, freezes a
  **single** original source project ONCE, distributes the identical
  checked original project/720-frame manifest to 3 parallel Ubuntu
  jobs, downloads official SHA-verified Blender 5.2.3, and renders
  each real 240-frame shot. The final collector checks all 720 genuine
  Blender frames before publishing a director sheet.
  Failed workers upload separate explicitly labeled diagnostic logs.
- Testing boundaries:
  tests/test_nvp_film02_blender_cycles_source.py checks all thirty
  exact-source 24-frame batches, no frame crossing edits, shared project,
  source SHA and source packet tamper rejection and supervised staging
  without pretending that staging is an actual Blender render.

**Open, not waived:** exact current-head Windows/Linux CI evidence;
successful actual three 240-frame Cycles artifacts; separately reopened
saved .blend/native pixels; human director visual review, timing and
reflection/shadow assessment; FILM02-03 genuine original source PCM and
continuous 30-second synchronized playback; real installed Windows
Blender/GUI, GPL notices and eventual calibrated 2K/DCI acceptance.
