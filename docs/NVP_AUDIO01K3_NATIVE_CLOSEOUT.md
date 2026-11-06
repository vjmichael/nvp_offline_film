# AUDIO-01K.3 — Native Execution / Production Closeout Record

**Status (2026-11-04): NOT CLOSED — real cinema encode/QC evidence still pending.**

This is a verification record, not a claim that an existing encoder binary has
produced a successful SMPTE DCP.

## Current code and verification

- Real DCP-o-matic CLI commands have been checked against the maintainer's
  published command-line manual:
  https://dcpomatic.com/manual/html/ch15.html
  https://dcpomatic.com/manual/html/ch15s02.html
- Independent DcpDoctor v1.3.2 strict SMPTE validation and no-skip/deep
  MXF/J2K behavior are grounded in upstream documentation:
  https://github.com/PostPerfection/dcpdoctor
- Production DCP-o-matic release is currently 2.18.51:
  https://dcpomatic.com/download
- `backend/nvp_audio01k3_dcp.py`, `backend/nvp_audio01k3_native_host.py`
  and `tools/nvp_audio01k3_dcp_worker.py` implement an OS-contained
  candidate workflow with native authority, SHA-bound executable paths,
  source-bound CPL timing, strict independent DcpDoctor QC, stopped-worker
  reconciliation and explicit **dcp_delivered=False**.
- The real native test `tests/test_audio01k3_native_dcp.py` **fails**
  on missing native binaries instead of using the old silent skip.
- A successful test can preserve actual cinema MXF/J2K, XML and complete
  separate DcpDoctor QC stdout/stderr in a GitHub Actions artifact before
  injecting the deliberately corrupted-MXF negative case.
- `tests/test_audio01k3_dcp_contract.py` includes malformed package,
  invalid asset map, source-clock, validator failure and skipped-check
  rejection tests.

## Native machine provisioning

**Ubuntu 24.04:** `.github/workflows/nvp-audio01k3-linux-real.yml`
downloads the official release's Ubuntu CLI .deb and GitHub's DcpDoctor
v1.3.2 Linux CLI release archive, installs FFmpeg, xmllint and NVP Python
dependencies, checks versions, executes the real test, and retains artifacts.
It runs on the development branch and on draft PRs.

**Windows 2025:** `.github/workflows/nvp-audio01k3-windows-real.yml`
downloads DCP-o-matic's Windows installer, rejects non-PE files, requires
a valid Authenticode signature, installs via the documented NSIS silent switch,
and provisions DcpDoctor v1.3.2, FFmpeg, libxml2 and pywin32. It checks exact
versions and must run actual native worker/Job Object tests. This installer
and dependency path is experimental until its native job log proves it works.

Both workflows fail closed on missing dependencies. Official version
selection alone is not a supply-chain content hash pin: before final installer
bundling, record and independently approve known-good SHA-256 hashes of the
native distribution binaries, and verify distribution license obligations.

## Blocking acceptance gates — ALL must pass

- [ ] **Ubuntu real native encode:** execute exact-head native tests, prove
      the DCP-o-matic 2K SMPTE generator produced actual valid J2K/MXF files
      and real CPL/PKL/ASSETMAP/VOLINDEX records.
- [ ] **Independent strict validator:** DcpDoctor returns success and
      non-skipped deep MXF/J2K/asset checksum evidence; full QC logs and
      output SHA are retained and verified against the emitted DCP.
- [ ] **Source timing/color/sound:** compare approved source frame count to
      CPL video and audio reel timing, and pass downstream cinema-calibrated
      XYZ image review and audio-channel routing review.
- [ ] **Windows native execution:** real Windows Job Object process
      containment and DCP-o-matic/DcpDoctor encoding and strict validation;
      preserve an actual output artifact on exact head.
- [ ] **Crash injection:** test before/after native worker stop, stage copy,
      directory rename, FilmIndex registration, ledger completion, and
      independent validator failure; no false DCP approval or RAM release.
- [ ] **Full upstream source:** replay an unmocked approved AUDIO-01J ->
      AUDIO-01K.1 -> AUDIO-01K.3 film with real FilmIndex/creator lineage,
      not only the synthetic ProRes fixture used in the current DCP test.
- [ ] **Power-loss and distribution:** validate same-filesystem atomicity,
      Windows durable sync, destination path/ancestor custody, disk pressure,
      feature duration/reels, and a separately authorized cinema ingest.
