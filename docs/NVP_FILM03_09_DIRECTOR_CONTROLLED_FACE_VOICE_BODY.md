# FILM03-09 — independent voice, mouth, face and body performance

**Creator decision, 2026-11-08:** Deliberate contrast between voice and face/body is valid direction, not a performance defect. A sad voice with a joyful smile, an angry face with a happy voice, or relaxed body language during an anxious speech are legitimate artistic choices. AI should help realize the creative decision rather than enforce emotion matching. Any canonical ActorID can be a character, including a donut, box, spacecraft, or other nonhuman object without a mouth.

## Four distinct source-authoritative tracks

1. **Spoken voice:** Actual original voice-actor recordings, director guide performances, independently qualified expressive TTS, and independently verified speech-to-speech conversions. Voice actors are human creative contributors, not just voice reference sources. Record performer identification, performance rights, permitted uses and credit; consent to use a recording does NOT imply voice-cloning, redistribution or model-training consent. Individual retakes and revisions must survive.
2. **Articulation:** The final selected audio's actual phonemes and timing drive candidate viseme, lips, jaw, tongue and mouth poses. Lip-sync is not simple amplitude animation. A reviewed aligner should provide actual audio/word/phoneme time coordinates, with coarticulation and transition smoothing; manual director adjustment is possible. Re-align after voice conversion, edit or timing revision. For nonhuman actors, no mouth or stylized abstract audio-reactive motion is artistically valid.
3. **Facial acting:** Independent artist-selected happiness, sadness, anger, calmness, irony, gaze, eye/brow/cheek expression and custom acting. Never force facial emotion to match audio tone. Audio emotion detection, if present, is an opt-in *suggestion*, not a trusted override.
4. **Body acting:** Independently directed gestures, posture, gaze/body turns, gait, hesitation and interaction, source-bound to the canonical ActorID and scene.

**Separation rule:** Accurately synchronized articulation is a technical target; expression is an artistic decision. The director may override articulation timing intentionally as well, but the system should surface measured sync deviations rather than silently alter authored takes.

## Implementation: FILM03-09A, source-only

New backend/nvp_film03_independent_facial_direction.py reopens the canonical ActorID, VoiceID, profile, frozen Take, original screenplay and an approved immutable vocal-direction revision. It independently verifies an original human-acted 48k PCM source via RecordedSoundSources and FilmIndex chunk hashes. This **does not** certify that those bytes contain speech or that they match the screenplay; test silence is a decoder fixture only.

The performer has a separate contributor ID/role and recorded rights-evidence SHA; that metadata is NOT verified consent or permission to clone. The original audio source remains separate from the canonical target VoiceID reference.

Facial direction binds proposed phoneme/viseme intervals, independent facial expression and body keyframes to integer audio sample offsets, mapped into NVP exact Film Time at 147,000 ticks per 48kHz sample (7,056,000,000 ticks per second). It supports mouth visemes, abstract reactions, or intentionally no mouth. The director can explicitly choose independent expression or intentional contrast without an emotion consistency rejection. All event positions are bounded and source-locked.

Trusted director authorization publishes **an immutable performance-direction revision only** with dependencies on the original audio, director's voice direction and frozen Take. Prior originals and revisions are preserved. Precommit checks reject stale ActorID profile or recast VoiceID.

**Not implemented/accepted:** Actual phoneme recognition/alignment; source speech transcript verification; naturalness; legal consent authentication; executed face rig or Blender/UsdSkel pose; spatial integration; film Take approval. Source tests cannot prove any of those.

## Required next phases

**09B — human voice-actor capture and performance provenance.** Original PCM/performance revision, session/performer ID, reuse rights, separate voice cloning/training authorization, credit, and retakes. The microphone performance and the target character voice are distinct; guide audio can be transformed later by a reviewed voice-converter. Do not mislabel derived TTS/converted audio as original microphone audio.

**09C — actual phoneme alignment.** Test Montreal Forced Aligner or another reviewed forced-aligner with real recorded screenplay dialogue, pronunciation dictionary, actual timestamps, pauses/breaths and phoneme confidence. Generate and independently validate complete phones-to-visemes mapping from the **final selected audio**, not an earlier guide. Audit native model/bin dependencies, model licenses, actual Windows AMD feasibility and NVP's no-FFmpeg restriction.

**09D — actual actor rig mapping and expression compositing.** Reopen original ActorID rig, source UsdSkel, blend shapes and Blender shape keys. Verify true lips/jaw/tongue coverage or fail to unsupported; never invent a mouth for a donut unless the director authors one. Use distinct articulation vs facial emotion and body layers, with intentional conflict resolution where multiple shapes affect the same vertices. Audio-inferred expression is optional, not mandatory.

**09E — render and independently verify.** Actual source-locked Blender/UsdSkel animated scene with measured audio/mouth timing, visible coarticulation and rig geometry. Verify smile+sad voice and angry face+happy voice survive as authored. Test real voice actor performances, qualified expressive TTS and converted audio separately. Installed Windows AMD and authentic human perceptual review remain separate gates.

## Upstream references for evaluation, NOT integrated or proven dependencies

- Blender 5.2 shape keys: https://docs.blender.org/manual/en/5.2/animation/shape_keys/introduction.html
- NVIDIA Audio2Face 3D open-source: https://github.com/NVIDIA/Audio2Face-3D
- NVIDIA Maya-ACE director/artist emotion controls: https://github.com/NVIDIA/Maya-ACE/blob/release/2.0/docs/userinterface.md
- Montreal Forced Aligner: https://montreal-forced-aligner.readthedocs.io/en/latest/

**Acceptance:** Source contract and regression stage 09A is implemented, but exact-head native Windows/Linux results are pending. Stages 09B–09E remain OPEN. Do not confuse a proposed viseme array with actually synchronized mouth animation.
