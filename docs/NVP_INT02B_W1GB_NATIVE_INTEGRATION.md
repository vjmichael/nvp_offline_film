# INT-02B / W1-GB — source implementation follow-on (2026-11-12)

Parent source: INT-02/W1-G implementation branch
nvp/int02-w1g-native-film-package-20261112.

## INT-02B — real native filmmaking/editorial/delivery integration (SOURCE IMPLEMENTED, ACCEPTANCE OPEN)

- backend/nvp_int02_edited_film.py opens an ACTUALLY COMMITTED
  SlateSequenceAssembly edit (not an unapproved suggestion or old B11–B14
  FFmpeg-era conform), validates its original Digital Take source SHAs,
  editorial intervals, 30-second duration, boundaries and unretimed layout.
- A single native-host authorization scope covers the exact edit revision,
  selected original source-sequence SHA, recipient path, 720 output picture
  samples and 1,440,000 original PCM samples; a WebView request cannot choose
  a filesystem destination, worker PID or authorization callback.
- On valid approved scope, one selected original OpenUSD camera state is
  rendered at each mapped Film Time instant, while the source PCM reader
  supplies the corresponding source-relative audio windows, including cuts
  between different frozen Takes. Original source events never become
  ordinary imported video/frame authority.
- verify_edited_film independently reopens all 720 original-time PNG
  samples, selected cameras, edited FilmIndex revision, original source Takes,
  picture hashes, exact WAV PCM sample values, original audio SHA and the
  full sequence. Changed output cannot be approved by trusting its JSON.
- The authenticated trusted native desktop bridge exposes read-only eligible
  edit discovery, exact preflight, approval-bound background export, progress,
  cancellation request, and independent verification. A non-CLI React panel
  surfaces the flow in the installed data-first filmmaker interface.
- Source-only regression tests exercise different Takes across a cut,
  denial, unsupported shot composition, time misalignment, unauthorized
  partial-output cancellation and independent reopen tamper detection.

Intentionally blocked:
- Director-authored SHOT-01 stronger USD opinions are refused rather than
  silently omitted in an exported source. The real compositing renderer
  must implement these before those edited films are eligible.
- Segment cuts must currently be aligned to derived 24-fps frame boundaries
  and native 48-kHz sample ticks. Arbitrary cinematic timing requires exact
  conform mapping without rounding away original intent.
- The existing NativeSourceRaster renders only authentic procedural
  cubes/spheres and camera gaps, not high-quality characters, rigging,
  Hydra/Cycles, facial acting, calibrated color or production 3D lighting.
- The output is a PNG sequence plus WAV, not a playable single-file master,
  theatrical DCP or sustained feature-length production.
- Native device filming/custody and real installed WebView2 worker/render
  results are NOT established by code and mock-oriented tests.
- Output currently runs inside a desktop-owned thread with cooperative
  cancellation; this is NOT an OS-protected Blender/cgroup/Job Object worker.
- Existing B11–B14 old FFmpeg-dependent editorial conform must not be
  silently revived or imported into INT-02.

## W1-GB — dependencies, upgrade handling and worker binaries (SOURCE IMPLEMENTED, ACCEPTANCE OPEN)

- tools/nvp_w1g_native_dependencies.py: explicit creator-review license
  reference for every exact-version, SHA-256 pinned original wheel. Checks
  wheel METADATA and architecture; rejects missing/corrupt/off-platform
  dependencies. Offline pip provisioning has no index/cache/source builds,
  requires full transitive hashes, installs into a new standalone target,
  then verifies the actual installed distribution roster. No network.
- tools/nvp_w1g_native_upgrade.py: program-only side-by-side preparation,
  SHA inventories, original-film preservation hashes, one-use native human
  authorization + repeated OS stop checks, durable rename state journal,
  interruption reconciliation and rollback without removing original films.
  A canonical NSIS-managed install REFUSES direct upgrade: installer-aware
  migration and signed update still need implementation. Linux runtime
  packages may use this primitive after native verification.
- tools/nvp_w1g_worker_package.py: exact roster of reviewed, precompiled
  amd64 native PE32+/ELF64 executable workers; rejects wrong architecture,
  source-only placeholder scripts, missing/tampered native binaries and
  wrong platform. Installed bundles may have the external native roster
  verified via tools/nvp_w1g_native_package.py, but absent worker roster
  is explicitly reported as unprovisioned.
- Source-only regressions cover wheel metadata and hash mismatches,
  refused authorization/OS stop, positive program rollback without original
  data mutation, NSIS refusal and worker executable tampering.

## Remaining actual acceptance

1. Authoritative renderer with director shot USD layers, real characters,
   facial rigs, photoreal native visual source and complete PCM sound.
2. A real 30-second film run in the installed NVP GUI using multiple Takes,
   exact native approval and genuine OS custody, followed by independent
   output/restart replay and visual/audio quality inspection.
3. Real offline, licensed, pinned wheel lock and reviewed native executables
   built and executed on Windows and Linux. No reviewed lock/worker binaries
   or real installation were supplied in this source checkpoint.
4. NSIS-specific safe upgrade/rollback and uninstall reconciliation,
   Linux .deb real installation and OS worker-tree containment.
5. Physical creator approval and long-duration production acceptance.

No CI, gh workflow rerun or physical installed NVP acceptance claimed.
