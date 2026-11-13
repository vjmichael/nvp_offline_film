# P1-A — OS-supervised original recording device producers

Source integration branch: `nvp/p1a-device-producer-custody-20261112`, based on
DATA-AV-01 PR #74 head `3a30050a813e15f6490bc636315a41a63c9ab46f`.

## Production boundary

The trusted desktop validates original scene/camera Film Time identity, displays
the original OS creator consent and creates the private recording spool. Only
then may `SupervisedNativeDevice` launch the pinned
`tools/nvp_native_device_producer_worker.py`. Actual miniaudio mono microphone
and PortAudio independent dual-ADC device opening/callbacks live in that child,
not in the desktop host. The existing source-only FilmIndex publication remains
host-owned; no FFmpeg, flattened soundtrack or browser-controlled worker paths.

Windows uses suspended-child assignment to the existing kill-on-close Job Object.
Linux strictly requires a delegated cgroup v2 leaf with an independent host-death
guardian; old process-group-only mode is forbidden. The host rejects startup
without genuine child-ready evidence. During finish it cooperatively stops,
waits for the original producer to exit and verifies tree shutdown before
reading original PCM and per-buffer ADC records. The PortAudio worker brackets
its stream clock in the same child and pins its device descriptor digest;
host-side calibration against a stale cross-process stream reading is forbidden.

Worker `.complete`/PCM hashes/packet hashes are NOT OS custody proof. A
clean child exit alone never authorizes the immutable Take. Any producer
exception, missing or mismatched source scope, malformed ADC record, corrupted
PCM, interrupted producer or uncertain kernel cleanup refuses publication.
Cancellation performs OS-wide process tree shutdown without inventing a clean
PCM receipt. Interrupted original source stays unapproved in the capture
recovery journal. Explicit human freeze approval remains required.

## Acceptance status (do not promote on unit tests)

- Source path: implemented for mono and independent dual endpoints.
- Isolated mock-producer and scope/PCM/cancel tests: authored; native test run
  evidence must be collected against this exact committed head.
- Windows Job Object: genuine native process-tree evidence **OPEN**.
- Linux delegated-cgroup guardian/ancestor migration: genuine native evidence
  **OPEN**.
- Physical miniaudio, dual PortAudio ADC clocks, device unplug/overflow,
  timed acquisition and encrypted original source: **OPEN**.
- Restart, EFS recovery and genuine installed production upgrade/rollback:
  **OPEN**, separate creator-authorized gates.

This change must not be treated as SEC-06, physical hardware, W1-G installed,
or release/upgrade acceptance.
