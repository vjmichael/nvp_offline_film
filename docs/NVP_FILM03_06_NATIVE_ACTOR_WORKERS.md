# FILM03-06 — ActorID Blender animation and film-quality voice qualification

**Revised November 8, 2026 on the director's voice-quality requirement.**
Source implementation is committed; native Windows/Linux and real Blender
evidence is OPEN. No generated cinematic voice or human artist's approval
is claimed.

## Decision: remove eSpeak NG from NVP film production

eSpeak NG is an existing open-source formant text-to-speech engine, not
something NVP or ChatGPT invented. An early exploratory adapter was useful
to exercise operating-system speech worker launch, WAV decoding and
hash-based candidate persistence. That does not establish expressive acting
or production-quality dialogue. This adapter is DELETED from NVP, the film
CI eSpeak execution job is removed, and the trusted desktop cinematic speech
action now fails closed even when supplied a prior source request.

Film acting requires real emotional interpretation, natural inflection,
word/phrase emphasis, nuanced pronunciation, breathing, whispering, soft
speaking, audible intensity/volume modulation, sighs/laughter/crying, and
consistent speaker identity across scenes/retakes. Valid WAV file creation
proves only that bytes were produced, NOT that a voice delivered believable
acting or matched its canonical ActorID/VoiceID.

A lightweight TTS engine might later be examined as an OPTIONAL Lu
accessibility tool in a separate scope, with distribution/licensing review.
This PR neither ships eSpeak for NVP nor integrates it into Lu.

## What stays in the ActorID-based movie architecture

The canonical StoryBible ActorID still owns every character resource:
appearance, model/mesh/texture/costume, personality, unusual gait,
behavior, VoiceType, approved VoiceID and original recorded source SHA,
exact screenplay, current director-selected performance, source Take,
OpenUSD prim and Film Time.

ActorIdentityCore.prepare_generated_voice remains a read-only, source-
validated plan pinned to these source revisions. It can NEVER on its own
give permission to run a speech provider, create a Take or approve output.

## Explicit director-authored vocal performance

New backend/nvp_film03_expressive_voice_direction.py stores per-actor,
per-exact-script-line, immutable and versioned FilmIndex speech directions.
Each is validated against real original script words; director controls:

- Emotion and intensity, including a changing emotional arc across words.
- Delivery mode: natural, soft, whisper, shout, crying, laughing.
- Relative volume in dB, pacing and breathiness.
- Exact word-index emphasis/stress.
- Exact word-index timed pauses and breath points.
- Pronunciation overrides anchored to the unchanged original written word.
- Director intent and explicit reason for a revised or alternative Take.

This is artistically necessary source metadata, but NEVER a claim that an
AI really whispered or pronounced the words correctly. Different providers
have different control methods; a qualified adapter must prove its actual
rendered sound followed the direction. Old approved notes, prior lines,
VoiceIDs and original Take versions remain intact.

Native installed first-party host method
film03_publish_actor_voice_direction uses exact creator confirmation and
saves these revisions. There is no model or web approval shortcut.

## FILM voice quality gate

All speech engines currently return DISABLED in
cinematic_engine_readiness, even if their spec claims expressive tags.

A film-qualified reviewed provider must pass actual audible tests
for contextual natural inflection; emotion/emotional arc; exact word stress;
pronunciation of fictional character names and difficult terms; real
whispers/soft speech and projected/shouted voice; timed pauses/breaths;
correct vocal loudness; nonverbal reactions; long-scene same-VoiceID
continuity and a believable actor performance; reproducible model/voice
selection, consent/licensing and artifact-level provenance.

The actual benchmark should compare the same dialogue in multiple emotional
conditions and multiple scene takes against suitable expressive
commercial systems such as ElevenLabs. Its quality and limitations must
be demonstrated with real output, independent tests and director listening.
Do not treat model capability declarations or metadata echoes as proof.
The director approves each final recorded/generated performance separately.

No new speech model was developed and no claim of ElevenLabs-level parity is
being made. An offline neural engine could qualify in the future if its
independently observed performance genuinely meets the same bar.

## Animation remains on the EXISTING verified Blender execution path

backend/nvp_film03_actor_animation_host.py reopens original frozen
FilmIndex/OpenUSD scenes, canonical 4-actor cast and actual source meshes,
camera, light, film-time world matrices and ActorID identity profile.
The actor's explicit typed gait preset is executed via NVP's preexisting
BlenderWorkerSupervisor and SHA-pinned first-party Blender worker.
It creates a real keyframed .blend, Cycles PNG preview and auditable
per-frame SHA/actor-motion receipts. All other actors remain at their
original source positions. A separate fresh Blender process independently
reopens and checks the scene.

These outputs are immutable FilmIndex candidates, NOT approved editorial
Takes, and no original source film is silently rewritten. Animator and
speech producer remain separate; failure to qualify TTS does not prevent
testing the reviewed actor gait.

## OS acceptance and remaining work

GitHub workflow .github/workflows/nvp-film03-06-real-actor-workers.yml
now tests Windows and Linux source identity, wrong speaker refusal,
original script/VoiceID preservation, actual director acting-direction
validation and fail-closed film TTS status. Ubuntu runs a real reviewed
Blender/Cycles gait and independently reopens its saved output.

The previous Ubuntu eSpeak NG speech job and its generated WAV artifact
publication were REMOVED from film CI.

Still OPEN: check exact-head native results, repair actual failures,
physical installed workflow acceptance, expressive/neural TTS provider
review and output comparisons, pronunciation and emotion matching,
speaker/acoustic continuity tests across multiple scenes, consent and
licensing checks, real director audible review, output receipts, eventual
3D spatial dialogue mixing and full finished-film acceptance.
