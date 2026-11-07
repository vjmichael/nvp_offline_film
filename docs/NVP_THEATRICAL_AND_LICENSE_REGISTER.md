# NVP — Theatrical DCP acceptance and deferred third-party licenses

Updated 2026-11-07. **Implementation may proceed. License collection and full
theatrical specialist acceptance are deferred by creator, not waived.** This
register is mandatory to reopen before a native NVP/Lu DLC installer is
published. It does not assert that NVP's own DCP auditor provides DCI
certification.

## Current external technical baseline

- [DCI Digital Cinema System Specification (DCSS)](https://www.dcimovies.com/dci-specification/):
  version **1.5.0**, published/approved 2026-01-29. Refer to the current
  definitive DCI HTML specification when making final release claims; don't
  freeze a 2025 version as if it were current in 2026.
- NVP outputs SMPTE-style picture/sound MXF, CPL, PKL, ASSETMAP and VOLINDEX,
  with DCP structure/UUID/SHA-1 PKL interchange checks and separate stronger
  source-custody SHA-256. This alone is **structural** evidence.
- 2K/4K original XYZ12 24fps cinema profiles, OpenJPEG codestream and actual
  CineCert/asdcplib native wrapper tests have passed on short source-bound
  synthetic media; extensive color and cinema interoperability gates remain.
- DCI's cinema-system compliance testing concerns projection, playback/
  media blocks, security, image and sound behavior, and interoperability.
  Validating one independently produced DCP is not a blanket DCI certificate
  for the entire NVP editor or for cinema hardware.

## NVP-owned export gates (engineering)

1. **Picture:** exact supported 2K/4K pixel dimensions and 24fps Film Time,
   correct 12-bit XYZ and applicable color transformation, no illegal
   subsampling, compliant JPEG2000 codestream profile, rate and tile markers;
   representative and full-source decode where required.
2. **Sound:** appropriate 48 kHz 24-bit PCM, declared channel order, reference
   gain/headroom and speaker map, measured peaks/loudness, sync drift and
   stereo/5.1/7.1 interoperability. Cinema playback reference is not the same
   as arbitrary online-streaming loudness normalization.
3. **DCP:** signed/unsigned/encrypted policy as selected for distribution,
   valid SMPTE MXF essence and edit-rate, CPL reels and UUIDs, PKL SHA,
   ASSETMAP paths, subtitles/timed text when present, exact content hashes,
   no missing files or source modification, full timeline continuity.
4. **External acceptance:** inspect with a separate capable specialist
   validator (not NVP's internal auditor), actual ingest on a cinema server
   or IMB, calibrated image and sound review at a reference facility,
   projector 2K/4K playback and subtitle/5.1/7.1 checks where applicable.
5. **Security/delivery:** if encryption/signing and KDM are required by a
   venue/distributor, implement and independently test credential custody,
   certificates, validity windows and package encryption. An unencrypted DCP
   may be appropriate for some independent cinema deliveries but is NOT
   evidence of complete security workflow compatibility.

**NVP must not claim DCI-certified theatrical delivery merely because a DCP
directory, XML hash check, or short native decode passes.** Independent
validation and real-theater ingest are specialist release gates.

## Third-party license/notice collection — deferred, tracked

| Component | Current role / evidence | License / notice action before redistribution | State |
| --- | --- | --- | --- |
| OpenJPEG and libopenjp2-tools | Native JPEG2000 codec; CI uses distro `/usr/bin/opj_compress` and `opj_decompress` | Resolve actual *shipped* version and source commit; collect full upstream license/copyright and all redistributed binaries, runtime libraries and notices | **DEFERRED / REQUIRED** |
| CineCert asdcplib | Native picture/sound MXF wrap/info/unwrap; GH pinned source at `905d6047f67c8211c2d22f29fb0e2e44c142b59b` and checks `deps/asdcplib/COPYING` | Read and preserve exact `COPYING` terms, contributor copyright, modified-source rules and notices; inventory any linked runtime dependencies and actual released commit/version | **DEFERRED / REQUIRED** |
| OpenUSD / `usd-core` | OpenUSD scene and frozen Digital Take; CI pinned `usd-core==26.11` | Collect exact installed wheel/runtime license, third-party notices and dynamically linked dependencies if redistributed in installer | **DEFERRED / REQUIRED** |
| Python native runtime + stdlib | Host-managed independent production supervisor and codec workers | Record version, runtime binaries, license files and any bundled wheels/standard libraries; include exact PSF/other required notices after source review | **DEFERRED / REQUIRED** |
| SQLite / database bindings | Persistent WAL/full-sync production/FilmIndex journal | Verify runtime distribution form and origin; preserve applicable notices or public-domain evidence in release bill of materials | **DEFERRED / REQUIRED** |
| Native Windows/Linux runtime dependencies | CRT/UCRT, libc/libstdc++, compiler runtime, OpenSSL or XML libraries only **if actually redistributed or dynamically linked** | Scan final binary dependency graph (`dumpbin`, PE imports, `ldd`/ELF), distinguish OS-provided components from bundled components, collect exact original notices | **DISCOVERY REQUIRED** |
| UI/installer stack (Lu host, Tauri, React, native helpers, NSIS) | Future installed Lu/NVP DLC; final version and transport not frozen | Record every bundled package (direct/transitive) and required notices at packaging freeze; no assumed generic MIT license for all dependencies | **DEFERRED / REQUIRED** |
| Build-only compilers and test tools | CMake, CI setup tools, DCP specialist validator used off-device | Determine whether code/binaries are actually shipped. Do **not** automatically add unused CI tooling to the runtime bundle; do comply when redistributed | **CLASSIFICATION PENDING** |

**Required artifact before release:** machine-readable SBOM with upstream
component/version/commit, exact binary SHA-256, source/download provenance,
direct+transitive dependencies, ship/non-ship classification, actual complete
LICENSE/NOTICE source files and their SHA-256, attribution and obligations.
`backend/nvp_wo4_native_bundle.py` already rejects missing license/notice
files for *declared* components, but cannot replace independent platform
dependency scanning or counsel/legal review.

## Full-duration GitHub Actions stress test

`.github/workflows/nvp-wo4-sustained-cinema.yml` tests all four combinations:
2-hour 2K, 3-hour 2K, 2-hour 4K and 3-hour 4K at 24 fps. It has a real
OpenJPEG three-unique-frame setup, 5-minute 7200-frame J2K frame hardlink
spool, actual CineCert picture+stereo PCM24 sound MXF **per reel**, a final
file-backed multi-reel CPL/PKL/ASSETMAP and independent complete structural
audit. It records SHA, wall clock, source custody, peak memory, disk use and
reel count into JSON artifacts. The full-duration frame slots are 172,800
(2h) and 259,200 (3h).

**Important limits of this CI stress test:** it deliberately reuses just
three original encoded 2K/4K XYZ12 frames (and a five-minute approved
synthetic stereo PCM master repeated across all reels); therefore this is
a FULL-DURATION NATIVE MXF WRAPPING + SMPTE PACKAGING test, NOT proof of
unique-frame rendering throughput, real cinematic complexity/compression,
full picture/sound independent DCI certification, calibrated color/audio,
full FilmIndex source-specific per-frame production approval, or a native
installed Lu DLC. The standard hosted Linux runner has a documented
14 GB SSD and GitHub-hosted jobs have a 6-hour maximum runtime. The test
must report an explicit low-disk failure if both source tracks and final
package cannot fit; never silently downsample, omit sound, shorten the
feature or mark a partial export complete.

**After CI:** If all four variants pass, close the full-duration
synthetic-native export stress gate only. Keep full original unique-frame
render performance and installed-app external cinema acceptance open.
