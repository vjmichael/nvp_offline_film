# G07 — Non-destructive Post-Production implementation

**Source branch:** `nvp/g07-source-editing-20261111`, stacked directly on G06 (`nvp/g06-filming-performances-original-takes-20261111`).

**Creator's policy:** Finish the full application build before GH Ops/CI/PR verification, regression suites and installed-app acceptance. These G07 source edits have **not** been compiled, batch verified, independently executed or physically accepted. No claims of completed movie export are made.

## Filmmaker-first workflow

The main movie window has five stages: Script (optional) → Set Up Scenes → Film Scenes → **Edit Film** → Export Film. **Edit Film** opens a separate, clean Post-Production window. The previous empty timeline placeholder has been replaced by `frontend/src/DirectorFilmEditor.jsx`. The window continues to enforce the existing movie project/lock checks and unloads editing data when the movie becomes inaccessible.

The director can:

- Select a frozen G06 Digital Take from the current film and add it to a real editable shot timeline. Each shot remembers its exact Take digest and original film-clock source In/Out times.
- Trim, split, duplicate, remove, replace and reorder shots. Choose a straight cut or time-based dissolve. All changes create new, immutable decision versions; the original Takes remain unchanged.
- Reframe a shot after filming using **any** valid 3D camera position, look-at target or 12–180 mm lens—not only the three familiar G06 coverage suggestions. The editor records camera decisions by value, independently of later edits to the G06 camera presets or G05 stage.
- Adjust exposure, contrast, saturation and warm/cool look per shot as non-destructive color decisions. The WebGL preview approximates these looks; calibrated/native final film color transformation is later G08/G09 work.
- Independently enable/mute each original sound clip, change volume, left/right position, scene-space sound on/off and Film Time placement. Set a movie-wide sound level. The editor can **listen to up to five seconds** of the resulting mix through a disposable 48-kHz stereo WAV buffer; original G06 PCM16LE samples and their hashes are never rewritten. Native spatial sound currently models camera-relative panning and distance attenuation. Room propagation, occlusion and HRTF remain later quality work.
- Scrub/play a source-time scene preview. The native host opens the **original frozen OpenUSD performance**, samples exact world positions at the desired Film Time and resolves the saved camera. The separate Three.js monitor renders those positions. At a dissolve it samples both real source Takes with explicit overlap weights. No generated still image is mistaken for original film data, and no preview is committed as final picture.
- Ask the local GGUF-backed model for optional editing ideas (reorder, soft transition, warmer/cooler look), with a verified provider completion receipt. Each idea is project-/revision-/clip-bound and **requires explicit approval** before creating a new edit revision. Manual editing never requires the AI model to be online.
- Restore any earlier edit as a new version. No hidden source overwrite. All saved changes use an optimistic exact revision check, and broken/missing original Takes block source substitution or export.

The interface shows creative movie language and hides database, rendering and model operations.

## Native implementation

- `backend/nvp_g07_edit.py` owns the versioned edit decision list (EDL). Its one current head and immutable `g07_edit_versions` live in ordinary Studio SQLite or the project's existing sealed G03 SQLite. Clip references are verified against G06's `_take` frozen-source reader under the same project/transaction context: immutable Take SHA, source OpenUSD, recorded audio SHA, exact start/end ticks, selected camera, look, sound and transitions. It supports transparent, source-bound AI proposals in a separate review table.
- `backend/nvp_g07_preview.py` provides independently reopened time-evaluated OpenUSD picture snapshots and bounded original-source stereo sound windows. Sound is projected at integer 7,056,000,000 ticks/sec and original 48-kHz sample boundaries. The output WAV is **only a disposable listening envelope**, not a recording, flattened soundtrack or exported film.
- `backend/nvp_g07_routes.py` exposes strictly director-gated edit, history restoration, picture preview, no-store sound listening and AI proposals. These routes are mounted in `backend/nvp_api.py` for ordinary and encrypted movies without adding external file operations, source upload or worker authority.
- `frontend/src/DirectorFilmEditor.jsx`, `director-film-editor.css`: separate edit room with original Take picker, timeline, source-cropped preview, camera, color, sound, notes, optional AI proposals and edit history. A persistent WebGL context avoids repeated GPU context teardown while scrubbing; preview fetches are bounded, replaceable and cancellable.

### Exact G07 → G08 handoff

`G07Editor.native_assembly(project_id, revision=None)` is a **trusted backend-only** handoff. It returns:

- Exact selected edit revision and total presentation duration in integer Film Time ticks.
- Ordered source segments with Take IDs/hashes, source In/Out ticks and presentation start/end ticks, overlapping transitions, camera position/lens, grade and original-sound mixer decisions.
- Verified original G06 **OpenUSD world bytes**, **OpenUSD performance bytes**, event manifests, stage object records, **unaltered PCM16LE original sound bytes**, source audio placement/emitter bindings and full source SHA proof.
- A derived-film marker `source_media_modified=False`, `derived_picture_frames=False`, `final_movie_exported=False`.

G08 owns actual native 2D rendering, sound mastering, frame/sample projection and mux/package output. It must not replace original OpenUSD with an intermediate frame index, write to G06 sources or treat an editorial preview as film delivery. G08 can choose a cinema release cadence without changing G07's exact film-time decisions.

## Open limitations and acceptance (deferred)

1. **No native/compiler/device/installed-app acceptance** was executed in G07 under the creator's policy; physical Radeon and desktop memory/latency remain unknown.
2. **No production-quality pixel render or completed film export.** The live WebGL monitor is a source-based editorial proxy. Color management and native external renderer integration belong to G08/G09.
3. **No full-duration mastered playback.** Five-second, source-derived stereo listening windows are intentionally bounded. G08's continuous synchronized audio path and high-quality mastering remain open. Spatial audio is simple camera-relative panning and distance attenuation, not full acoustic geometry or multichannel cinema sound.
4. **No native render worker custody/recovery implemented in this group.** Editorial preview cancellation aborts client fetches; ordinary revision writes are atomic/transactional. Longer-running render/cancel/restart custody belongs to the production worker/export integration in G08/G03.
5. **Existing G06 original sound capture crash gap** remains open for interrupted *uncommitted* microphone sessions; completed PCM and frozen Takes are durable. G07 cannot synthesize or recover missing original audio.
6. **Large feature, actor-performance, long-film scaling and DCP** remain G09 work. G02 Lu workspace integration remains separately deferred; G03 secure migration/OS worker hardening remains a separate backlog.

**Next implementation group:** **G08 — Export Film.** Render one actual 30-second source-referenced performance film through a non-FFmpeg native picture/audio pipeline; preserve the reusable OpenUSD performances and original PCM; then extend the master/export path. Do not switch to CI until full application build work is done.
