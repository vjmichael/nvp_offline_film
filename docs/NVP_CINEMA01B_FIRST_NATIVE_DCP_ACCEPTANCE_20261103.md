# NVP-CINEMA-01B: First real independent DCP technical acceptance

**Date:** November 3, 2026  
**Outcome:** REAL DCP-o-matic encode/decode/independent external verifier passed on a supplied NVP ProRes test movie. **FilmIndex end-to-end registration remains refused pending a frame-padding decision and source-ledger replay. Not screening-ready.**  
**Related:** [CINEMA-01B essence audit](NVP_CINEMA01B_JPEG2000_MXF_EVIDENCE.md), [package intake](NVP_CINEMA01B_DCPOMATIC_PACKAGE_INTAKE.md).

## Input integrity

- Offline user-uploaded Ubuntu 26.10 amd64 dependency bundle, `NVP_CINEMA01B_UBUNTU2610_AMD64_20261103_153902.zip` (147,514,375 bytes), SHA-256 `911592507859af9880cd655fcb2f95e369db663b87415e28e2721c92bb09509b`.
- `manifest.json` declared 238 verified packages, zero unresolved. An independent read-back of each ZIP member's full bytes, SHA-256 and size passed **238/238**.
- Original DCP-o-matic Debian package, `dcpomatic_1+2.18.51-1_amd64.deb`, SHA-256 `8b8f1d38fa2db1c2d65690f7007f99e0df2a0fdec5ac25cd78477412c21a1e70`.
- Uploaded NVP ProRes test movie `NVP_ProRes_422_HQ_Professional_Test.mov`, SHA-256 `f8eab0440a5a79aeea830e273d735d4e5c975927afc0355647599cf331603216`. Independent FFprobe read: `prores/apch`, 128×72, `yuv422p10le`, 24fps, **16** frames; **no** approved audio.
- **Origin caveat:** the Ubuntu InRelease PGP signatures were *retained*, not cryptographically authenticated. Hashes guarantee archive content consistency with the collected package indexes, not publisher provenance.

## Runtime method and privileges

All 238 Ubuntu `.deb` dependencies were **extracted only** with `dpkg-deb -x` into a private staging root; the DCP-o-matic package's privileged `postinst` and disk-writer capability grant were **never run**. The host's Debian glibc 2.41 stayed intact. The three DCP CLIs used the staged Ubuntu glibc 2.44 loader in a Linux user/mount/network namespace and a private chroot. The test used three **host fallback components** that were absent from the dependency bundle: `libsqlite3.so.0`, `libpulsecommon-17.0.so`, and `dash` for `/bin/sh`. A private `/proc/self/exe` link and namespace-local /dev binds were needed to launch the tools; this is not a complete production containment design.

Observed tool versions: `dcpomatic2_create` and `dcpomatic2_cli` **2.18.51 920fb9b044**; `dcpomatic2_verify_cli` **dcpverify 1.10.64**.

## Measured first-run DCP package

- Generated and completed a real **unencrypted SMPTE 2K Flat**, 24fps, 2D `TST` technical DCP from the uploaded NVP ProRes movie, with local-only, two-thread DCP-o-matic conversion.
- DCP-o-matic generated `ASSETMAP.xml`, `VOLINDEX.xml`, `cpl_*.xml`, `pkl_*.xml`, actual `j2c_*.mxf` and `pcm_*.mxf` files.
- Independent FFprobe measured picture `jpeg2000`, **1998×1080**, `xyz12le`, 24/1 fps, **24 decoded frames**.
- Independent FFmpeg full-decode of the complete JPEG2000 picture MXF returned **exit 0**.
- Independently decoded the DCP picture to RGB; source content spans the first **16** frames. For the remaining **8 frames**, a separate full-resolution FFmpeg decode selected frames 17–24 and produced exactly **51,788,160 RGB24 bytes** (8 × 1998 × 1080 × 3), with **zero nonzero channels** and exit 0. Thus the entire trailing section—not just a downsampled thumbnail—is verified black. This is one second of packaged picture, compared to the original two-thirds-of-a-second source.
- Independent FFprobe measured an audio MXF with `pcm_s24le`, **48 kHz**, **6 channels**, generated as **technical silence only**; it is *not* an approved dialogue/music/soundtrack master.
- Running `dcpomatic2_verify_cli` against the actual resulting DCP validated CPL, picture hash/details, sound hash/metadata, PKL and ASSETMAP, finally reporting **`DCP verified OK.`**
- Repacked technical DCP and full SHA-256 package inventory for local download as `NVP_CINEMA01B_First_Real_DCP_Technical_20261103.zip`. This artifact exists in the working session but is **not** committed to the source repository.

## Important integration blocker: 16 → 24 frames

The NVP CINEMA-01B `audit_dcp_picture_essence` currently rejects every DCP whose total picture frame count differs from the source presentation frame count. That fail-closed behavior is correct as written: **this 24-frame package must not receive a source-identical FilmIndex receipt as a 16-frame take**.

The test proves the extra eight frames are black, but a transparent director-approved duration/padding contract and an independent **strict trailing-pad** validation rule must be introduced before allowing the 16 → 24 transformation into the indexed production pipeline. Alternatives include capturing an approved take of at least 24 source frames. Do not silently weaken frame count checks.

## What this does—and does not—close

**Closes for this narrow test:** creator-provided dependency bytes verified, real DCP CLI launch, real local JPEG2000/MXF and 48k/24-bit sound-track packaging, FFmpeg full decode, and independent DCP-o-matic technical verification.

**Does not close:** self-contained runtime (three host fallbacks), signed package trust provenance, exact FilmIndex source take/index replay, approved audio, independently calibrated XYZ conversion, true high-fidelity imagery, director-approved padding policy, independent cinema server/projection ingest, general release support. None of these are implied by DCP-o-matic's successful CLI exit or the externally verified 1-second test.

**Next action:** add `libsqlite3`, PulseAudio's matching common library and dash to the reproducible worker inputs; define/pin the exact source duration-to-DCP policy; run the adapter over the actual FilmIndex database with source-revision and DCP receipt reopen; then pursue calibrated color/audio and theater ingest.
