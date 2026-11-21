# NVP-CINEMA-01B — Independent JPEG 2000 / MXF picture evidence

**Date:** November 3, 2026  
**State:** Implementation and mocked regression added; real DCP source conversion remains **BLOCKED** by verified DCP-o-matic CLI package availability in GitHub Actions.  
**Parent gate:** [PRO-02](NVP_PRO02_CINEMA_DCP_DNXHR.md)  
**Authority:** [NVP Master Design](NVP_MASTER_DESIGN.md), [Data-First Filmmaking ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md).

## Problem and change

Previous PRO-02 technical packaging checked the existence of ASSETMAP, PKL, CPL and MXF, hashed their bytes, and called `dcpomatic2_verify_cli`. This was not sufficient independent **picture essence** evidence: arbitrary bytes named `.mxf` could satisfy the NVP structural audit. No valid DCP was claimed.

`backend/nvp_cinema_essence.py` now adds a separate, bounded read-only movie essence audit using FFprobe plus full FFmpeg decode of actual unencrypted MXF picture reels. The `CinemaDCP.package_technical_test` path invokes it **after structural inspection and before indexing any published technical DCP**.

The independent check rejects:

- missing or symlinked MXF content; no video reel; multiple picture streams in a reel; more than 16 picture reels;
- picture essence codec other than `jpeg2000`;
- any raster or decoded frame rate that differs from the selected SMPTE 2K Flat (1998×1080) / Scope (2048×858) 24fps technical profile;
- missing counted decoded frames; extra/short reels relative to the immutable source;
- any full FFmpeg decode failure, subprocess nonzero exit or timeout;
- missing trusted `ffprobe` / `ffmpeg` tools.

The evidence receipt records exact per-reel decoded frame counts, raster and rate. The immutable `FilmIndex` DCP presentation stores this receipt, and project reopen additionally demands that the receipt exist and that every package file still has the original SHA-256. Source motion/take hashes remain independently verified and unchanged.

**Unit evidence only:** `tests/test_cinema_essence.py` mocks the external programs to test rejection paths and receipt logic. `tests/test_cinema_dcp.py` also makes a fake packager create plausible XML/MXF names and proves the DCP is not indexed when picture decoding rejects it. These tests do **not** prove that an actual DCP, JPEG2000 codestream or projector-compatible package was created.

## Native test still required

Dedicated native acceptance is in `.github/workflows/nvp-cinema-dcp-technical.yml`, using the actual frozen NVP source from the accepted ProRes run. It needs a **version- and hash-verified** DCP-o-matic 2.18.51 CLI, the native `dcpomatic2_create`, `dcpomatic2_cli` and `dcpomatic2_verify_cli`, then FFprobe/FFmpeg decode. The vendor Ubuntu CLI package download previously returned HTTP 403; no unsigned/unverified mirror should replace that dependency silently. Do not mark this gate closed until the package is obtained and the actual full pipeline passes.

Further acceptance: independent CPL/PKL/ASSETMAP cross-reference and digest validation, sound essence/48kHz/24-bit/channel mapping, correct measured XYZ/transfer color conversion, independent cinema server/player ingest. Technical silent picture tests require explicit creator approval. Low-resolution 8-bit proxy inputs remain **not theatrical color masters**, even if the DCP JPEG2000 picture technically decodes.

## Relevant external references

- [DCP-o-matic CLI documentation](https://dcpomatic.com/manual/html/ch15.html)
- [DCP-o-matic CLI encoding options](https://dcpomatic.com/manual/html/ch15s02.html)
- [DCP-o-matic 2.18.51 stable download](https://dcpomatic.com/download)
- [Digital Cinema Initiatives specifications](https://www.dcimovies.com/dci-specification/)

This is NVP's film-specific production code. **No Lu repository changes.**
