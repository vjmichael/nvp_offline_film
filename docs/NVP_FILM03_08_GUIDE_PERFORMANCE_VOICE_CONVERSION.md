# FILM03-08 — performance-driven speech-to-speech voice acting

**Creator decision (2026-11-08):** NVP must support both expressive **text-to-speech** and **speech-to-speech / tone-color voice conversion** as peers. A third hybrid path may use a qualified TTS guide performance followed by separately reviewed voice conversion. The previously agreed Production Bible → screenplay + director instructions → performance generators → NVP independent verification → director-approved dialogue Take architecture remains authoritative.

**This change implements a source-only, permission-checked guide-binding contract and immutable FilmIndex performance intent.** No voice-conversion model is run, no quality claim is made, and NVP still blocks film TTS until a real voice producer passes the FILM03-06 qualification process. FILM03-07A's actual PCM audition import/comparison is preserved.

## Why both paths are necessary

- **TTS actor:** The director supplies the exact words, ActorID/VoiceID, persona and notes; the generator interprets emotion, rhythm, timing, breaths and intonation. Useful for auditions, background dialogue and alternate performances. Whether it follows direction is an audible measurement, not a manifest claim.
- **Human guide + voice conversion:** A consenting performer actually delivers the correct script line. The guide audio carries performed timing, phrasing, hesitation, breaths, intensity and inflection. The conversion model attempts to **change speaker timbre/tone color** toward the approved VoiceID while retaining the guide's acting. The model can accidentally smooth or alter prosody, overprocess whispers, shift pitch, hallucinate syllables or eliminate breaths; compare source versus converted sound before approval.
- **TTS guide + voice conversion:** An already independently qualified generative performance becomes an explicit *derived* guide recording, and a tone-color converter attempts to map it toward a character's canonical VoiceID. All intermediate PCM and original model/source receipts remain separately inspectable. Never silently use an unreviewed TTS model's sample as a film dialogue Take.
- **No conversion/direct recording:** The original consented performance can itself be approved for the actor if the production bible's voice casting supports it. Conversion is an **option**, not a mandatory destructive step.

**Clarify model terminology:** Tone-color conversion seeks to change the *perceived vocal identity*. Speech-to-speech may do broader style/prosody transfer, depending on the specific model. Many models do not preserve the guide's timing, emotion or nonverbal sounds reliably. Do not conflate a successful timbre swap with successful acting.

## NVP source custody and user control

The existing canonical StoryBible ActorID/VoiceID and original screenplay remain source of truth. A voice-conversion intent references:

1. Exact ActorID, approved VoiceID, identity profile revision and approved **target VoiceID reference recording SHA**.
2. Exact frozen Digital Take, canonical script line, unchanged words and approved director-emotion/pace/pronunciation revision.
3. **Separate guide signal**, recorded as an immutable, chunk-addressed 48kHz mono PCM16LE original source in the existing RecordedSoundSources/FilmIndex, with full sample count, independently rehashed chunks, guide source document SHA, and guide original PCM SHA. Original signal never overwritten. **Existing recorded-dialogue retakes are not yet supported by this source-only plan because it reuses an unrecorded dialogue planning contract; a separate retake-safe source route remains required.**
4. Guide origin is reserved for human acting or a future qualified TTS acting candidate. **The current original-PCM binding accepts human_acted_guide only**; a derived TTS guide MUST use a separately reviewed derived-media provenance adapter, rather than being relabeled as an original microphone capture. A claimed rights-evidence SHA is not proof of performer consent: verification remains separate.
5. Conversion mode: tone_color_transfer versus performance_to_target_voice. These are **director intents**, not proof that any given model supports or faithfully performs the operation.
6. Human director grants authority only to **publish the exact source binding**. Separate reviewed consent must later authorize native worker execution and distinct approval for any resulting generated PCM. No input, model response, web UI, or persisted direction record bypasses approval.

The first implementation, backend/nvp_film03_voice_conversion_intent.py, exposes verified_guide_signal() for actual recorded data readback and FilmGuideVoiceConversion.plan()/publish_intent(). It prevents ActorID/VoiceID/source-script swaps, guide/direction/Take identity aliasing, altered recordings, stale cast/profile publication, unapproved director events, and overwriting existing revisions. The original guide, ActorID reference and original screenplay remain untouched. FilmIndex dependencies bind guide original PCM, director voice-direction revision and original Take to the immutable proposed performance intent. Every returned receipt explicitly states **NO conversion executed**, **NO proof the guide says the script line**, **NO acoustic voice similarity measured** and **NO movie Take approved**.

