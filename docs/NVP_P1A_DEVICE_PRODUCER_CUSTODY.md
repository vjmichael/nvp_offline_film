# P1-A / P1-B — Native custody and physical ADC / installed candidate

## Source and scope

Draft PR #156, stacked on DATA-AV-01 PR #74. P1-A workers are OS-
supervised independent original PCM producers. The desktop alone owns original
scene/camera identity, creator start/freeze consent, PCM journal and FilmIndex
publication. There is no FFmpeg intermediate or automatic Take authorization.

## P1-A native kernel gate: PASSED at exact SHA 5ae153833710a3a06ad0472c71c32f0476e63335

Original run: https://github.com/vjmichael/nvp_offline_film/actions/runs/43372223674

- Windows: 2 real Job Object tests passed, including detached descendant
  cancellation, zero Job processes, hard host exit and new-host read-only
  unapproved original journal.
- Linux: 4 real delegated-cgroup tests passed. Systemd scope had a dedicated
  host subgroup. Original guardian killed detached descendants after host loss;
  ancestor cgroup.procs migration was attempted and denied under the child
  Landlock policy; guardian loss failed closed; host restart did not freeze.
- Repairs from independent logs: Job query-handle rights, occupied delegated
  root controller EBUSY, Landlock /dev/null O_RDWR used by child subprocess.

These are process custody tests, not real physical microphone tests.

## P1-B implemented / acceptance pending

- Fixed packaged Windows worker dispatch: frozen NVP.exe now exposes an
  internal --device-producer-worker role before WebView2 startup, rather than
  incorrectly invoking an absent Python script with the GUI PE as interpreter.
- The reviewed bundle includes native miniaudio and PortAudio sounddevice data.
  A source-only --smoke-producer-bundle verifies imports without device capture.
- Added explicit creator-consented physical ADC acceptance harness for default
  mono or two *distinct* real PortAudio device endpoints. It checks original
  signal sample count, PCM SHA-256, RMS/clipping, nonmonotonic ADC buffers,
  independent native device clocks, model residuals/drift and OS custody.
  Output explicitly states loopback NOT independently certified and no Take
  approved. Windows physical test data must inherit an EFS-protected root;
  EFS key recovery remains a separate gate.
- Repaired E2E-01D subprocess test inheritance of PYTHONPATH to reach the
  actual backend when the test itself is executed by filename.
- Added Windows installed *candidate* job with PyInstaller, genuine NSIS
  installation, installed source-only USD/PCM smoke, persistent restart,
  WebView2 startup and uninstall data retention. It does NOT authorize a
  one-use production upgrade, rollback or signed release.

## Outstanding acceptance, not to be inferred from static checks

1. Actual physical Windows microphone signal/acoustic test, independently
   clocked *two-device hardware loopback*, unplug/overflow cases and verified
   EFS key recovery. Hosted runners do not provide that equipment.
2. Exact-head full source and cross-platform E2E regressions. Do not credit
   canceled, queued, older-head or fixture-only runs.
3. Genuine installed candidate result on final SHA; inspect original
   PyInstaller/NSIS/WebView2 log and repair demonstrated failures.
4. Independent reviewed native worker/dependency wheelhouse and signatures;
   physical creator-authorized installed production upgrade/rollback.
5. Sustained filmmaking, 3D real-time A/V, HRTF, and FFmpeg-free 2D export.

Any failed or unknown gate stays OPEN. Preserve immutable original sources.
