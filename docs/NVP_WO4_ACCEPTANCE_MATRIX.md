# NVP WO4 cinema-mastering acceptance matrix

**Status:** Work order implementation in progress; no production/cinema
certificate. No FFmpeg. This document records evidence requirements, not
claims that missing external evidence has occurred.

## Native code gates

| Gate | Evidence | Required outcome |
| --- | --- | --- |
| PCM24 source | Native Win/Linux Python 3.11 and 3.13 tests | Exact original SHA, 48 kHz, 24-bit, 24 fps timing, declared channels, no source mutation |
| Motion custody | Real frozen USD Take + FilmIndex + ordered frame-SHA manifest | Approved exact Film Time range, immutable decision ID, denial/tampering after approval |
| Picture transform | Independent ST 428-1 vectors and test images | Correct 12-bit DCDM transfer, explicit D65 vs Bradford cinema-white decisions, bounded gamut and no implicit clipping |
| Audio metrics | Independent BS.1770 calibrated meter on genuine samples | K-weighted gated loudness accuracy within published tolerance; LFE excluded; oversampled true peak verified |
| Full native delivery | Real encoder/wrapper/decoder binaries, independently SHA pinned | Three distinct WO4-derived 2K XYZ12 pictures and original PCM24 through SMPTE DCP, unwrap, pixel and sound SHA reconciliation |
| Extended real-time production | Large varied 2K and 4K reels, bounded resources | Progressive disk-spooled frames and MXF with memory/throughput/cancellation receipts; no all-frames-in-RAM reliance |
| Native fault containment | Kill after file write, fsync, publish, FilmIndex commit | No source overwrite, no published unverified candidate accepted, restart reconciliation |
| Installer | Native NVP Windows/Linux desktop installer | Reviewed codec builds and transitive libraries; complete actual upstream notices; host approval and trusted OS directory picker; reinstall/uninstall |
| External DCI | Independent full DCP validator + projector/server | Schema, essence and cinema ingest; no false certification from NVP self-check |
| Calibrated image/sound | Reference projector/monitor and audio lab | Chromaticity, white point, Y luminance, transfer curve, channel layout, film-mix SPL, loudness and true peak |

## Explicitly unaccepted

- No physical theater screen, calibrated projector or cinema audio measurement
  is available from CI. Source and native unit tests cannot replace those.
- Current WO3 native picture/MXF interface loads whole reels into process
  memory. It is a short-reel acceptance route and must be redesigned for
  production-size 2K/4K features with bounded streaming.
- WO4-05 adapter has a native three-distinct-frame test workflow, but that
  workflow must actually pass at the exact current head before native
  integration acceptance can be recorded.
- Direct installed creator controls and host-connected OS approvals need real
  installed application acceptance. A mock approved callback is not proof.
- An uncertified BS.1770-style pure-Python meter is a diagnostic; laboratory
  true-peak and loudness conformance is still a release gate.
- WO3 independent SMPTE schema and external DCP checks remain outside WO4
  and must be reconciled before a theatrical release.
- Always bundle the exact applicable license/copyright notices for every
  shipped third-party component, including transitive native dependencies.

## Handoff policy

The next work order may proceed while these external/installed gates remain
OPEN, but no document or product UI may call an NVP cinema master formally
accepted until the signed/native, external and physical receipts are present.


## Native disk-spooled sound acceptance additions (2026-11-07)

| Gate | Implementation currently committed | Remains to accept |
| --- | --- | --- |
| Long-form PCM24 mastering | `nvp_wo4_pcm_stream.py` hashes original PCM file before/after consent and streams signed 24-bit samples to a new no-replace WAV; identity and rational gain have parity tests | Run current exact-head Windows/Linux native jobs; verify OS picker and installed desktop acceptance; RF64/reel partitioning for WAV tracks beyond 4 GiB |
| Long-form sound MXF | `nvp_wo4_mxf_stream.py` reuses host-approved file-backed sound, stream-copies a private verified WAV into the pinned asdcplib worker (no shared source inode), verifies native MXF metadata and full source WAV SHA before file-based publication | Complete real CineCert native unwrap CI and independent MXF checker, packaged binary transitive DLLs and legal notices, full feature-length capacity test |
| Long-form loudness | `nvp_wo4_loudness_stream.py` computes K-weighted window energies with bounded sample memory and one block per 100 ms; guards SHA and channel layout | Compare against accredited BS.1770 meter, measure 4×/higher intersample true peak with independent reference, agree target theatrical level |
| Full feature-length picture/DCP | Still relies on in-memory J2K picture/MXF author | Implement bounded picture/MXF spooling and file-backed author; verify 2K and 4K sustained throughput, crash recovery, and independent DCI ingest |

