# SCALE-03C.1 — Media-index upgrades, source integrity and binary-license audit

**Decision recorded 2026-11-05. Status:** Backend notice/version tracking and binary-license inspection tool committed. Desktop notice display, asynchronous index rebuild queue, release-binary provenance and final legal review are OPEN.

## 1. FFMS2 index compatibility is not source media compatibility

The upstream FFMS2 API states that a saved .ffindex may only be opened with the **exact FFMS2 version that wrote it**. The underlying original video, its project source SHA, source identities, FilmIndex revisions, edit decisions and approved frozen takes are not FFMS2 indexes and are not invalidated by an FFMS2 upgrade.

The NVP index is a derived disposable cache. On upgrade:
- Preserve the old index and original video; never silently delete footage, archived takes, metadata or backups.
- Query the fast backend readiness endpoint `FFMS2SourceIndex.compatibility_status(project, asset, source_sha)`. It reads only a tiny NVP-controlled compatibility record (no camera-card access and no whole-source SHA).
- Return `REINDEX_REQUIRED` and the structured user notice `VIDEO_INDEX_VERSION_CHANGED` when a previously indexed source used a different exact FFMS2 engine version **or DLL hash**. The notice states that media/edits are safe.
- Queue real reindexing separately through trusted host authorization and NVP TaskLedger/resource budgets. Never run a large reindex during ordinary project open or navigation. Batching, cancellation, progress, space checks, crash reconciliation and restored offline volumes remain implementation gates.
- After native index creation/reuse passes source SHA, manifest hash and FFMS2 source-match verification, atomically record the current engine version. Preserve older index caches for optional explicit creator-controlled cleanup. Do not relabel an old .ffindex as current.
- An unsafe or corrupt cache marker is `INDEX_METADATA_UNSAFE` / `INDEX_METADATA_INVALID`, not a claim the original media is corrupt. User-visible UI must distinguish cache maintenance from original-media-integrity errors.

**User-facing copy** (do not expose `FFMS_IndexBelongsToFile` or raw file paths):

> Media indexes need updating
>
> NVP's video indexing engine changed. Some saved indexes must be rebuilt before frame-accurate previews are available. Your original footage, edits, and film projects are safe.
>
> Action: Rebuild indexes

Code: `backend/nvp_ffms2_index_maintenance.py` and `tests/test_nvp_ffms2_cache_maintenance.py`.

**Important scope honesty:** The backend emits a structured notice on inspection; no current NVP desktop component has been confirmed to render it. Mark UI notification as OPEN until a native Windows UI test sees and acknowledges it.

## 2. Whole-original SHA checks, their purpose and cost

Current `ExternalMediaCatalog._read_and_hash` and `nvp_ffms2_native.sha_file` loop over the **entire source file**, in small (4 MiB) chunks. They avoid large RAM residency but still incur full source-storage I/O. This detects content replacement even if a name/size remains constant and is vital when removable SD/USB media can disappear or be swapped.

Current code can repeat the full scan:
- at initial source registration;
- before/after metadata probing and source publication;
- during trusted source-window preflight, approval and worker admission;
- before cache create/reuse, after index creation and after native decode;
- before host acceptance of completed source-window output.

On large originals, these independent checks are correct at their respective boundaries but **not suitable as a per-scrub/per-frame interactive path**. A 100 GB media original requires reading roughly 100 GB for EACH full SHA pass, even if only a few frames are requested.

Target distinction:
- **METADATA_ONLY**: project navigation/film overview/clip seek uses SQLite, no original-file read; offline media remains visible.
- **PRESENT_UNVERIFIED**: cheap size/volume/identity/stat hints for displaying current online state. Explicitly not proof of source bytes or permission to publish a verified output.
- **SOURCE_VERIFIED**: true full SHA over exact source bytes, revision pinned to FilmIndex, adequate custody evidence at the verification instant, but not a guarantee that an external drive cannot change afterward.
- **READ_LEASE_VERIFIED** (not yet implemented): an OS-authorized, immutable snapshot/copy-on-write volume or checked file-read handle under a trusted native worker with suitable device mutation/lease protection; avoid repeating full SHA between frames while its bytes are guaranteed unchanged by the platform's actual custody mechanism. A Python open handle on an ordinary FAT32/exFAT/USB file is *not* itself proof of immutability.
- **OUTPUT_VERIFIED**: independently recheck the source identity, selected frame provenance, output hashes and native durable receipts at publication/acceptance. Avoid claiming review previews are final picture masters.

Do not replace full SHA with a quick sample hash, modification time or name **and call the result VERIFIED**. A sampled fingerprint may be used for provisional quick detection only, marked clearly as unverified. Do not hold an SQLite write transaction while hashing terabytes.

## 3. FFMS2 / FFmpeg binary license audit

Authoritative references:
- FFMS2 project README: https://github.com/FFMS/ffms2
- FFMS2 API (index-version incompatibility): https://github.com/FFMS/ffms2/blob/master/doc/ffms2-api.md
- FFmpeg legal checklist: https://ffmpeg.org/legal.html
- MSYS2 FFMS2 distribution: https://packages.msys2.org/packages/mingw-w64-x86_64-ffms2
- MSYS2 FFmpeg distribution: https://packages.msys2.org/packages/mingw-w64-x86_64-ffmpeg
- Fedora ffms2: https://packages.fedoraproject.org/pkgs/ffms2/ffms2/

**Audited upstream claims on 2026-11-05:**
- FFMS2's source is MIT licensed. Official upstream Windows binaries are described as GPLv3 due to their FFmpeg build configuration.
- FFmpeg's default is LGPL-2.1-or-later. With `--enable-gpl` its distribution obligations change to GPL; with `--enable-nonfree`, FFmpeg notes the resulting combination may be unredistributable.
- The MSYS2 `mingw-w64-x86_64-ffms2` package currently declares **MIT**, but it depends on `mingw-w64-x86_64-ffmpeg`, whose package declares **GPL-3.0-or-later**. **Package metadata alone does not certify the resulting NVP redistributed binary.** Treat that Windows toolchain as development/test-only until precise compiled DLL linkage and license compliance are independently reviewed.
- Fedora's ffms2 package declares MIT AND LGPL-2.1-or-later, demonstrating that distribution configurations differ.
- GPL is not simply a prohibition on proprietary software using external processes; whether NVP's particular linking/packaging arrangement triggers source-release obligations requires build-specific legal analysis. Do not present a blanket assertion.

**Release controls:** `tools/nvp_ffms2_license_audit.py` records actual binary SHA-256 values, FFmpeg `-buildconf` hash, and a conservative license flag classification. Normal CI can run it as a non-release development inventory. With `--release-gate` it rejects packaging unless a separately reviewed manifest pins exact FFMS2/FFmpeg binary hashes, source commits, linkage evidence, license notices, corresponding source availability, and an explicit LGPL/GPL-compliant distribution policy. No approved manifest is currently committed; therefore any attempt to run the release gate for current unreviewed binaries must fail. Installer wiring remains OPEN until a real packaging pipeline adopts this gate.

**Preferred evaluation:** build FFMS2 from the MIT source against a verifiably LGPL-only FFmpeg library set, with optional GPL/nonfree codecs disabled in that linking configuration, and review source/linkage/notice obligations for NVP's actual distribution. Keep a separate GPL-compliant packaging option only after counsel signs off. Verify which codecs the creator really needs before excluding them.

Do not claim NVP's NSIS installer is cleared, or that the current MSYS2 test DLLs are suitable for distribution.
