# NVP Windows CI repair — AUDIO-01G / native audio

## Verified failures from actual GitHub Actions logs

1. Windows run 41912184600, job 126862347751: `test_reconciled_job_requires_new_authorized_native_attempt` failed with `NameError: name '_id' is not defined` in `backend/nvp_audio01e3_native_host.py`. Fixed by importing the existing authoritative FilmIndex `_id` validator. The same failure occurred in Linux job 126862347360.
2. The same Windows job reported `[WinError 32]` deleting a temporary `native_journal.sqlite3` file after `test_stale_generation_and_persisted_events`. The test used `with sqlite3.connect(...)` which **does not close the SQLite connection**. Fixed with `contextlib.closing` around the test reader.
3. Earlier Windows run 41909292183 had `Unrecognized legacy admission; quarantine only`: uncommitted audio grant/outbox transactions disappeared after connection close. This was fixed in earlier AUDIO-01E changes; the later run progressed into actual native worker tests. Do not regress explicit COMMIT.
4. Windows B14 contract workflow had a **false-green risk**: it ran many commands in one PowerShell step and checked `$LASTEXITCODE` only after the last test. An early test failure could be hidden by a later passing command. All 21 Python compile/test commands in that block now have their own immediate failure guard.
5. Dedicated Windows native audio and AUDIO-01F workflows installed FFmpeg in one step but did not reliably persist the Chocolatey bin directory for subsequent steps. Missing FFmpeg could cause conditional `unittest.skipUnless` tests to skip and give false acceptance. Both now persist tool location through `GITHUB_PATH`, require FFmpeg/FFprobe and check availability again in the test step.

## Exact-head verification

The preceding NVP PR #44 head before these fixes was 6759a2d838c29d82e1782a084cfc49b11413928b; its full B14 Windows/Linux/Blender jobs were still **queued** when checked. No new latest-head Windows pass should be inferred from older run conclusions (particularly the earlier masked test failures).

Required closeout: inspect exact-HEAD Windows job logs, confirm zero failed/skipped required native tests, and run the dedicated AUDIO-01G 21-point crash matrix and the seven real contained-worker late boundaries. Only then mark production gates accepted.

Strict Linux delegated cgroup-v2 guardian acceptance remains OPEN / DEFERRED by decision; these Windows fixes do not change it.

## B14 main Windows gate hardened

The main `windows-conform-contract` job now installs/locates real FFmpeg and FFprobe and insists both remain visible in the test step. Previously its AUDIO-01F `unittest.skipUnless` suite could skip, and Windows Job Object pipeline would still appear green. The fast dedicated workflow also persists the FFmpeg PATH between steps and enforces native availability.

All acceptance claims must use the actual exit status of every test command. A full workflow's `success` conclusion does not imply required suites ran unless their own logs show non-skipped executions.
