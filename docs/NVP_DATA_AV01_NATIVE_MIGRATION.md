# DATA-AV-01 — Native Digital Take A/V Migration

**Creator directive: 2026-11-06. New active draft PR #74. Source branch**
`nvp/data-av01-native-scene-playback-20261106`; stacked on the existing
authored OpenUSD SLATE-08B scene branch, NOT the obsolete FFmpeg preview
branch.

> **Superseding creator clarification:** NVP **never uses FFmpeg**, including incoming media compatibility, native A/V, picture/sound mastering, video encoding/muxing, and the final 2D presentation. Earlier references below permitting FFmpeg for import/final export are historical and expressly withdrawn. Until independently implemented with other components, those legacy operations must be unavailable. Consult the [ordered DA-00–DA-07 ledger](NVP_DATA_ALL_TASK_LEDGER.md).\n\n## Supersession and state

The creator explicitly requires NVP to treat its Digital Film World,
OpenUSD scene, exact Film Time event ledger, immutable recorded sound
signals and positional sound relationships as the **entire editing/playback
source of truth**. No initial/ordinary movie prerender, MP4 proxy, nominal
video-frame index, forced BWF stem or FFmpeg runtime is needed for an
NVP-native Digital Take. The final approved 2D presentation is a separate
delivery/export process. Existing imported footage (MOV/MP4), optional
MP3 soundtrack, audio interchange and final export may use compatibility
decoders including FFmpeg, but cannot redefine the native capture model.

**Retired**: INDEX-CLOSEOUT / INDEX-TIME 01–10 draft PRs #53–57 and #68–73,
plus original frame-index core PR #47. These PRs were *closed, not merged*.
GitHub workflow runs already in progress on their previous SHA may still
execute; closing a PR is **not proof that GitHub cancelled an already
admitted runner**. No GitHub run-cancel API was available in the connected
tools at this checkpoint. The old benchmark, FFmpeg installer and index
workflows are changed to manual-only on THIS migration branch; old branches
are preserved for provenance. The separate NVP DCP CI closeout automation
was disabled to prevent recurrence during the architectural migration.

## New native source and runtime

- `backend/nvp_data_av_source.py`: immutable 48-kHz mono PCM16LE
  **recorded source assets**, up to 1-MiB content-addressed FilmIndex chunks,
  versioned audio source revisions. Arbitrary bounded indexed sample-window
  reads recheck original SHA. No compulsory BWF/WAV/codec container.
- `backend/nvp_data_av_scene.py`: verifies frozen Digital Take,
  scene/timeline revision hashes and USD checkpoints. Evaluates objects
  and semantic sound/dialogue event sources at precise integer Film Time.
  A first dry mono-source→stereo-device spatial mix applies emitter/listener
  position, distance and panning; at most 4096 samples per request. The
  resultant PCM bytes are disposable device buffer data, not a soundtrack.
  No video frame or FFmpeg decoder participates in source evaluation.
- `backend/nvp_data_av_usd.py`: constructs **in-memory**
  `UsdMedia.SpatialAudio` descriptors bound to source IDs/SHA/positions
  without replacing frozen USD scene layers or trusting arbitrary media
  file paths.
- `backend/nvp_data_av_desktop.py`: trusted **native** creator confirmation
  for one exact frozen Take/virtual listener/finite Film Time interval,
  opaque window-local authority, bounded read/seek/stop, no public HTTP
  endpoint or JS-authored filesystem path.
- `backend/nvp_slate08b_native_camera_ipc.py` bridges these operations
  through an authenticated pywebview window. A process restart loses
  the temporary creator audition session, not the original Take.
- `frontend/src/DataFirstAVPanel.jsx`: in an installed desktop,
  discover the trusted native bridge, choose frozen Take and USD listener,
  seek in PCM samples forward or backward, and feed short native stereo
  PCM windows into the audio device via Web Audio; read structured
  scene status. No temporary full movie file, FFmpeg runtime requirement,
  or new master authorization.
- `tools/nvp_data_av_installed_acceptance.py` and
  `tools/nvp_desktop_alpha.py --smoke-data-av`: actual packaged EXE
  makes an immutable, disposable native USD Take, records source sound
  signal, tests two listeners, source SHA and stop/reopen boundaries,
  without FFmpeg; independent real Windows WebView2 panel discovery gate.
- `.github/workflows/nvp-data-av01-native.yml`: new native OpenUSD +
  source audio tests on Linux/Windows 3.11/3.13, frontend UI, packaging,
  installed Windows binary and uninstall. Nothing on this new workflow
  installs, discovers or bundles FFmpeg.

## Engineering gates — not automatically fulfilled by code presence

**Implemented but exact-head CI not yet accepted:** frozen scene and
PCM sample-window core, dry stereo spatial mix, trusted desktop
authorization, React WebAudio glue, real USD and source SHA tests,
installed Windows candidate tests.

**Still genuinely open:** authored 3D visual *interactive live presentation*
rather than only structured scene readouts and optional manually approved
camera stills; full acoustic simulation/HRTF/environment obstruction/
reflection and native spatial-device measurement; capture-session producer
that emits semantic sound events + recorded signals during filming;
multi-track synchronized 3D audio and advancing real scene output with
actual device-clock sync/latency measurements; native Windows/Linux
independent crash/recovery/cancellation (not merely window-local stop);
short discontinuity-free 20-minute/feature-length acceptance; provenance
at all read boundaries for huge (>32 MiB) source PCM; platform installer
redistribution/CPU/GPU constraints; and final approved flattening/export
from the **same immutable scene**, distinct from legacy FFmpeg proxy
reels. Do not claim 3D A/V is commercially complete until these pass.

**Source of truth:** `docs/NVP_MASTER_DESIGN.md`, this migration ledger
and `docs/NVP_SOUND01_NATIVE_SPATIAL_AUDIO.md`; code and exact GitHub
per-commit native logs control actual acceptance.

## Exact-head CI observation — 2026-11-06

GitHub connector inspected PR #74 at head `440b40f121bf7e1dfa6be24b19c4a90c643f7b06`. The commit-specific workflow query returned eight runs, **all queued, none concluded**: DATA-AV-01 run `42307456319`; USD-01 `42307456303`; USD-02 `42307456347`; USD-02C `42307456340`; USD-02D `42307456418`; SLATE-06 `42307456434`; SLATE-08 `42307456356`; SLATE-08B `42307456385`. No executable job logs or Windows installed `NVP.exe` results existed in that snapshot; **zero native passes may be inferred**. React, real Linux/Windows OpenUSD/PCM and packaged Windows application acceptance remain unproven. These IDs are observations of the original SHA only; any later documentation commit requires a fresh exact-head CI inspection. Next: inspect completed jobs/logs and repair reproducible failures rather than treating queue admission as success.
