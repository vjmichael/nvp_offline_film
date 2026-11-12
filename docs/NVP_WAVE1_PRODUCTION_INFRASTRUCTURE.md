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

## Remaining Wave 1 engineering before claiming closure

1. **W1-C:** Real native Windows/Linux PyInstaller bundle, source import graph, installed fixed worker subprocess with OS Job Object/Linux custody, logs, hard cancellation and restart. Inspect exact compiler/build results only when the owner reopens acceptance.
2. **W1-D:** G06 live microphone adapter still limits one new native recording to 120 seconds; a single continuous three-hour PCM source remains beyond the ordinary SQLite BLOB limit. Implement chunked capture/write and immutable chunk-manifest source identity rather than increasing a memory bound or inventing samples.
3. **W1-E:** Protected G03 movies still cannot use the ordinary disk-based G09-E worker or G09-F portable film library. Complete independently confined, encrypted chunk/checkpoint worker and safe historical source migration; no plaintext fallback.
4. **W1-F:** Verify bounded page-reader speed, SQLite concurrent writer/read races, actor/audio seek parity, storage quotas, tamper and restart behavior on 30/60–90/180-minute authentic original footage. Present ten-second reels as working-film SDR MJPEG/PCM16, not cinema mastering or a completed feature.
5. **W1-G:** Audit and pin actual Windows/Linux binary wheels, native ABI/library dependencies, PyInstaller collect paths, product licensing, original file preservation and upgrade/uninstall restoration.

## Source-only acceptance checks to execute later

- Frozen NVP binary --g09e-worker --selfcheck must return zero only with actual native accelerated DSP and fixed worker import.
- A real reviewed G09-E film must produce independently verified reels from a >64 MiB single original, show exact sample equality across every boundary and preserve original Take/PCM SHA before and after cancellation/restart.
- Host authorization, job process custody, worker exit/recovery and source-to-export SHA receipts must be independently verified; no queued/running CI job or model UI state counts as passing.
- Physical Radeon/Windows + native Linux installation and owner-operated long-film playback remain separate acceptance gates.

**Next task:** W1-D or W1-E depending on immediate priority: durable chunked original capture versus sealed feature-length production. Neither should be counted complete because W1-A/B source is now present.
