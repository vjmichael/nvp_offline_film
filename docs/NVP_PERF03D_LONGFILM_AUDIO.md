# PERF-03D — Bounded long-film PCM24 mastering and exact reel clocks

## Scope

Host-only source-bound partitioned PCM candidate on the existing WO4 protected mastering path. Approved raw little-endian interleaved PCM24 at 48 kHz; stereo, 5.1, 7.1 existing explicit channel orders. Existing single-file mastering and its format remain unchanged. The new operation does not approve a renderer, cinema master, DCP, playback, release, or native worker automatically. The caller is a trusted host supplying the original Take digest and exact approved raw source digest; this does not establish new FilmIndex authority or automatically assemble multi-Take raw audio. No new IPC or GUI control.

## Exact time and large-file policy

24 fps, exactly 2,000 samples per channel per picture frame; frame count bounded by exact IEEE-754 source tick representability. O(1) balanced reel lookup; default ceiling 7,200 frames (five minutes); effective maximum also constrained by the existing finite master and conservative classic RIFF payload bound. Refuse impossible minimum-three-frame partition. All reels are ordinary PCM24 WAVE with exact 44-byte headers, no silent 32-bit wrap. Whole raw source length and global sample cursor may exceed 4 GiB; single oversized WAV/RF64/BW64 and arbitrary external WAV variants are not introduced or qualified. Source is not converted, resampled, padded, or truncated.

Full-film arithmetic at 48 kHz/24 bits (decimal GB, excluding headers and filesystem overhead):

| Hours | Reels at 5 min | Stereo bytes | 5.1 bytes | 7.1 bytes |
|---|---:|---:|---:|---:|
| 0.5 | 6 | 518400000 | 1555200000 | 2073600000 |
| 1 | 12 | 1036800000 | 3110400000 | 4147200000 |
| 3 | 36 | 3110400000 | 9331200000 | 12441600000 |
| 6 | 72 | 6220800000 | 18662400000 | 24883200000 |
| 8 | 96 | 8294400000 | 24883200000 | 33177600000 |
| 12 | 144 | 12441600000 | 37324800000 | 49766400000 |
| 24 | 288 | 24883200000 | 74649600000 | 99532800000 |

## Publication and verification

The existing Windows protected-path/EFS guard is reused. Exact source SHA/size streamed before separate creator approval; exact scope includes source, Take, channels, sample count, rational gain, destination root and partition descriptor. Root/source identities rechecked, actual disk admission before stage creation. Original PCM is read in <=4,096-sample blocks, gains rounded with existing integer policy, clipping refused. Raw whole/source-reel, transformed whole/reel and exact WAV bytes separately hashed. Receipts streamed into bounded <=4 KiB canonical JSON lines with compact <=16 KiB root. Every reel and ordered manifest independently reopened before promotion, original directory/source identities rechecked, and existing kernel atomic no-replace directory promotion used. Fsync staged files. Reopen published bytes before returning candidate. Cancellation before publication cleans the owned stage; an error after promotion leaves an unapproved orphan for review, not a success or silent replay. Actual physical Windows EFS/power-loss/host-death behavior remains gated. Whole-film output-producing journal/lease integration is not yet implemented; synchronous trusted-host candidate path is not a new supervisor or autonomous job.

A finite-reel compatibility function verifies the entire manifest and all media, requires exact requested first-frame and count and existing <=7200-frame delivery bound; produces original per-reel disk-backed WAV candidate receipt including per-reel original PCM SHA and parent manifest SHA. Existing sound source guard independently reopens WAV and PCM and checks Take and frame count. The original delivery journal still requires exact independent mastering decision hashes and separate authorization. No codec or DCP worker launched in this task. Picture reel matching must be handled by trusted caller/approved decision; this is not full delivery routing.

## Bounded loudness

Existing K-weighting, LFE exclusion and 400 ms window / 100 ms step. First pass computes absolute gate sum and count; optional second verified replay computes relative gate sum/count. No retained full track block list; filter state and sample cursor continuous across reel boundaries within each pass. Every pass verifies source PCM SHA and exact sample count; partitioned input also verifies all ordered receipts and WAV bytes. Legacy single-file loudness entry point now uses the same bounded packet function, original file verification before/after each pass. Still diagnostic, not true peak oversampling, calibrated meter, final loudness compliance or automatic normalization.

## Local evidence

Recovered archive dependency base, not full exact checkout. Existing WO4 loudness source, PCM stream/master, resource budget, atomic publish, supervised sound and MXF stream match current Git blobs before edits. New long-film module, modified loudness implementation and test suite compiled and byte-match uploaded blobs. Ten portable new tests passed, one actual native Windows EFS test skipped. Real small PCM files, actual WAV generation, atomic no-replace local Linux publication, original PCM unchanged, clipping/creator refusal/source mutation/cancel/tail tamper, source guard/finite bridge and exact integer gain/loudness parity. Windows-specific encryption and process custody mocked only in portable fixtures; sparse 6.2208 GB raw file checked for correct length and cancellation before approval (not all bytes read/rendered; POSIX only). Clock arithmetic through 24h in all three layouts, conservative RIFF bounds and minimum reel tests. Existing nine zero-FFmpeg negative tests and six temporal-ledger tests pass, total 25 local successes; archive active no-FFmpeg policy with new entry point passes. Exact current remote guard updated by one anchored entry addition; no full exact checkout acceptance. Real native EFS test authored/compiled and included in existing WO4 workflow. No new workflow.

Actual in-memory synthetic packet diagnostic (Linux CPython 3.13.5, same deterministic stereo PCM24 packet repeated):
| Samples/channel | Nonzero 400ms blocks | Traced Python peak bytes | Elapsed seconds with tracing | LUFS |
|---:|---:|---:|---:|---:|
| 24576 | 2 | 621698 | 1.519 | -22.9002955689 |
| 98304 | 17 | 621698 | 7.063 | -22.9002866664 |
Traced Python allocations only; includes instrumented execution, not RSS/GPU/real-time performance. These are actual tiny packet measurements, not hours of produced audio. Full-duration audio master, native MXF/DCP/large-file performance, EFS crash recovery, output producing journal custody, actual scene/audio assembly, and physical native qualification still open. Existing historical AUDIO-01D recovery worker's 2h cap remains unchanged; that legacy path is not the new native PCM partitioned master. Complete active-path integration and native acceptance before advertising large-film delivery.
