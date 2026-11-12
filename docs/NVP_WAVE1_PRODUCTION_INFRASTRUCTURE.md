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
- G06NativeRecorder/G09CCaptureJournal and the director API still require the same project/session/real microphone authority as the preexisting short-recorder path. Unlocked G03 films now use W1-E sealed source chunks; plain SQLite capture for encrypted projects remains forbidden. A short 120-second capture remains backward-compatible.
- A normal Stop/Save first drains the device tail and SQLite queue, then atomically hashes the entire staged source. One host-reviewed G06 transaction verifies every chunk and publishes the byte-identical stream as ordered **at-most-120-second native G06 original PCM clips**, a canonical full-stream SHA+sample-offset manifest, membership links, and the G09-C original callback receipt. The provisional staging copies are removed **inside that same publishing transaction** only after byte verification. The original Film Time source remains independent of the eventual export frame cadence.
- G06 Take freeze and reopen now bind and verify the authoritative recording ID, whole-stream SHA, manifest SHA and exact sample offsets of the component clips. Film Scenes displays the original group, permits selecting its entire ordered set after restart, and defaults their scene-time placement to the original source offsets. Original Takes and their underlying OpenUSD or PCM never change when camera or editorial choices change.
- An unexpected host death leaves durable **non-publishable staged chunks**. Restart-visible health marks the session interrupted, never complete or automatically resumed. A distinct filmmaker-confirmed Discard Interrupted Chunks action deletes only unpublished stage data, never original clips/Takes. Salvaging unknown trailing microphone samples or claiming calibrated hardware A/V sync is intentionally forbidden.
- W1-D source fixtures cover ordered durable offsets, callback stop/tail samples, >120-second original publication into multiple clips, full-source hash and manifest identity, atomic staged cleanup, corrupted chunk refusal and interrupted state. They have **not been executed** under the build-first policy.

**Remaining W1-D acceptance and duration limits:** physically verify miniaudio device callbacks, SQLite writer pressure/latency, 30-minute RAM/disk/audio continuity, interrupted device/host/power failures, Windows/Linux installation, and actual rendering from published source clips. A G06 **single scene** is intentionally limited to 30 minutes, so a three-hour feature must be assembled from multiple independent filmed scenes/Takes; there is no claim of one uninterrupted three-hour microphone take. Physical hardware audio-to-picture synchronization remains G09-C.

## W1-E — Protected encrypted long-film production (source authored)

**Status:** implementation sources have been committed; native Windows/Linux worker execution, actual Windows AppContainer cleanup, real microphone and long-film acceptance have NOT run. No CI or merge.

### W1-E1 Sealed original microphone custody

- Native G06 long capture routes ordinary films to the original SQLite spool and unlocked G03 films exclusively to the new SealedOriginalChunkStore. Native callback data is bounded in RAM and encrypted in independent five-second AES-GCM source assets; only encrypted identities, source SHA-256, sample offsets and state are written to G03 authenticated SQLite snapshots. The 64 MiB encrypted database limit remains intact; no plaintext source film files or temp originals are created.
- Completed sealed capture authenticates the whole source stream and publishes original <=120-second clip identities and exact offsets as empty BLOB markers backed by protected source-asset references. A placeholder must NEVER be interpreted as silence. VerifiedSealedPCM authenticates original chunks in bounded windows, and G06 freeze/readback, G07 assembly, original preview, G09-B actor voice and G09-C acoustics all use the bound original, rejecting lock/tampering.
- Restart never auto-publishes incomplete source; interrupted source chunks remain encrypted and quarantined. Explicit discard marks unfinished records cancelled. Reviewed encrypted orphan reclamation is still required to recover occupied space without destroying original films.

### W1-E2 Protected native private film rendering and checkpoints

- Fixed native child --w1e-sealed-reel-worker accepts bounded original OpenUSD and source PCM over anonymous pipes, verifies source digests, renders exactly one ten-second AVI with original 24fps/48k Film Time and returns data via pipe. No model token, key, source filename, arbitrary script, network URL or disk export is passed to the worker.
- Native supervisor requires a real Windows AppContainer with zero network capabilities, Job/process-tree custody, code-only ACL and disposable working directory. Mere Job Object custody does NOT authorize private sources. After verified worker exit/profile teardown and independent AVI/frame/PCM readback, the host seals derived output via a one-use G03 worker grant and writes authenticated worker receipts.
- SealedFilmDelivery persists reviewed source SHA, edit revision, sound plan, job state and completed reel checkpoints in encrypted G03 SQLite. Crash/restart marks uncertain work interrupted, never adopts unknown worker artifacts, and requires new human review before restart. Prior completed reels are reauthenticated; the final playlist is itself AES-GCM sealed.
- The actual desktop bridge now mints a short-lived, one-use, exact-project/edit/source/duration authorization only after an OS confirmation dialog. The API cannot mint that ticket. Human-reviewed job grants issue scoped one-use internal reel tickets. Headless/browser-only encrypted export fails closed, as do Linux protected workers pending equivalent OS isolation.

### W1-E6 — Native host integration and source-level reconciliation (authored)

