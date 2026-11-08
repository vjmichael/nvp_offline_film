# FILM03-07 — expressive voice performance laboratory

**Status, 2026-11-08:** real-audio evidence *import/evaluation* implemented; qualified cinematic voice generator **NOT implemented**, independent human acting review **NOT performed**, native CI/installed acceptance **OPEN**. Stacked on FILM03-06 PR #120. The eSpeak NG film adapter is deleted; do not restore it. No new TTS engine is built here.

## Architectural rule

NVP is the director and immutable film-data authority, **not** the speech synthesizer. ActorID is the canonical StoryBible character identity; VoiceID, voice casting, reference recording SHA, approved profile revision, exact screenplay words, immutable Digital Take and exact Film Time, and director-authored expressive direction are authoritative source data. An external generative speech worker is replaceable, untrusted until reviewed, and never allowed to edit the screenplay, impersonate another actor, assign its own VoiceID, or promote its output into the actual movie.

No model may obtain execution authority from a prompt, a file path, a React button alone, a claimed manifest, or a quality rating. Production permission requires reviewed binary/model/weights, explicit director consent for that exact operation, OS-supervised lifetime, original-source recheck, bounded output verification, authenticated director audition, immutable new PCM source revision, and a separate take-selection action. **FILM03-07 does not implement that speech-worker authorization.**

## Practical engine shortlist and control translation

These are test candidates, **not accepted NVP dependencies**. Verify code **and model-weight** terms, indirect dependencies, source consent, hardware, output rights, executable hashes, redistributability, and absence of FFmpeg **before integration**. No current vendor claim counts as real film-acting evidence.

