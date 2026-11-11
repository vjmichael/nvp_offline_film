<#
G03 physical Windows acceptance handoff.
Run in Windows PowerShell 5.1 or PowerShell 7 after installing an exact-head
G03 NSIS candidate from PR #155's matching successful GitHub workflow.

This does not operate real projects. All film work in this test is isolated
under a NEW temporary NVP_HOME. It DOES NOT uninstall, delete or encrypt any
user-owned source. No movie passphrase is ever collected by the script.

Human judgments are recorded separately from real Windows UIAutomation roles.
#>
[CmdletBinding()]
param(
  [string]$InstalledExe = (Join-Path $env:LOCALAPPDATA 'Programs\NVP\NVP.exe'),
  [string]$OutputDirectory = (Join-Path $env:TEMP 'NVP-G03-Physical-Acceptance')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Find-NvpWindow {
  $windows=[System.Windows.Automation.AutomationElement]::RootElement.FindAll(
    [System.Windows.Automation.TreeScope]::Children,
    [System.Windows.Automation.Condition]::TrueCondition)
  foreach($w in $windows){
    try{
      if($w.Current.Name -like '*NVP*Make Your Movie*' -and
         -not $w.Current.IsOffscreen){return $w}
    }catch{}
  }
  return $null
}
function Require-Window([int]$Seconds=25) {
  $deadline=(Get-Date).AddSeconds($Seconds)
  while((Get-Date) -lt $deadline) {
    $w=Find-NvpWindow
    if($null -ne $w){return $w}
    Start-Sleep -Milliseconds 400
  }
  throw 'Installed NVP user window did not appear in Windows UI Automation'
}
function Check-Uia([string]$Name,[string]$Role,[bool]$SetFocus=$false) {
  $w=Require-Window
  $children=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                       [System.Windows.Automation.Condition]::TrueCondition)
  foreach($c in $children){
    try{
      $x=$c.Current
      if($x.Name -like "*$Name*" -and $x.ControlType.ProgrammaticName -eq $Role -and
         $x.IsKeyboardFocusable -and -not $x.IsOffscreen){
        if($SetFocus){
          $c.SetFocus()
          Start-Sleep -Milliseconds 100
          $focused=[System.Windows.Automation.AutomationElement]::FocusedElement
          if($null -eq $focused -or $focused.Current.Name -notlike "*$Name*"){
            throw "Keyboard focus could not reach $Name"
          }
        }
        return [ordered]@{name=$x.Name;role=$Role;focusable=$true;visible=$true;
                           focused=$SetFocus}
      }
    }catch{
      if($_.Exception.Message -like '*Keyboard focus*'){throw}
    }
  }
  throw "Missing visible UIAutomation control: $Name ($Role)"
}
function Ask-Operator([string]$Label,[string]$Question) {
  Write-Host ''
  Write-Host "G03 OPERATOR CHECK: $Label" -ForegroundColor Cyan
  Write-Host $Question
  $answer=Read-Host 'Enter PASS, FAIL or SKIP'
  $value=$answer.Trim().ToUpperInvariant()
  if($value -notin @('PASS','FAIL','SKIP')){throw "Invalid response for $Label"}
  $script:checks+=@([ordered]@{check=$Label;result=$value})
  if($value -eq 'FAIL'){Write-Warning "Operator reported failure: $Label"}
}
function Start-IsolatedNvp {
  $script:app=Start-Process -FilePath $InstalledExe -PassThru
  $null=Require-Window
}
if(-not (Test-Path -LiteralPath $InstalledExe -PathType Leaf)){
  throw "Installed NVP.exe not found: $InstalledExe"
}
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$testHome=Join-Path $OutputDirectory ("NVP-G03-Test-"+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testHome -Force | Out-Null
$exeHash=(Get-FileHash -LiteralPath $InstalledExe -Algorithm SHA256).Hash
$oldHome=$env:NVP_HOME
$env:NVP_HOME=$testHome
$script:checks=@()
$uia=@()
$script:app=$null
$receipt=Join-Path $OutputDirectory ("G03-Physical-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.json')
try {
  Write-Host "NVP installed SHA256: $exeHash"
  # Cryptography must execute in the actual installed executable, under
  # the operator's Windows DPAPI identity. Synthetic test sources only.
  $crypto=Start-Process -FilePath $InstalledExe -ArgumentList '--smoke-vault' -PassThru
  if(-not $crypto.WaitForExit(90000)){
    & taskkill.exe /PID $crypto.Id /T /F 2>$null | Out-Null
    throw 'Installed Windows DPAPI vault smoke exceeded 90 seconds'
  }
  if($crypto.ExitCode -ne 0){
    throw 'Installed Windows DPAPI archive/restore verification failed'
  }
  Write-Host 'Windows current-account DPAPI and encrypted source archive smoke passed.'
  $newFilm=Start-Process -FilePath $InstalledExe -ArgumentList '--smoke-live-create' -PassThru
  if(-not $newFilm.WaitForExit(90000)){
    & taskkill.exe /PID $newFilm.Id /T /F 2>$null | Out-Null
    throw 'Encrypted live film creation exceeded 90 seconds'
  }
  if($newFilm.ExitCode -ne 0){
    throw 'Installed DPAPI live film creation/original source validation failed'
  }
  $reloadFilm=Start-Process -FilePath $InstalledExe -ArgumentList '--smoke-live-reopen' -PassThru
  if(-not $reloadFilm.WaitForExit(90000)){
    & taskkill.exe /PID $reloadFilm.Id /T /F 2>$null | Out-Null
    throw 'Encrypted live film recovery exceeded 90 seconds'
  }
  if($reloadFilm.ExitCode -ne 0){
    throw 'Installed encrypted live film could not reopen in a fresh process'
  }
  Write-Host 'G03 installed live encrypted film, OpenUSD source, revision and relock passed.'
  foreach ($mode in @('--smoke-live-worker','--smoke-legacy-migration','--smoke-capture-denied')) {
    $native=Start-Process -FilePath $InstalledExe -ArgumentList $mode -PassThru
    if(-not $native.WaitForExit(110000)){
      & taskkill.exe /PID $native.Id /T /F 2>$null | Out-Null
      throw "Installed G03 native acceptance timed out: $mode"
    }
    if($native.ExitCode -ne 0){
      throw "Installed G03 native acceptance failed: $mode"
    }
  }
  Write-Host 'Protected native three-camera staging, non-destructive migration and mic consent denial passed.'
  Write-Host "Isolated test films: $testHome"
  $physicalMicAnswer=(Read-Host 'Optional physical microphone test: enter RECORD for a real 1-second recording (two native Yes/No prompts) or SKIP').Trim().ToUpperInvariant()
  $physicalMicPassed=$false
  if($physicalMicAnswer -eq 'RECORD'){
    $capture=Start-Process -FilePath $InstalledExe -ArgumentList '--g03-physical-capture-owner' -PassThru
    if(-not $capture.WaitForExit(120000)){
      & taskkill.exe /PID $capture.Id /T /F 2>$null | Out-Null
      throw 'Physical native microphone test did not exit'
    }
    if($capture.ExitCode -ne 0){
      throw 'Real physical microphone capture/consent/encryption test did not pass'
    }
    $physicalMicPassed=$true
  }elseif($physicalMicAnswer -ne 'SKIP'){
    throw 'Enter RECORD or SKIP for physical microphone acceptance'
  }
  Write-Host "No existing NVP projects will be deleted or encrypted."
  Start-IsolatedNvp
  $uia+=@(Check-Uia 'New Movie' 'ControlType.Button' $true)
  $uia+=@(Check-Uia 'Resume Working' 'ControlType.Button')
  Ask-Operator 'Welcome & keyboard' 'Verify the New Movie/Resume dialog. Try Tab and Shift+Tab; check visible focus and accessible names with Narrator or your screen reader.'
  Ask-Operator 'Create first movie' 'Using NVP, create G03 Test Film A from an idea; go to Script and save an EXT. FOREST - MORNING scene. The system must not claim a 3D scene was generated.'
  $uia+=@(Check-Uia 'Set Up Scenes' 'ControlType.Button' $true)
  Ask-Operator 'Create and switch' 'Create G03 Test Film B with a different script. Switch A to B and back via the project list. Verify the screenplay and scene list never mix.'
  Ask-Operator 'Encrypted new movie' 'Create one additional movie using Encrypt this new movie on this Windows account. Use a TEST-ONLY passphrase, enter an idea or screenplay, save, lock, unlock and re-open it. The title remains visible but its private content should require the passphrase.'
  Ask-Operator 'Lock and unlock' 'Lock one test movie with a test-only passphrase, verify access is denied, then unlock it. The warning should say files on disk are NOT encrypted.'
  Ask-Operator 'Open editing window' 'Select Edit Film and open the separate Post-Production window. Verify Export remains unavailable and opening the editor does not modify source.'
  Ask-Operator 'Close and restart' 'Close the NVP window normally, then return here and enter PASS once it has exited.'
  if(-not $app.WaitForExit(30000)){throw 'NVP did not exit normally'}
  $script:app=$null
  Start-IsolatedNvp
  $uia+=@(Check-Uia 'New Movie' 'ControlType.Button' $true)
  Ask-Operator 'Saved movies after restart' 'Choose Resume Working and confirm all test movies, including the encrypted one, retained their scripts. The encrypted movie must demand the passphrase after restart. No plaintext export/filming is allowed.'
  Ask-Operator 'Accessibility after restart' 'Try keyboard-only navigation and a screen reader in the restarted UI; verify New Movie, Resume, project switching, Lock and Edit Film are navigable.'
  if($physicalMicPassed){
    Ask-Operator 'Physical microphone result' 'Did the two native microphone approval dialogs appear, did recording require Yes twice, and did the installed binary return success without a visible plaintext audio file?'
  }else{
    $script:checks+=@([ordered]@{check='Physical microphone result';result='SKIP'})
  }
  $fail=@($script:checks|Where-Object {$_.result -ne 'PASS'})
  $record=[ordered]@{
    format='nvp.g03.physical_windows_user_acceptance.v1'
    executed_by='local human operator'
    measured_at=(Get-Date).ToUniversalTime().ToString('o')
    installed_exe=$InstalledExe
    installed_exe_sha256=$exeHash
    isolated_test_home=$testHome
    actual_windows_uia=$uia
    operator_checks=$script:checks
    all_operator_checks_passed=($fail.Count -eq 0)
    windows_user_dpapi_archive_smoke_passed=$true
    new_live_encrypted_film_restart_smoke_passed=$true
    windows_job_opensud_staging_smoke_passed=$true
    nondestructive_legacy_migration_candidate_smoke_passed=$true
    native_microphone_consent_denial_passed=$true
    physical_native_microphone_recording_passed=$physicalMicPassed
    legacy_project_data_encryption_accepted=$false
    protected_external_workers_accepted=$false
    lu_model_integration_deferred=$true
    physical_radeon_inference_tested=$false
  }
  $record|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $receipt -Encoding UTF8
  Write-Host "Wrote operator and Windows UIA evidence: $receipt" -ForegroundColor Green
  if($fail.Count -gt 0){throw "G03 physical acceptance has $($fail.Count) incomplete or failed operator checks"}
  Write-Host 'G03 owner-operated UI/restart/keyboard acceptance passed (NOT encryption acceptance).' -ForegroundColor Green
}finally{
  if($null -ne $script:app -and -not $script:app.HasExited){
    Write-Host 'Close the isolated NVP test window before using other projects.'
  }
  $env:NVP_HOME=$oldHome
  Write-Host "Test-only movie data retained for review at: $testHome"
}
