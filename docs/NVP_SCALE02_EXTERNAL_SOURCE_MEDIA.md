# SCALE-02 — External Source Media Catalog

**Status:** Initial incremental file hashing + indexed external custody committed. Native source ingestion, codec probing, creator UI integration, terabyte acceptance and full worker wiring remain OPEN.

## Purpose

NVP must show a complete multi-terabyte production as lightweight indexed metadata while accessing only the source files needed by current work. Existing FilmIndex's 32 MiB small-blob and 2 GiB imported-media limits remain safe limits for those APIs; they are not the appropriate storage contract for 20 TB of originals.

`backend/nvp_external_media_catalog.py` adds `ExternalMediaCatalog`, storing only project-scoped source identity, absolute original path, media type, SHA-256, 64-bit size and registration time in the existing Studio SQLite database. Originals are not copied, decoded or loaded whole into RAM.

`register` reads files in 4 MiB blocks and compares file metadata before and after hashing. Source symlinks are refused and records are inserted only after hashing finishes. This does **not** guarantee arbitrary external paths are immutable or safe against all concurrent storage changes: the native host must confine allowed source roots/ownership, handle volume movement and prevent concurrent mutation where feasible.

`probe(verify_bytes=False)` is a cheap filesystem size check and returns PRESENT_UNVERIFIED, OFFLINE or CHANGED; it never asserts that existence implies content integrity. `probe(verify_bytes=True)` rehashes actual current bytes and verifies SHA and size, with VERIFIED, CHANGED or UNAVAILABLE_OR_CHANGED outcomes. These are point-in-time results and must be rechecked when committing outputs. `list_assets` pages metadata by asset ID without reading source bytes.

### Unit tests and CI

`tests/test_nvp_external_media_catalog.py` covers a greater-than-4-MiB source, fresh Studio reopen, same-length tampering, offline source preservation, cross-project rejection, duplicate identity, pagination and symlink refusal. `.github/workflows/nvp-scale01-02.yml` requests native Windows/Linux Python 3.11/3.13 test cells. Exact-head CI acceptance is pending.

### Remaining before real multi-TB filmmaking

1. Replace raw arbitrary path registration with creator-authorized source-root/volume capabilities and OS-native exclusive/leased media opens; defend against ancestor-symlink replacement and path races on each platform.
2. Design stable volume identifiers and relocatable media references, with explicit relink/reverify process and error reporting for offline disk/NAS sources.
3. Incrementally index codec metadata, frame rates, rational timebases, source timecodes, audio channels, frame/keyframe seek tables and indexed take/camera identities using approved native media tools, not invented metadata.
4. Build proxies, thumbnails and waveforms with the existing durable native TaskLedger/worker containment, measuring disk/RAM/VRAM budgets and hash-pinning all derivatives.
5. Connect source identities to exact FilmIndex object revisions and compact editorial decisions. Current `EditorialCatalog.publish` only records trusted caller-provided source refs; it is not independent source authorization.
6. Stress actual multi-GiB and eventually multi-TB files, including partial read, disk-full, changed source, interrupted copy/hash, disconnected drives and concurrent edits. Synthetic metadata tests cannot stand in for actual media stress.
7. Add project browser navigation with indexes and bounded active working set. Never require entire originals or the whole finished feature in memory.

No AI Assistance Layer dependencies. No studio-scale or feature-length runtime acceptance is claimed.
