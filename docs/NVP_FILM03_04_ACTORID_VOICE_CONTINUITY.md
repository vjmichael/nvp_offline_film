# FILM03-04 — Character VoiceID Continuity and Actor Asset Audit

**Source implementation submitted 2026-11-08. Exact-head Windows/Linux native
and UI CI plus real installed NVP acceptance are separate gates.**

## The continuity problem

A generative model can correctly select the actor and screenplay line but
render that line with the WRONG character voice. A proper actor registry must
therefore separately identify:

1. **ActorID**: canonical project-scoped StoryBible character entity ID.
   Survives renamed actor, script edits, multiple 3D models, scene Takes,
   wardrobe/props/material changes, performances and recorded voices.
2. **VoiceID**: stable identity for that actor's approved audible character
   voice; owned by exactly one ActorID at a time, bound to an exact immutable
   reference PCM recording SHA, not the most recently imported WAV filename.
3. **Voice-cast revision**: append-only decision of which VoiceID is current
   for this character. An intentional recast requires a NEW VoiceID,
   a NEW reference recording, an explanation and native director consent.
4. **Recorded dialogue Take**: an immutable FilmIndex performance bound
   to its exact screenplay line/revision, ActorID, OpenUSD actor, Take,
   original recorded PCM source/revision/SHA and Film Time. This is not
   automatically approved for a VoiceID.
5. **Voice review**: a separately stored append-only director decision that
   compares the candidate original audio clip and this VoiceID's reference,
   pinned to both immutable audio SHA and exact performance document SHA.
   A later recast invalidates the old recording for CURRENT-voice playback;
   prior decisions and audio remain historically discoverable.

**A matching ActorID + matching text + correctly linked PCM file is still
not enough** to deliver audible dialogue. FILM03's canonical routing
requires an approved current VoiceID and separately approved original
recorded performance, or it refuses delivery.

## Implementation

Source module: backend/nvp_film03_voice_identity.py. It persists
nvp_bible_voice_casts and nvp_bible_voice_take_approvals as production
Bible-owned SQLite histories keyed by ActorID and exact revisions. NVP
never silently overwrites a voice profile, reference WAV, source
performance, script revision, approved recording or earlier Take.

VoiceID binding is checked alongside the full source-cast validation in
backend/nvp_film03_dialogue_manager.py. The production-bible actor
resource inspector now includes the current VoiceID and immutable full
recast history. Its existing mesh/model/texture/wardrobe/prop/scene/voice
resource relationships remain independently source-verified.

Two critical prohibitions:
- An ActorID cannot borrow another actor's VoiceID or another actor's
  original reference recording. A recorded clip already reviewed under
  one VoiceID cannot be relabeled to another VoiceID merely because
  a model or filename says the actor has a new voice.
- No newly recorded clip is silently declared part of the canonical
  actor voice. The director must separately review it against the
  reference and authorize exact source SHAs; otherwise routing refuses
  audio delivery, including when screenplay, model and ActorID match.

Ordinary costume or script research is not voice-casting authority.

## Actual voice audition in installed NVP

Native trusted desktop host methods:
- film03_audition_original_voice: read only, strictly bounded original
  PCM16LE source (48 kHz mono) and return genuine WAV encoded via
  first-party Python standard library. Max 3 seconds/source request.
  Source SHA and sample indexes are supplied, not invented by a model.
- film03_cast_actor_voice: enroll exact ActorID/VoiceID and reference
  source under the existing native director confirmation. Recasting
  carries a separate reason and preserves all historical assignments.
- film03_approve_actor_voice_take: confirm an exact actor/performance,
  VoiceID casting revision, both reference and candidate PCM SHAs, and
  the director's comparison note before adding approval history.

**There is no HTTP endpoint issuing a voice-casting approval token.**
The browser may GET only actor-scoped recorded performance candidates
and their SHA provenance; native first-party host confirmation is required
for source mutation.

frontend/src/Film03ActorVoicePanel.jsx lives in the existing Story Bible
ActorID inspector. It exposes actual reference and candidate WAV auditions,
full voice recast history, explicit voice-cast consent, and per-recording
director comparison. Separate audio players must be opened before
submitting a review. Voice recast operations require an explicit note
and a NEW VoiceID. Browser-only mode cannot authorize this work.

## Integrity limits — important

NVP can cryptographically prove **which bytes** and **which original
voice source revisions** were submitted for an authorized decision.
It CANNOT prove two different voices have identical timbre merely from
the fact that a human reviewed them or their metadata references one
VoiceID. The director's audition is a meaningful reviewed-workflow
gate, not acoustic biometrics. In a later work group, independent
voice-similarity measurements and speaker verification may be added as
a warning/second opinion, with tested false-acceptance rates and
consent, but **never** as license to bypass an explicit casting decision.

Sample audio used in current automated regression is **TEST-ONLY
deterministic PCM**, not actual human actors or generated character
voices. No real voices have been cast into the original FILM02 film.
No newly generated dialogue, audio retake or movie is claimed.

## OS acceptance

Native tests: tests/test_nvp_film03_dialogue_manager.py plus earlier
FILM03 source, StoryBible, original recorded PCM and OpenUSD regressions.
Tests include wrong speaker, wrong VoiceID, crossed reference, unauthorized
host, original PCM readback, voice recast with distinct reference,
old voice continuity refusal, new take requiring separate approval,
documented historical voice preservation and SQLite restart.

UI tests: frontend/src/Film03ActorVoicePanel.test.jsx and existing
Film03ProductionBiblePanel.test.jsx. They require actual original
source audition steps, native host-only consent, and no HTTP mutation.

Workflow: .github/workflows/nvp-film03-04-actor-voice-continuity.yml
Windows 2025 and Ubuntu 24.04, real Python/OpenUSD source tests,
React/Vitest and desktop production build.

**Still OPEN:** exact-head OS CI results and repairs; genuine installed
Windows WebView2 + Linux GTK actor-voice UX acceptance; original actor
microphone recording/retake capture; vendor TTS identity profile binding
and actual generated speech; independent acoustic continuity validation;
3D source-relative spatial voice and physical actor performance; human
creative listening and the full feature-film acceptance.
