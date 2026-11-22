# NVP-PRO-02 — Professional Formats and Cinema DCP

**Date:** November 3, 2026  
**Status:** DNxHR HQX editorial export implemented, native regression underway. DCP preflight/guarded adapter implemented, but **a real DCP has not yet passed native acceptance**: DCP-o-matic CLI package download returned HTTP 403 in GitHub Actions.  
**Governing design:** [Data-First Filmmaking](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md) and [Master Design](NVP_MASTER_DESIGN.md).

## Professional output choices

| Filmmaker's purpose | Output | Current status |
| --- | --- | --- |
| Fast review and public online video | H.264 MP4 (8-bit 4:2:0) | Existing, native verified |
| Professional edit interchange | Apple ProRes 422 HQ MOV (10-bit 4:2:2, \`apch\`) | Existing, native verified |
| Avid and other professional editing | **DNxHR HQX MOV** (10-bit 4:2:2, FFmpeg \`dnxhd\` encoder, profile \`DNXHR HQX\`, tag \`AVdh\`) | **New implementation; native test added** |
| Festival/theatrical delivery | **SMPTE Digital Cinema Package (DCP)**, not one MOV/MP4 | Cinema adapter and preflight added, **real acceptance blocked by vendor tooling** |
| Color/VFX interchange | OpenEXR multi-layer scene-linear sequences, TIFF/DPX | Future gates |
| With alpha / advanced post-production | ProRes 4444 and equivalents | Future gates |
| Editorial exchange / audio | OTIO/AAF/FCPXML, 48kHz 24-bit PCM/BWF, approved stems | Future gates |

The same immutable approved Digital Take may produce several presentations and several codecs from **the same exact stored frame hashes**, without reconstructing the 3D performance. The source-backed pipeline retains take, engine, image, codec and resulting media SHA provenance.

DNxHR HQX input must be at least **256×120 pixels** for the FFmpeg encoder. The native fixture now uses 256×144 for the Cycles source so ProRes and DNxHR share identical frames. FFprobe must verify actual codec name, \`DNXHR HQX\` profile, \`AVdh\` tag, 10-bit 4:2:2 decoded image format, frame count and FPS. A 10-bit output wrapper does **not** create genuinely high dynamic range out of 8-bit PNG source pixels.

## Cinema DCP architecture

A theater DCP contains JPEG 2000 picture essence, MXF tracks, composition playlists (CPL), packing lists (PKL), asset maps and strict cinema picture/sound requirements. It is **not** an MP4 or ProRes MOV with a new extension.

The new \`backend/nvp_cinema_dcp.py\` contains:
- \`CinemaDCP.preflight\`: checks an independently reopened frozen NVP motion presentation, source SHA, requested SMPTE 2K Flat (1998×1080) or Scope (2048×858) at 24fps, sound status, resolution and quality warnings
- **Fail-closed sound policy:** a filmmaker must have director-approved real soundtrack material; current NVP only has dialogue timecode, not generated/approved waveforms. For non-exhibition technical testing an explicit **silent-picture** acknowledgment is required
- \`package_technical_test\`: invokes trusted installed DCP-o-matic \`dcpomatic2_create\`, \`dcpomatic2_cli\` and **independent verifier** (rather than reimplementing MXF/J2K); no remote encoding
- \`inspect_dcp_folder\`: refuses missing XML AssetMap/PKL/CPL, MXF, malformed/empty assets, symlinks, abnormal asset counts and changed SHA content
- \`reopen\`: checks exact immutable source reference, DCP folder path and all media hashes; **never labels the technical-test DCP as screening-ready**

The adapter currently requires the DCP-o-matic CLI as a separately installed backend, with a future single-installer distribution to avoid making users install multiple tools.

**Primary references:** [DCP-o-matic CLI documentation](https://dcpomatic.com/manual/html/ch15.html), [DCP-o-matic verifier](https://dcpomatic.com/manual/html/), [Library of Congress moving-picture formats](https://www.loc.gov/preservation/resources/rfs/moving.html), and [Digital Cinema Initiatives specifications](https://www.dcimovies.com/dci-specification/).

## Real acceptance and blocker

- Cross-platform Linux/Windows Python, React and Blender regression: [NVP PRO-02 main workflow](https://github.com/vjmichael/nvp_offline_film/actions/runs/41709815109). DNxHR HQX now has a real encode/decode fixture and adversarial codec tests.
- Dedicated real cinema attempt: [DCP test workflow](https://github.com/vjmichael/nvp_offline_film/actions/runs/41709815064) uses the actual frozen NVP ProRes source from run 41700029191, not fabricated movie bytes. The runner received **HTTP 403** when downloading the official DCP-o-matic 2.18.51 Ubuntu 24.04 CLI package. **It did not install the tools, construct a DCP or pass native cinema tests.**
- Therefore the DCP gate is **blocked by unavailable vendor CLI bytes**, not accepted. Keep the dedicated test manually triggerable until a trusted binary archive is available, rather than rerunning a known blocked download on every unrelated commit.

**DCP completion will require:** a reproducibly obtained, version/hash-verified CLI and verifier; actual creator-owned NVP movie conversion to 2K/24fps DCP picture/audio; independently verified JPEG2000/MXF/CPL/PKL/ASSETMAP and SMPTE constraints; correct color transformation; genuine approved audio or explicitly permitted intentional silence; successful package reopen; and a real cinema server or vetted DCP playback ingest check. A successful command exit or XML structural scan alone is **not a certification**.

## Next roadmap

1. **NVP-PRO-02A:** close native DNxHR HQX acceptance (including Windows regression); keep the same indexed source-frame reuse contract.
2. **NVP-CINEMA-01B:** obtain trusted DCP-o-matic binaries, run native DCP test from saved NVP ProRes take, and independently verify exact DCP picture/sound package.
3. **NVP-COLOR-01:** actual scene-linear OpenEXR/OCIO render passes, calibrated transforms and color/bit-depth measurement before calling a ProRes/DCP output a professional color master.
4. **NVP-AUDIO-01:** real audio stem ingestion/generation and 48kHz/24-bit timing/mix approval.
5. **NVP-EDIT-01 / MASTER-01:** the creator's source-aware editing and final cinema deliverables remain the highest product-value goal.

**Product principle:** give solo filmmakers **format choice and eventually theatrical reach**, without compromising source truth, independent verification or creative control.
