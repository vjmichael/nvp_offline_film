# FILM03-06 — REAL supervised ActorID speech and Blender motion workers

**Implementation branch: nvp/film03-06-supervised-voice-animation-workers-20261108.**
A new source implementation is NOT technical acceptance until the exact-head
Windows/Linux native tests and genuine generated WAV/.blend/Cycles PNG artifacts
pass independent verification. Physically installed director acceptance,
full neural TTS and actual artist/audible approval are separate open gates.

## ActorID is the only authoritative character identity

An AI output must NEVER become a character voice or motion merely because
the model says "This is the DONUT". The source-of-truth is NVP's existing
canonical StoryBible ActorID and current director-published identity profile.

That profile includes appearance, personality, signature movement/odd gait,
VoiceType, current VoiceID, exact voice reference SHA and the reviewed
engine/model/voice-selector settings. Every generated candidate includes the
source ActorID, selected Take SHA, source script line SHA and profile/VoiceID
identities; mismatches fail closed rather than silently recasting characters.

The approved PROFILE is not an execution permission. Model output or ordinary
web API cannot submit arbitrary executable paths, Blender Python, provider
URLs, new voice selectors or invented source Takes. The existing trusted
desktop host must make two separate confirmations: creator intent AND native
OS execution under the exact source/operation digest. Installed host
configuration supplies the executable and its SHA, never the browser.

## Real spoken voice generation: eSpeak NG pilot

- backend/nvp_film03_actor_voice_worker.py executes the real reviewed
  **eSpeak NG 1.51** offline rule-based speech engine. It is an actual speech
  synthesizer and verified audio producer, **NOT** a neural voice model or
  speaker clone, and is not silently claimed to match a human actor.
- Requires exactly NvpEspeakNG / EspeakNG / EspeakNG_1_51 in the current
  ActorID profile, plus a restricted installed voice selector (e.g. en-us).
  Rejects unsupported engine parameters (seed/stability/pitch-shift) rather
  than pretending to honor them.
- Source text comes ONLY from ActorDialogueManager's exact original
  screenplay, selected unrecorded performance, fully verified OpenUSD cast,
  ActorID and source Take. It stages the fixed text and immutable contract in
  a private job directory, SHA-pins the executable, checks runtime version,
  then invokes the reviewed command as an argv array under NVP's existing
  launch_contained OS execution layer. No shell, internet, external model
  code or browser-supplied file path.
- The worker reopens the source after native execution to reject changes
  during its run, rechecks source contract, binary and text SHA, independently
  decodes actual generated WAV into non-silent bounded PCM16 mono, and
  registers the WAV as an immutable FilmIndex content-addressed blob. A
  separate versioned **unapproved** FilmIndex asset candidate includes:
  ActorID, VoiceID, VoiceType, source script/Take/profile hashes, versioned
  executable, actual engine selector, voice wav/PCM hashes and sample count.
- Uses a durable local journal and kernel-backed host lease. Replays of
  completed/failed/interrupted work IDs are refused. Windows uses
  suspended process creation and a Job Object, while Linux uses the
  existing process guardian; the latter is NOT a guarantee about every
  hypothetical detached grandchild unless strict cgroup v2 custody is
  selected and independently proven.
- Neither a successful process nor a valid WAV establishes acoustic
  same-speaker fidelity. The output **cannot become an approved recorded
  performance or production soundtrack** until a separate director audition,
  speaker-consistency review, sound source binding and editorial approval.
- No eSpeak binary is bundled by this PR, and distribution/license review
  is open. NVP's native desktop must supply a reviewed installed binary SHA.
  The native Ubuntu CI obtains the Ubuntu 24.04 eSpeak NG package separately.

## Real procedural gait: original OpenUSD actor -> supervised Blender

- ActorIdentityCore now has an optional explicit **gait_preset**
  ("steady", "lopsided_roll", "uneven_step", "unconfigured"). Old profile
  versions remain readable; "unconfigured" cannot be executed. Vague
  prose is NEVER interpreted by AI as an executable motion profile.
- A director selects the preset in the Story Bible. The original
  characteristic gait/behavior/quirks remain separate descriptive identity
  traits, still available to future animation and film research workers.
