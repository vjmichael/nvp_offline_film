# NVP B14 — First picture-conform implementation

## Relationship to B13
This branch is stacked on B13, not merged into main. B13 imports a creator's externally edited OpenTimelineIO cuts as immutable FilmIndex edit revisions. B14 takes one **explicit** edit revision and produces a new ordered sequence of **real original 16-bit RGB SDR review PNG bytes**, copied from FilmIndex by SHA-256. Trims, repeats and reorders become actual visible frame order. It never mutates the source Digital Take, original B12 portable package or previous edit versions.

## Implemented in this first increment
- `backend/nvp_b14_picture_conform.py`: worker-side conform and independent reopen/verification.
- Conform checks the B13 edit revision and B12 immutable original package, verifies every original source-frame identity, shot and PNG/RGB48/FLOAT32 SHA, and refuses invalid or missing 16-bit RGB images.
- Writes an isolated, absent output directory containing `media/edit_000001.png`, etc., and a deterministic `conform_manifest.json`.
- Records a new FilmIndex `presentation` revision with edges to **the exact B13 edit revision**, original B12 delivery and original Digital Take. Reopens source/edit/conform and independently verifies numbered frame bytes and manifest.
- `tests/test_b14_picture_conform.py`: rejects forged source hashes/shots, out-of-range and noncontiguous edits, unexpected timebase, existing or symlinked paths.

## Strict limitations and remaining acceptance gates
This is a **worker-side implementation**, not yet an installed-app action. The native host must authorize creator intent, exact B13 edit SHA and output path; enforce RAM/disk budget and OS process containment; supervise cancellation and staging cleanup. Do not expose this module to HTTP/browser/model calls as a substitute for native consent.

This output is **SDR 16-bit sRGB review imagery**. It is **NOT** a scene-linear EXR sequence, does not render Rec.1886/BT.709 technical ProRes/DNxHR, and does not claim to be a calibrated final master. The B12 video encoder intentionally uses a separate source-linear grade-to-master path, rather than sending sRGB PNG code values to a Rec.709-labelled encoder. A future B14 increment must conform **original scene-linear sources** in edited order through existing grade/encode and independently decoded video-audit tooling; no shortcut color conversion.

Tests and real acceptance still needed:
1. Green Windows/Linux native unit jobs on exact B14 HEAD, including B13 regressions.
2. Genuine 120-frame Blender B12 → externally edited OTIO B13 → B14 actual source-bound SDR16 frame conform → reopen FilmIndex and verify every output PNG.
3. Native authorized host/isolated worker, RAM/disk reservation and cancellation/cleanup.
4. True edited high-bit-depth technical MOV from source-linear color mastering, independently decoded/audited.
5. Audio alignment, picture-lock approval, final master and DCP are separate gates.

**Status: B14 incremental source code and tests committed; no real B14 pipeline/installed app certification claimed.**

## Subsequent B14 native implementation (Nov 4, 2026)

Added `tools/nvp_b14_conform_worker.py` and `backend/nvp_b14_native_conform.py`. B14 now has an explicit creator-policy-checked staging host, an immutable bound spec and exact edit SHA/revision/output destination, queued native resource admission, a contained worker launched from pinned executable and worker script, live RAM/VRAM critical-pressure watchdog, independent output verification, durable receipt and restart verification. The real Blender B13→B14 acceptance runner now submits both imported edit revisions to this native host, injects memory-based queue refusal, then allows actual OS-contained worker execution and audits the two resulting SDR16 sequences.

**Known limits:** A fixture-supplied native creator policy is not the installed creator UI; OS resource admission uses a controlled test sampler for reproducible refusal/admission, and native worker process memory is OS-limited. There is no completed edited scene-linear technical MOV, disk-capacity reservation, full crash-recovery reconcile, interactive cancellation, audio or film master. B14 new-head CI is required before native acceptance may be marked passed.

**Verified previous checkpoint:** Workflow run `41869316782` was green on Windows/Linux and actual Blender integration before these native-host changes. That prior green run does not certify this newer revision.

## B14 edited professional technical MOV candidate increment

Added `backend/nvp_b14_edited_movie.py`: derives the exact B13 edited frame order from its verified B14 SDR16 conform, reopens **original scene-linear FLOAT32 OpenEXR** media, applies the established pinned OCIO ACES2 Rec.1886/Rec.709 display transform, encodes ProRes 422 HQ (or supported DNxHR HQX), independently decodes and compares to a matching 10-bit YUV reference, records the real indexed QuickTime media and exact edit/conform/take revision dependency chain, and verifies that movie on a fresh FilmIndex instance. It intentionally **does not** feed sRGB PNG review pixels to the Rec.709 mastering encoder. The genuine Blender acceptance runner now calls this for the first edited revision after both native picture conforms.

The initial movie gateway is still bounded to 480 frames and a 1 GiB temporary RGB48 upper bound; it processes frame-by-frame when preparing the original scene-linear source and uses on-disk raw intermediates. Production-length streaming encoders, native approved movie-mastering host, audio, picture lock and final professional delivery remain separate tasks. No claim of a completed 30–60-second short film. **Fresh exact-HEAD CI remains required before acceptance.**
