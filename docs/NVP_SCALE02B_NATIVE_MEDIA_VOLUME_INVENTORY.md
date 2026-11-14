# SCALE-02B — Native source metadata and logical storage-volume records

**Status:** Implementation and real-FFmpeg regression code committed. Windows/Linux exact-head execution and native UI integration **not verified**.

## What is implemented

- `backend/nvp_source_media_inventory.py` extends the existing Studio SQLite-backed source catalog; no separate film database or AI server.
- `ffprobe_media` invokes installed native FFprobe without a shell, with a 60-second default timeout and 1 MiB JSON output bound; it stores real stream codec, pixel format, dimensions, rational timebases and frame-rate fields, color attributes, audio channels and sample rate, and container duration if reported. A metadata probe is **not** proof that every source frame can decode.
- `SourceMediaInventory.register_volume` registers a creator/host-assigned project-scoped logical volume ID, root and human-readable label. Neither Windows drive letters nor Linux mount paths are treated as permanent hardware identity.
- `enrich` binds a previously SHA-indexed source to the volume-relative path, full source hash and actual native stream metadata. It rehashes both before and after FFprobe and refuses changed source bytes.
- `describe` returns the saved metadata and current inexpensive availability result when the source is on an unplugged drive. It does not load source video.
- `relink_volume` checks the full SHA and byte count of every asset on the candidate new root **before** applying database path changes atomically. It does not silently accept a different copy based on the same name or size. A successful relink is only point-in-time verification; native rendering re-verifies actual original media before accepting outputs.
- `tests/test_nvp_source_media_inventory.py` generates a real local MPEG-4-in-MOV source at 24000/1001 fps and probes it, tests offline persistent metadata, same-name tamper rejection, exact-hash relocation, cross-project isolation and invalid native stream metadata.
- `.github/workflows/nvp-scale01-02.yml` requests real FFmpeg/FFprobe on Windows Server 2025 and Ubuntu 24.04, Python 3.11 and 3.13.

## Important limitations

The initial `ExternalMediaCatalog.register` path policy still requires a **trusted native caller**; these source paths are not safe to accept directly from the model, untrusted web clients or arbitrary browser DOM. Path ancestor symlinks, Windows reparse points, network-share remounts, volume spoofing, file handles changed after verification, codec spoofing, concurrent writes and FFprobe executable authenticity still need stronger native host containment and executable pinning. These are a security/verification backlog, not accepted gates.

Real metadata is not source decode acceptance. Source timebase/frame count and keyframe indexing, content-addressed proxy generation, media volume identity across device movement, host-authorized media relinking, native UI and FilmIndex source-revision linkage remain open.

The source database intentionally does not duplicate huge originals into FilmIndex small-blob storage. It records a stable **project/asset ID plus source SHA**, and a **logical volume ID plus relative path** as a movable locator. Source bytes remain external.

## Next steps

1. Native source-root authorization, executable SHA pinning and path/volume safety.
2. Multi-track video/audio/timecode probing and validated source container/frame seek metadata (rational).
3. Link source metadata to exact FilmIndex immutable asset revisions and editorial source lookups.
4. Create resource-admitted proxies and thumbnails through the existing TaskLedger and contained workers.
5. Implement working-set preparation/readiness for fast project and scene navigation.
6. Benchmark source media indexing at truly large sizes without high RAM residency.

**No claim of multi-terabyte media acceptance or full feature-film support follows from these source changes alone.**


## SCALE-02D — SD, microSD and camera-card media (mandatory scope)

**Creator requirement:** Removable media support includes full-size SD, microSD (via adapters/readers), and camera cards exposed through operating-system storage APIs, alongside USB flash drives, external SSD/HDD and other removable sources. A card reader or USB port is a *transport*, not the durable identity of a camera card. A card appearing under a different drive letter, mount point or reader must remain findable by its recorded logical media identity plus validated content.

- **Preserve complete camera-card structures.** Ingest must support camera directory trees, spanned clips, sidecar metadata, XML, proxy/thumbnail files and manufacturer-specific layouts. Do not treat only individual .MOV/.MP4 files as an adequate card backup.
- **Read-only originals by default.** Never format, rename, delete, modify, write cache files onto, or automatically eject a camera card. Honor physical write-protect switches and OS read-only state, but do not assume they guarantee protection.
- **Verified ingest:** Copy to creator-selected production storage using durable staged publication, streaming hashes, directory/file inventory and post-copy re-verification. Preserve sidecars, timestamps where possible and original relative paths. An interrupted, incomplete or altered copy must not become an accepted master original. The external-reference-only catalog implemented in SCALE-02B is **not** this verified card-copy operation.
- **Card/copy identity:** Track physical or OS-exposed device hints when available, but never assume card serial numbers are globally unique or obtainable. The immutable source-file hashes and approved full-card ingest manifest are the source of truth. Same card label, capacity or path is not sufficient to authorize relinking.
- **Safe disconnect:** Warn when an indexed card is being actively read or a contained ingest job is running. Treat surprise removal as OFFLINE or INTERRUPTED, keep prior indexed metadata and verified destination files, and reconcile pending receipts before retry. A complete verified copy may permit the original card to be released after explicit creator confirmation, but NVP cannot guarantee that a filesystem/device has been safely removed merely from a UI signal.
- **Multiple verified copies:** Keep all validated replicas and their storage locations separately. Deduplicate identical content identities without conflating distinct takes or automatically deleting any source, card or backup.
- **Filesystem compatibility:** Test common SD camera filesystems such as FAT32 and exFAT and actual reader/hot-unplug behavior on Windows and Linux, including split/spanned recordings, case differences, Unicode names and near-full cards. FAT32 file size limits must never become a general NVP project limit.
- **User experience:** Show CARD CONNECTED / INGEST REQUIRED / COPYING / VERIFYING / INGEST VERIFIED / OFFLINE / INGEST INTERRUPTED accurately; make it possible to review indexed metadata while the card is absent.

**Acceptance gate:** On real SD and microSD media, verify a multi-file camera-card copy, mid-ingest removal, corrupt destination, resumed/repeated ingest without silent duplicates, changed mount/reader, original write protection, creator-controlled release and post-restart authoritative source custody. This gate is **OPEN**; adding this requirement does not claim implementation.
