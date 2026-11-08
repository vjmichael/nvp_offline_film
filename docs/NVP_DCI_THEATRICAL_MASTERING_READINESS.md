# NVP — DCI-targeted theatrical finishing pipeline readiness and acceptance gates

**Reviewed:** 2026-11-08. **Status:** architecture READY TO TARGET, delivered DCI/SMPTE-compliant picture/sound/package NOT ACCEPTED.
**Reference baseline:** DCI Digital Cinema System Specification (DCSS) **v1.5.1**, approved 2026-10-20; DCI Compliance Test Plan (CTP) **v1.6.0**, approved 2026-10-20; applicable SMPTE DCP standards including **SMPTE RDD 52:2020 Bv2.1 Application Profile** for baseline interoperable packaging. The official DCI site has version/archive and addendum policies; recheck exact versions at a release freeze.

Primary references:
- https://www.dcimovies.com/ (DCSS 1.5.1 / CTP 1.6.0 October 20, 2026 announcements)
- https://www.dcimovies.com/dci-specification/
- https://www.dcimovies.com/compliance-test-plan/
- https://www.dcimovies.com/compliance-testing/
- https://www.isdcf.com/resources/documents/ (SMPTE RDD 52 Bv2.1)
- https://www.isdcf.com/registry/standard/ (SMPTE DCP distinction)

## Precise meaning of "DCI-ready"

The intended outcome for NVP is **a verified interoperable theatrical DCP authored from original scene, picture, editorial, sound and effect data**. DCI's formal CTP/listing primarily governs cinema exhibition equipment and licensed independent test organizations; don't advertise NVP as "DCI certified" or NVP's desktop viewer as a DCI-compliant media block/projector. Content masters and DCP packaging must conform to their relevant DCI, SMPTE, ISO/IEC and theater/venue constraints, then undergo independent validation and actual cinema ingest/replay.

NVP's existing original OpenUSD/FilmIndex/TemporalLedger, immutable Takes/edits, PCM source, scene-linear rendering paths and WO4/WO5 DCP/MXF/JPEG2000 work are suitable **architectural inputs** for a finishing pipeline. They do not by themselves establish full valid DCP delivery.

The latest WO6-07F preview is deliberately 640×360, 24fps-bounded, CPU scene-linear raster with source-level mono PCM16 and WebAudio; it is **NOT the final DCI imaging or mastered sound path**. WO5 installed Windows native full-playback smoke previously failed (30s bounded workload exceeded 180s; WebView2 visible playback exceeded 600s). Newer standalone code and queued runs do not erase those failures.

## Core principle: offline cinema master != real-time render

The **final** film can render offline at any speed. For a locked immutable source revision, each exact editorial frame must deterministically render at proper cinema output resolution, image encoding and color; then record hash/provenance and assemble into ordered reel/cinema packages. The renderer may take seconds or minutes per frame if its output is exact. **Actual installed editor playback** and a theater's **playback decoder/projector** have separate real-time/24fps acceptance. Do not require the Python 640×360 preview raster to meet 24fps before attempting a DCI-targeted offline finishing path. Nor infer successful DCP theatrical playback from an offline render.

The light FX system must be deterministic at every Film Time (including independent live oscillators once captured/baked); silver/gold passive bounce and colored strobes require a renderer with genuine light transport and managed scene-linear output. The old CPU raster's neutral SphereLight is not yet enough for theatrical PBR/GI light fidelity.

## Target profiles

**Baseline P0:** 2K **2048×1080 container, 24fps**, with properly chosen active area/aspect, graded source-managed reference image transformed to required **12-bit X'Y'Z'** theatrical picture, compliant **JPEG 2000** codestream/bitrate and SMPTE MXF picture track, separately mastered **24-bit linear PCM at 48kHz** with theater channel labeling/routing, matched reel boundaries and CPL/PKL/ASSETMAP metadata, stable source/reel hashes and validation of frame/time correspondence. Treat encryption/KDM and specific subtitle/accessibility features as separately chosen distribution conditions; don't assert every theatrical DCP must be encrypted.

**Extend later:** true 4K **4096×2160 container at 24fps**, optional 2K/48fps, optional other approved DCI addendum profiles such as HDR or direct-view where chosen and supported. A 640×360 or upscaled 2K preview is NOT native 4K source-render evidence.

