# NVP STACK-02C3B12 — Portable editorial interchange and verified technical picture delivery

**NVP film engineering only. Lu↔DLC Workspace interface remains deferred until after Lu v1.0.**

## What changed

B11 established an immutable, indexed 120-frame 24fps, 16-bit SDR RGB review of the B9 genuine 32-bit OpenEXR captured take using official pinned ACES 2 SDR viewing. NVP B12 delivers an editor-readable, **portable** picture handoff: the shot order, source frame ranges, actual numbered review media, technical codec candidates and content-addressed source evidence. The original Digital Take, original scene-linear 32-bit EXRs, and independently indexed ACES 2 review are **never** overwritten.

### Official timeline interchange

- NVP uses the real Academy Software Foundation **OpenTimelineIO 0.18.1** `Timeline` / `Track` / `Clip` / `ImageSequenceReference` types and the **official** `otio_json` adapter. The generated `timeline.otio` is parsed independently by OpenTimelineIO before publication and after NVP restart; NVP does not implement a competing proprietary timeline format.
- Every original frozen camera shot becomes one native OTIO clip. Each clip is mapped to its exact original **[start_frame, stop_frame_exclusive)** interval, 24fps and a bounded `RationalTime` source duration. All clip durations sum to the original 120 frames (five seconds) with no duplicate, missing or overlapping frame.
- Each image reference points only to the package-relative `media/review_000001.png` ... `media/review_000120.png`, via `ImageSequenceReference` with 6-digit frame padding and `MissingFramePolicy.error`. A bare OTIO file **does not include actual picture media**; NVP packages the numbered media with it. Rewriting an OTIO media path to a different project or changing its frame count is rejected.
- The editor may import the `.otio` in software that supports OTIO image-sequence references. **Application-specific import success is not claimed yet.** Native EDL/FCP XML/AAF adapters (where supported) are separate optional interoperability gates; B12 does not fake an FCPXML or guarantee all NLEs understand OTIO.

### Portable picture delivery

- B12 independently reopens the *entire* B11 original SDR sequence and B9 source ancestry. It reproduces the 16-bit RGB files to a new `media/` package without color-converting or recompressing them. Every file is hashed against its FilmIndex `png16_sha256`, opened with FFmpeg and checked byte-for-byte against the original RGB48 readback SHA.
- Exact source frame hashes, frozen camera shot identifiers and output image hashes are in `package_manifest.json` and the new `nvp.presentation.b12.editorial_delivery.v1` FilmIndex presentation. Only after every original image and OTIO clip has been verified does NVP register the new presentation, with typed original Digital Take, B9 float EXR, and B11 SDR review revision-1 dependencies.
- The portable directory contains `timeline.otio`, `package_manifest.json`, and `media/review_*.png`. `FilmIndex` keeps a content-addressed copy of the OTIO and its references; a fresh NVP Studio can re-open the original take, image provenance, OTIO, and all packaged frame bytes.

### Professional technical MOV candidates (reusing existing code)

- Optional `prores_422_hq_mov` and `dnxhr_hqx_mov` are produced through **the existing `nvp_color_mastering` official ACES 2 Rec.1886 view, neutral grade, and FFmpeg codec functions**, not custom bitstream/color encoders. **Critical color boundary:** B11 portable review PNG values are display-encoded sRGB and therefore may *not* be copied into a MOV tagged Rec.709/Rec.1886. The MOV encoder instead reopens each original B9 **32-bit scene-linear FLOAT32 EXR**, applies the previously verified near-opaque antialiasing rule only to its derived CPU buffer, runs COLOR-01B2's real ACES 2 Rec.1886/Rec.709 SDR view to distinct RGB48 pixels, then encodes 10-bit 4:2:2 Rec.709/TV-range YUV. FFmpeg/FFprobe independently decode the finished movie, verifying true codec metadata, continuous 24fps frame count, legal sample range and bounded lossy difference from a fresh YUV reference produced by **replaying the original Float32-to-Rec.1886 grade after restart**. The portable sRGB PNGs and technical Rec.1886 MOVs are intentionally different display products derived from the same original frozen take.
- The B12 actual Linux CI proof targets **a real 120-frame 160×90 ProRes HQ technical candidate** and a portable 120-image OTIO package. Existing COLOR-01B2 tests independently cover real ProRes HQ/DNxHR HQX codec behavior on bounded 256×144 frames. DNxHR from the B12 source is supported as a selectable profile but not necessarily real-tested at every raster.
- B12 refuses MOV when the picture size exceeds the previously accepted COLOR-01B2 codec gateway (≤1024×576 pixels, even dimensions) rather than silently writing an unaudited Full HD movie. Higher-resolution professional mastering remains another performance and codec acceptance gate.
- **There is no audio track**, picture lock, editorial approval, calibrated monitor, final color grade or theatrical DCP in these candidates. They are technical picture handoffs for editing, not finished film masters or sound-mixed screenings.

