# NVP Wave 1 — long-film production infrastructure (source handoff)

**Branch:** nvp/wave1-longfilm-runtime-pcm-20261111  
**Base:** nvp/g09f-portable-film-distribution-20261111, original at b83ac974ae4295da32e09ea8e6ebe739c71f912b  
**Status:** source implementation only. No CI, compiler, native Windows/Linux execution, package installation, waveform calibration, completed long film or physical owner acceptance has been run. No PR/merge to canonical DATA-AV #74.

## W1-A — Actual installed G09-E worker dispatch (source implemented)

- tools/nvp_desktop_alpha.py dispatches the fixed --g09e-worker role *before* the regular desktop parser/WebView/server. Existing G09ELongDelivery._cmd supplies exactly this role when the NVP application is PyInstaller-frozen.
- tools/nvp_g09e_worker.py accepts a separate fixed --selfcheck. It imports real native dependencies and requires a SciPy-accelerated FilmMeter for longer-than-10-minute films. This check has **no film, project, original-source or execution authority**. It is only an install/runtime dependency probe, not a renderer test or verified worker-custody receipt.
- Windows PyInstaller configuration now explicitly collects tools and NumPy/SciPy. Installed candidate workflow includes frozen worker selfcheck; Debian build script refuses a frozen bundle that cannot run it.
- Worker actions remain analyze/render/verify/finalize using host-owned project, job, index and database identity. No FFmpeg, arbitrary script, model-provided worker path or untrusted native command was added.

## W1-B — Original PCM above 64 MiB (source implemented)

- backend/nvp_g09e_pcm.py adds VerifiedSQLitePCM, an **ordinary project only** source adapter over Python 3.11+ sqlite3.blobopen. It hashes the complete immutable original microphone BLOB in 256 KiB pages and retains the original SHA-256 plus each page digest; source samples are subsequently fetched through a bounded <=1 MiB read with per-page SHA recheck and exact row identity. Connections are closed after verification/read so a long-held SQLite read transaction cannot block the host's durable progress journal.
- backend/nvp_g07_edit.py now admits an over-64-MiB participating original for a G09-E 10-second film window via the verified source adapter rather than reading or rejecting its complete BLOB. The existing 256 MiB *resident original payload* budget is maintained; 64 MiB-and-smaller originals keep their original byte-for-byte reader. The encrypted in-memory G03 database cannot be silently downgraded to this unsealed disk worker.
- The G08 source sound evaluator, G09-C source spatial sound mixer and G09-B reviewed actor voice/jaw analyzer now accept verified bounded original PCM page reads while retaining the exact original source sample position, Take/ActorID bindings and SHA. The jaw RMS analyzer reads max 100 ms of original samples per source evaluation.
- Added tests/test_nvp_wave1_large_pcm.py: source SHA, page crossings, foreign identity, checksum tampering, short actor-RMS windows and a real >64 MiB SQLite zero-BLOB fixture. Tests are authored but **not executed**, per build-first instructions.

## W1-D — Durable original microphone streaming (source implemented)

