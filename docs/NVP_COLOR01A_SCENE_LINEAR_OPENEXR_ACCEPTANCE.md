# NVP-COLOR-01A — Native scene-linear OpenEXR sources

**Date:** November 3, 2026  
**Branch:** `nvp/color01a-native-scene-linear-exr-20261103`  
**State:** **NATIVE ACCEPTANCE PASSED** — GitHub Actions [run 41743018120](https://github.com/vjmichael/nvp_offline_film/actions/runs/41743018120), both Python regression and actual Blender/Cycles acceptance jobs green. This is a high-bit-depth source-frame technical gate, **not** colorimetric calibration or theatrical mastering.

## Source-to-presentation correctness

NVP's authoritative Digital Film World and immutable Digital Takes are unchanged. This gate adds a **new renderer-selected frame format**, rather than trying to create high-fidelity color by relabeling an already quantized video.

- The established **Workbench / PNG 8-bit** preview path remains available.
- Cycles PBR presentations may explicitly request `openexr_half_rgba_scene_linear`, which sets Blender to `OPEN_EXR`, `RGBA`, `16`-bit floating point, ZIP compression and Raw display view during the EXR export.
- Actual render outputs are validated by a bounded OpenEXR header reader: data window, exact RGBA channels, HALF pixel type and ZIP compression. Raw bytes are stored under FilmIndex SHA-256 in the originating project, linked to the immutable frozen take and approved camera/frame sequence.
- A new Studio must reopen the render receipt, source take, frame schedule, pixel contract and original EXR bytes. Existing PNG presentation history remains readable using a legacy default.
- The native acceptance fixture performs **full independent FFmpeg decoding of every selected EXR**. The EXR header by itself is not treated as proof of valid pixels.
- A separate small Cycles emissive color-reference scene deliberately renders RGB `[2.25, 0.123456, 0.01953125]` into HALF EXR. Independent FFmpeg raw float32 inspection rejects clipped, range-limited, or 8-bit-quantized results. This test is independent of the frozen production scene, so the test does not add unapproved patches to a director's film.
- The native fixture flips a byte of the indexed EXR image, demands rejection in a fresh Studio, restores the original bytes, reopens the source, and confirms that the original take SHA did not change.

## Truthfulness of video quality

An EXR file stores scene-linear floating-point values, but this **does not automatically calibrate color or produce an HDR movie**. A correct output-referred transfer/color conversion (e.g. an approved and version-pinned OCIO transform) is still missing. Consequently, `FullMotionPipeline` is guarded against presenting an EXR-to-ProRes or EXR-to-DNxHR conversion as a professional color master. An explicitly identified, uncalibrated H.264 review path may be used, but it is **not** an approved graded deliverable.

The demonstrated geometry remains proxy-quality. Half-float precision cannot manufacture actor geometry, lighting detail, dynamic range in the original artwork, or mastered audio.

## Acceptance conditions

1. The dedicated `color-contracts` CI job must pass pure tests, PNG legacy regressions, and frame-source contracts.
2. The native `native-cycles-exr` CI job must render actual frozen-take camera frames via Blender 5.2.3 Cycles as 16-bit-half RGBA EXRs.
3. FFmpeg must decode all stored EXR frames and the diagnostic full-float reference successfully.
4. The diagnostic must retain high-range scene-linear values (>1.9 red) and a green component distinguishable from nearest 8-bit discrete value.
5. A fresh FilmIndex reopen must reproduce all hashes, source take and rendered frame identities; a corrupted frame must be rejected.
6. NVP must not claim OCIO/ACES/XYZ or theatrical delivery certification solely from these results.

**Next:** NVP-COLOR-01B: explicit source/working/display color spaces, pinned OCIO config and measured EXR-to-ProRes/EXR-to-DCP transforms with independent pixel/colorbar acceptance. Then production-grade render materials/characters, approved audio and editorial mastering.

## Independently measured native acceptance — PASSED

Official Blender **5.2.3** was downloaded and SHA-256 checked in the CI job; a real NVP approved Digital Take was reopened after its live world had changed. Blender/Cycles rendered four selected frozen-camera frames as genuine **128×72 RGBA HALF (16-bit float), ZIP-compressed OpenEXR** files. The four frame SHA-256s were:

| Frozen camera frame | Indexed image SHA-256 |
| --- | --- |
| 1 | `ebcbc7d50aff02cf6f8a83cae077ae16041b22c4102e5461486663fba62759e4` |
| 30 | `642b57d9cf4c6d5c2d7f4aa5d19e525b5b72f470930c2c64e0b648f575ec6ee5` |
| 61 | `5256a8a836bf57ef090268e397c0f4dfa730023a69583f418bb9cd85181c6a8a` |
| 90 | `02677b04c202afcbf8f55dcbd6223fed101ced5b9de50c1baadbbb97177e3a6b` |

All four were independently decoded by FFmpeg, recorded as true EXR source bytes in the FilmIndex, and reopened by a newly constructed Studio. Deliberately corrupted EXR bytes were **rejected**; after restoring the bytes, the original presentation and frozen take reopened with unchanged identities.

The separate Cycles emission reference retained unclipped scene-linear values in its EXR image. Independent FFmpeg **native `gbrapf32le`** decoding measured:

- **Red: 2.25** (above normalized SDR 1.0)
- **Green: 0.370361328125** (retains sub-8-bit precision)
- **Blue: 0.05859375**

The diagnostic EXR SHA-256 was `873f219e1bfdb0831bd57d60ed232e014ac4e9dd1c3f98376ac5ba6258b601b1`. A second decoder (OpenCV) independently measured the same values during investigation.

Two failures were important and corrected before acceptance: Blender sets the legal OpenEXR `LONG_NAMES` version bit `0x400` (version word `0x402`), and FFmpeg converting from native RGBA float to RGB float clips HDR values above 1.0. The acceptance implementation now permits legal long names while refusing deep/tiled/multipart EXR, and samples native RGBA planes without HDR-clipping conversion.

**Actual successful output:** [CI workflow](https://github.com/vjmichael/nvp_offline_film/actions/runs/41743018120), artifact `nvp-color01a-native-exr-evidence`. The EXR frames and controlled HDR source are genuine rendered images, not a PNG repackaging. No ACES config, tone mapping, reference display calibration or verified EXR-to-ProRes transform has yet been implemented.
