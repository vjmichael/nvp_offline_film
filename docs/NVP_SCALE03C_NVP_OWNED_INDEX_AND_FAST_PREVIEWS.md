# SCALE-03C — NVP-owned frame indexing, fast preview custody, and FFmpeg decoder

**Decision 2026-11-05:** Replace the proposed FFMS2 runtime/index dependency with NVP's own versioned SQLite source-frame index. Do not add FFMS2 libraries to the NVP installer. Keep FFmpeg/FFprobe as the current decoder/probing tools. The original FFMS2 prototype PR #46 is superseded by this implementation.

**State:** Source indexing, exact timestamp seeking, host/worker integration, and real-media tests committed in draft form. Exact-head Windows/Linux CI, feature-length I/O benchmarks, installer licensing approval, and full producer acceptance remain OPEN.

## Code

- `backend/nvp_native_frame_index.py`: NVP v1 SQLite index with 64-bit frame ordinals, monotonic presentation PTS, exact rational stream timebase, keyframe references, packet position hints, video-stream identity and first-source registration SHA. The original video is **not hashed** in this module. SQLite is a controlled, documented, migratable NVP-owned format; a newer FFprobe executable does NOT alone invalidate old indexes.
- `backend/nvp_indexed_preview.py`: decodes only a bounded selected source interval using FFmpeg input-side `-ss`, `-copyts` and `showinfo`. Every frame's **actual decoded PTS must exactly match** the NVP index. A mismatch fails closed; it never silently claims the wrong frame. Uses the operating-system/container native FFmpeg seek machinery for GOP dependencies.
- `backend/nvp_native_indexed_window.py`: maps the exact FilmIndex-bound editorial source slices into source intervals, performs bounded indexed decoding, and issues SHA-256 **output PNG** receipts. Output image hashes are small; this does not rehash a 3-hour original.
- `SourceWindowPreflight.prepare(... integrity_policy="preview")`: retains FilmIndex exact source-revision binding, validates online status, and returns `PRESENT_UNVERIFIED_PREVIEW_ONLY` instead of whole-source SHA. The original `integrity_policy="full"` remains the default and continues to SHA-verify exact source bytes where required. Disabling byte verification with legacy `verify_original_bytes=False` is still rejected.
- `NativeSourceWindowHost(... decoder_backend="nvp_index")` and `tools/nvp_source_window_worker.py`: native trusted creator authorization, sealed worker plan and decoder selection, pinned FFprobe/FFmpeg tools, TaskLedger resource admission, OS-contained workers, independent receipt verification, durable reopen. Existing FFmpeg legacy full-hash worker remains compatible. A fast preview is not a final picture/master.

## Index building

1. At original camera ingest, `ExternalMediaCatalog.register` already records the whole-file SHA. The FilmIndex source revision pins that identity; these are one-time custody/registration gates.
2. The indexer requests stream timebase and one video stream through native FFprobe. It then **streams** `ffprobe -show_frames` results in presentation order, inserting one compact SQLite row per frame. This is an upfront *one-time* source scan and may involve decoding every frame during indexing. No frames or whole file are materialized in Python RAM. This is an accepted first indexed design, not yet the cheapest possible initial index builder.
3. At completion, it checks that the same storage-file identity, byte size, mtime and ctime are still present. It atomically installs the new SQLite index. Interrupted/incomplete builds leave an explicit reconciliation state; they are not silently reused.
4. On next project visit or scene seek, NVP opens the SQLite index, does only a quick file stamp comparison, seeks directly to a 64-bit frame row and finds the nearest preceding keyframe. Repeated previews do not decode the entire original and do not recalculate whole-video SHA.
5. FFmpeg input-side accurate seeking begins near a suitable GOP seek point; NVP checks actual decoded PTS against the requested frame indexes. It does **not** assume packet order equals presentation order, which matters with B-frames.

The index belongs to NVP project cache, not to original SD/microSD cards, USB drives, external SSD/HDD, or a camera volume. An index is keyed by project ID, immutable source asset ID and originally registered content SHA. FFprobe binary SHA is *recorded* for provenance, **not** used as a compatibility version lock. Future NVP schema migrations can support older SQLite indexes instead of automatically destroying them.

## Crucial integrity distinction

**FAST_PREVIEW / UNVERIFIED_FAST_PREVIEW:** check project/asset/revision identity, recorded SHA, online presence, file device/inode/size/timestamps, index schema and actual decoded PTS. It is fast, but file metadata can be forged or restored, FAT/exFAT timestamps may be coarse, and another process can replace the file. This is **not cryptographic source verification**. Call it SOURCE_STAMP_UNVERIFIED; the source's SHA is the previously recorded ingest hash, not a fresh proof.

**VERIFIED_FINAL_PUBLISH:** when NVP publishes a creator-approved, authoritative final picture/film master, require a separate exact-source cryptographic custody check at an appropriate publication boundary. Implement streaming output receipts and source inputs over a protected snapshot/host-managed read lease or equivalent verified custody. Do not repurpose provisional preview evidence as final acceptance.

Only output PNGs and sealed worker documents are SHA-hashed on the fast preview path; no repeated whole-original SHA during index lookup, creator approval, worker preflight, source window processing or review-output acceptance. The original image/film project remains browsable while its camera SD drive is offline.

## License posture

NVP's frame-index code and SQLite format are NVP-owned; **no FFMS2 binary or .ffindex is required**. This resolves FFMS2's exact-version cache compatibility and FFMS2-specific binary distribution problem. **It does not eliminate FFmpeg licensing**: packaged FFmpeg/FFprobe binaries and their linked codecs can still be LGPL/GPL-configured and must be reviewed before the single NVP Windows installer ships. See https://ffmpeg.org/legal.html . Source-code ownership of the indexer does not make FFmpeg's codecs proprietary.

## Native test and acceptance plan

`tests/test_nvp_owned_frame_index.py` generates real 150-frame B-frame/GOP source video, builds and reopens the index, seeks near its end and validates exact PTS, patches original media SHA routine to assert it is **never invoked during fast preview**, checks same-size file mutation rejection by source stamp, preserves legacy full-hash mode, exercises an actual creator-approved TaskLedger/contained indexed review across an edit cut, checks durable output receipts, offline reuse and tampered frame provenance.

`.github/workflows/nvp-scale03c-owned-index.yml` runs real FFmpeg/FFprobe on Windows Server 2025 and Ubuntu 24.04 with Python 3.11 and 3.13. Tests must actually decode media, not just compile or mock worker results. A queued, skipped or failed run is **not** acceptance.

Remaining: measured multi-hour/4K/VFR access benchmarks; verified font/codec/PNG consistency, high-bit-depth output, OS file identity/reparse protection, long-index timeout/resource checks and cancellation, index corruption/migrations, SD-card unplug recovery, source-snapshot/read leases, and safe final-film custody. The AI Assistance Layer stays deferred.
