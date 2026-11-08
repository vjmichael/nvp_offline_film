# WO5 — Finished-film XYZ12 preview and PCM24 cache integrity follow-up

**Date:** 2026-11-07. **Status:** implementation submitted; native acceptance **OPEN**.
**Stack:** WO5 follow-up on WO3 MaterialX PR #96, which includes prior WO1 PCM boundary repair from PR #94.
**Branch:** `nvp/wo5-preview-pcm-custody-closeout-20261107`.

## Verified source-review issue and remediation

`backend/nvp_wo5_finished_playback._display_png` previously sampled
`raw[::stride,::stride]` to create a 1024-wide screen PNG, then validated that
*sampled* ndarray for values greater than 4095. For actual published DCP
XYZ12 from a genuine native OpenJPEG decode, an out-of-range word (e.g.
`0x1000`) at an unsampled position could escape rejection. The changed
source scans the **whole original >u2 XYZ frame** with `raw.max()`
before slicing the downsampled display image. This avoids allocating
a full-resolution extra boolean mask and preserves the original frame and
the intentionally uncalibrated preview conversion. No JPEG2000 or MXF
source is modified.

## PCM24 and multi-reel custody

Earlier WO1 PR #94 repaired an actual window issue: a window starting at
local frame 22 with four frames must split into the 24-frame region starting
at 0 and the next region starting at 24. The split uses separate
`snd_000000000`/`snd_000000024` native unwrap outputs, then concatenates
only original 48 kHz/24-bit samples.

Added regression for a **26-frame terminal 5.1 reel**, where the second
region contains **only two frames**. The native unwrap fixture generates a
different six-channel PCM24 sample label for every original film frame.
Assertions check all four frames, exact 2000 samples/channel/frame, correctly
ordered 5.1 labels, region boundaries `(0,24)` and `(24,2)`, cache
reuse, and explicit cache eviction after stop. This is source-level
contract evidence only, not a replacement for genuine MXF unwrap
or installed NVP.exe audio output.

## Required native evidence

Workflow: `.github/workflows/nvp-wo5-preview-pcm-custody.yml`.

Run all four combinations of Windows 2025 / Ubuntu 24.04 and Python
3.11 / 3.13 against **the final exact commit**. The workflow compiles
the native finished-film module, executes the entire existing playback
unit suite (including new 2K unsampled-value and partial 5.1 boundary
tests), and checks the no-FFmpeg contract. Do not mark this accepted
from queued or skipped jobs. If the first run fails, inspect its actual
logs, repair the cause, and rerun the entire matrix.

**Still separate OPEN acceptance:** real native asdcplib/OpenJPEG exact
published 2K/4K MXF, continuous picture + mastered WebAudio in installed
NVP.exe, 24fps sustained throughput, original authored 30-minute film,
creator approval and screening, source/original SHA custody under hostile
external filesystem changes, SMPTE Bv2.1 and theater/projector acceptance.
Pure unit tests cannot certify these.
