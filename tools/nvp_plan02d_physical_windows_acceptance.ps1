# PLAN-02-D5. Run ONLY from an interactive Windows desktop, not a CI service.
# Usage:
# powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\nvp_plan02d_physical_windows_acceptance.ps1 -Installer "C:\...\NVP-Alpha-Setup.exe" -ShaFile "C:\...\NVP-PLAN02D-CANDIDATE-SHA256.txt"
# Do not run this on an existing NVP installation: the script deliberately refuses it.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [Parameter(Mandatory=$true)][string]$ShaFile,
  [string]$EvidenceDir = (Join-Path (Get-Location).Path 'NVP-PLAN02D-physical-evidence'),
  [switch]$ManualThirtySecondFilm
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$installerFile = (Resolve-Path -LiteralPath $Installer).Path
$shaFile = (Resolve-Path -LiteralPath $ShaFile).Path
$expectedLine = (Get-Content -LiteralPath $shaFile -Raw).Trim()
if ($expectedLine -notmatch '^([0-9a-fA-F]{64})\s+NVP-Alpha-Setup\.exe$') {
  throw 'Candidate SHA file is invalid or names a different binary'
}
$expectedSha = $expectedLine.Substring(0, 64).ToUpperInvariant()
$actualSha = (Get-FileHash -LiteralPath $installerFile -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualSha -ne $expectedSha) { throw 'Installed candidate SHA256 does not match artifact receipt' }
if (-not [Environment]::UserInteractive) { throw 'Refusing non-interactive Windows session' }
$sessionId = (Get-Process -Id $PID).SessionId
if ($sessionId -le 0) { throw 'Session 0 cannot establish interactive WebView2 acceptance' }
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\NVP'
$installedExe = Join-Path $installDir 'NVP.exe'
if (Test-Path -LiteralPath $installDir) {
  throw 'NVP is already installed. Preserve it: use an isolated clean Windows test account'
}
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$EvidenceDir = (Resolve-Path -LiteralPath $EvidenceDir).Path
$report = [ordered]@{
  format = 'nvp.plan02d.physical_windows_native_acceptance.v1'
  status = 'NOT_ACCEPTED'
  claimed_physical_interactive_session = $true
  session_id = $sessionId
  installer_sha256 = $actualSha
  installed_sha256 = $null
  native_source_stages_passed = $false
  clean_uninstall_preserved_original_data = $false
  webview2_react_and_ipc_passed = $false
  second_uninstall_passed = $false
  human_approval_refusal_witnessed = $false
  actual_30_second_audio_device_playback_observed_by_operator = $false
  original_30_second_film_test_signal = $false
  error = $null
}
$oldHome = [Environment]::GetEnvironmentVariable('NVP_HOME', 'Process')
$oldDiag = [Environment]::GetEnvironmentVariable('NVP_SMOKE_DIAGNOSTIC_PATH', 'Process')
$tempHome = Join-Path $env:TEMP ('nvp-plan02d-physical-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempHome | Out-Null
$env:NVP_HOME = $tempHome
$env:NVP_SMOKE_DIAGNOSTIC_PATH = Join-Path $EvidenceDir 'installed-webview2-checkpoints.txt'
$sentinel = Join-Path $env:LOCALAPPDATA ('NVP\Projects\nvp-d5-preservation-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $sentinel -Force | Out-Null
$sentinelFile = Join-Path $sentinel 'original-source-preservation.txt'
Set-Content -LiteralPath $sentinelFile -Value 'NVP-CREATOR-DATA-MUST-SURVIVE' -NoNewline
$sentinelHash = (Get-FileHash -LiteralPath $sentinelFile -Algorithm SHA256).Hash
function Invoke-Checked([string]$exe,[string]$arg,[int]$seconds,[string]$label) {
  Write-Output "NVP_PHYSICAL_STAGE_START $label"
  $process = Start-Process -FilePath $exe -ArgumentList $arg -PassThru
  if (-not $process.WaitForExit($seconds * 1000)) {
    & taskkill.exe /PID $process.Id /T /F 2>&1 | Out-String | Write-Output
    throw "$label timed out (native process did not exit)"
  }
  $process.Refresh()
  if ($process.ExitCode -ne 0) { throw "$label exited $($process.ExitCode)" }
  Write-Output "NVP_PHYSICAL_STAGE_PASS $label"
}
function Assert-RealUninstall([int]$seconds = 90) {
  $until = [DateTime]::UtcNow.AddSeconds($seconds)
  while (Test-Path -LiteralPath $installedExe -PathType Leaf) {
    if ([DateTime]::UtcNow -ge $until) {
      throw 'NSIS parent exited but installed NVP.exe still exists'
    }
    Start-Sleep -Milliseconds 500
  }
  if (-not (Test-Path -LiteralPath $sentinelFile -PathType Leaf)) {
    throw 'NSIS uninstall removed creator-owned source sentinel'
  }
  if ((Get-FileHash -LiteralPath $sentinelFile -Algorithm SHA256).Hash -ne $sentinelHash) {
    throw 'NSIS uninstall modified creator-owned source sentinel'
  }
}
function Uninstall-Nvp {
  $uninstaller = Join-Path $installDir 'Uninstall NVP.exe'
  if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) {
    throw 'Actual NSIS uninstaller missing'
  }
  Invoke-Checked $uninstaller '/S' 120 'nsis-uninstall-launcher'
  Assert-RealUninstall
}
try {
  Invoke-Checked $installerFile '/S' 120 'nsis-install'
  if (-not (Test-Path -LiteralPath $installedExe -PathType Leaf)) {
    throw 'Native installed executable missing'
  }
  $report.installed_sha256 = (Get-FileHash -LiteralPath $installedExe -Algorithm SHA256).Hash
  Invoke-Checked $installedExe '--smoke-data-av' 150 'native-openusd-original-pcm'
  Invoke-Checked $installedExe '--smoke-plan02d' 150 'original-camera-raster-source-receipt'
  Invoke-Checked $installedExe '--smoke-plan02d-restart-create' 150 'sqlite-restart-create'
  Invoke-Checked $installedExe '--smoke-plan02d-restart-reopen' 150 'sqlite-restart-reopen'
  $persistentRoot = Join-Path $tempHome 'plan02d-native-restart'
  $preservedFiles = @(
    (Join-Path $persistentRoot 'studio.sqlite3'),
    (Join-Path $persistentRoot 'restart-receipt.json')
  )
  $preservedHashes = @{}
  foreach ($p in $preservedFiles) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Missing durable source receipt: $p" }
    $preservedHashes[$p] = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash
  }
  $report.native_source_stages_passed = $true
  Uninstall-Nvp
  foreach ($p in $preservedFiles) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Uninstall erased source: $p" }
    if ((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ne $preservedHashes[$p]) {
      throw "Uninstall changed immutable source: $p"
    }
  }
  $report.clean_uninstall_preserved_original_data = $true
  # A separate, SHA-identical reinstall is required for real GUI/JS IPC.
  Invoke-Checked $installerFile '/S' 120 'nsis-reinstall-before-webview2'
  if ((Get-FileHash -LiteralPath $installedExe -Algorithm SHA256).Hash -ne $report.installed_sha256) {
    throw 'Reinstalled executable differs from independently checked source'
  }
  Invoke-Checked $installedExe '--smoke-window' 160 'actual-interactive-webview2-react-and-js-ipc'
  $report.webview2_react_and_ipc_passed = $true
  if ($ManualThirtySecondFilm) {
    # Film test is opt-in, isolated in a temporary workspace. Never seed
    # synthetic test audio into the creator's actual Projects directory.
    $filmHome = Join-Path $env:TEMP ('nvp-plan02e-physical-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $filmHome -Force | Out-Null
    $env:NVP_HOME = $filmHome
    Invoke-Checked $installedExe '--plan02e-seed-physical-playtest' 180 'test-only-30-second-original-source-seed'
    $marker = Join-Path $filmHome 'plan02e-physical-seed-receipt.json'
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
      throw 'No original 30-second Digital Take created in temporary workspace'
    }
    $report.original_30_second_film_test_signal = $true
    Write-Output 'NVP_PLAN02E_PHYSICAL_REVIEW_REQUIRED'
    Write-Output 'Open the PLAN02E Native 30-Second Film — TEST SOURCE project.'
    Write-Output 'Select Native 3D sound, then OriginalThirtySecondFilm and a Camera listener.'
    Write-Output 'First refuse one native OS approval; confirm no audio starts.'
    Write-Output 'Then start again, APPROVE the real OS dialog, and listen for the entire thirty seconds.'
    Write-Output 'Observe all 3 authored camera cuts, moving USD geometry, stable sound and the final audio tail.'
    $windowProcess = Start-Process -FilePath $installedExe -PassThru
    $answer = Read-Host 'Enter PASS only if you personally observed the refusal AND full thirty-second audible playback (otherwise FAIL)'
    if ($answer -cne 'PASS') { throw 'Operator did not witness required native film playback' }
    $report.human_approval_refusal_witnessed = $true
    $report.actual_30_second_audio_device_playback_observed_by_operator = $true
    Read-Host 'Close the NVP window normally, then press Enter to check clean exit' | Out-Null
    $windowProcess.Refresh()
    if (-not $windowProcess.HasExited) {
      throw 'NVP interactive playback window did not close normally'
    }
  }
  Uninstall-Nvp
  $report.second_uninstall_passed = $true
  $report.status = 'NATIVE_INTERACTIVE_WINDOWS_INSTALL_AND_GUI_PASS'
} catch {
  $report.error = $_.Exception.Message
  Write-Warning $report.error
} finally {
  $reportPath = Join-Path $EvidenceDir 'plan02d-physical-windows-evidence.json'
  $report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $reportPath -Encoding UTF8
  [Environment]::SetEnvironmentVariable('NVP_HOME', $oldHome, 'Process')
  [Environment]::SetEnvironmentVariable('NVP_SMOKE_DIAGNOSTIC_PATH', $oldDiag, 'Process')
  if ($report.status -eq 'NATIVE_INTERACTIVE_WINDOWS_INSTALL_AND_GUI_PASS') {
    Remove-Item -LiteralPath $sentinel -Recurse -Force
    Remove-Item -LiteralPath $tempHome -Recurse -Force
  } else {
    Write-Warning 'Failed acceptance: all source/diagnostic evidence retained. Any installed NVP is deliberately left untouched.'
  }
  Write-Output "NVP_PHYSICAL_EVIDENCE=$reportPath"
}
if ($report.status -ne 'NATIVE_INTERACTIVE_WINDOWS_INSTALL_AND_GUI_PASS') {
  throw 'PLAN-02-D5 physical Windows acceptance remains FAILED; inspect evidence JSON'
}