**Interoperability baseline:** SMPTE DCP with Bv2.1/RDD 52 profile constraints where appropriate; validate resulting deliverable using an independent implementation, not only NVP self-tests. A general DCI format target and a Bv2.1 interoperability profile are related but not identical notions.

## Implementation / acceptance work orders

| Gate | Required implementation and independently observed evidence | Current status |
|---|---|---|
| **DCI-P0 Source freeze** | Complete original director-accepted cut, exact Film Time and SHA dependency closure for every scene, shot override, music/dialogue/FX, light timer and bounced material | Source architecture present; shot-local composed render, full soundtrack and light effect synchronization OPEN |
| **DCI-P1 2K offline raster** | Real frame-by-frame 2048×1080 scene-linear render from approved source including accurate USD/MaterialX, UsdLux timed lights and indirect gold/silver bounce, frame/hash/abort-resume receipts, no frame duplication or omissions; independent renderer comparison | OPEN; WO6-07F is CPU **640×360 uncalibrated preview** |
| **DCI-P2 Cinema color** | Tested OCIO/ACES-managed working space; reference output/view transforms, scene exposure/white balance, DCDM X'Y'Z' 12-bit quantization verification, gamut and highlight clipping/gradient/scientific color checks at output; multiple known color test images | OPEN; WO3 MaterialX/Hydra verification in stacked draft/CI |
| **DCI-P3 Cinema sound** | Multitrack authored sound mix at exact editorial time, channel map, headroom/loudness/peak QC, sample-accurate reel lengths, 24-bit 48k linear PCM master; optional 96k and immersive audio only with dedicated separate conformity gates | OPEN; WO6-07D/07F handles source PCM16 audition, not mastered PCM24 |
| **DCI-P4 DCP package** | Proper DCI JPEG2000 12-bit XYZ codestream (correct profile/rate), reel-contained MXF image and sound, SMPTE CPL/PKL/ASSETMAP, appropriate content naming, edit rate/durations/hash IDs and optional encryption/KDM if needed; no FFmpeg dependency required | Existing WO4/WO5 DCP/MXF tools under test; finished-package acceptance OPEN |
| **DCI-P5 Independent decode / ingest** | Reopen every emitted frame and sample in at least one independent decoder/tool, test first/last frame and every reel cut, check source-vs-decode checksum or defined image error, zero A/V discontinuities, validate against RDD 52 and adopted SMPTE specs, actual representative DCI cinema server and projector ingest/playback with a master/sound engineer | OPEN |
| **DCI-P6 Durable feature production** | Genuine 30-minute original creator-driven pilot from source lock through full rendered picture, sound master and a playable DCP; then feature (60–90min) and epic (~3h) memory, restart/partial-export recovery, artifact provenance and disk/heat/resource measurements | OPEN; earlier 30-minute original **source pilot** does not equal final finished-film screening |

NVP should add tests using known reference DCI frames, sample PCM/channels and third-party audits. A 30-second real 2K/24fps **offline export, package, decode and visible screening** is the first practical evidence gate; follow with an original 30-minute scene-level film. Do not require a real-time **render** benchmark to accept an offline final-picture exporter, but do require measured installable native playback/ingest for the viewer and actual theater.

## Existing work to preserve and not reinvent

- WO3 renderer/MaterialX native graph fidelity and color custody; NVP source color grade is not yet a DCI proof.
- WO4/WO5 source-first 2K/4K/JPEG2000, MXF, XYZ12 and PCM24 paths; verify all current versions and preserve original output hashes; some earlier CI runs passed standalone tests but installed throughput failed.
- WO6 film crew sources, creator OS approvals, first-party workers, durable recovery; model advice remains untrusted.
- WO6-07D native authored PCM cue/edit, 07E original source-time WAV, 07F rendered preview and WebAudio clock.
- V-LIGHT-FX independent monotonic clock/capture and reflective bounce fixtures; final frames evaluated at exact authored Film Time with suitable light-transport renderer.

## Bottom line decision

**YES: begin the DCI-targeted finishing pipeline now, in parallel with repairing installed 24fps preview.** Prioritize true deterministic **offline 2K/24fps scene-light-color render**, source+reel/time locked PCM24 mix, real SMPTE DCP and independent decode/ingest. Keep installed interactive WebView2 performance separate. **NO:** do not claim DCI certification or existing compliance, physically accurate silver/gold bounce or passed cinema QC until independently demonstrated on exact source.
