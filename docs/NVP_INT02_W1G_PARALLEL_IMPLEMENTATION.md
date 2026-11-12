# INT-02 + W1-G — Parallel implementation checkpoint (2026-11-12)

Branch: nvp/int02-w1g-native-film-package-20261112, based on immutable
DATA-AV PR #74 head c1e5706d615108d05554946e0ffbb87588cc8135.
These are independent, additive integrations; they do not alter frozen Take
publication, original PCM, FilmIndex time, the Lu model owner or FFmpeg policy.

## INT-02 — complete filmmaker vertical slice (PARTIAL / OPEN)

backend/nvp_int02_film_delivery.py connects the existing
Approved2DPackage (a trusted, OS-approved, real-USD-native renderer must be
injected by its host) to an independent full 30-second reopening gate.

The gate insists on one immutable FilmIndex OpenUSD Take with verified scene
and timeline source and exactly 30 seconds of original Film Time. It reopens
all 720 individually sampled 24-fps PNG frames and checks exact source-tick
order, hashes, continuous picture index, fixed dimensions,
48-kHz/16-bit/stereo uncompressed soundtrack WAV with 1,440,000 samples,
source identity after export, and derived-manifest SHA. Test-only PNG
fixtures are explicitly NOT production 3D-rendering evidence.
The produced asset is a source-bound PNG sequence + PCM WAV derivative,
not a conventional playable encoded film or DCP. Source remains immutable.

Open: real scene creation in the installed filmmaking interface; physical
recording devices and frozen source; G07/G08 nondestructive editor and actual
OS-approved 30-second 720-frame production renderer; FFmpeg-free conventional
movie mastering; installed filmmaker workflow, restart and author acceptance.
Do not promote INT-02 based on fixture tests or a static manifest.

## W1-G — native packaging and production infrastructure (PARTIAL / OPEN)

tools/nvp_w1g_native_package.py extends the real PE32+/GUI and bundled
React/PyInstaller validation with a SHA-256/size inventory for every installed
runtime and worker file. The W1-G manifest is emitted outside the package.
Post-install auditing fails on missing, changed, linked or injected files,
except NSIS-owned uninstall executable and install marker; it rejects FFmpeg
executables and native codec libraries. Separate read-only snapshot and
post-uninstall verification ensure every preexisting creator-owned project
file remains byte-for-byte preserved.

packaging/build-nvp-nsis.sh and the existing manual-only Windows installed
acceptance workflow are wired to generate and check these receipts.
No workflow, runner, user machine or physical install was executed by this
checkpoint. The test suite covers a modified worker DLL, extra payload,
forbidden binary and changed original movie file as negative cases.

Open: trusted version and redistribution-license approval for all native
dependencies; Windows protected worker provisioning/OS process-tree custody;
Linux real package build/install/uninstall and cgroup-v2 admission;
secure signed-update/upgrade transaction and rollback; full installed
Windows/Linux lifecycle and physical creator original-film preservation.
A payload byte-hash match is not proof of safe runtime behavior.

## Gates for later acceptance

1. Run the INT-02 test file against a real source and production raster
   renderer; independently inspect the full verified original and derivative.
2. Run W1-G build/installed/preservation receipts on the exact Windows NSIS
   release head; check protected native workers and license evidence.
3. Produce a genuine Linux bundle and prove installed lifetime, original
   film preservation, rollback and worker containment under the real kernel.
4. Perform owner-operated physical Windows filmmaker path and sustained
   production acceptance. Do not infer a pass from new source code.

Both groups remain OPEN, and W1-F physical/sustained acceptance remains
outstanding. No CI/PR verification was requested or submitted here.
