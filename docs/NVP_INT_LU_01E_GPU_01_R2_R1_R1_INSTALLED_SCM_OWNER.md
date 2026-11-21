# NVP-INT-LU-01E-GPU-01-R2-R1-R1 — installed SCM owner and physical GPU gate

**Status:** NVP installed Windows service-control source **PREPARED**, native qualification **OPEN**, physical signed/Radeon **NOT RUN**. Remains within the original task, branch and PR #161. This is not approval to install, merge, expose signing keys, or launch Lu-controlled GPU diffusion.

## Previously qualified exact-source baseline

- Original branch/PR source `d13f214a4014e6fcd0ca377b726dc446234396ec`. Focused [Windows/Ubuntu GPU R2](https://github.com/vjmichael/nvp_offline_film/actions/runs/44956990130) **PASS** on attempt 2, after Chocolatey 504 package-feed outage in attempt 1; [IPC Rust/prost](https://github.com/vjmichael/nvp_offline_film/actions/runs/44956990124) **both PASS**; [provider](https://github.com/vjmichael/nvp_offline_film/actions/runs/44956990117) **both PASS**; [Windows SCM denial](https://github.com/vjmichael/nvp_offline_film/actions/runs/44956995722) **PASS**. None is a physical positive.
- Immutable Core schema remains commit `60afe6908a6abe3408bb952869d85b43781313ca`, Protobuf blob `747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1`. Do not repin or broaden the legacy GGUF inference lease.
- `backend/nvp_lu_windows_gpu_binding.py` requires an **actual** `InstalledScmLtxServiceControl` before asking Core to yield GPU. Arbitrary Python callback collections alone cannot admit this path.

## NVP-owned source prepared here

- `backend/nvp_lu_windows_scm_service_control.py` is a **read-only Win32 SCM admission and original start/stop transport**, not a creator grant issuer. It uses Windows machine known-folder ProgramFiles, rejects unpinned or changed image bytes and reparse-pointed parents, requires exact fixed `NVP-POST01F-SCM-LTX-Picture` service image and `LocalSystem` service account.
- The independently trusted installer MUST provide a **64-bit HKLM** `SOFTWARE\\NVP\\POST01F\\InstalledScmOwner` with REG_SZ `Format=nvp.post01f.installed_scm_owner.v1` and REG_SZ `ImageSha256` as the SHA-256 of fixed `%ProgramFiles%\\NVP\\LTX\\nvp_scm_ltx_gpu.exe`. This is a **contract**, not a claim it is present. File/SCM write permissions and service DACL remain installer custody.
- Before `StartService`, the control reads protected `SOFTWARE\\NVP\\POST01F\\ApprovedLtxPicture` fields, and verifies exact one-use ticket, project, original reserved job, model/runtime/source digests, Lu GPU lease/device/epoch/session and user-turn scope against the typed `YieldIntent` and independently accepted `CoreYieldGrant`. It **never writes HKLM** or invents the creator's CMS .p7s.
- SCM start and STOP can only target this fixed service. STOP is an asynchronous request, not worker-stop proof. On ambiguous timeout, retain the original stop custody in-process and leave Lu's no-reload fence intact. Even successful service STOP/exit returns `native_job_zero_verified=False` and `core_release_authorized=False`; actual CNG/EFS Job receipt and driver quiescence are separate.
- The NVP C++ GPU stop issuer now derives **Lu's receipt store** from the real ProgramData KnownFolder, validates each installed subdirectory against reparse/junction redirects, keeps Lu-owned directories intact, and signs only after the original SCM Job is `ACTIVE_ZERO`. No user/worker identity can choose the signer or receipt path.
- Focused portable tests reject fake owner callback, stale/wrong Core lease, foreign project/plan/Job/epoch/device/session/turn, reused ticket, missing/foreign pin, invalid native service status, uninstalled platforms, restart timeout auto-clear, and claim-less STOP. **These are synthetic negative tests, never installed positive evidence.**

## Mandatory installed-machine acceptance register (NOT YET RUN)

| Gate | Exact physical requirement | State |
| --- | --- | --- |
| P1 Installer custody | Authenticated signed NSIS/MSI or approved package; verified fixed SCM image, owner and protected HKLM pin; explicit independent license/creator signoff; restricted service start/stop rights | OPEN |
| P2 SCM secret separation | Independently created and ACLed **distinct** machine P-256 GPU-stop signer key; independently provisioned Lu protected verifier public pin; original POST01F picture P-256 signer still separate | OPEN |
| P3 Original Job | Creator-approved immutable Take; one preallocated LTX job; StartService creates suspended lowbox under original SCM Job, WFP no egress, EFS stage, bounds and exact approved source; no second Python Job | OPEN |
| P4 Physical GPU | Actual Radeon AI Pro R9700 LUID/VRAM WDDM/DXGI measurements and GGUF GPU unload before diffusion; no concurrent Core inference while NVP owns lease | OPEN |
| P5 Safe release | Cancel/failure/success all require original Job kernel `ActiveProcesses=0`, all driver GPU contexts drained, signed original stop receipt, replay-resistant Lu verification and durable Core acknowledgement before reload | OPEN |
| P6 Recovery | Crash, uncertain STOP, orphan, revoked creator/session, timer expiry, stale Core model generation, Lu restart, tampered/foreign signer, wrong ticket/pin keep UNKNOWN/NO-RELOAD until independent native reconciliation | OPEN |
| P7 Film | LTX picture-only output verified against original Take and audio/PCM untouched; creator explicit review, no automatic export | OPEN |

**Critical boundary:** The newly prepared Python controller does **not** implement the missing trusted *installer/privileged writer*, native owner receipt-to-Journal observer, independent Lu CNG verification, or R9700 physical measurements. It is a real control path only when installed machine prerequisites exist. Its return dict must never be converted to `NativeGpuQuiescence` or `CoreReleaseAck` without separately authenticated original SCM and GPU evidence.

**Next within the same task:** obtain exact-SHA Windows and Ubuntu source qualification for this successor, correct only observed compile/negative failures, then connect trusted machine installer/SCM owner and independently run P1–P7 on physical Windows. No Docker, fake keys, forced commit, new branch/PR or positive claims from CI fixtures.