The first three are **implementation-only pending exact-head CI and installed/native acceptance**. Do not confuse safe disk-backed sound candidates with completed production theatrical mastering.


**Codec workspace isolation checkpoint:** The genuine approved WAV is never hardlinked into the wrapper's work directory. Bounded-memory *copying* incurs scratch disk space but isolates the original from worker writes. Native hostile-worker regression tests must pass separately from a real CineCert unwrapping roundtrip. Even a fully passing test does not establish sandboxed process containment or independently certified DCI ingest.


## WO4-LF03 manual workspace lock (decision 2026-11-07)

**Implemented UI:** global manual **Lock NVP** action, app-local full-window inert modal, intentional **Home · Open NVP** or slide-to-open unlock. It does not automatically time out, lock the OS, terminate native work or grant any job cancellation permission. Only a convenience/accidental-interaction lock; not security/authentication. Screen state survives accidental page refresh in the same webview session.

**Verification:** Native Linux Ubuntu 24.04 frontend Vitest + Vite bundle job in run `42354746851` succeeded; native Windows 2025 job had not completed when last inspected. Real installed desktop/OS lock integration acceptance remains OPEN.

**Separate capabilities not implemented yet:** a single genuinely out-of-process durable production supervisor, SQLite journal, process ownership and crash recovery; explicit optional host-vetted Windows/Linux OS session-lock button; production-aware sleep policy and sustained AFK full-film encoding acceptance. These must be tested without conflating the UI convenience lock with a security boundary. See `docs/NVP_PRODUCTION_SUPERVISOR_AND_LOCK.md`.


## LF01 durable supervisor — first native implementation, not feature export

| Gate | Evidence now submitted | Not yet certified |
| --- | --- | --- |
| Host-approved assembly snapshot | Real FilmIndex immutable edit/presentation SHA, dependency and contiguous Film Time job manifest, creator callback | Installed editor host grant, stronger source-root authorization, an actual frozen 3-hour export assembly |
| Independent supervisor ownership | Native Python process, exclusive Linux flock / Windows msvcrt lock, SQLite WAL job journal and process PID, heartbeat | Installed Windows service or headless worker manager, OS process-tree containment, GUI reconnect |
| Real durable verified work | One admitted bounded-memory read-only source verifier, SHA/size segment commits, event trail, no network/FFmpeg | Actual picture render, J2K, MXF and DCP publishing worker handlers with output receipts |
| Crash and restart | Test child process dies via os._exit after claiming, new process reopens and resumes safe source-only scan, detects tampered verified sources | Interruption during output file writing, fsync, atomic promotion, FilmIndex commit; genuine power-loss hardware tests |
| Cancel/AFK | Native host callback required for cancellation; manual NVP lock contains no worker API and is not supervisor-linked | Cooperative termination of real codec subprocess trees, installed app session lock/background job acceptance |
| Native four-platform | GitHub workflow for Ubuntu 24.04/Windows 2025 × Python 3.11/3.13, plus full process subprocess tests | Exact-head completed native success and any actual repairs |

**Status:** LF01 core backend implemented and tested in submitted source; native CI acceptance pending. Do not mistake an in-process source SHA worker inside an independent **supervisor** process for protected subprocess-tree execution of real codec workers. WO4-LF02 and future output-producing worker handlers must use a stricter stage/publish/reconciliation contract; existing code deliberately refuses unknown job types.


### LF01 verified CI checkpoint and project monitor (2026-11-07)

| Evidence | Accepted at tested head? |
| --- | --- |
| Run `42355702884` at commit `d9e1c5dd`: native Ubuntu 24.04 and Windows 2025 × Python 3.11/3.13, separate-process crash and restart, read-only hashing, SQLite owner and cancel | **YES — all four matrix jobs SUCCESS** |
| `backend/nvp_production_monitor.py`: native host-authorized project-scoped read-only source-redacted job progress and post-GUI restart journal reopen | Implemented, **exact newer head CI pending** |
| WAL status/catalog/events no writer lock, restored-source hash outside write transaction followed by atomic reviewed segment check | Implemented, **exact newer head CI pending** |
| Genuine NVP installed-app process/worker host, per-project native UI bridge, OS-contained J2K/MXF subprocess ownership and resumption | **OPEN** |
| Feature-length rendered picture→J2K→MXF→DCP output receipts and physical cinema source/calibration | **OPEN, separate LF02/LF04 and WO5** |

The supervisor's first verified task is **read-only original media SHA verification**. The successful tests cannot be represented as a completed film export or proof that the OS will continue running during sleep/shutdown. The app-local Home/slide lock is separately verified as a convenience overlay and does not stop native production jobs.


## LF02/LF04 native file-backed picture worker acceptance (2026-11-07)