### Future Voice Studio interface (NOT implemented)

The illustration should remain a functional production workflow, with these creative controls:

- Character/VoiceID cast picker, approved reference auditions and visible latest profile.
- Side-by-side **Generate from Script** and **Act/Record Guide → Convert Voice** actions. Both show exact source words/scene, original recording and direction notes.
- Guide from microphone or original reviewed source; multiple legitimate guide performances and AI suggestions, each clearly labeled. The director can keep the natural version or transform the voice without changing original recorded evidence.
- Tone-color intensity, target voice, pitch preservation, rate alignment, breath preservation and emotion preservation only when independently supported by the selected reviewed model. Do not fabricate universally supported sliders.
- Multi-lane A/B audition: original guide, generated TTS, converted candidate, reference VoiceID, optional previous approved performance. A director can select a timestamp range and ask for retakes or re-record one phrase without altering old versions.
- Show actual independently determined word timing/alignment, transcript accuracy, source-vs-converted breath/voice continuity, clipping/pitch artifacts and dropouts. High automatic similarity scores do NOT overrule a director's artistic rejection.
- Explicit **Approve as new voice Take** only after final independent provenance, rights, Native PCM receipts and human listening. Old approved performances and rejected candidates remain addressable. Place approved dry source audio in original 3D scene/Film Time with spatial sound in another reviewed work order.

## Candidate model priorities and licensing

1. **OpenVoice V2** is the preferred **early tone-color proof-of-concept**. Official MyShell project and checkpoint documentation describe MIT licensing and tone-color cloning alongside separate expressive base-voice performance. Need real no-FFmpeg dependency and Windows AMD/native execution audit, voice actor consent, stable same-VoiceID tests and thorough temporal/prosody preservation checks. See https://github.com/myshell-ai/OpenVoice and https://huggingface.co/myshell-ai/OpenVoiceV2 .
2. **Seed-VC** is useful as an independent zero-shot voice-conversion **research comparison**, but its original repository is **archived since November 21, 2025** and GPL-3.0 licensed, requiring separate redistribution and maintenance review. Do not treat it as a default NVP shipping choice. See https://github.com/Plachtaa/seed-vc .
3. **Qwen3-TTS** is a separate expressive TTS/voice-clone candidate under Apache 2.0; its published Base/CustomVoice/VoiceDesign checkpoints must be treated according to actual features rather than assuming its TTS API is a performance-preserving waveform-to-waveform converter. See https://github.com/QwenLM/Qwen3-TTS .
4. **RVC-style converters** can be examined for voice transfer under controlled rights. Hardware/quality depend on separate models and dependencies, not merely the framework name. Do not assume pitch/rhythm continuity or legal rights from a model card.

Before any runtime integration, review **model weights plus source code plus dependencies** for distribution, CPU/AMD Vulkan/ROCm feasibility on physical Windows, total runtime memory, crash/cancel recovery, license notices, and the no-FFmpeg rule. Studio-capable voice-conversion playback can be offline, and need not be low-latency live unless the creator explicitly asks for live directing.

## Required real acceptance and next development

- **08A IMPLEMENTED/source only, native acceptance OPEN:** Director-authorized, immutable original 48kHz guide source and target voice reference, real sample readback, full SHA plus FilmIndex dependencies, no execution, wrong actor/cast/script refusals. Windows/Linux matrix in .github/workflows/nvp-film03-08-voice-conversion-source.yml.
- **08B OPEN:** Actual native approved guide microphone performance/voice-cast reference capture and independently verified speech/source rights. A guide can presently be a human-acted original PCM recording. A qualified TTS output must instead be imported as **derived** guide media through a future verified provenance adapter. Arbitrary provider-supplied files cannot grant permission.
- **08C OPEN:** Supervised review of OpenVoice V2 tone-color adapter using an actual model checkpoint, model hash, weight-license notice, verified original PCM input, exact target reference, output source SHA, no FFmpeg; Windows AMD and Linux real execution, cancellation/restart.
- **08D OPEN:** Multi-scene and multi-emotion listening/A-B with source vs converted vs approved reference: actual transcript alignment, intensity, breath/noise preservation, whisper accuracy, speaker similarity and whether original emotions survive. Independent listening and human director take approval.
- **08E OPEN:** Installed NVP actor Voice Studio UI, guide capture, take revision/retake and delivery provenance, integrated Digital Take and scene spatial audio.

**Acceptance is not closed** on this source-only implementation. Never take a silent sine/zero PCM regression fixture as a successful acted line or use developer-written metadata as proof of matching timbre.