- backend/nvp_g06_chunked_capture.py extends the **existing actual native audio callback**, without ever allowing browser-uploaded or model-invented source PCM. The director explicitly chooses long capture in Film Scenes. Source sample count at 48 kHz (not wall time or a picture FPS) is authoritative. A single ordinary film scene may now record **up to 30 minutes** in bounded five-second SQLite chunks instead of only a two-minute memory buffer.
- A bounded callback queue separates the audio device thread from a separate SQLite FULL-synchronous source writer; each committed chunk records contiguous sample offset, count and SHA-256. Queue overflow, invalid native callbacks, disk exhaustion, missing tail, changed source stage, or an unclean device stop **fail closed**. The host does not label partial audio a completed original.
- G06NativeRecorder/G09CCaptureJournal and the director API still require the same project/session/real microphone authority as the preexisting short-recorder path; new encrypted projects are explicitly rejected until sealed W1-E custody exists. A short 120-second capture remains backward-compatible.
- A normal Stop/Save first drains the device tail and SQLite queue, then atomically hashes the entire staged source. One host-reviewed G06 transaction verifies every chunk and publishes the byte-identical stream as ordered **at-most-120-second native G06 original PCM clips**, a canonical full-stream SHA+sample-offset manifest, membership links, and the G09-C original callback receipt. The provisional staging copies are removed **inside that same publishing transaction** only after byte verification. The original Film Time source remains independent of the eventual export frame cadence.
- G06 Take freeze and reopen now bind and verify the authoritative recording ID, whole-stream SHA, manifest SHA and exact sample offsets of the component clips. Film Scenes displays the original group, permits selecting its entire ordered set after restart, and defaults their scene-time placement to the original source offsets. Original Takes and their underlying OpenUSD or PCM never change when camera or editorial choices change.
- An unexpected host death leaves durable **non-publishable staged chunks**. Restart-visible health marks the session interrupted, never complete or automatically resumed. A distinct filmmaker-confirmed Discard Interrupted Chunks action deletes only unpublished stage data, never original clips/Takes. Salvaging unknown trailing microphone samples or claiming calibrated hardware A/V sync is intentionally forbidden.
- W1-D source fixtures cover ordered durable offsets, callback stop/tail samples, >120-second original publication into multiple clips, full-source hash and manifest identity, atomic staged cleanup, corrupted chunk refusal and interrupted state. They have **not been executed** under the build-first policy.

**Remaining W1-D acceptance and duration limits:** physically verify miniaudio device callbacks, SQLite writer pressure/latency, 30-minute RAM/disk/audio continuity, interrupted device/host/power failures, Windows/Linux installation, and actual rendering from published source clips. A G06 **single scene** is intentionally limited to 30 minutes, so a three-hour feature must be assembled from multiple independent filmed scenes/Takes; there is no claim of one uninterrupted three-hour microphone take. Physical hardware audio-to-picture synchronization remains G09-C.

## Remaining Wave 1 engineering before claiming closure

1. **W1-C:** Real native Windows/Linux PyInstaller bundle, source import graph, installed fixed worker subprocess with OS Job Object/Linux custody, logs, hard cancellation and restart. Inspect exact compiler/build results only when the owner reopens acceptance.
2. **W1-D:** Source implementation written: 30-minute continuous G06 scene recording using 5-second durably committed chunks, exact source manifest, and atomic <=120-second original segments. Native device, sustained disk/load, physical crash and installed acceptance **remain open**; 3-hour single Take is not supported or claimed.
3. **W1-E:** Protected G03 movies still cannot use the ordinary disk-based G09-E worker or G09-F portable film library. Complete independently confined, encrypted chunk/checkpoint worker and safe historical source migration; no plaintext fallback.
4. **W1-F:** Verify bounded page-reader speed, SQLite concurrent writer/read races, actor/audio seek parity, storage quotas, tamper and restart behavior on 30/60–90/180-minute authentic original footage. Present ten-second reels as working-film SDR MJPEG/PCM16, not cinema mastering or a completed feature.
5. **W1-G:** Audit and pin actual Windows/Linux binary wheels, native ABI/library dependencies, PyInstaller collect paths, product licensing, original file preservation and upgrade/uninstall restoration.

## Source-only acceptance checks to execute later

- Frozen NVP binary --g09e-worker --selfcheck must return zero only with actual native accelerated DSP and fixed worker import.
- A real reviewed G09-E film must produce independently verified reels from a >64 MiB single original, show exact sample equality across every boundary and preserve original Take/PCM SHA before and after cancellation/restart.
- Host authorization, job process custody, worker exit/recovery and source-to-export SHA receipts must be independently verified; no queued/running CI job or model UI state counts as passing.
- Physical Radeon/Windows + native Linux installation and owner-operated long-film playback remain separate acceptance gates.

**Next task:** W1-E — independently confined, encrypted long-film source capture/render/checkpoint custody. W1-D source has been authored and the deferred W1-D native/physical acceptance items remain open; W1-A/B/C are likewise unaccepted until consolidated native verification.
