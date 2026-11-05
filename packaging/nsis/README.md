# NVP E2E-01E — real Windows stage and NSIS package

This is an **installer source**, not evidence of an installed desktop alpha. It packages an actual, already-built Windows desktop app. The standalone WebView2/native host, Python and worker executables, and runtime assets must all be present in the staged folder, with no checked-out source tree necessary.

## Build using Windows NSIS

Stage the real built NVP Windows desktop application and every native dependency under one folder (example \`C:\nvp-stage\`). Name the actual launcher \`NVPDesktop.exe\` in this example; substitute the actual name rather than renaming a placeholder. Before packaging, inspect the launcher as a Windows PE, launch it without a dev server, save a project, close, and reopen.

\`\`\`powershell
$stage = 'C:\nvp-stage'
$out = 'C:\nvp-output'
$exe = 'NVPDesktop.exe' # replace with actual existing desktop executable
New-Item -ItemType Directory -Force $out | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $stage $exe) -PathType Leaf)) { throw 'No native desktop executable in stage' }
& makensis "/DSTAGE_DIR=$stage" "/DAPP_EXE=$exe" "/DOUTPUT_DIR=$out" packaging\nsis\NVPDesktopAlpha.nsi
if ($LASTEXITCODE -ne 0) { throw 'NSIS packaging failed' }
Get-FileHash (Join-Path $out 'NVP-Desktop-Alpha-Setup.exe') -Algorithm SHA256
\`\`\`

The script intentionally has no browser-server fallback and refuses a missing launcher. It installs per user under \`%LOCALAPPDATA%\Programs\NVP\`, writes the HKCU uninstall entry and start-menu shortcuts, and only removes its dedicated installation folder on uninstall. Keep film projects **outside** the program installation directory (for example \`%LOCALAPPDATA%\NVP\` or an explicitly chosen creator directory).

## Required acceptance before declaring E2E-01E passed

1. In a Windows VM or fresh user account, verify the downloaded installer signature/hash and inspect embedded files. Do not use an empty or fake \`.exe\`.
2. Install without the repository or any dev server. Launch the real NVP window, not a web-test harness.
3. Create a film project, persist it, exit the app, relaunch, and reopen. Confirm project bytes and database state persist across process restart.
4. Start an authorized native rendering/editorial/audio worker; verify actual OS child process, resource tracking, completion receipt, and output FilmIndex integrity.
5. Cancel and force-kill a real worker and verify native process-tree cleanup and durable reconciliation.
6. Uninstall and confirm binaries and shortcuts are removed, while the saved project remains intact; reinstall and reopen that project.
7. Record Windows version, host/worker executable SHA256, NSIS version, installer SHA256, all logs, screenshots, exact Git commit and worker results.

**Not yet passed:** This runtime did not contain a Windows staged build or NSIS compiler. This commit adds hard-gated packaging source; it does not produce or certify the binary installer. Integrate this with the existing Windows build/staging pipeline rather than replacing it with a fabricated stub.