# PLAN-02-D — native acceptance handoff (not a release)

**Status: OPEN / DO NOT PROMOTE TO PR #74.** This branch is deliberately independent of the canonical DATA-AV PR while the NVP daemon and native host are being completed. This document is an acceptance procedure, not evidence that it has run.

## Acceptance gates

- **D3 Windows OS custody:** launch a real detached descendant, prove active heartbeat, cancel via Windows Job Object, prove no further heartbeat; repeat after abrupt host death. Evidence must be an actual Windows native result with exact source SHA.
- **D3 Linux OS custody:** do the *same* on genuine unified cgroup v2 under a systemd-delegated **writable** service or scope, using the real guardian and `cgroup.kill`. Current fake process-group fallbacks and test doubles are prohibited. The worker must join the cgroup before exec, and a stopped heartbeat must be independently checked.
- **D4 original camera / approved rail:** a real frozen OpenUSD Take and exact Film Time, real primitive source geometry and selected camera, SHA-verified derived image, no source mutation and no worker authority from a preview. This is **not** a claim for a production film-quality Hydra/Cycles renderer.
- **D5 installed app:** actual NSIS install, `NVP.exe` source raster and recorded PCM smokes, *separate installed process* restart/create and reopen, actual NSIS child completion, source SQLite and project hash retention, **interactive WebView2 React + real JS/Python IPC**, and post-GUI uninstall. CI-only approval stand-ins are not physical human consent.
- **Delivery artifact:** the grouped run should upload `nvp-plan02d-NOT-RELEASED-physical-test-candidate` with `NVP-Alpha-Setup.exe` and `NVP-PLAN02D-CANDIDATE-SHA256.txt`; compare SHA-256 before any physical test. The artifact is not an accepted production release.

## Genuine Linux delegated-cgroup acceptance

The **host** must have systemd 254+, writable unified cgroup v2 delegation including `memory` and `pids`, and sudo access for creating a bounded delegated unit. From the exact checked-out source branch, on an actual native Linux host (not a cgroup read-only container), run as the user who owns the project:

```bash
set -euo pipefail
report="$(mktemp -u /tmp/nvp-plan02d-real-kernel-XXXXXXXX.json)"
sudo -n systemd-run --quiet --wait --pipe --collect --service-type=exec \
  --property=Delegate=yes --property=DelegateSubgroup=nvp-host \
  --uid="$(id -un)" --working-directory="$PWD" \
  --setenv="PYTHONPATH=$PWD" \
  --setenv="LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}" \
  "$(command -v python)" -m tools.nvp_plan02d_custody_native_witness --report "$report"
python -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="ACTUAL_NATIVE_DESCENDANT_CANCEL_AND_HOST_CRASH_PASS" and r["custody_backend"]=="linux_delegated_cgroup_v2_guardian" and not r["output_publication_authorized"]' "$report"
sha256sum "$report"
```

The kernel witness must run and verify **both** cancellation and abrupt host death with real detached descendants. If delegation cannot be established or is not writable by the runtime user, it **fails**. An xattr delegation marker alone is never accepted.

## Actual interactive Windows WebView2

1. On a clean Windows user account **without an existing NVP installation**, download the installer/checksum pair from the **same exact-head grouped run**. Do not install an artifact marked NOT RELEASED as an accepted film-production release.
2. Verify the installer SHA-256 against its paired receipt.
3. Open a normal, interactive PowerShell desktop session. From the exact source checkout corresponding to that run, execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\nvp_plan02d_physical_windows_acceptance.ps1 -Installer "C:\YourFolder\NVP-Alpha-Setup.exe" -ShaFile "C:\YourFolder\NVP-PLAN02D-CANDIDATE-SHA256.txt"
```

4. Retain the resulting `NVP-PLAN02D-physical-evidence/plan02d-physical-windows-evidence.json` and `installed-webview2-checkpoints.txt`. A valid PASS includes actual WebView2 window load, mounted React components, native camera+sound JS IPC, two installed SQLite processes, clean NSIS uninstall and unchanged creator project data. Any missing stage is FAIL. **Do not delete evidence on failure.**

This script does **not** claim to witness actual human allow/refuse dialog interaction. Record that separately with creator observation, explicitly bounded authority and refusal/restart proof.

## Promotion decision

Keep PR #74 draft. Before promoting PLAN-02-D, reconcile the exact accepted branch against the independently moving canonical PR #74, run one consolidated Win/Linux exact-head check after reconciliation, complete real human approval/refusal and physical desktop gates, and preserve source hashes. No FFmpeg, derived-frame or synthetic cgroup workaround.

After D, the next task area is **PLAN-02-E: one continuous 30-second authored OpenUSD film with original time-synchronized PCM audio, verified original source immutability and genuine installed playback**, before cinema mastering/DCI and AI Skin.
