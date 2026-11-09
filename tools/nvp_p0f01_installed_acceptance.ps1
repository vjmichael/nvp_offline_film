# P0-F-01 single grouped Windows NSIS/real-GGUF installed acceptance.
# Only disposable acceptance projects. OS dialogs are real Windows UI,
# but clicks from the test driver are NOT human director consent.
param(
    [Parameter(Mandatory=$true)][string]$ModelPath,
    [Parameter(Mandatory=$true)][string]$LlamaServer
)
$ErrorActionPreference='Stop'
$installedRoot=Join-Path $env:LOCALAPPDATA 'Programs/NVP'
$installed=Join-Path $installedRoot 'NVP.exe'
$setup=(Resolve-Path 'dist/NVP-Alpha-Setup.exe').Path
if (-not (Test-Path $ModelPath) -or -not (Test-Path $LlamaServer)) {
    throw 'Actual model GGUF / native llama-server is missing'
}
$process=Start-Process -FilePath $setup -ArgumentList '/S' -Wait -PassThru
if ($process.ExitCode -ne 0 -or -not (Test-Path $installed)) {
    throw 'Actual NSIS installation failed'
}
$builtHash=(Get-FileHash 'dist/NVP/NVP.exe' -Algorithm SHA256).Hash
$installedHash=(Get-FileHash $installed -Algorithm SHA256).Hash
if ($builtHash -ne $installedHash) {
    throw 'Installed executable differs from verified PyInstaller payload'
}
$ident=@(
    "installer_sha256=$((Get-FileHash $setup -Algorithm SHA256).Hash)",
    "installed_exe_sha256=$installedHash",
    "source_sha=$env:GITHUB_SHA"
)
$ident | Out-File -Encoding utf8 (Join-Path $env:RUNNER_TEMP 'p0f01-installed-identity.txt')
$env:NVP_HOME=Join-Path $env:RUNNER_TEMP 'p0f01-installed-original-film-projects'
$env:NVP_NATIVE_SMOKE_DIAGNOSTICS=Join-Path $env:RUNNER_TEMP 'p0f01-installed-window.log'
$env:NVP_FILM02M_GROUP_ACCEPTANCE='1'
# First actual installed EXE creates original 3D source and durable draft.
& $installed --smoke-create
if ($LASTEXITCODE -ne 0) { throw 'First installed project creation failed' }
# Spawn a second actual installed EXE and hard-kill it AFTER SQLite WAL
# persists a host-session-owned model attempt. No fabricated test results.
$child=Start-Process -FilePath $installed -ArgumentList '--smoke-model-interrupt' -PassThru
$marker=Join-Path $env:NVP_HOME 'installed-smoke-project.json'
$ready=$false
for ($i=0;$i -lt 120;$i++) {
    if (Test-Path $marker) {
        try {
            $saved=Get-Content $marker -Raw | ConvertFrom-Json
            if ($saved.p0f01_forced_model_attempt) { $ready=$true; break }
        } catch { }
    }
    Start-Sleep -Milliseconds 250
}
if (-not $ready) {
    Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue
    throw 'No durable installed model attempt before forced termination'
}
Stop-Process -Id $child.Id -Force
$child.WaitForExit(12000) | Out-Null
if (-not $child.HasExited) { throw 'Acceptance-owned installed host did not terminate' }
# Third actual installed process must preserve project and draft hashes, but
# classify the killed attempt as interrupted and refuse authorization.
& $installed --smoke-reopen
if ($LASTEXITCODE -ne 0) {
    throw 'Installed process restart lost original source or resurrected model'
}
# Load genuine installed WebView2 React, edit/undo/discard original USD and
# exercise native MessageBox denial then approval using a same-process,
# test-only Windows UI driver (not a user's human creative signature).
$env:NVP_P0F01_TEST_OS_DIALOGS='1'
& $installed --smoke-window
if ($LASTEXITCODE -ne 0) { throw 'Installed native WebView2/OS dialog acceptance failed' }
$log=Get-Content $env:NVP_NATIVE_SMOKE_DIAGNOSTICS -Raw
if (-not $log.Contains('p0f01_installed_native_os_deny_approve_source_reopen_passed')) {
    throw 'No actual same-process Windows native deny/approve source-reopen proof'
}
if (-not $log.Contains('p0f01_durable_model_attempt_ready_for_force_kill')) {
    throw 'Installed forced termination receipt is missing'
}
# The same installed binary now starts the exact acceptance-owned native
# llama-server, hashes the actual GGUF, and requires its genuine response
# to produce a valid unapproved original source district via WebView2 IPC.
& $installed --smoke-wo6-real-gguf --gguf-path $ModelPath --llama-server-path $LlamaServer --gguf-report (Join-Path $env:RUNNER_TEMP 'p0f01-real-gguf-installed.json') --gguf-test-consent I_APPROVE_DISPOSABLE_LOCAL_GGUF_TEST --gguf-visible-webview2
if ($LASTEXITCODE -ne 0) { throw 'Installed actual GGUF-to-source draft failed; no mock substitution' }
$proof=Get-Content (Join-Path $env:RUNNER_TEMP 'p0f01-real-gguf-installed.json') -Raw | ConvertFrom-Json
if (-not ($proof.status -eq 'LOCAL_GGUF_COMPLETION_OBSERVED' -and
          $proof.visible_webview2_checked -and
          $proof.installed_windows_app_verified -and
          $proof.server_main_process_exited_after_test -and
          ($proof.completed_provider_receipt.provider_reported_completion_tokens -gt 0))) {
    throw 'Actual GGUF / same-source installed WebView2 evidence incomplete'
}
$log=Get-Content $env:NVP_NATIVE_SMOKE_DIAGNOSTICS -Raw
if (-not $log.Contains('p0f01_real_gguf_model_source_draft_no_approval_passed')) {
    throw 'No authentic installed local-model generated USD source draft'
}
# Test GGUF and server remain outside installer. Do NOT uninstall NVP user
# data or model runtime belonging to someone else.
if (@(Get-ChildItem $installedRoot -File -Recurse -Filter '*.gguf').Count -ne 0 -or
    @(Get-ChildItem $installedRoot -File -Recurse -Filter 'llama-server.exe').Count -ne 0) {
    throw 'Acceptance-only GGUF or llama-server incorrectly bundled'
}
$uninstaller=Join-Path $installedRoot 'Uninstall NVP.exe'
$un=Start-Process -FilePath $uninstaller -ArgumentList '/S' -Wait -PassThru
if ($un.ExitCode -ne 0) { throw 'NSIS uninstall failed' }
Start-Sleep -Seconds 2
if (Test-Path $installed) { throw 'NSIS uninstall left NVP.exe installed' }
if (-not (Test-Path (Join-Path $env:NVP_HOME 'nvp_studio.sqlite3'))) {
    throw 'NSIS uninstall deleted original filmmaker project database'
}
Write-Output 'P0-F-01 Windows installed technical acceptance passed. Real human-operated physical Windows approval remains separate.'
