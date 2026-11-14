# NVP-CINEMA-01C — Authoritative source duration and real FilmIndex DCP acceptance

**Date:** November 3, 2026  
**Engineering state:** **Native Linux technical-source gate PASSED locally.** Draft integration PR; not a theatrical master, not a shipped film exporter.  
**Governing design:** [Master Design](NVP_MASTER_DESIGN.md) · [Data-First Film](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md) · [CINEMA-01B first real DCP](NVP_CINEMA01B_FIRST_NATIVE_DCP_ACCEPTANCE_20261103.md).

## Why this gate was needed

The original approved 16-frame/24fps ProRes source from NVP's real FilmIndex was converted by DCP-o-matic to a one-second, 24-frame SMPTE DCP. Blindly declaring this source-identical would overwrite the director's intended duration. CINEMA-01B correctly refused it.

CINEMA-01C makes source-to-output duration a **typed, creator-authorized transformation**, and independently checks all output picture frames. The default `exact_source_frames` policy fails early if a subsecond source is likely to be extended. The **only** short-take exception is `explicit_one_second_black_tail`; it requires a separate creator approval in addition to explicit silent-film technical-test approval. It is available only for **1–23 frames at 24fps**, and its output is **exactly 24 frames**, not an arbitrary duration. For source films of 24–240 frames, only exact output is accepted in this limited adapter.

The output ledger records `source_frames`, `dcp_frames`, `black_tail_frames`, sample-accurate 48kHz timebase, `source_video_sha256`, `source_motion_sha256`, `source_take_id`, `source_take_sha256`, direct FilmIndex edges and the separate creator approvals. It never changes the original Digital Take or source video.

## Technical implementation

- `backend/nvp_cinema_duration.py`: pure bounded duration-policy builder plus strict independent receipt validation.
- `backend/nvp_cinema_essence.py`: FFprobe count, codec, dimensions, fps; full FFmpeg JPEG 2000 decode; then a **second** full-resolution RGB24 decode of every extra frame. Requires exactly all-zero RGB bytes and the correct byte count, and SHA-256-addresses the result.
- `backend/nvp_cinema_dcp.py`: DCP presentation v2, default strict preflight, independent source MOV full decode, opt-in silent/padding approvals, genuine DCP-o-matic conversion, structural SHA audit, essential-independent picture proof, independent DCP-o-matic verification, only then an immutable FilmIndex registration. The registered DCP now depends **directly on both** the motion presentation and its frozen Digital Take. Reopen independently checks stored evidence, FilmIndex/asset hashes and source-take identity; `check_decode=True` repeats the physical picture evidence and source decode.
- `tools/nvp_pro02_dcp_fixture.py`: native cinema acceptance on previously frozen `pipe01b/film.sqlite3` and real ProRes/Blender media. A new `Studio` is used after packaging.
- `tests/test_cinema_duration.py`, `test_cinema_dcp.py`, `test_cinema_essence.py`: strict negative tests for unknown formats, forged approval, forged frame counts/samples, nonzero black pixels, missing/extra output, corrupted video, incorrect codec/raster/fps, and misleading successful-looking verifier output.

**Classification matters:** a DCP-o-matic `-c FTR` package of this one-second test failed Bv2.1 because it lacks Feature first-credits markers, even though the CLI printed a nominal success line. The technical-only packager now sets `-c TST`. Regression tests prevent returning to `FTR`; the verifier rejects any Bv2.1 errors.

## Genuine native acceptance with independent restart — PASSED