- [ ] **Real cinema delivery:** projector/cinema-server ingest and
      exhibition acceptance are separately required. A technical
      DCP candidate never sets `dcp_delivered=True`.

## Live CI tracking

A draft verification PR was opened (not merged):
https://github.com/vjmichael/nvp_offline_film/pull/45

At the time of this record, the native Ubuntu PR jobs inspected had
`queued` state with null conclusion, and no successful Windows native
execution or DCP QC logs were available. The final PASS must refer to
a specific HEAD SHA and actual successful job/asset evidence; queued,
skipped, cancelled or absent runs are never PASS.

The execution environment itself has local FFmpeg but no installed
DCP-o-matic or DcpDoctor and no available network route to install the
binaries. No native DCP could be created locally here.

**Closeout decision: BLOCKED ON NATIVE EXECUTION EVIDENCE, NOT COMPLETE.**
Remaining work can continue without waiting on GitHub queues, but this
gate must not be released or merged as production-cinema-ready.


## 2026-11-04 offline Library native execution evidence (NEW)

The user-uploaded Library contains both a complete DCP-o-matic 2.18.51 Debian
package and a matching Ubuntu 26.10 offline dependency ZIP with 238 packages,
plus two earlier real technical DCP evidence archives.

The original `dcpomatic_1+2.18.51-1_amd64.deb` SHA-256 matches the offline
manifest: `8b8f1d38fa2db1c2d65690f7007f99e0df2a0fdec5ac25cd78477412c21a1e70`.
All 238 packaged Debian dependency archives matched their manifest SHA-256
and byte sizes. The complete runtime was extracted **under an isolated
working directory**; Debian 13 libraries were not overwritten.

Actual `dcpomatic2_create --version` returned `2.18.51 920fb9b044`.
Actual `dcpomatic2_cli`, `dcpomatic2_create`, and
`dcpomatic2_verify_cli` help revealed a code defect: `--dcp-path`
is a switch followed by the `make-dcp <film>` subcommand, not an argument
named path. The native call has now been corrected in the DCP generator.

**Two new real native DCP technical encodes were completed:**

1. One-second 24fps ProRes video plus 48kHz, six-channel PCM24:
   real SMPTE DCP with JPEG2000 picture MXF, PCM sound MXF, CPL/PKL,
   ASSETMAP/VOLINDEX. Native libdcp verification returned exit 0.
   Full FFmpeg decoded exactly 24 JPEG2000 frames and 864,000 raw PCM24
   bytes (48,000 samples × 6 channels × 3 bytes).
2. One-second 24fps ProRes video plus **stereo** 48kHz PCM24:
   real SMPTE DCP with **six-channel cinema PCM**, with the original
   left/right program mapped to channels 1–2 and channels 3–6 silent.
   Native libdcp verification returned exit 0. This is the validated
   initial NVP stereo-to-cinema6 delivery mapping. The code and contract
   now use `--audio-channels 6` and
   `smpte_2k_24fps_unencrypted_stereo_to_cinema6_v1`.

The existing uploaded CINEMA-01B and CINEMA-01C archives also independently
passed the actual native DCP-o-matic verifier (exit code 0). The new first
DCP's picture MXF was altered by changing one byte at offset 65536;
the verifier returned **exit 1** and reported the mismatch between the
picture-asset SHA-1 and PKL. The older CINEMA-01C corrupted picture MXF
also failed with exit 1.

Both newly generated DCPs use real JPEG2000 at **1998×1080, 24fps, 24 frames**
and **six-channel 48kHz/24bit PCM**, 1 second in each stream.
Real output archives with SHA256SUMS and the native technical verification
reports have been materialized in the conversation.

**Important limits:** The container runtime disallows device mounts/nodes;
isolated tool execution used temporary static random input in place of
`/dev/urandom`, so it is ONLY a technical test configuration, not secure
production cinema ID/certificate authoring. No independent DcpDoctor
binary was available; the reported PASS is the **native DCP-o-matic/libdcp
verifier**, NOT DcpDoctor. These DCPs are synthetic sources, not the
NVP creator-approved AUDIO-01J film, and the new FilmIndex reopening
workflow has NOT run against these newly generated tests.

**Revised closeout:** Real encoder, real J2K/MXF, native libdcp verifier,
picture/sound clock and modified-MXF rejection are now locally proven
on Linux for synthetic test media. DcpDoctor strict independent QC,
Windows Job Object native machine, unmocked NVP approved film, durable
FilmIndex reopen and real production entropy remain OPEN.
