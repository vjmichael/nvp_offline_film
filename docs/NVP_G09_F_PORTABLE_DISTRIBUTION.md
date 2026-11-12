# NVP G09-F — Portable Film Distribution

Branch: nvp/g09f-portable-film-distribution-20261111
Base: G09-E, nvp/g09e-sustained-scale-20261111
State: Source-layer implementation authored, NOT an accepted native or released product.

## Product intent

A filmmaker has already directed original OpenUSD scenes, performances,
original microphone PCM, cameras and approved edit/finishing. Once an
ordinary G09-E long-film render has completed independently verified
10-second native working AVI reels, the creator can:
1. Choose "Watch Complete Film" from Export Film. NVP reopens the verified
   reels with one global 24fps picture/48kHz original-derived sound clock.
   At a reel cut, the reader requests the next reel's exact global audio
   samples rather than reinitializing the original microphone recording.
2. Choose "Prepare Portable Film". NVP streams the complete real verified
   reel collection to one .nvpfilm Zip64 container. The worker never
   overwrites original film sources or presents a partial archive as ready.
3. Choose "Save Portable Film" to download the checked collection.
4. Open Export Film -> "Your Film Library" in an ordinary NVP project,
   select an existing .nvpfilm file, import, and watch it from that project's
   persistent local film collection. No external streaming service, shell,
   executable archive payload or remote code provider is needed.

The film library is under NVP's user-owned project-data parent, not the
application executable/install location. Existing movie projects, frozen
Takes, original mic audio and edit/approval histories are NOT moved into
the package or changed by packaging/import/playback. The portable package
contains the *finished derived film* and its SHA-provenance index, not
original source USD/PCM files, licensed actors, scene assets or GGUF models.

## Source implementation

### F1. Portable source-verified package and import
- backend/nvp_g09f_package.py: a fixed three-part format:
  package.json (bounded schema, SHA binding, explicit non-cinema profile),
  manifest.json (G09-E completed original-source film index),
  reels/reel-NNNNN.avi (original completed G09-E working AVI reels).
  ZIP64 with STORED members supports bounded large collections without
  ZIP decompression bombs or loading a three-hour film into memory.
  Streams at most 1MiB per copy. Strict filename/order, member count,
  per-reel SHA256 and size, global frame/sample/tick continuity, 32GiB
  media quota, 2MiB manifest limit and original source-hash check.
  No symlinks, arbitrary unzip paths, scripts, executables or network.
  Atomic exclusive publish after separate archive reopening/checks.
  SHA256 verifies file integrity; it does NOT authenticate the director,
  guarantee redistribution rights or constitute a digital signature.
- backend/nvp_g09f_distribution.py: source-locked, owner-scoped durable
  package state (queued/packing/completed/cancelled/interrupted/failed),
  periodic heartbeat, explicit human package launch and cancel, publication
  receipts, crash-between-link-and-DB-commit recovery via byte recheck.
  Imports get a different opaque library ID after ALL reels are
  rehashed and atomically committed. An interrupted import never enters
  the visible library; earlier completed film sources remain untouched.
  Imported files are owned by that user's current project.
- backend/nvp_g09f_routes.py: director session/film lock, first-party
  fixed route families and bounded application/x-nvpfilm streamed upload.
  No arbitrary host file path, model authorization or remote URL fetch.
  Protected projects refuse ordinary packaging and import.

### F2. Continuous source-reel playback
- backend/nvp_g09f_reel_playback.py: verifies actual RIFF AVI headers,
  chunk ordering, physical index offsets, JPEG bounds and exactly 2,000
  PCM16 stereo samples per native 24fps film frame. On first reel use,
  checks the original expected reel SHA. Bounded LRU source index cache
  invalidates when file identity/size/timestamps change. Returns at most
  12 actual JPEG frames or 24,000 actual 48k stereo audio samples per
  request. A single audio request may cross the reel cut with no synthetic
  gap. Uses original G09-E full-film source SHA; no source USD/PCM override,
  false 4K picture, FFmpeg or synthetic replacement audio.
- frontend/src/DirectorReelPlayback.jsx: uses WebAudio device clock as
  master, prefetches bounded real reel frames/PCM, plays across reel cuts,
  supports precise seek, Pause, Stop and source revisions; deliberately
  stops when it cannot keep a picture or sound window ready rather than
  presenting drifting A/V as synchronized. Physical gapless playback
  over 30min/60–90min/3h is NOT yet independently measured.

### F3. Persistent filmmaker UI
- frontend/src/DirectorFilmDistribution.jsx: "Watch Complete Film",
  "Prepare Portable Film", package progress/cancel and source-verified
  .nvpfilm download on genuine completed G09-E renders.
- frontend/src/DirectorFilmLibrary.jsx: safe user-selected streamed file
  upload, verified imported film catalog and exact original-film replay.