- Actual installed desktop startup binds a real per-WebView OS confirmation bridge to the FastAPI host only AFTER the local NVP window is established. One-use grants are strictly scoped to a trusted project, saved edit revision, original+approved source SHA-256, and exact frame count. Consumption now requires that the originating trusted desktop window remain at NVP's verified loopback origin. The headless API cannot create approvals or substitute a browser confirmation. The fixed worker retains a mandatory real AppContainer launch; a native API preflight is not mistaken for a successful sandbox execution.
- Project lock now closes native microphone capture while its sealed writer has a valid host grant, signals active private reel workers to cancel, and only then revokes the project and AES-GCM session. Native desktop shutdown also signals cancellation for all private film jobs; neither signal invents a process-tree exit receipt. A cancelled, failed or revoked worker cannot publish new film output without independently verified AppContainer/Job cleanup.
- The installed executable now has a fixed, **source-free** `--w1e-runtime-selfcheck` role: imports AES-GCM source readers, protected reel worker, and actual Windows AppContainer security APIs without any movie data, source path or worker authority. The deferred Windows PyInstaller workflow runs it on the genuine built NVP.exe candidate. The later **NSIS-installed step remains a distinct acceptance item**.
- Source-mode AppContainer launch uses the exact reviewed worker script rather than `-m` from a disposable cwd, with a deterministic fixed import root and no untrusted PYTHONPATH. Frozen workers still dispatch through the exact installed binary role, independent of browser code.
- The protected long-film UI's malformed JSX string was fixed. The encrypted job register and microphone health now perform read-only checks for healthy polls and publish a new AES-GCM SQLite revision only when an actual interrupted-state transition is needed, avoiding a full snapshot on every 1.2-second UI refresh.
- Final film playlist publication now independently decrypts and verifies **every** sealed reel's SHA-256, decoded MJPEG pictures, frame count and exact 48 kHz PCM clock. Encrypted original PCM evaluates the 48k sample/sec loop with an in-memory key-revocation check for **every** sample and a bounded 100 ms cross-process session verification interval; each new sealed source chunk and any reel publication triggers full authorization.
- New source fixtures cover one-use OS review revocation after browser navigation, project-specific lock/shutdown cancellation, no-write status reconciliation, worker invocation from fixed script paths, and immediate local key lock under repeated original sound reads. No fixture or runtime test has been executed under the build-first policy.

**Scope boundary:** Source-level W1-E6 integration has been authored, but **neither native Windows AppContainer admission nor the installed product's long-film capture/export has been executed**. Linux private-film isolation, authenticated orphan asset reclamation, and physical/production-scale operation remain open engineering items; no plaintext fallback, automatic orphan adoption, cinema mastering or G09-F encrypted portable library is claimed.

### Remaining W1-E gates

1. Genuine exact-head Windows compiler, frozen module and native AppContainer runtime, OS profile/ACL cleanup, cancellation, original-source equality and independently inspected 10-second protected output.
2. Genuine Windows physical microphone permission and continuous 30-minute encrypted capture under sustained disk/CPU pressure; callback overrun and process/power interruption/restart matrix.
3. Native Linux private-worker confinement including independently verified filesystem/network sandbox; ordinary cgroup-only custody is not sufficient.
4. Reviewed authenticated orphan reclamation for encrypted partial outputs, durable SQLite snapshots, and retained original film and keys.
5. Actual 30-minute, 60-90-minute and three-hour encrypted scene+sound reel scale and playback, plus Windows installed-app UI and accessibility.
6. G09-A/C/D high-fidelity final mastering and cinema DCP Bv2.1 remain separate work; W1-E AVI is a working format, not a professional delivery certification.

Source fixture tests: tests/test_nvp_w1e_sealed_custody.py. They have NOT been executed; synthetic tests do not prove native OS isolation or AES-GCM physical custody.
## Remaining Wave 1 engineering before claiming closure

1. **W1-C:** Real native Windows/Linux PyInstaller bundle, source import graph, installed fixed worker subprocess with OS Job Object/Linux custody, logs, hard cancellation and restart. Inspect exact compiler/build results only when the owner reopens acceptance.
2. **W1-D:** Source implementation written: 30-minute continuous G06 scene recording using 5-second durably committed chunks, exact source manifest, and atomic <=120-second original segments. Native device, sustained disk/load, physical crash and installed acceptance **remain open**; 3-hour single Take is not supported or claimed.
3. **W1-E:** Encrypted original source chunks, host verified source windows, Windows AppContainer native reel worker, one-use OS grant, sealed checkpoint and replay-safe restart are source authored. Native acceptance, encrypted orphan cleanup and independent Linux isolation remain open. G09-F portable encrypted distribution remains disabled.
4. **W1-F:** Verify bounded page-reader speed, SQLite concurrent writer/read races, actor/audio seek parity, storage quotas, tamper and restart behavior on 30/60–90/180-minute authentic original footage. Present ten-second reels as working-film SDR MJPEG/PCM16, not cinema mastering or a completed feature.
5. **W1-G:** Audit and pin actual Windows/Linux binary wheels, native ABI/library dependencies, PyInstaller collect paths, product licensing, original file preservation and upgrade/uninstall restoration.

## Source-only acceptance checks to execute later

- Frozen NVP binary --g09e-worker --selfcheck must return zero only with actual native accelerated DSP and fixed worker import.
- A real reviewed G09-E film must produce independently verified reels from a >64 MiB single original, show exact sample equality across every boundary and preserve original Take/PCM SHA before and after cancellation/restart.
- Host authorization, job process custody, worker exit/recovery and source-to-export SHA receipts must be independently verified; no queued/running CI job or model UI state counts as passing.
- Physical Radeon/Windows + native Linux installation and owner-operated long-film playback remain separate acceptance gates.

**Next task:** W1-F/W1-G — consolidate source integration and actual Windows installed/native results; independently verify OS AppContainer Job/profile cleanup, actor/audio parity, original-source hashes, long render and protected source safety. Linux confinement and reviewed encrypted orphan reclamation are still distinct unresolved W1-E engineering gaps, not silently accepted or downgraded.