### Production-native permission and resource safety

1. A trusted NVP native creator-presence verifier (supplied by the installed NVP host, **not** an HTTP query or model text) approves the exact source take/review SHA, camera cuts, intended media/codec profiles, 24fps/raster, original ACES 2 OCIO profile, disk headroom, RAM budget and honest audio/mastering flags. CI uses a controlled fixture event only; installed desktop approval is an open gate.
2. `NativeB12DeliveryHost` binds the grant to a SHA-sealed JSON plan plus pinned local Python executable and exporter source. `ApprovedTaskBindings` provides durable queuing, source-sensitive reauthorization, measured RAM admission via TaskLedger, and OS-contained native execution. A queued task may be revoked by a *new* authenticated creator action.
3. The isolated worker stages a brand-new private handoff directory with exclusive files; existing outputs and FilmIndex presentation identities are never overwritten. The OS job ends before the host independently reopens the `.otio`, all media images and full decoded technical MOV evidence. Errors or source drift prevent success. If kernel process cleanup is uncertain, the ACTIVE RAM reservation remains for explicit reconciliation.
4. A newly constructed `DigitalCapture(Studio(...))` and native B12 host independently verify the archived handoff after restart. No 120-frame pile of RGBA image data stays resident in NVP RAM/VRAM after completion. Temporary uncompressed RGB48/YUV intermediates are deleted after audited encoding; durable media and FilmIndex manifests remain on disk.

## CI acceptance

`.github/workflows/nvp-stack02c3b12-editorial-delivery.yml` runs Windows and Linux actual OTIO 0.18.1 clip/time math, path and metadata tampering, native consent/revocation/expiry, low-RAM refusal and OS-launch ambiguity; it repeats B11/FilmIndex source regressions. React build/tests run without granting browser-side native authority. Real Linux Blender + FFmpeg/FFprobe + OCIO + OpenEXR reproduces the entire B9/B11 chain, then a separately resource-admitted native B12 worker produces a **120-image portable package, actual OpenTimelineIO timeline and independently audited ProRes HQ**, reopens everything and checks RAM reconciliation.

**Truth boundary:** The availability of a generated `.otio`, a decoded ProRes sample and format-compliant PNGs is an **interoperable technical candidate**. It is not yet a verified user experience in DaVinci Resolve, Adobe Premiere, Final Cut Pro, Avid, Kdenlive or an installed NVP desktop application. NLE-specific round-trip import/export, editable audio tracks, mixed audio, grading approval, editorial picture lock, real Full HD/DCP delivery and 4K GPU admission remain explicit later gates.

## Established tool references

- Official [OpenTimelineIO editorial format / API](https://opentimelineio.readthedocs.io/en/latest/), [ImageSequenceReference](https://opentimelineio.readthedocs.io/en/latest/api/python/opentimelineio.schema.html), official Python package pinned to [OpenTimelineIO 0.18.1](https://pypi.org/project/OpenTimelineIO/0.18.1/).
- Existing NVP `backend/nvp_color_ocio.py` and `backend/nvp_color_mastering.py` remain the approved reuse targets for OCIO/SDR viewing and ProRes/DNxHR technical encoding; no custom equivalent codecs or OTIO schema implemention are being invented.

**NVP B12 is stacked on B11 (draft PR). Final acceptance requires current-HEAD CI success.**
