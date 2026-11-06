# SCALE-03C — FFMS2 indexed media-access backend

**Status: native C-ABI integration committed; exact-head Windows/Linux acceptance OPEN.**

## Architecture and provenance

FFMS2 is NVP's first **indexed video frame-access backend**, not a replacement for FFmpeg encoding, grading, or film mastering. Source media stays on creator-selected USB, SD/microSD, external and network storage. FFMS2 indexes and tiny manifest receipts are stored in NVP-controlled project cache, never on the original card.

The new production modules are backend/nvp_ffms2_native.py (native FFMS2 C ABI, exact frame number, PTS/timebase, bounded PNG output), backend/nvp_ffms2_index_cache.py (immutable source-SHA + FFMS2-version + library-SHA cache identity), backend/nvp_ffms2_source_window.py (exact FilmIndex-bound source-window decoding), and the extended backend/nvp_source_window_native_host.py / tools/nvp_source_window_worker.py (explicit creator-approved FFMS2 engine selection inside existing TaskLedger and OS containment).

A native index is accepted only with FFMS2's IndexBelongsToFile check, an independent SHA-256 index manifest, the exact source-content hash and the same FFMS2 binary version. Any modified or incomplete cache fails closed. The current index cache rehashes original source bytes before index reuse, and after initial index creation; decoded source windows rehash after native operations.

The FFMS2 C API uses zero-based signed 32-bit frame indices; the NVP editorial project/FilmIndex remains 64-bit. Values outside FFMS2's range must be rejected or handled by another decoder; never silently truncate. Native metadata retains integer source-frame PTS and rational timebase for future VFR workflows.

## Output and verification

The initial output is 8-bit RGB review PNG (bounded 3840×2160 pixels), not a high-bit-depth/HDR/color-managed master. The creator must approve the precise edit revision, frame window, output destination, RAM budget and FFMS2 library digest. A supervised native worker outputs frame hashes, frame origin, PTS/timebase and FFMS2 index digests. Post-restart receipt verification remains supported. Selecting FFMS2 with a missing native library fails; it never silently falls back to FFmpeg.

The existing FFmpeg native review path remains available for compatibility and unsupported media. NVP AI assistance is not reactivated by this work.

## Tests and CI

tests/test_nvp_ffms2_indexed_native.py exercises genuine source generation, index creation/reuse, frame 119 seek, source-content modification, index-manifest tampering, out-of-range frame rejection, exact source-bound editorial cross-cut review, sealed creator approval, native OS containment, source receipts and restart verification.

.github/workflows/nvp-scale03c-ffms2.yml provisions actual Ubuntu/Windows FFMS2 libraries, FFmpeg/FFprobe and pywin32 where needed. The four cells are Windows Server 2025 and Ubuntu 24.04, Python 3.11/3.13. Passing CI on the exact head is mandatory; queued/failed/skipped cells are not acceptance.

## Remaining work

- **License/installer:** Upstream notes official Windows FFMS2 builds are GPLv3 depending on their FFmpeg compile flags. FFMS2's MIT source license alone does not govern linked binaries. Complete a legal/build-configuration review before shipping a standalone installer.
- **Performance:** Cache-hit retrieval avoids reindexing, but cryptographic verification of enormous removable originals remains expensive. Build trusted source snapshots/read leases for fast interactive access without weakening verification of final outputs. Benchmark long-GOP video, ProRes, VFR, 4K and near-end random access with actual cold/warm I/O, decoding time and memory statistics.
- **Accuracy:** FFMS2 PTS metadata does not itself solve NVP's pending VFR-to-editor frame mapping, retiming, synchronized sound, transition handling or high-bit-depth picture mastering.
- **Worker hardening:** Finalize source-root authorization, symlink/reparse/volume anti-substitution, native library loading trust, storage reconnect and whole-process-tree containment; protect native index jobs with measured resource budgets and safe cancellation.
- **Testing:** True multi-TB indexing, SD-card hot unplug during indexing, corrupt index and native process-kill injections, and Windows installed-desktop acceptance remain open.

This is an engineering deliverable with real native code, not a claim of a finished feature-film editor.
