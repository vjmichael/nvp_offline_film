# Public synthetic CI provisioning only; no private film execution authority.
Set-StrictMode -Version Latest
function Get-NvpCiBlender {
    if (-not $IsWindows) { throw 'Blender provisioning requires Windows' }
    $root = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'Blender Foundation'
    $folder = Join-Path $root 'Blender 5.3'
    $path = Join-Path $folder 'blender.exe'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    foreach ($entry in @($root,$folder,$path)) {
        if ((Get-Item -LiteralPath $entry -ErrorAction Stop).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked Blender installation refused' }
    }
    $PSNativeCommandUseErrorActionPreference = $false
    $version = & $path '--version' 2>&1
    if ($LASTEXITCODE -ne 0 -or (($version -join "`n") -notmatch '(?m)^Blender 5\.3\.0(?:\s|$)')) { throw 'Unexpected Blender binary version' }
    Write-Host "Qualified public CI Blender 5.3.0 at $path"
    return $path
}
function Invoke-NvpBlenderProvisioning {
    param([Parameter(Mandatory)][scriptblock]$Probe,[Parameter(Mandatory)][scriptblock]$Install,[Parameter(Mandatory)][scriptblock]$Delay,[ValidateRange(1,3)][int]$Attempts=3)
    $bin = & $Probe
    if ($bin) { return $bin }
    for ($i=1;$i -le $Attempts;$i++) {
        $rc = & $Install
        if ($rc -isnot [int]) { throw 'Invalid package installer exit status' }
        if ($rc -eq 0) {
            $bin = & $Probe
            if ($bin) { return $bin }
        }
        Write-Host "Blender provision attempt $i/$Attempts failed (exit $rc)"
        if ($i -lt $Attempts) { & $Delay ($i*15) }
    }
    throw 'Blender unavailable after bounded retries; actual render gate blocked'
}
function Install-NvpCiBlender {
    if (-not $IsWindows) { throw 'Blender provisioning requires Windows' }
    Invoke-NvpBlenderProvisioning -Probe { Get-NvpCiBlender } -Install {
        if (-not $env:ChocolateyInstall) { throw 'Chocolatey installation missing' }
        $choco=Join-Path $env:ChocolateyInstall 'bin/choco.exe'
        if (-not (Test-Path -LiteralPath $choco -PathType Leaf)) { throw 'Chocolatey executable missing' }
        $PSNativeCommandUseErrorActionPreference = $false
        # Pin the same version that passed the predecessor and failed to fetch.
        & $choco install blender --version=5.3.0 --no-progress -y --limit-output | Out-Host
        return [int]$LASTEXITCODE
    } -Delay { param($seconds) Start-Sleep -Seconds $seconds }
}
