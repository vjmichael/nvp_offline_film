# FILM03-05 — ActorID as the Character's Authoritative Core

**2026-11-08: implemented source model and genuine native-test/React acceptance
submitted. The actual verified voice-generation WORKER and installed filmmaker
approval tests remain separate OPEN gates.**

## The fundamental invariant

A character is the product of everything linked to ONE durable ActorID.
A screenshot or a mesh filename is NOT that identity. Character names may
change, lines can be rewritten and wardrobe/voice/mesh may evolve, but every
source decision belongs to the same project-scoped canonical StoryBible
character entity ID (ActorID).

The same ActorID owns:

- **Looks:** linked original models, meshes, textures, materials and
  wardrobe from existing production-bible resource registry; a separate
  actor-specific appearance profile for consistent silhouette, visual
  expression, distinguishing marks and surface treatment.
- **Voice:** current unique, human-approved VoiceID, its immutable recorded
  voice reference, independently approved individual recordings, and a
  separate descriptive **VoiceType** for generated voices.
- **Voice generation:** explicit model/engine identity and version, provider
  voice selector, deterministic seed, speaking rate, pitch adjustment,
  stability and language. These settings belong to the ActorID, not to
  the model's prompt interpretation of the character name.
- **Behavior:** personal traits, habits, emotional reactions, motivations
  and characteristic speech rhythm. They persist across shots.
- **Physical action:** posture, gait, gestures and movement peculiarities
  such as an uneven walk, slow leftward recovery or a distinctive wobble.
  The original behavior source travels into future animation/AI work.
- **Story:** screenplay role and line identity, source OpenUSD actor prim,
  original scene Take, exact film time, performances and source editorial
  selections, all verified by their own persistent references.

A generic prop or base mesh may legitimately be shared between several
characters. The source asset *relationship* is actor-scoped and versioned.
Actual speaking **VoiceID, provider-specific generation voice selector,
and scene cast identity** have stronger one-to-one restrictions.

## VoiceType is not VoiceID

- **ActorID**: who the character IS.
- **VoiceType**: what their voice is *supposed to sound like* (pitch,
  register, timbre, accent, cadence, articulation, signature quirks).
  Several characters may share the same broad descriptive type.
- **VoiceID**: the exact APPROVED audible identity for that character,
  anchored to one original source recording SHA with immutable casting
  revisions and director approval.
- **Engine voice selector**: the specific reviewed TTS engine/model/voice
  setting that MUST be bound to that ActorID and that VoiceID. Two actors
  cannot silently use the same engine/model revision/voice selector.
- **Individual speech Take**: source-authored or AI-generated audio of an
  exact ActorID, screenplay line, selected performance, VoiceID,
  source/model revision, approved output reference and Film Time.
  Every new Take still needs native output provenance, acoustic/identity
  checks as available, and separate creator listening/approval.

An AI engine can be given a VoiceType but still generate a different voice.
**A VoiceType prompt is NOT proof of matching audible identity.**
The actual source/audio reference and VoiceID are still required, and
a real generator cannot be trusted merely because it echoes metadata.

## Immutable production-bible actor profile

New module backend/nvp_film03_actor_identity_core.py stores
nvp_bible_actor_identity_profiles, keyed by project and canonical ActorID.
Each new profile has a full canonical source SHA, append-only version,
director note, snapshot of approved VoiceID, voice cast revision and
reference source SHA, and typed sections for appearance, behavior,
movement, voice_type and voice_generation.

Profiles are exactly shaped and size bounded; unauthorized fields, arbitrary
URLs/executable paths, nonfinite numeric parameters and unapproved model
overrides are refused. Publishing a profile is a native director action
with an exact hash, existing Bible revision and optimistic profile revision.
Old versions can always be read. No old appearance, gait, source image,
audio, original Take, VoiceID or source script is edited as a side effect.
An uncast character may have authored physical/voice-type traits, but
**AI speech is blocked until an approved VoiceID is attached and a matching
current profile is republished.**

