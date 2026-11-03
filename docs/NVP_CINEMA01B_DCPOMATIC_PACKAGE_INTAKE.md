> **Later execution update (November 3, 2026):** The follow-on creator-uploaded `NVP_CINEMA01B_UBUNTU2610_AMD64_20261103_153902.zip` independently passed SHA-256 verification for all 238 .deb files. DCP-o-matic was launched using extracted Ubuntu glibc 2.44, a private chroot/user/mount/network namespace and three specifically named host fallbacks. Actual SMPTE 2K unencrypted technical test DCP creation, FFmpeg full picture decode, and DCP-o-matic verification **all passed**. This supersedes the *not executed* status below, which records the earlier intake milestone. The FilmIndex source-exact registration remains gated by observed 16-to-24-frame black padding and is not a finished cinema master. [Measured first-run acceptance](NVP_CINEMA01B_FIRST_NATIVE_DCP_ACCEPTANCE_20261103.md).

# CINEMA-01B: Library DCP-o-matic package intake and runtime compatibility

**Date:** 2026-11-03  
**Source:** creator-provided ChatGPT Library `/NVP/Packages/dcpomatic_1+2.18.51-1_amd64.deb`  
**Acceptance state:** package received, byte hash recorded, structural audit passed; **NOT EXECUTED**, **NOT NATIVE-DCP-ACCEPTED**.

## Immutable package fingerprint

| Field | Observed |
| --- | --- |
| Filename | `dcpomatic_1+2.18.51-1_amd64.deb` |
| SHA-256 | `8b8f1d38fa2db1c2d65690f7007f99e0df2a0fdec5ac25cd78477412c21a1e70` |
| Size | `262580654` bytes |
| Debian package format | `2.0`, zstd payload |
| Package/version/arch | `dcpomatic`, `1+2.18.51-1`, `amd64` |
| Advertised homepage | `https://dcpomatic.com/` |
| Internal `md5sums` entries | 241 checked against unpacked payload, **241 passed** |
| Required executables present | `usr/bin/dcpomatic2_create`, `dcpomatic2_cli`, `dcpomatic2_verify_cli` |

**Evidence interpretation:** Internal MD5 match detects extraction/payload inconsistency, not independent origin or a cryptographic publisher signature. The uploaded source's authenticity is not independently established. The package was **extracted only** with `dpkg-deb -x`; no maintainer script was run and no global install was performed.

## Important runtime and installation boundaries

The supplied amd64 binaries import **GLIBC_2.43** and **GLIBC_2.44** symbols. The current Debian 13 development host exposes glibc **2.41** and also lacks some direct linkable dependencies, including `libboost_thread.so.1.90.0`, `libboost_filesystem.so.1.90.0`, `libcrypto.so.4`, `libicuuc.so.78`, `libicui18n.so.78`, `libx264.so.165` and `libxml2.so.16`. Therefore the three CLI tools cannot start here. Do not create compatibility symlinks between mismatched SONAME/ABI versions or upgrade the host libc in place.

**Privilege warning:** The package's `postinst` calls
`setcap "cap_dac_override+ep cap_sys_admin+ep" /usr/bin/dcpomatic2_disk_writer`.
DCP picture encoding does **not** require this unrelated privileged disk-writer tool. NVP must not silently install the full package globally; prefer extracting verified required CLI binaries into a tightly scoped worker image, with no privileged disk-writer exposure.

Ubuntu 26.04 GitHub-hosted runners are available but have glibc 2.43, which **does not** satisfy this package's GLIBC_2.44 ABI. Ubuntu 26.10 has glibc 2.44; this is a possible *compatibility test target*, not a proven successful native installation. It must also satisfy the linked Boost, ICU, crypto and other SONAMEs.

## How this contributes to the cinema gate

The earlier vendor download at `https://dcpomatic.com/dl?id=ubuntu-24.04-x86-cli&version=2.18.51` returned HTTP 403 in GitHub Actions. The creator-provided Library package resolves the **missing package bytes** in our local development workspace, but ChatGPT Library files are not automatically accessible to GitHub Actions. This package is additionally unsuitable for an Ubuntu 24.04 or 26.04 runner without a compatible isolated runtime.

CINEMA-01B closes only when the exact SHA-256 package is made available to a compatible test worker (without executing privileged post-install scripts), the three CLIs start, the real frozen NVP source is encoded to a DCP, and both DCP-o-matic verifier and the independent FFprobe + full FFmpeg JPEG2000/MXF decode pass. Then check manifest hashes/CPL/PKL/ASSETMAP, approved sound, color transform and independent cinema ingest. Current work remains **technical only**; do not advertise exhibition certification.

## Developer disposition

- Keep the original uploaded .deb intact as a locally fingerprinted input.
- Do not modify Lu.
- Keep PR #16 draft until a real native execution gate passes.
- Choose a verified runtime-specific dependency set or a vendor-provided Debian 13 CLI package for the current host. Do not force-install incompatible packages.

References: [DCP-o-matic official downloads](https://dcpomatic.com/download), [GitHub-hosted Ubuntu 26.04 runner announcement](https://github.blog/changelog/2026-09-17-ubuntu-26-generally-available-and-latest-migration/).