| Engine | Directed performance path to test | Gap/gate |
| --- | --- | --- |
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) | 1.7B VoiceDesign: prompt with timbre, emotion, pacing, breath/volume; CustomVoice: named voice plus style; Base: reference-conditioned cloning. These are separate checkpoints, not one magical combined API. | Controlled style and canonical same-VoiceID identity must be tested across many takes; Qwen publishes Apache-2.0 code/weights, still audit installed components. |
| [IndexTTS-2.5](https://github.com/index-tts/index-tts) | Reference timbre, explicit 8-component emotion vector, phoneme/pinyin/kana disambiguation, duration factor; do not replace original written words with phonetic notation in NVP's original script. | Good candidate for difficult fictional names and exact emotional controls; weight license is a separate bilibili Model Use License. Official examples target NVIDIA GPU, so Windows AMD support is unproven. |
| [CosyVoice 3](https://github.com/QwenAudio/CosyVoice) | Instructed emotion, voice speed, volume, speaker reference, pronunciation inpainting. | Compare naturalness, word accuracy and real delivery change; package/licensing/device compatibility must be checked end-to-end. |
| [Fish Audio Drama 3](https://github.com/fishaudio/fish-speech) | Direct natural-language film notes; multi-character scene coherence; iterative revision of a prior take; individual word/phrase infilling. | Large 35B-A3B footprint, hardware/performance unknown for target Windows AMD, special community-license/hosted-service terms; not a default redistributable engine. |
| [OpenVoice V2](https://github.com/myshell-ai/OpenVoice) | **Guide performance → voice conversion**: have an authorized performer act the whole line with believable intent and convert its tone color toward a consented canonical VoiceID. | Style, emotion and pronunciation largely come from the guide performance/base voice, not from cloned reference timbre. MIT project; evaluate actual tone continuity and artifacts. |
| [Dia](https://github.com/nari-labs/dia) | Two-actor conversations and controlled reactions, original line dialogue. | Scene-level consistency and speaker identity must be measured; review model and auxiliary licenses. |
| [Chatterbox](https://github.com/resemble-ai/chatterbox) | Legacy low-cost expressive baseline with exaggeration control. | Upstream marked project retired/unmaintained in August 2026: research baseline, not preferred new production dependency. |

**Recommended experiment order:** (1) Qwen3-TTS 1.7B and IndexTTS-2.5, (2) CosyVoice 3, (3) guide-performance plus OpenVoice V2, (4) Fish Drama 3 for high-end scene directing if licensing and hardware work. **Do not download or bundle weights, execute models, install tools, or authorize providers as part of this source-only lab.** Target hardware includes actual Windows AMD GPU; an NVIDIA-only demo is not proof of supported native NVP operation.

Original upstream references: [Qwen3-TTS README](https://github.com/QwenLM/Qwen3-TTS/blob/main/README.md), [IndexTTS-2.5 model card](https://huggingface.co/IndexTeam/IndexTTS-2.5/blob/main/README.md), [CosyVoice repo](https://github.com/QwenAudio/CosyVoice), [Fish license](https://github.com/fishaudio/fish-speech/blob/main/LICENSE), [OpenVoice tone-color explanation](https://github.com/myshell-ai/OpenVoice/blob/main/docs/QA.md), [Chatterbox maintenance notice](https://github.com/resemble-ai/chatterbox/blob/master/README.md).

## How the implemented lab works

1. Use native FilmIndex to reopen the **existing** character profile and a creator-published FilmActorVoiceDirection revision. The frozen case is bound to canonical ActorID, VoiceID, reference audio SHA, exact original line/document, original Take SHA, source contract, specific emotion/delivery direction and immutable direction revision. All mismatch cases deny.
2. In a separate, explicitly reviewed experiment, a qualified human/test harness may render actual neural audio into an external WAV file. FILM03-07 **does not** launch a model, train it, download checkpoints, invent a WAV, or run provider-supplied scripts.
3. Import only a regular WAV in the chosen audition root, no symlink/relative traversal. Reopen native RIFF PCM, stream and count all samples, calculate full original-byte SHA-256, duration, PCM bit depth, channels, RMS/peak dBFS, clipped and very-low-level sample fractions. Unsupported formats, truncated audio or hash mismatches fail. No FFmpeg dependency.
4. Require a complete *reported* provider/model/voice-source/consent/license/run-evidence provenance manifest. The lab binds the actual WAV SHA and source case SHA. **These reported metadata hashes have NOT themselves been independently verified; the returned receipt says so.**
5. Collect structured listening notes and 1–5 scores for ten categories: naturalness, emotion/arc, word emphasis, pronunciation, breath/pauses, whisper/softness, shout dynamics, voice continuity, retake editability, and performer intent. Reviews are submissions: reviewer identity is **not yet authenticated**. Mechanical WAV metrics never assert emotion, pronunciation, breath quality or authentic whisper.
6. Compare only same-case candidates. The result is a **descriptive table**, never a film-quality approval or speech-worker authorization. Repeat across different real screenplay lines and directing revisions. Previous sources, revisions and takes remain unchanged.

**Important limitation:** case/metadata/reviewer assertions passed to the import API are not yet cryptographically authenticated. Only call the lab through an authoritative FilmIndex case builder and the future trusted host; the current import/score facilities are for offline investigations, not published/protected production verdicts.

### Mandatory real audition matrix (to be executed later)

Each engine must generate the **same genuine screenplay text under the same frozen directing revision**. Do not compare a whisper candidate to a different line in the excited voice. New emotional variants are new authoritatively published directing revisions.

- Neutral, warm/reassuring, sorrowful with breath, angry-but-controlled, frightened, sarcastic and a multi-stage emotion arc.
- A **true whispered** line and a genuinely projected/shouted line, not a quiet normal voice or a digitally amplified normal delivery.
- Proper-name pronunciation, a deliberately stressed target word, an exact pause, an inhalation/sigh/laugh, repeated words, punctuation and sentence-long natural inflection.
- A very short retake with “more sorrow, less panic”; test whether the engine follows the revision **without mutating text or changing VoiceID**.
- At least three scenes per same VoiceID; reference-vs-output blind speaker continuity; two different ActorIDs must not exchange voice selectors.
- Same seed/revision repetition and changed-seed variation; measure actual inference latency, memory, device utilization, GPU/CPU errors, dropouts and clipping on target Windows AMD and reference Linux.

For each audition preserve actual original WAV SHA, model/weights/runtime hashes, source consent, license notices, actor reference audio proof, exact direction, editor selection, execution receipt, native resource/cancellation events and human listening notes. Add independent ASR word accuracy, alignment/phoneme and speaker-embedding analysis only when actual benchmark libraries have separately passed installation/licensing review. Automated emotion classifiers are supporting evidence, **not** proof of acting.

## Remaining gated work

- **07A:** Import/readback, source locking, offline candidate provenance and manual-review schema: **IMPLEMENTED, source-only/local smoke evidence; exact-head Win/Linux CI OPEN**.
- **07B:** Independently execute Qwen3-TTS and IndexTTS with verified checkpoint, trusted runner and real PCM outputs; audit native dependency chain **including FFmpeg exclusion**: **OPEN**.
- **07C:** Cross-model matched emotional/audible comparisons, original pronunciation/stress, speaker continuity, acoustic analysis and separately authenticated human listening: **OPEN**.
- **07D:** ActorID-to-provider adapters, exact director instruction mapping, voice-to-audio source capture, non-destructive revision and retake management: **OPEN**.
- **07E:** Real supervised Windows/Linux worker termination/recovery, AMD GPU acceptance, installed director UI, spatial dialogue placement, performance approval without inherited permissions: **OPEN**.

**No provider will pass cinematic_engine_readiness from the FILM03-06 module solely because this laboratory receives a valid WAV or scores.** That function remains fail-closed, as it should.
