# NVP — Local Windows installer compiler recovery

**Purpose:** Persistent environment inventory so future development sessions
do not rediscover NSIS from scratch. This is build-tool evidence, **not**
Windows NVP installed-app acceptance.

## Known package sources (user Library)

The original, previously verified Debian packages are Library-root files:

- `/nsis_3.11-1_amd64.deb`
- `/nsis-common_3.11-1_all.deb`

Prior Lu experiments also confirmed NSIS 3.11 and Windows SDK/MSVC/LLVM
recovery, but their original per-session executable directories are
**ephemeral**. Treat these entries as *known package sources*, not proof
that the binaries exist in the next conversation.

## Restore into a fresh Linux workspace

After materializing both originals into a local directory, run:

```bash
mkdir -p /mnt/data/nvp_build_toolchain/nsis
dpkg-deb -x nsis_3.11-1_amd64.deb /mnt/data/nvp_build_toolchain/nsis
dpkg-deb -x nsis-common_3.11-1_all.deb /mnt/data/nvp_build_toolchain/nsis
export NSISDIR=/mnt/data/nvp_build_toolchain/nsis/usr/share/nsis
/mnt/data/nvp_build_toolchain/nsis/usr/bin/makensis -VERSION
```

On the 2026-11-04 local recovery, `makensis` returned `v3.11-1` and
compiled an NSIS Windows PE installer. That prior smoke used a 37-byte
placeholder `NVP.exe`; it proves **NSIS works**, not that NVP launches.

## Build only a real NVP alpha candidate

1. Produce a **genuine Windows AMD64 GUI** PyInstaller one-directory
   build at `dist/NVP/NVP.exe` plus `dist/NVP/_internal`, including
   the actual bundled Python runtime and Vite assets.
2. `python tools/nvp_e2e01e_validate_installer_payload.py --bundle dist/NVP`
   must pass. It rejects truncated/placeholder binaries, incorrect
   machine/subsystem, and missing Python/Vite resources.
3. On Linux with the real Windows payload, set
   `MAKENSIS=/mnt/data/nvp_build_toolchain/nsis/usr/bin/makensis`,
   export `NSISDIR` as above, then run
   `bash packaging/build-nvp-nsis.sh` from a checked-out NVP repo.
4. A locally compiled NSIS EXE is *not* installed Windows acceptance.
   On Windows 11 or Windows Server run the actual:
   install -> NVP.exe --smoke-create -> close -> NVP.exe --smoke-reopen
   -> NVP.exe --smoke-window -> uninstall while retaining creator SQLite.
5. Windows CI has this acceptance workflow:
   `.github/workflows/nvp-e2e01e-windows-alpha.yml`. A queued CI run
   does not count as a passing test.

## Recorded blocker

This Linux workspace has no Windows NVP executable, Windows Python runtime
or Windows GUI session. Cross-platform installer packaging is viable
once the authentic Windows onedir payload exists; **do not substitute a
Lu executable, static page, or 37-byte stub**.

All sources must be tied to one exact NVP Git commit and original Windows
artifact SHA. The CI workflow verifies installed NVP.exe SHA-256 matches
the build payload.