| Gate | Exact evidence | Status |
| --- | --- | --- |
| Real verified 2K OpenJPEG per-frame worker | Run `42357220969`, source-bound full 1998×1080 XYZ12, 3 distinct original frames, SHA-pinned OpenJPEG, separate process per frame | **PASS at commit `3857076b`** |
| File-backed CineCert picture MXF and actual unwrap | Same run, matching real asdcplib wrapping/info and independent full codestream unwrap SHA, no full MXF byte array | **PASS at commit `3857076b`** |
| Same SQLite production journal + durable per-frame/track checkpoints | Independent supervisor process reopened four times; final output state `OUTPUT_READY` not DCP accepted | **PASS at commit `3857076b`** |
| Windows/Linux process-tree cancel and timeout | Actual OS subprocess+grandchild tests in `test_nvp_supervised_codec_process.py`, POSIX process group / Windows Job Object | Implemented; **new-head native CI pending** |
| Output crash recovery, quarantine and reviewed retry | Real `os._exit(79)` partial stage and uncommitted file tests; host-approved no-clobber quarantine preserving all bytes | Implemented; **new-head native CI pending** |
| Post-wrapper source integrity | Rehash approved J2K files after CineCert, reject symlinked output stage and altered original source | Implemented; **new-head codec acceptance pending** |
| Features, full DCP and physical release | Long 2K/4K multi-reel, PCM picture/sound integration, file-backed XML/DCP, installed service and independent cinema ingest | **OPEN** |

Note that LF02's `OUTPUT_READY` is **only a verified disk-backed picture MXF candidate**. No full sound track, DCP AssetMap/PKL/CPL package, external DCI compliance or certified theatrical master is implied. A 3–7200 frame bounded reel is an intentional first production unit; concatenating two hours of cinematic material into one in-memory object remains disallowed. The native output's reviewed quarantine preserves the creator's files; uncommitted stages require explicit disposition rather than automatic deletion.


## LF02/LF04 — supervised complete file-backed SMPTE DCP acceptance (2026-11-07)

| Gate | New implementation / test | Exact acceptance |
| --- | --- | --- |
| Sound MXF in same job | `nvp_wo4_supervised_sound.py` binds the prior approved 24-bit 48 kHz WAV and exact PCM SHA to the verified original mastering decision, streams a private copy, invokes SHA-pinned CineCert wrapper/info through OS process-tree supervisor, and commits output SHA + size in the existing SQLite job | **Code committed. Latest Windows/Linux + real native CI pending** |
| Complete file-backed DCP publisher | `nvp_wo4_file_dcp.py` streams the two real file-backed MXFs in bounded blocks into private stage, generates genuine CPL/PKL/AssetMap/VOLINDEX, independently audits PKL and full hashes, and promotes only with OS atomic no-overwrite directory primitive | **Code committed; structural fake-MXF unit tests pending** |
| Two durable final commits | `CinemaDeliveryJournal.commit_package` records published directory and hash manifest; `commit_filmindex` reopens original FilmIndex, verifies Take/mastering decision and all original WAV/XYZ12/J2K/MXF SHAs, commits exact immutable project revision and is idempotent across crash after FilmIndex commit/before journal update | **Code committed; restart tests pending** |
| Proven actual source + decode | Extended `test_nvp_production_cinema_real.py` continues from prior independently verified genuine 2K OpenJPEG/CineCert picture track through real supervised sound MXF, full SMPTE package, 3 additional independent supervisor processes, FilmIndex receipt and full J2K/PCM decode | **New-head real Linux codec CI queued; old picture-only 2K PASS must not certify new sound/DCP stages** |
| Explicit cancel before publish | New separate creator-confirmed delivery cancellation, no cancelled sound/MXF checkpoint; retroactive cancel of `DCP_PUBLISHED` or `DCP_INDEXED` refused | **Code committed; native CI pending** |
| Crash after promotion but before journal | Existing final folder retained and job put into `REVIEW_REQUIRED` without silently trusting, deleting or automatically relinking it | **Code committed; exact native tests pending** |
| Crash after FilmIndex commit but before final journal | Reads the existing exact immutable FilmIndex record and verifies equality instead of duplicate-revision publication | **Code committed; exact native tests pending** |
| Native installed 2–3 h feature and independent theatrical mastering | Multi-reel/4K performance, OS service deployment, trusted desktop binding, Win suspended-first-job containment, installed binary licenses, independent SMPTE schema/true peak/color/projector validator | **OPEN** |

The full DCP output is still a **source-bound structural candidate**. Correct native MXF wrapping/decoding and SMPTE PKL consistency do not establish formal DCI certification, projector calibration or physical exhibition acceptance. An orphaned final DCP published before journal commit requires a future trusted, creator-approved review disposition rather than automatic overwrite or removal.
