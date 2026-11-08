# FILM03-09C — real audio-to-phoneme timing and mouth-viseme candidates

**Scope:** This work order is pure filmmaking. It converts actual recorded dialogue and the exact selected screenplay into a traceable candidate for mouth/lip/jaw timing. It neither adds a legal-permissions subsystem nor makes acting decisions about which facial emotion the director should choose.

## Source and execution

1. Reopen original StoryBible ActorID, VoiceID, immutable screenplay line/Take, approved facial-direction source and the exact 48kHz original PCM sample manifest; rehash every original chunk. Never align a different character's words or an unrelated microphone track.
2. The native host exports a temporary 48kHz/16-bit/mono WAV and exact unmodified screenplay text. Model paths and executable are **host supplied and SHA-pinned**; an LLM, browser request, filename or artist-facing UI cannot invent an executable. The preview studio need not bundle a compulsory aligner.
3. The reviewed [Montreal Forced Aligner](https://montreal-forced-aligner.readthedocs.io/en/latest/user_guide/workflows/alignment.html) CLI supports single-utterance real audio alignment and JSON output. NVP's adapter invokes `mfa align_one --output_format json` inside its existing OS worker containment. Linux requires a functioning cgroup-v2 custody layer rather than pretending group cleanup handles escape-capable descendants. Windows requires Job Object custody. An unavailable model/binary or unsupported OS fails closed; no fake timestamps or bare subprocess fallback.
4. Independently parse the aligner's actual `words` and `phones` JSON tiers, require a single speaker, exact same screenplay word order, nonoverlapping bounded intervals and recognized ARPABET pronunciations. Use integer PCM samples, not movie frames, to index all timings; each sample maps to 147000 NVP Film Time ticks. Ambiguous phones, mismatched words, missing word coverage, sample overflow and malformed JSON are errors, not silently guessed mouth shapes.
5. Map reviewed phones to 17 rig-independent categories such as MBP, FV, TH, CH, AA, IH, OH, RR and L, leaving expression/body animation untouched. These are *candidates*, not a guarantee the character has corresponding mouth geometry. Blender/UsdSkel rig adapters and coarticulation still need actual implementation and visual acceptance.

## Verification honestly separated

**09C-1 implemented:** first-party parser/clock mapping, source-bound candidate builder and a real native-worker execution adapter. Win/Linux Python source-contract CI tests import structural fixtures and reject wrong ActorID/words/phones/timing and unreviewed executables. The parser's known timings are **not** real acoustic model results.

**09C-2 OPEN:** install/build a particular reviewed MFA executable and English acoustic/dictionary checkpoint on genuine supported Windows/Linux workers, verify full dependency closure and no FFmpeg dependence in the chosen native NVP path, and actually align a human-spoken reference recording. Obtain exact worker process, original waveform checksum, model checkpoint checksum, output JSON, sample-accurate timestamps, failure/cancel/restart receipt and independent ground-truth phoneme timing comparison.

**09C-3 OPEN:** add a source-bound adapter to the **final artist-selected** converted/TTS audio, rather than assuming a guide is final. Re-run alignment after retake, edits or time-stretch. Existing 09C plan explicitly says source audio may still be only a guide.

**09D/09E OPEN:** map visemes into real original ActorID Blender/OpenUSD rig controls, resolve coarticulation and shared facial muscles, render mouth in motion and inspect against final sound. Facial emotion follows the voice by default; deliberately contrasting director expressions remain preserved.

## Engineering facts

MFA 3.4+ transitions toward new Hugging Face model workflows; the API/version and phonetic dictionary must be pinned and actually tested. Current candidate uses the documented legacy `align_one` signature, and cannot be called native-accepted until a matching reviewed model executes. Third-party packages must not automatically install arbitrary transitive workers into NVP.

No NVP legal forms, contracts or performer-rights settings were created for this task.
