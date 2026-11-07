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
