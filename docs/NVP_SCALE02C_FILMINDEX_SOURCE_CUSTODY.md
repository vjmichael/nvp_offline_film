# SCALE-02C — External camera originals as immutable FilmIndex source revisions

**Status:** First source-to-FilmIndex integration committed, real-media regression and native CI added; acceptance still OPEN.

## What changed

`backend/nvp_source_film_bridge.py` supplies a trusted native-only `SourceFilmBridge` between:
- `ExternalMediaCatalog`: project-scoped source asset ID, original external locator, full-file SHA-256 and size.
- `SourceMediaInventory`: logical storage volume, relative path and native normalized FFprobe streams.
- `FilmIndex`: authoritative immutable, project-scoped `asset` source revision.

The bridge stores immutable content identity, byte size, normalized native probe metadata and explicit external-source custody status in the FilmIndex revision. It **does not** embed a drive letter, mount point or physical pathname in that immutable source. That locator remains mutable under the separate source-volume table, with hash-verified relinking.

A source is published only after full external-file rehash returns VERIFIED. FilmIndex's transaction-time source precommit guard checks the stored SHA, size, media type and probe JSON identity, and refuses duplicate creation under the same source asset ID. File bytes are **not** copied into the 32 MiB FilmIndex small-blob store. Opening a source from an unplugged SD/USB drive still returns its FilmIndex revision and indexed metadata with OFFLINE status. Reconnected media is independently rehashed on request; no cached status is reused as persistent proof.

`tests/test_nvp_source_film_bridge.py` generates actual native source MOV media and exercises first FilmIndex publication, restart with offline original, same-content relocated copy, duplicate publish refusal, changed bytes, project isolation and database isolation. The pre-existing four-cell Windows/Linux/Python native CI workflow now runs this test. Exact-head results must be inspected before accepting.

## Boundaries

- The source is an **external reference**, not an immutable, protected on-disk copy. A file on an SD card can change or disappear even after verification. Every downstream native render, edit conform or publication must bind the exact FilmIndex revision and reverify its source at consumption/publication boundaries.
- The bridge does not authorize browsing arbitrary paths, creator approval, native worker execution, proxy generation, or removable-drive write operations.
- An SD card's logical volume ID is host-assigned. The reader, drive letter, partition path and OS device number are not trusted as proof of source identity.
- Movie metadata is actual FFprobe data, **not a guarantee** that all frames and audio samples decoded.
- Studio-scale indexed timeline clips are not yet atomically linked to FilmIndex edit-revision dependency edges. That is the next SCALE-02C integration. Without it, partial invalidation and creator-approved final edit binding cannot be claimed.
- Current native source-root authorization, device hot-unplug reconciliation, verified camera-card folder ingest and multi-replica management gates remain OPEN. SD and microSD requirements are in SCALE-02D documentation.

## Next implementation

Create a native trusted `EditorialSourceBinder` that validates every compact editorial clip against exact FilmIndex `asset` revisions and source ranges/timebase; publish a FilmIndex `edit` revision with scalable source-reference manifest and indexed dependency edges. Preserve transaction integrity across editor interval tables and FilmIndex so a crash cannot create a false accepted edit or orphan a falsely authoritative timeline. Avoid a whole-film array or exceeding FilmIndex's 128-direct-edge limit: represent indexed source references hierarchically and page dependency retrieval.

Do not mark NVP as accepting studio-scale source editing, real multi-terabyte media, or a verified feature film based on this initial bridge.
