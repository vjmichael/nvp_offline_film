# FILM03-09B — human voice actor session intake and separate permission scopes

**Development status: IMPLEMENTED source-level, native/installed acceptance OPEN.** Branch nvp/film03-09b-human-voice-actor-intake-20261108, stacked on FILM03-09 PR #123. Real voice actors and director-performers are creative participants, distinct from a StoryBible character ActorID and from the character's approved VoiceID.

## Why this stage precedes real lip sync

A recorded human performance can provide actual rhythm, pauses, breaths and emotion, and a later voice-conversion worker may try to transfer its timbre to an approved character voice. Neither a PCM file nor a contributor's name proves the recording actually speaks the intended text or that all permissions are valid. Lip sync must ultimately align the **final selected speech**, not a discarded or pre-conversion recording. Facial emotion follows the approved vocal emotional state by default unless the director intentionally overrides it, as established in FILM03-09.

## New source implementation

**backend/nvp_film03_human_actor_intake.py** works with the already implemented native FilmIndex/RecordedSoundSources/StoryBible and source-routed ActorDialogueManager:

1. Accept an **already captured**, SHA-addressed, immutable 48 kHz mono PCM16LE original recording. The existing trusted capture worker creates that source. FILM03-09B does **not** itself operate a microphone, audio device or process. It reopens the original first-party PCM, independently hashes all source chunks and computes peak/RMS, nonquiet and clipped-sample fractions. Refuses silence, obvious insufficient level, severe clipping, incomplete chunks and unsupported duration. These are mechanical signal tests, **not speech recognition or proof of believable acting**.
2. Reopen the authoritative current ActorID/VoiceID and exact original screenplay selection, dialogue performance, source Take and original script SHA. A human performer ID/role is distinct from both actor identities. The source recording is *not* automatically a selected performance or a replacement for an approved Take.
3. Require a typed **recorded_line_use** permission and separately explicit records for **voice_conversion**, **voice_cloning**, **model_training**, and **distribution**. Each consenting scope has an independent SHA of its purported evidence; non-consenting scopes must not carry evidence. A performer may agree to an ordinary recorded line and deny conversion, cloning, training and distribution. Agreement to voice conversion never implies consent to training.
4. Receive **two separately validated native host events**, scoped to exactly this PCM SHA/ActorID/script and these permissions: authenticated performer consent and director source-intake approval. An LLM prompt, filename or ordinary UI data cannot substitute for these callbacks. Note that the callbacks are trusted execution contracts; the source-only tests simulate them and **do not establish a working installed identity/consent verification workflow or legal clearance**.
5. Publish an immutable new FilmIndex performance-session revision with typed source dependencies on the original audio, original performance, screenplay selection and source Take. Inside the same SQLite transaction, fence current screenplay, profile, VoiceID and selection and register a **unique custody row** tying original audio bytes to one performer/ActorID/session. A second recording entry reusing the same original PCM SHA cannot masquerade as a different actor or human.
6. A fresh Studio/FilmIndex can reopen the saved session after restart and recompute the original source PCM measurements, verify unique custody and preserve old source. Model training, voice cloning, conversion execution, voice identity similarity, speaker review and film Take selection remain separately **DISABLED**.

## What is still open

- **09B-1 (source admission):** code + regression tests + native Windows 2025/Ubuntu 24.04 workflow added; completed passing exact-head OS execution still required.
- **09B-2 (physical capture and installed consent):** genuine NVP app microphone / OS-chosen original audio session integrated with installed user interface, actual performer identity and independently verified source-use, voice conversion, cloning/training and distribution permissions. Signed legal licensing and performer credit decisions must be separately reviewed.
- **09B-3 (human voice-acting quality):** actual real voice-actor PCM supplied for a valid NVP screenplay line, human audition and independent word/timing/phoneme checks; audio waveform metrics cannot prove speech, and the sample tests use explicitly NON-SPEECH tones.
- **09C:** independently reviewed phoneme alignment and real lips/jaw/tongue mapping against final delivered audio, followed by actual Blender/UsdSkel facial rendering (FILM03-09D/E). No model, voice converter, aligner, original microphone, facial animation or FFmpeg is launched in this stage.

Native regression: .github/workflows/nvp-film03-09b-human-actor-intake.yml; tests/test_nvp_film03_human_actor_intake.py.

Source and legal rights remain project-scoped and versioned. The creator-approved art principle is still **match voice emotion by default, with full director authority for deliberate contrasts**.