- backend/nvp_film03_actor_animation_host.py opens the exact frozen
  FilmIndex Digital Take and OpenUSD scene, requires complete canonical
  actor casting (every authored actor prim has exactly one ActorID),
  verifies actual source meshes, camera, light, all actor transforms,
  original per-frame snapshot SHA and current approved profile/VoiceID.
  A bounded 2–24 frame packet carries source time and the exact actor
  prim to animate.
- tools/nvp_film03_actor_animation_worker.py is a fixed first-party
  Blender Python script. It uses Blender's own mesh, animation and
  Cycles APIs under the established BlenderWorkerSupervisor, with a
  SHA-pinned worker script and immutable source packet, native
  memory/resource supervision, OS process containment, cancellation,
  durable journal/recovery and independent input/output SHA checks.
- Exactly ONE source cast actor receives approved procedural gait
  keyframes; original camera, light, background and every other actor
  remain source-positioned. A real .blend animation, Cycles PNG preview
  and per-frame ActorID/source/transform receipt are generated.
- The host verifies every gait frame, source snapshot, cast source SHA,
  Blender binary+script, .blend/PNG bytes and current ActorID profile,
  reopens the original source AGAIN after execution, and publishes
  content-addressed .blend and PNG into FilmIndex. Its new asset
  candidate is explicitly **not approved for the editorial film**.
- A separate Blender process reopens the saved scene.blend, checks
  actual source character keyframes, original 4-actor cast and
  unmodified other-actor matrices at every frame. This is stronger
  than trusting the worker's own JSON receipt. It is a native test
  oracle, not a new user-facing renderer.
- The current pilot supports original OpenUSD mesh/cube/sphere actors
  and one selected frozen Take range. Fully general armatures, facial
  rigging, cloth and arbitrary game engine actor geometry remain open
  and require reviewed extensions rather than invented transforms.

## Actual installed NVP integration

TrustedDesktopWO6Bridge.film03_run_actor_voice_candidate and
film03_run_actor_animation_candidate are first-party native IPC actions.
They receive only source ActorID/script/performance/Take/frame identities
and job ID, **not executable paths**. The first-party installed host
bootstrap must inject reviewed binary manifests with executable path,
SHA-256 and exact version. No provider configured => fail closed.
Both actions use separate creator/OS execution consent and return verified
source receipts/candidates rather than silently altering the original film.

The current native bridge uses synchronous process invocation, so
production interactive dispatch (non-blocking UI progress, explicit
cancellation and durable job recovery) remains an open desktop
integration gate. Do not represent this as a completed installed alpha
workflow. The native jobs and source validation are independently testable.

## Real native acceptance

.github/workflows/nvp-film03-06-real-actor-workers.yml:
- Windows 2025 and Ubuntu 24.04 source-contract and cross-character
  regression (actual Studio/FilmIndex/StoryBible/USD identity checks).
- Ubuntu native eSpeak NG engine: execute real original screenplay
  into nonzero generated PCM WAV and separately decode/rehash the source
  plus FilmIndex candidate. Upload WAV and original source/receipt.
- Ubuntu official Blender 5.2.3: verify download against Blender's own
  SHA, launch under NVP's existing contained BlenderWorkerSupervisor,
  produce real 4-frame actor gait in a .blend and Cycles PNG, then
  independently reopen in a new Blender process to check the original
  four actor prims, source matrices and gait. Upload .blend, PNG,
  source manifest, native audit and independent reopen evidence.

Native CI uses a **disposable, TEST-ONLY** original Studio/OpenUSD source
and a TEST-ONLY reference PCM to establish ActorID/VoiceID source lineage.
A generated eSpeak spoken WAV can be genuine speech yet still fail
artistic voice continuity, particularly when the reference is test noise.
No AI-generated audio is mixed into FILM02's existing 30-second original
Cycles/PCM AVI, and no generated gait silently replaces its source Take.

## Open gates

Native exact-head CI results and repairs; actual Windows eSpeak runtime
packaging and binary/license compliance, full Linux kernel cgroup
descendant protection for high-risk engine providers; neural TTS
provider/model/voice pack verification and replay-safe execution;
acoustic speaker/timbre consistency measurements and human audition;
actual director approval of resulting spoken/audio and animated Takes;
nonblocking installed desktop progress, cancellation and restart; fully
general rigged/recast actors and spatially synchronized dialogue; final
director picture/audio approval.