- frontend/src/DirectorLongFilmExport.jsx and DirectorExportFilm.jsx:
  integrate both workspaces without replacing short-film G08 export,
  changing frozen performance/camera/sound, or claiming a theatrical master.
- backend/nvp_api.py: G09-F routes registered behind existing G03 project
  lock/session middleware; G03 encrypted live movie routes are refused
  by the actual ordinary distribution service.

### F4. Installed lifecycle / runtimes
- backend/nvp_studio.py: packaged executable refuses a project-data root
  located underneath its uninstallable program directory. Existing
  NVP_HOME override and historical default HOME/NVP_Projects location
  are preserved; there is no invisible migration of source films.
- packaging/nvp-alpha.nsi: per-user Windows uninstall restricted to the
  dedicated LOCALAPPDATA/Programs/NVP tree and marker; explicitly leaves
  NVP_HOME, source films, saved G09-E working reels and imported G09-F
  film libraries alone. Genuine physical install/uninstall preservation
  remains NOT tested.
- packaging/build-nvp-deb.sh: builds from a genuine Linux x86_64
  PyInstaller onedir/React bundle, requires an audited non-empty Debian
  dependency list, rejects stubs/symlinked payloads, and installs
  application files under /opt/nvp without maintainer scripts that can
  delete user movie directories. Debian native install and actual
  dependency/licensing acceptance NOT performed.
- requirements-foundation.txt: includes CPU-native NumPy and SciPy for
  long-film accelerated 48k stereo DSP along with existing Pillow and
  PortAudio source microphone dependencies. The exact Windows/Linux
  installer dependency inventory and redistributable wheel licenses
  have NOT been independently accepted.
- backend/nvp_g09f_runtime.py: first-party actual-runtime introspection,
  including Pillow, NumPy, SciPy, OpenUSD, FastAPI, sounddevice and
  installed-versus-source status. Version/license metadata are
  observations, never legal approval or evidence of physical GPU/camera
  acceptance.

## Explicit remaining obligations (G09-F acceptance OPEN)

1. The actual Windows NSIS and Linux Debian installed executables must
   dispatch the fixed G09-E --g09e-worker command rather than merely
   accepting an argument with no handler. The repository does not yet
   contain a verified frozen desktop-worker entrypoint, true Windows
   packaging evidence, pinned Python native ABI hashes, or genuine
   long-form package import/playback results. No release/merge authority.
2. In the installed app, package, move, import and watch a real 30-minute
   film, then 60–90 minutes and ultimately a three-hour verified
   film. Prove cross-reel audio/sample continuity and visual frame
   timing on a physical Radeon Windows machine, actual disk/CPU/RAM
   limits, large-file access, interruption/restart and live director
   playback. Source code represents this behavior; actual hardware
   proof and measurements remain open.
3. Portable ZIP and library SHA attest integrity against the manifest,
   not authorship. Public distribution requires creator-approved
   title/credits/rights, reliable redistribution/license attribution,
   optional authenticity signature, publication policy, backup and
   deliberate deletion workflows, and accessibility acceptance.
4. Protected G03 movies cannot be exported through G09-F's ordinary
   packaging or library, because encrypted chunk source/material
   custody and protected process staging for a long render remain
   G09-E/G03 open engineering work. Never publish plaintext by
   downgrading the security boundary.
5. The original G09-E long-render source reader still rejects
   microphone PCM clips larger than 64MiB without incremental BLOB
   source slicing; the 30-minute/feature-length first genuine
   performance pass and accelerated runtime installed-bundle validation
   remain open. No claim that all possible film lengths are renderable.
6. Existing G09-A/B/C/D professional visual/acting/audio quality gates
   remain open, including true scene-linear Cycles/OpenEXR/OCIO/ACES
   color-managed pictures, expressive actor performance, real 3D
   multichannel spatial sound, intersample true peak and genuine
   SMPTE DCP Bv2.1 creation and DcpDoctor/physical cinema acceptance.
   The package is a native SDR 640x360 MJPEG / PCM16 working film, not
   a 4K cinema master, a source-asset portable film, or a streaming
   service.
7. Consolidated source repair and exact-head native regression,
   installer, uninstall, secure project denial, API import limits,
   checksum tampering, multi-instance race handling, browser
   AudioContext behavior, Windows/Linux OS worker containment,
   real telemetry and human accessibility remain deferred under the
   director's build-first workflow.

## Next task group

G09-F source implementation is provisionally authored. There are no
further G09 groups after F. Next is codebase-wide integration
reconciliation and compiler repairs followed by consolidated native
Windows/Linux acceptance, real device/long-film performance validation,
secure source custody review, licensing/legal inventory and installed
owner-operated acceptance. Do not infer feature-length readiness from
the presence of a source module or from a 30-second short movie.
