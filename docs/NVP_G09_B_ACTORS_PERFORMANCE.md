# G09-B — Actors and Performance Quality: source implementation

**Branch:** `nvp/g09b-actor-performance-20261111` stacked on `nvp/g09-production-environments-20261111`. **Status:** implemented source-level actor-direction, native articulated USD and source-based export integration. **Not** compiled or accepted on physical Windows. The creator's policy explicitly defers CI/PR checks, installed acceptance and consolidated regression until the full application backlog has been built.

## Filmmaker-first workflow

In **Edit Film → select a frozen Take → Direct the Performers**, the filmmaker sees names of actual characters from the approved scene, never a list of model commands, skeleton paths, audio sample formats or native worker settings.

For each current **ActorID**, the director can:

- Decide the actor's **movement style, gait energy, expression, blink pacing, physical proportions, skin/hair/eye/wardrobe color and hairstyle**.
- Add or remove **expression changes at specific scene moments**. Each cue has exact original Film Time and a chosen emotion and strength. The actor's head and brows ease between creative directions rather than holding one expression throughout.
- Preview actual source-based acting at selected scene times. The original G06 OpenUSD root movement, authored semantic gesture and action events remain the source; derived body/face animation plays on top.
- **Listen to a genuine original recorded dialogue delivery** taken from the immutable G06 microphone PCM corresponding to that ActorID in this exact Take. Accept or decline that source recording for facial animation, with direction and continuity notes. Neither words nor an original recording are invented. No synthetic TTS success is claimed.
- Approve the acting performance for the finished film, preserving earlier versions as editable history. A later change requires another explicit approval. Restore an older direction set as a new version without overwriting frozen Takes.
- Save an approved character appearance/base style under the same original **ActorID** and apply that continuity to later scenes. The stored baseline never transfers a different Take's actor object ID, voice recording, scene timing, expression cues or dialogue script; all new source-specific performance must be reviewed.

There is no automatic film export, native capture, file/network access or model authority in the actor interface.

## Original data / derived animation

**`backend/nvp_g09_actor.py`** owns project- and Take-scoped immutable draft/approved actor revisions in `g09_actor_versions` and `g09_actor_heads`. Reusing a character requires the same G04/G06 authoritative ActorID and a separate approved `g09_actor_templates` continuity record. Source SHA is checked against the frozen G06 Take and its verified G06 `_take` original PCM/USD auditor. Original project SQLite or protected G03 in-memory AES-GCM movie storage is used; no parallel plaintext actor database.

**`backend/nvp_g09_actor_rig.py`** authors a new, separately reopened USD actor scene layer containing real **UsdSkel Root/Skeleton/Animation** with a bounded 14-joint hierarchy, timed joint rotations/translations, typed local humanoid proxy geometry, hair/skin/wardrobe materials, jaw, eye/blink, brow and smile geometry. Timing comes from the source clock and G06 performer event interval; walking, jogging, running, crawling, look/gesture and human-reviewed expression decisions shape visible animation. The frozen G06 original root movement remains authoritative and is not re-authored from a newer scene. Neither source USD nor PCM bytes are overwritten.

**Actual speech-synchronized jaw:** approved actor sound is exclusively **original mono signed 16-bit 48 kHz native microphone PCM**. The actor's mouth amplitude is a bounded real RMS envelope of that waveform, and a producer/filmmaker may hear and approve the source. The signal does *not* determine phonemes, actual spoken words or actor facial capture. When G07 mutes a source clip, the final mouth closes; when it moves the sound relative to the picture, the final mouth animation follows the edited audio offset. Reused Takes with different voice timings produce separate verified derived actor layers **per edited shot**, each carrying the exact source clip/voice edit digest. Real PCM never becomes a source replacement.

**`backend/nvp_g07_edit.py`** exposes only **approved** ActorID directions under an independent `actor_performances_sha256`, alongside the G07 edit SHA and G09-A environment look SHA. **`backend/nvp_g08_native_avi.py`** refuses changes in approved performance digests, authors and reopens derived USD rig layers before film rendering, and uses their same source-time joint/face evaluation to produce actually articulated picture frames. The first G08 delivery remains bounded 640×360 MJPEG/PCM AVI; no photoreal claim. **`backend/nvp_g08_export.py`**, **`backend/nvp_g08_sealed_export.py`** and **`tools/nvp_g08_export_worker.py`** bind the actor SHA in ordinary/secure job records and fixed worker start/receipts. The source sound and G07 editorial mix remain intact.

**`backend/nvp_g09_actor_routes.py`** + **`backend/nvp_api.py`** expose filmmaker-only creative actions, no-store derived actor picture preview and no-store original microphone WAV audition through existing ordinary/encrypted project access. **`frontend/src/DirectorActorStudio.jsx`**, `director-actor-studio.css` and `DirectorFilmEditor.jsx` expose the integrated nontechnical UI.

## Explicit production-quality gaps

1. **No physical/source acceptance:** native USD skeleton and derived OpenUSD reopened in source logic only. Real USD/USD Skel validation on physical Windows, Blender/Cycles/Hydra, real loaded GGUF interaction, 24 fps motion, pixel/sound sync and actual 30-second completed film playback have **not** been exercised. There is no claim of real human face fidelity.
2. **No professional facial capture or phoneme alignment:** real PCM is used for jaw energy. Recognizing the true transcript, phonemes, vowel/consonant shapes, time alignment and fitted facial muscles requires separate specialist models/assets and explicit approval. Do not label RMS jaw motion phoneme-accurate lip sync.
3. **No ElevenLabs-class synthetic performance voice:** the project only provides genuine recorded human/actor voice capture and source-based audition/review here. Robotic eSpeak is not a substitute. Proper offline qualified emotional voice production and per-ActorID voice model eligibility/licensing remain open.
4. **No high-fidelity human-surface skin, calibrated rigging, physical hair/cloth, BVH/FBX retarget acceptance:** the new timed USD skeleton and animated visible geometry are a foundation; the actor is still a bounded stylized articulated representation. Existing older BVH parser and USD skinning primitives may be selectively integrated later after exact source/ActorID and licensing reviews; no false merge or imported human performance is claimed.
5. **No independent protected renderer sandbox acceptance:** ordinary export continues under the G08 host-owned worker and protected in-memory derived output. G03 AppContainer confinement/host-signed approval and physical key custody remain security requirements before release.
6. **No long-form film proof:** G08's initial 30-second/24fps production scope remains; the first actor-rendered exporter bounds up to 32 edited acting shots and 12 performers per Take. G09-E must implement true scalable source-aware chunking, durable checkpoints, bounded CPU/GPU budgets and 30-minute → feature-length acceptance.

**Next group:** **G09-C — continuous native 3D A/V, performance/capture synchronization, spatial sound, acoustic/environment interaction and host-supervised worker recovery**. G09-B quality gaps remain tracked under G09-B2/B3 and G09-D/G09-E; do not block unrelated implementation on routine GitHub Ops checks.
