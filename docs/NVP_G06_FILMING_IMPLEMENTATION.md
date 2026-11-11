# G06 — Film Scenes: build-first implementation handoff

**Development branch:** `nvp/g06-filming-performances-original-takes-20261111` stacked on G05's visual stage. G06 source features were written without invoking CI, PR checks, compiler gates or installed-app regression, per the creator's explicit build-first policy. **No native Windows/loaded-model acceptance claim is made.**

## Filmmaker surface

Film Home remains the creator's five-stage experience: Script (optional) → Set Up Scenes → **Film Scenes** → Edit Film → Export Film.

In **Film Scenes** the director chooses an approved G05 visual scene, sees three simultaneous **Wide / Medium / Close-up** 3D camera views, scrubs/plays a scene-time timeline and adds directions to actual characters, props and the environment. Actor actions: walk/jog/run/crawl (native USD timed translation source), gesture/look/expression/dialogue and wardrobe change (native USD timed semantic performance source). Prop actions: move/turn/interact; environment actions: wind/fog/rain/snow/light/ambient. A performerless landscape is valid and can be frozen without any invented cast or voice.

Right-click a performer in the camera preview to give a note, change wardrobe or ask the local model for a suggestion at that exact scene moment. AI output is a source/ActorID/revision/time-scoped proposal, and may be edited, accepted or declined. Only director approval creates a timed event. Approved wardrobe directions appear in the G04 Production Bible under the verified scene/ActorID; existing frozen Takes are never changed.

The director may operate the **native microphone** for voice/ambient sound. The host uses the existing miniaudio device (mono signed PCM16 at 48 kHz); original samples never originate in React or from model JSON. A sound recording may be stopped and saved or explicitly cancelled. The director can listen through a disposable no-store WAV playback envelope and place selected original clips at exact scene times. The PCM source remains unchanged. Recordings are bounded to two minutes per clip; longer recording and multi-device genlock are later work.

The **Freeze Digital Take** action copies the approved original USD world, authors an independently reopenable performance USD layer with exact time samples, checks original PCM sample hashes and stores a single immutable Take manifest and originals transactionally in the film's existing SQLite storage. For secured movies it uses the existing G03 sealed SQLite rather than plaintext sidecar storage. The director may refuse the current performance and start a retake; previous Takes and working revisions survive. The director may reopen earlier working directions as a new revision.

**Wide / Medium / Close-up camera plans are separate mutable revisions** referencing the Take. Changing lens or camera position after freezing does not alter the original Take digest or PCM. Time is authoritative 7,056,000,000-ticks/second Film Time, not fixed video frames. A temporary Three.js camera preview is not misrepresented as final filmed picture. No FFmpeg or flattened film media is required at this point.

## Internal source additions

- `backend/nvp_g06_filming.py`: G05 stage source binding; exact-timed typed events and revision history; OpenUSD native performance time samples; source/world and original PCM SHA checks; single-commit Take publication; original-source reopen; independent G07/G08 trusted `native_take()` reader; camera-independent framing revisions.
- `backend/nvp_g06_native_recorder.py`: host-owned native PCM16 microphone input, bounded callback sample ledger, cancellation and error guards, source publication only when a valid completed recording exists.
- `backend/nvp_g06_routes.py`: director-only routes using existing G03 project access and encrypted film storage; no routes for arbitrary audio upload, filesystem paths, model authority or rendering worker launch.
- `backend/nvp_api.py`: mounts filmmaker routes, allows only project-guarded live filming routes for secured films, cancels native microphone sessions when a movie is locked.
- `backend/nvp_g04_preproduction.py`: projects director-authored wardrobe continuity back into the Production Bible for exactly matching scene revisions.
- `frontend/src/DirectorFilmingStudio.jsx`, `director-filming-studio.css`: 3D preview, world-time timeline, performer/prop/environment direction, actor context menu, optional local AI note review, native sound audition, retakes/freeze, Take list, camera framing.

## Incomplete or deferred work

- **Native physical acceptance:** genuine microphone permissions, loaded local GGUF actor-note inference, real OpenUSD independent process reopen, Windows installed UI/VRAM and long-running recovery have **not** been executed under the creator's defer-verification instruction.
- **Original recording interrupted mid-clip:** the G06 host fails closed and cannot publish an interrupted microphone session as authentic source. Its bounded live microphone samples are in memory until completion; they are **not durably recoverable after a process crash**. Completed, committed original PCM and Takes are durable. A protected worker-level in-progress capture journal remains part of G03/G09 production hardening; do not misrepresent this as solved.
- **Full actor biomechanics/voice synthesis:** walk/run/crawl author native timed world translation and semantic action; complex skeleton gait, expressions, lip sync and ElevenLabs-class generated voice are not implemented here. They remain G09 production capabilities.
- **Weather presentation:** OpenUSD ambient events and approximate 3D preview cues exist, but full physically simulated atmosphere and cinema-quality render parity remain G09.
- **Production sound:** original mono PCM with spatial emitter references is preserved; advanced microphone calibration, multichannel location sound, HRTF/acoustic simulation and final mixing remain separate integration/quality work.
- **Legacy/secured worker custody:** historical migration, full Windows AppContainer production-worker acceptance and owner-key recovery remain open G03 work. No unsafe bypass or automatic film source cutover was introduced.

**Next implementation group:** **G07 — Edit Film**. Consume `G06Filming.native_take(project_id,take_id)` and camera revisions directly, use non-destructive picture/sound assemblies and source-referenced edit decisions; do not mutate frozen source. Batch compilation, CI, regressions and installed acceptance only after NVP's full application build, as requested.
