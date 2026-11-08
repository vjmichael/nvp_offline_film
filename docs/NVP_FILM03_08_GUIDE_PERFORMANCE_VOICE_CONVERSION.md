# FILM03-08 — Performance-directed voice conversion

**Creative choice:** NVP supports expressive script-to-voice TTS and guide-performance-driven voice conversion as peer filmmaking workflows. A future hybrid route may use independently generated TTS as a guide. A real voice actor or director can deliver timing, pauses, sighs and emotion, and an optional voice converter can try to transfer tone color toward the approved character VoiceID.

Existing first-party FilmIndex and original audio source infrastructure store the guide and the target voice reference *separately*, with the same ActorID, source Take, screenplay line and director instruction revision. All original recordings and prior performances survive retakes. A converted waveform is a candidate, not an automatically chosen Take.

**Technical development:** backend/nvp_film03_voice_conversion_intent.py presently binds a real 48kHz original guide signal to the target VoiceID, independently rehashes original PCM, and creates a director-reviewed creative source-binding revision. It does not run a voice model, verify any delivered speech quality or automatically select a film Take. Derived AI-generated guide audio remains a distinct future provenance adapter rather than being mislabeled as original microphone audio.

**NVP scope:** This is a filmmaking workflow. No performer legal consent, license, rights records, training/cloning or distribution permission screens or paperwork are part of it. Performer identity/credit can be tracked as a simple production attribute.

**Next:** Actually test OpenVoice V2 and other converters on real actor dialogue; measure source/converted speech timings, breaths, stress, vocal identity, acoustic artifacts, Windows AMD and OS cancellation. Re-align final chosen waveform for lip articulation using FILM03-09C. No FFmpeg dependency in the native NVP path.
