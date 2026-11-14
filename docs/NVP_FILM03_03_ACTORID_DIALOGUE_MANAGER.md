# FILM03-03 — ActorID-Locked Dialogue Manager

**Implemented 2026-11-08; exact-head Windows/Linux tests are pending. No generated character voice or final dialogue film claimed.**

## Production rule

Generative AI can give correct words to the wrong character. The production
Bible must assign all speech by canonical ActorID rather than guess a speaker
from text, a similar name, OpenUSD prim labels, voice profile or 3D appearance.

Canonical ActorID is the project-scoped existing StoryBible character ID.
Nonhuman object actors (donut, box, sphere, service craft) follow the SAME
rules as humans. An ActorID can survive renaming, recasting, different
models, outfits, materials, voice retakes and screenplay changes.

## Strict source request

The new ActorDialogueManager accepts EXACT:
actor_id, script_line_id, script_document_sha256,
selected_performance_id, selection_id, selection_revision,
source_take_id, source_take_sha256, film_time_tick, exact_text.

It does not accept unspecified role fields or infer a missing speaker.
The manager independently verifies:

- The current Studio screenplay, immutable original script snapshot,
  exact selected performance ID, script line SHA and text.
- The full source OpenUSD Take and cast; EVERY authored actor prim has
  exactly one StoryBible ActorID. No ambiguous or uncast person.
- This ActorID has active production-bible links to the exact
  script source, performance and (if voice is recorded) source voice.
- The independently verified original authored event at Film Time has
  the same ActorID, performance ID, text hash, USD actor prim and source SHA.
- A historical delivery whose source script changed is retained only
  following a documented director decision and an updated selection.

Wrong actor, swapped line, unregistered or mismatched voice, stale script,
another Take, overlapping actor speech, missing full cast or source hash
differences are all errors. **No guessing or automatic fallback.**

## A key correction to the original temporal event contract

Earlier FILM03 source metadata used the basename of the OpenUSD prim as
the event subject. That is mutable GEOMETRY, not a stable CHARACTER ID.
New dialogue and voice events encode the speaker as Actor_ followed by
the exact StoryBible ActorID; each event payload carries the same full
ActorID and its selected script/performance source identity.

Old historical timeline revisions stay unchanged. They are not silently
reinterpreted as if they already had the new ActorID guarantees.

An unrelated costume, mesh, prop or material link may increment Bible
entity revision; this is not itself a change to dialogue canon. The
strict source check uses the accepted canon digest and actual historical
script-scene link, not a blanket rejection of every metadata revision.

## Real original recorded voice versus missing voice

Only a true existing immutable RecordedSoundSources PCM16LE revision
bound to this ActorID and selected performance can be heard.
The manager validates the source SHA and authored sound event and offers
a bounded 48-kHz mono PCM16 sample window at sample-aligned Film Time.
It never creates a spoken voice, TTS, microphone capture, spatial
master, or AI-improvised substitute for missing sound.

A metadata-only performance without a recorded voice remains legitimate
source data but is explicitly not audible: trying to read sound raises
an error. Automated source-byte tests use an openly labeled disposable
deterministic PCM signal, **not a real actor recording**.

## Real scene crew connection

WO6-03's scene context accepts an optional exact dialogue-route request
that must match the selected dialogue revision, source Take and Film Time.
It invokes the same authoritative manager. Mere descriptive scene
context is explicitly NOT permission to assign speech.

This is a read-only source gate. All future native recording, TTS,
playback and multimodal generation workers must invoke this validation
before associating spoken output with a character.

## Verification and remaining gates

Native tests use the actual FILM02 source-authored OpenUSD scene with
four actor prims, real Studio/StoryBible/FilmIndex, revised source
timeline and original PCM test bytes. They verify original donut speech,
cross-character denial for box and sphere, script/text mismatch denial,
Take and timing scope, missing voice link, uncast actor, source readback
and durable restart.

Windows 2025/Ubuntu 24.04 Python 3.11 OpenUSD matrix:
.github/workflows/nvp-film03-03-actorid-dialogue-manager.yml

**Still OPEN:** exact-head OS execution results and repairs; real microphone
voice capture, human-approved recorded voices and alternate retakes;
spatial dialogue audio, full native voice-worker integration, actor
performance animation, installed-app acceptance and human screening.
Existing FILM02 completed original 30-second picture/PCM AVI is not
modified by these changes.
