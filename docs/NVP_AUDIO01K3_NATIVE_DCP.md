# AUDIO-01K.3 — Real SMPTE Cinema DCP Generator (native candidate)

## Purpose and source trust

NVP's first cinema deliverable is a genuine **unencrypted SMPTE 2K, 24fps,
2D, stereo DCP candidate** made by DCP-o-matic, independently validated
by DcpDoctor, and tied to an already completed AUDIO-01J audiovisual
master plus AUDIO-01K mezzanine distribution.

This is NOT an MXF- or XML-naming simulation. The code invokes real cinema
encoder and validator executables; NVP does not implement its own fake J2K
or MXF muxer. The project-specific output is created only after creator
authorization and a verified, content-addressed final audiovisual master.

**Production status:** Implementation and native acceptance tests committed,
but the cinema dependencies are not installed in the model execution
environment; no actual SMPTE DCP has yet been encoded or certified there.
A generated candidate is NOT an approved theatrical delivery.

## Real open-source cinema tools

- DCP-o-matic stable 2.18.51 (October 16, 2026):
  https://dcpomatic.com/download
- Documented CLI: `dcpomatic2_create` and `dcpomatic2_cli`:
  https://dcpomatic.com/manual/html/ch15.html
- DcpDoctor independent SMPTE/DCI/J2K/MXF/PKL/CPL validator:
  https://github.com/PostPerfection/dcpdoctor

The host requires installed, trusted, SHA-pinned executable files with
their exact expected names; it does not download programs at runtime or
allow arbitrary user/model shell binaries. For DcpDoctor schema verification,
`xmllint` and packaged cinema XSD schemas must be provisioned. A missing
required validator, skipped essential schema/MXF/J2K checks or nonzero strict
SMPTE validation exit cannot promote a candidate.

NVP's eventual single-click installer should ship a vetted, licensed,
version-pinned native DCP tool bundle on Windows and Linux. This stage
does not ask end users to manage Docker or a multi-install CLI workflow.

## Stage boundaries

1. **AUDIO-01J** previously approved the picture and final PCM24 soundtrack
   and published the synchronized ProRes audiovisual master.
2. **AUDIO-01K.1** emitted an immutable, verified mezzanine MOV with SHA
   manifest, FilmIndex lineage and independently approved NVP source.
3. **AUDIO-01K.3 host** checks current `NativeAudio01KHost.verify`,
   source SHA, owner/creator scope, destination and a one-use SQLite
   creator event. It seals a typed operation into `ApprovedTaskBindings`.
4. **Native OS-contained worker** checks the active TaskLedger grant and
   SHA-pinned Python/worker/DCP-o-matic/DcpDoctor executables. It invokes
   the documented DCP-o-matic CLI with explicit SMPTE, 2K, 2D, 24fps,
   unencrypted and Rec709-input settings. No remote encode servers.
5. DCP-o-matic converts picture to cinema XYZ JPEG 2000 in MXF,
   audio to cinema PCM MXF and creates CPL/PKL/ASSETMAP/VOLINDEX.
   The worker requires exact on-disk DCP structure and actual MXF files.
6. Independent DcpDoctor runs **strict SMPTE** and performs default
   cross-reference/hash/deep J2K/MXF validation. The worker saves the
   entire bounded stdout/stderr QC evidence and their SHA digests. Any
   validator error or explicitly skipped essential check fails closed.
7. A separate NVP CPL reader ensures each 2D reel's MainPicture and
   MainSound are both at 24/1 edit rate, their durations match, and the
   total picture/sound duration equals the source's approved frame count
   (2,000 audio samples per 24fps frame).
8. The worker copies *only* DCP assets to a unique staged output directory
   and fsyncs every file. No fake NVP manifest is inserted into the actual
   DCP folder. The worker writes a private non-authoritative receipt.
9. After the native worker is **reaped** and a durable stopped witness
   recorded, the trusted host independently rehashes DCP assets, checks
   the separate validator reports and source, promotes the directory with
   same-filesystem atomic rename, and registers an immutable FilmIndex
   **unapproved DCP candidate** (not a terminal theatrical master).
10. After a restart, `recover_completed` can reconcile only a stopped,
    independently verified candidate without rerendering. An unknown
    worker OS state does not release its ACTIVE resource reservation.

## Implemented files

- `backend/nvp_audio01k3_dcp.py` — real DCP CLI, structural audit,
  strict independent validator and source-bound CPL timing.
- `tools/nvp_audio01k3_dcp_worker.py` — sealed and contained long-running
  DCP-o-matic/DcpDoctor worker.
- `backend/nvp_audio01k3_native_host.py` — authorization, TaskLedger,
  resource watchdog, native process-tree containment, durable custody,
  FilmIndex candidate promotion and crash reconciliation.
- `tests/test_audio01k3_dcp_contract.py` — Windows/Linux no-false-green
  contracts for CLI, asset paths, malformed XML, clock drift, validator
  failure and skipped checks.
- `tests/test_audio01k3_native_dcp.py` — actual ProRes/PCM24 input,
  DCP-o-matic encode, independent DcpDoctor, host FilmIndex registration,
  restart and tampered MXF refusal. Upstream NVP source approval uses an
  explicitly labeled fixture: it is independently covered by AUDIO-01J/K.
- `.github/workflows/nvp-audio01k3-contract.yml` — required Windows/Linux
  Python 3.11/3.13 unit and syntax matrix.
- `.github/workflows/nvp-audio01k3-native.yml` — opt-in real cinema
  acceptance. This workflow MUST NOT pass through missing-binary skips;
  it fails if installed actual tools are absent.

## Explicit limits and next gates

- DCP-o-matic and DcpDoctor are **NOT currently executable in this
  environment**. Real native encode and strict-validation logs on
  Windows/Linux are necessary to close AUDIO-01K.3 production acceptance.
- The first profile is **SMPTE 2K 24fps 2D unencrypted stereo** only.
  No 4K, 3D, 5.1, 7.1, immersive audio, subtitles, VF/OV, multi-language
  reels, encrypted DCP/KDM, projector ingest, or onsite exhibition claim.
- NVP currently provides the source through an SDR Rec.1886/Rec.709
  technical picture workflow. Accurate Rec709-to-cinema XYZ color
  conversion and graded picture rendition must be viewed and audited on
  cinema-calibrated reference equipment before release.
- The independent validator check is a technical candidate gate,
  NOT proof of cinema-server interoperability or projector certification.
  A separately authenticated **final theatrical delivery authorization**
  and drive/ingest verification remain open.
- The native DCP worker implements process-tree containment but does not
  yet have the full AUDIO-01K.3 abrupt-exit filesystem/SQLite matrix;
  this needs dedicated crash injection on physical Windows and Linux.
- Real feature-duration disk-pressure tests, multi-reel migration,
  source-ancestor replacement races, fail-safe Windows directory sync and
  Linux delegated cgroup-v2 protection are remaining gates.
- At no point should the candidate set `dcp_delivered=True` until
  separate creator approval, complete QC, distribution custody and
  cinema ingest acceptance actually occur.