The existing ProductionBibleActors.actor returns the source profile and
full history together with original typed asset links and voice history,
instead of creating duplicate character identity objects.

## Generated speech requires a sealed source contract

prepare_generated_voice(project_id, exact_dialogue_route,
profile_revision) invokes the strict existing ActorDialogueManager
for the REAL source authored screenplay, selected line, frozen performance,
ActorID, genuine one-to-one OpenUSD cast, Take and Film Time.

It then checks the saved profile is the latest revision, its VoiceID,
voice-casting revision and reference source SHA match the current
production-bible voice, and the performance is genuinely unrecorded.
The immutable returned contract contains:

- Original ActorID + pinned identity-profile revision/SHA;
- authoritative VoiceID and voice reference SHA/cast revision;
- approved VoiceType including timbre, pitch and articulation;
- reviewed model identifier/version, voice selector, seed and settings;
- selected script line/text/SHA and actual source Take/selection SHA;
- characteristic speech style and movement behavior from the same ActorID;
- a canonical SHA of the entire requested contract.

Neither AI prompt text nor a guessed character name can substitute these.
**The contract is READ ONLY.** It explicitly declares both
audio_generation_executed=false and tts_worker_authorized=false.
It does not invoke a model, approve a particular third-party voice,
create PCM, verify generated timbre or authorize putting audio into a film.

A later reviewed native TTS worker must be registered with a verified
engine/voice capability; receive this exact source contract from NVP's
trusted host; return a durable source-bound execution receipt and
immutable audio file hash; verify actual output identity against its
approved voice (automated comparison is advisory, not sufficient alone);
and obtain creator approval before attaching the generated Take.
Unknown engines, arbitrarily supplied voice selectors, stale scripts,
stale character profiles and output lacking trusted provenance fail closed.

## Existing NVP desktop integration

frontend/src/Film03ActorIdentityProfile.jsx is embedded inside the existing
Story Bible ActorID inspector. The director can edit appearance, behavior,
off-gait and other unusual movement, VoiceType and pinned model-voice
settings, inspect old profile revisions and submit an explicit new one.
Only the trusted installed WebView2/GTK native host action
film03_publish_actor_identity_profile may commit the profile after a
human-reviewed exact source SHA and confirmation. Ordinary HTTP can
display profiles but cannot approve identity changes.

A separate first-party method,
film03_preview_actor_ai_voice_contract, returns the exact validated,
NO-EXECUTION generation source plan to the installed director interface.
The actual model invocation and voiced-film audio remain unimplemented.

## Native acceptance and open gates

tests/test_nvp_film03_actor_identity_core.py constructs the real original
FILM02 Studio/StoryBible/OpenUSD source, full 4-actor cast, exact
source-authored DONUT screenplay performance, immutable ActorID, a TEST-ONLY
PCM reference for VoiceID (not a real actor's speech), and verifies:

- Character voice type and quirky gait remain linked to the same ActorID;
- generated-voice request is pinned to original ActorID, line, Take,
  exact profile/VoiceID/model selector/seed, and a canonical contract SHA;
- swapping the actor for BOX/SPHERE, spoofing text or injecting voice
  overrides fails without generating audio;
- two characters cannot use the same actual provider voice selector;
- director revision preserves original behavior/visual/voice history;
- stale profile, unapproved changes and model-delivered provider URLs fail;
- restart recovers original immutable records and source revisions;
- native first-party host denies publishing without actual director
  consent and does not invoke any TTS/animation worker.

The Windows 2025/Ubuntu 24.04 native and React UI matrix is
.github/workflows/nvp-film03-05-actorid-voice-type-ai.yml.

**OPEN:** exact-head native OS CI results and repair, physical installed-app
acceptance, licensed original voice engines and creator consent, real
voice-model execution and output attestation, speaker acoustic comparison
with calibrated error rates, independent source-time/phoneme/camera
spatial alignment, character procedural locomotion and gait enforcement,
and full human-reviewed finished-film acceptance. FILM02's genuine
30-second Blender/Cycles AVI and original audio are unchanged.
