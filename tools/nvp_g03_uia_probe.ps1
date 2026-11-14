# G03 native Windows UIAutomation acceptance. No DOM selectors, OCR or screenshots.
# Run while the installed NSIS NVP.exe WebView2 window is visibly open.
param(
  [ValidateSet('welcome','editor')][string]$Phase='welcome',
  [string]$ReceiptPath,
  [string]$WindowTitle='NVP Director-first Acceptance'
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$target=if($Phase -eq 'welcome') {
  @(
    @{name='New Movie';role='ControlType.Button';exact=$true},
    @{name='Resume Working';role='ControlType.Button';exact=$false}
  )
} else {
  @(
    @{name='Edit Film';role='ControlType.Button'},
    @{name='Set Up Scenes';role='ControlType.Button'},
    @{name='Open Post-Production Window';role='ControlType.Hyperlink'}
  )
}
$deadline=(Get-Date).AddSeconds(14)
$observed=@()
$focusName=''
$windowFound=$false
$failure='UIAutomation has not yet produced required controls'
while((Get-Date) -lt $deadline) {
  try {
    $root=[System.Windows.Automation.AutomationElement]::RootElement
    $windows=$root.FindAll(
      [System.Windows.Automation.TreeScope]::Children,
      [System.Windows.Automation.Condition]::TrueCondition)
    $main=$null
    foreach($item in $windows) {
      try {
        if($item.Current.Name -like "*$WindowTitle*") {$main=$item;break}
      } catch {}
    }
    if($null -eq $main) {throw 'NVP window absent from actual UIAutomation tree'}
    $windowFound=$true
    $descendants=$main.FindAll(
      [System.Windows.Automation.TreeScope]::Descendants,
      [System.Windows.Automation.Condition]::TrueCondition)
    $controls=@()
    foreach($element in $descendants) {
      try {
        $props=$element.Current
        $controls+=@([pscustomobject]@{
          Element=$element
          Name=$props.Name
          Role=$props.ControlType.ProgrammaticName
          Focusable=$props.IsKeyboardFocusable
          Offscreen=$props.IsOffscreen
        })
      } catch {}
    }
    $observed=@()
    foreach($wanted in $target) {
      $matching=@($controls|Where-Object {
        $(if($wanted.ContainsKey('exact') -and $wanted.exact) {
          $_.Name -eq $wanted.name
        } else {
          $_.Name -like "*$($wanted.name)*"
        }) -and
        $_.Role -eq $wanted.role -and
        $_.Focusable -eq $true -and
        $_.Offscreen -eq $false
      })
      if($matching.Count -lt 1) {
        throw "Missing visible keyboard-focusable UIA $($wanted.role) named $($wanted.name)"
      }
      $observed+=@([pscustomobject]@{
        Name=$matching[0].Name
        Role=$matching[0].Role
        Focusable=$matching[0].Focusable
        Offscreen=$matching[0].Offscreen
      })
    }
    # The visible filmmaking step has an accessible numeric prefix, e.g.
    # "4Edit Film"; find it by the same role/name contract as the control
    # check instead of incorrectly demanding an exact label.
    $focusTargets=@($controls|Where-Object {
      $_.Name -like "*$($target[0].name)*" -and
      $_.Role -eq $target[0].role -and
      $_.Focusable -eq $true -and
      $_.Offscreen -eq $false
    })
    if($focusTargets.Count -lt 1) {
      throw "No real UIA focus target for $($target[0].name)"
    }
    $focusTargets[0].Element.SetFocus()
    Start-Sleep -Milliseconds 160
    $focused=[System.Windows.Automation.AutomationElement]::FocusedElement
    if($null -eq $focused -or
       $focused.Current.Name -notlike "*$($target[0].name)*") {
      throw "UIA keyboard focus did not reach $($target[0].name)"
    }
    $focusName=$focused.Current.Name
    $failure=''
    break
  } catch {
    $failure=$_.Exception.Message
    Start-Sleep -Milliseconds 350
  }
}
if($failure) {throw "Native G03 UIAutomation failed ($Phase): $failure"}
if($observed.Count -ne $target.Count) {throw 'G03 incomplete UIAutomation evidence'}
$receipt=[ordered]@{
  format='nvp.g03.native_windows_uia.v1'
  phase=$Phase
  real_windows_uia=$true
  window_title=$WindowTitle
  window_found=$windowFound
  controls=$observed
  focused_accessible_name=$focusName
  model_connected=$false
  physical_owner_workstation_test=$false
}
$payload=$receipt|ConvertTo-Json -Depth 6
Write-Host "G03_WINDOWS_UIA_$($Phase.ToUpper())_PASS"
Write-Host $payload
if($ReceiptPath) {
  $parent=Split-Path -Parent $ReceiptPath
  New-Item -ItemType Directory -Path $parent -Force|Out-Null
  $payload|Set-Content -LiteralPath $ReceiptPath -Encoding utf8
}