**Frozen creator source:** The original real NVP native acceptance artifact `nvp-real-blender-acceptance` from GitHub Actions [run 41700029191](https://github.com/vjmichael/nvp_offline_film/actions/runs/41700029191), artifact 13262603085, was downloaded and extracted. The genuine `pipe01b/film.sqlite3` plus its blob store were reopened through the current NVP `Studio`, `FilmIndex` and `FullMotionPipeline`, including independent FFmpeg video decode. The immutable source records' on-disk SHA-256s matched their database revision hashes.

| Source/record | Measured value |
| --- | --- |
| Frozen take ID | `take_full_motion` |
| Frozen take revision SHA-256 | `ecd404742204e6e7a1d7de941dc5d2606f5406357cf0b06f3961df0b31eb4157` |
| Approved ProRes presentation ID | `motion_prores_hq` |
| ProRes presentation revision SHA-256 | `ad4ea8312de09fc3c0bd9610aef3de7515b0f3ca7c1fbac6b4adb29877a66c7a` |
| Original immutable ProRes movie SHA-256 | `f8eab0440a5a79aeea830e273d735d4e5c975927afc0355647599cf331603216` |
| Original movie | Real ProRes 422 HQ MOV, 16 frames, 24fps |
| Exact output request | **Blocked** by short-take duration policy before calling DCP tools |
| Explicit technical request | 16-to-24, **eight padded frames**, creator-approved |
| Source 48kHz samples | 32,000 |
| Output 48kHz samples | 48,000 |
| Full-resolution padded decode | **51,788,160 RGB24 bytes**, all precisely zero |
| Black-tail SHA-256 | `193ad75f9256358c540b337bca5fbbb5ef8599ef558c704eeceb5de7e74da2a6` |
| Output | Actual unencrypted SMPTE 2K Flat, 24fps, 1998×1080 JPEG2000 MXF |
| Technical content type | `TST`, **not** `FTR` |
| Independent DCP verifier | **`DCP verified OK.`** with no Bv2.1 errors |
| FilmIndex registered DCP ID | `dcp_cinema01c_tst_verified`, revision 1 |
| Indexed DCP receipt SHA-256 | `a0e29c4868b727f3b88caf3c028894567e8ccbd6870fac3f4f8440f767d48196` |
| New Studio/FilmIndex independent reopen | **PASSED**, including `check_decode=True` source and DCP full decode |
| `screening_ready` | **false** — technical output only |

The executed DCP runtime used previously documented staged Ubuntu 26.10 libraries and DCP-o-matic 2.18.51 + dcpverify 1.10.64 in a private Linux namespace/chroot. Neither privileged DCP disk-writer `postinst` nor a system glibc replacement was run. The runtime still uses a few enumerated host fallbacks and is **not a portable production installer**.

## Live adversarial native results — 4/4 refusal and clean recovery

After the DCP receipt was committed to the real local FilmIndex database, the following were actually attempted:

1. Flip one byte of the indexed JPEG2000 picture MXF → **reopen rejects changed package SHA**. Restore original bytes; hash matches again.
2. Flip one byte of the original indexed ProRes source MOV → **reopen rejects immutable source-media SHA failure**. Restore original bytes.
3. Attempt to reopen the DCP under a different project ID → **project isolation rejects**.
4. Attempt technical DCP packaging with silent-test approval but **without** the independent duration-padding approval → **rejects before output directory/tool execution**.

After restoration, a new `Studio` once again reopened and independently decoded the original registered cinema package. Its two direct FilmIndex dependencies were exactly `take_full_motion` (source_take) and `motion_prores_hq` (presentation). No acceptance or source hash changed.

## CI and limitations

The targeted duration, essence and DCP tests passed in GitHub Actions [run 41738484766](https://github.com/vjmichael/nvp_offline_film/actions/runs/41738484766), including **9 duration tests, 6 original essence tests and 13 cinema adapter tests (28 total)**. The exact source tree was also recovered as a SHA-verified CI artifact and tested locally. The broader native Blender/React production workflow is enabled on this development branch; an attempted complete local unittest run exceeded the execution limit and is **not** counted as passed.

This passes **CINEMA-01C source-bound technical conversion and restart** in the observed Linux development environment only. It does **not** prove commercial 12-bit color fidelity from 8-bit proxy source, approved dialogue/music and surround mix, cinema-server ingestion, Bv2.1 universal compatibility, completed editorial mastering, portable path remapping, cancellable hardened long-running job supervision, or independent package publisher identity. DCP distribution outside a technical acceptance context remains restricted.

**Next film-production priorities:** a production-quality color-managed float/OpenEXR pipeline (NVP-COLOR-01); director-approved 48kHz/24-bit audio stems and mix (NVP-AUDIO-01); source-aware editorial and selective regeneration (NVP-EDIT-01). Keep source and take revision IDs authoritative.
