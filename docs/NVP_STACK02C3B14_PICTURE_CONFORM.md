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
