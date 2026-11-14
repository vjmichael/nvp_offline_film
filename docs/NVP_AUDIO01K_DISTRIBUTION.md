# AUDIO-01K — Final Film Distribution, Mezzanine Custody and DCP Readiness

## Implemented development candidate

AUDIO-01K.1 packages the **native-host-verified AUDIO-01J final ProRes+
PCM24 MOV** as a lossless, immutable mezzanine. It copies the exact approved
MOV bytes, without hidden re-encoding, into a new directory:

- `feature_master.mov` — exact source-byte match, checked against AUDIO-01J
  FilmIndex and trusted native AV publication
- `manifest.json` — canonical and versioned source, profile, media SHA,
  picture/audio clock and approval provenance
- `SHA256SUMS` — deterministic content checksum for transfer verification

The only admitted delivery profile is
`mezzanine_prores_pcm24_mov_v1`. This is a professional intermediate
**distribution master**, not a theatrical DCP or IMF package.

`backend/nvp_audio01k_distribution.py` performs bounded absent-only
publication with source and destination hashes, fsync of individual files,
and same-filesystem directory promotion, then indexes a new immutable
FilmIndex revision that depends on the originally approved AUDIO-01J master.

`backend/nvp_audio01k_native_host.py` is the trusted entrypoint. The host:
- Rechecks `NativeAudio01JHost.verify_published`, which requires exact
  native-worker custody, source hashes, creator event, independently decoded
  picture/sound and the currently approved AUDIO-01I audio master.
- Requires a new explicit creator policy approval for the exact project,
  source SHA, mezzanine profile, destination and distribution ID.
- Consumes the creator event exactly once in durable SQLite BEFORE any
  output bytes are written; an interrupted event cannot be replayed.
- Registers `PUBLISHED` only after FilmIndex and filesystem publication.
  `verify` refuses an indexed file with merely RESERVED creator state.

The distribution copy runs in the trusted host, not a separate uncontained
FFmpeg subprocess. **It is not yet a resource-supervised/OS-contained copy
worker**; bounded native-copy authorization, filesystem races and large-file
progress/cancellation remain production hardening gates.

## AUDIO-01K.2 — DCP readiness without misrepresentation

`backend/nvp_audio01k_dcp_preflight.py` always reports `NOT_READY` for
the MOV mezzanine. It identifies missing cinema-specific independently
validated components, including JPEG 2000 XYZ picture in MXF, cinema sound
assets, CPL, PKL, ASSETMAP, and complete asset-hash and metadata QC.

This is an honest readiness gate, **not** an implemented DCP packager.
No `dcp_delivered=True` flag is issued, and stereo PCM24 MOV is never
misrepresented as a DCP.

## Verification committed to the branch

- `tests/test_audio01k_distribution.py`: immutable source copy, checksum
  verification, creator-event replay denial, source revocation, tamper and
  interrupted staging refusal. These are focused mocked-AV-provenance tests.
- `tests/test_audio01k_native_e2e.py`: real ProRes/PCM24 integrated
  audiovisual pipeline through approved AUDIO-01J master and AUDIO-01K
  distribution. The synthetic picture fixture substitutes only the full
  upstream B14 scene-linear conform audit, as documented in AUDIO-01J.
- `tests/test_audio01k_distribution_crash_matrix.py`: eight abrupt
  `os._exit(98)` publication boundaries using **real SQLite, FilmIndex,
  and filesystem**. Its upstream native AV approval is deliberately
  stubbed; the end-to-end test independently exercises native AV custody.
- `tests/test_audio01k_fault_coverage.py`: verifies all eight crash points
  exist in the native distribution code exactly once.
- `.github/workflows/nvp-audio01k-distribution.yml`: required real FFmpeg,
  Windows 2025 and Ubuntu 24.04, Python 3.11 and 3.13 matrix.

## Explicit outstanding acceptance

- The code and tests are **committed**, but exact-head native Windows/Linux
  CI test results have not been confirmed. No production PASS is claimed.
- The trusted-host copy must still become a durable, cancelable, contained
  native worker for long features, rather than blocking the host.
- Full power-loss persistence, ancestor directory replacement races,
  filename/handle custody, crash-safe resumed transfer and resource
  accounting need independent validation.
- DCP production requires an actual cinema-picture/audio MXF encoder and
  interoperable CPL/PKL/ASSETMAP authoring plus independent validator.
- Native NVP creator UI-origin authorization and full unmocked B14 source
  replay remain open. Linux delegated cgroup-v2 remains deferred.

The next development gate after the mezzanine stage is **AUDIO-01K.3,
actual cinema-DCP asset generation**, starting with a reference-backed,
non-certifying DCP candidate and independent conformance tests rather than
declaring generic MP4/MOV cinema-ready.
