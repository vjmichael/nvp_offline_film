# PLAN-02-E — 30-second continuous native OpenUSD film with original PCM

**Engineering status: IMPLEMENTED SOURCE/TEST PATH; NATIVE GATE AND PHYSICAL DEVICE ACCEPTANCE ARE INDEPENDENT.** This is a data-first film audition, not a compiled movie master or a claim of finished cinema-quality rendering.

## Authoritative film

- One frozen OpenUSD Digital Take is the source of truth. Exactly **30 seconds** in canonical Film Time (`211,680,000,000` ticks at `7,056,000,000` ticks/s).
- Three contiguous original USD camera observations: **0–10 s**, **10–20 s**, **20–30 s**, without duplicated world/performances or invented camera frames.
- Animated native OpenUSD geometry moves during the film. The live Three.js viewport follows the timeline-selected **original authored camera** at the **audio output-device presentation time**, rather than the PCM prefetch cursor. A viewer can explicitly switch back to orbit inspection.
- The recorded sound is immutable original mono PCM16LE, **48,000 samples/s**, a total of **1,440,000 samples**. It is read in bounded source chunks from the SQLite/FilmIndex audio revision; the mixer produces disposable 4096-sample maximum stereo device buffers. There is no feature-long RAM soundtrack, pre-rendered video, MP4, FFmpeg or forced BWF.
- The WebAudio scheduler queues 4096-sample PCM device buffers, maintains an approximately 0.45-second limit, and updates the 3D scene using the **audible sample position**. End of source reads is *not* end of playback; only the last device buffer's `onended` closes the audition.
- Native OS approval for a creator's real Take remains tied to the existing trusted `data_av_begin` one-use source SHA, listener, and time span. New read-only film checks cannot grant approval.

## Genuine acceptance fixture — not a movie substitute

`tools/nvp_plan02e_installed_acceptance.py` produces a deliberately labeled synthetic test *source signal* plus native OpenUSD sphere, camera events and a frozen Take, and performs these checks:

1. Build the actual scene and recorded source in a real SQLite `Studio`, with original PCM as authoritative source bytes and exact revision digests.
2. Check all **720** exact 24-fps *presentation instants* for gap-free film camera coverage. This is a schedule check; **not** a claim that 720 fully rendered frames were played at 24 FPS.
3. Independently render multiple **real native source PNG probes** on both sides of all three camera intervals; confirm picture actually changes and is not an empty card.
4. Stream and SHA-check **all 1,440,000** samples of derived spatial PCM without generating a WAV or flattened soundtrack. Validate last sample is at the exact source end.
5. Run the same **installed `NVP.exe`** for creation, then close it. A new installed `NVP.exe` reopens the frozen SQLite Take and source receipts, rejects stale authorization and confirms first and last original source samples.
6. Uninstall the native app and prove both this original project and the prior PLAN-02-D original SQLite / creator Projects sentinel remained byte-identical.
7. Record the full 30-second PCM evaluator wall-clock duration independently from the actual OS audio-device clock. **Evaluator throughput is not a speaker playback certification.**

Native `unittest` also exercises the trusted desktop controller's `scene_at` at the source cut boundaries, rejects camera gaps and stale SHA, and checks never to report physical approval when only fixture consent was used.

The installed WebView2 gate must see `OriginalThirtySecondFilm` in the actual **native catalog and React take selector**, along with the existing original camera/sound capability tests. It cannot automatically claim speaker output or a human OS-approval dialog was witnessed merely from that catalog.

## Interactive physical 30-second playback and creator authorization

Use the **checksum-paired NOT RELEASED installer** from the same successful native grouped run, never a source-only commit. Run on a clean native Windows account with actual desktop and audio hardware:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\nvp_plan02d_physical_windows_acceptance.ps1 -Installer "C:\YourFolder\NVP-Alpha-Setup.exe" -ShaFile "C:\YourFolder\NVP-PLAN02D-CANDIDATE-SHA256.txt" -ManualThirtySecondFilm
```

The optional physical procedure creates a deliberately **TEMP-only** test project and records original SHA evidence, then launches the **installed** NVP app normally. Once the operator closes NVP, a **new installed process** independently reopens the exact TEMP source project and rechecks all original OpenUSD and PCM hashes; a missing or modified source fails the physical acceptance gate. An actual operator must choose `OriginalThirtySecondFilm`, refuse the first genuine native OS consent request, approve a separate fresh consent request, and personally observe 30 seconds of audible output and the original 3D camera cuts. The operator's response is explicitly labeled as a *human observation*, not an independently authenticated instrument/clock trace. Failed results retain source and diagnostics; the script refuses existing NVP installations.

## Still unaccepted

- Human-observed physical Windows 30-second playback and actual speaker/device sample-clock measurements; hosted headless/interactive WebView2 success alone cannot establish these.
- Real physical microphone recorded source (fixture's deterministic PCM is only a controlled test input), genuine actor dialogue/performance, complex original character meshes, production Hydra/Cycles picture, advanced HRTF/acoustics.
- Native measured 24-fps sustained viewport throughput, zero audio buffer underruns under real load, and long-film checkpoint/restart.
- Original PCM and 3D scene remain authoritative; any later video/audio flattening requires a separate creator-approved derivative export. The 30-second test intentionally produces **no conventional movie master or DCP**.

**Promotion gate:** Do not merge experimental PLAN-02-E into the independently advancing canonical PR #74 before exact-head Windows/Linux consolidated native tests, fully installed GUI validation, physical-device approval/refusal evidence and source-integrity acceptance. DCI/SMPTE mastering and AI Skin remain downstream.
