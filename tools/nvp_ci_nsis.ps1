# CI-only provisioning. Never select a compiler supplied by a film/project.
# The actual Windows installer smoke test remains mandatory.
Set-StrictMode -Version Latest

function Get-NvpNsisCompiler {
    if (-not $IsWindows) { throw 'Windows NSIS compiler qualification requires Windows' }
    $candidates = @(
        (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'NSIS/makensis.exe'),
        (Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'NSIS/makensis.exe')
    )
    foreach ($path in $candidates) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $item = Get-Item -LiteralPath $path
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Refusing linked NSIS compiler'
        }
        $PSNativeCommandUseErrorActionPreference = $false
        $version = & $item.FullName '/VERSION' 2>&1
        if ($LASTEXITCODE -ne 0 -or (($version -join ' ') -notmatch 'v?3\.[0-9]+')) {
            throw 'Installed NSIS compiler failed version qualification'
        }
        Write-Host "NSIS compiler: $($item.FullName) version $version"
        return $item.FullName
    }
    return $null
}

function Invoke-NvpNsisProvisioning {
    # Injected callbacks are confined to this build helper and its unit tests.
    param(
        [Parameter(Mandatory)][scriptblock]$Probe,
        [Parameter(Mandatory)][scriptblock]$Install,
        [Parameter(Mandatory)][scriptblock]$Delay,
        [ValidateRange(1,3)][int]$Attempts = 3
    )
    $compiler = & $Probe
    if ($compiler) { return $compiler }
    for ($i=1; $i -le $Attempts; $i++) {
        $rc = & $Install
        if ($rc -isnot [int]) { throw 'NSIS installer did not return a bounded exit code' }
        if ($rc -eq 0) {
            $compiler = & $Probe
            if ($compiler) { return $compiler }
        }
        Write-Host "NSIS provisioning attempt $i/$Attempts failed (exit $rc); no package authorized."
        if ($i -lt $Attempts) { & $Delay ($i*15) }
    }
    throw 'NSIS dependency unavailable after bounded retries; installed acceptance blocked'
}

function Install-NvpCiNsis {
    if (-not $IsWindows) { throw 'NSIS provisioning requires Windows' }
    Invoke-NvpNsisProvisioning -Probe { Get-NvpNsisCompiler } -Install {
        if (-not $env:ChocolateyInstall) { throw 'Trusted Chocolatey installation missing' }
        $choco = Join-Path $env:ChocolateyInstall 'bin/choco.exe'
        if (-not (Test-Path -LiteralPath $choco -PathType Leaf)) { throw 'Trusted Chocolatey executable missing' }
        $PSNativeCommandUseErrorActionPreference = $false
        # Same version attempted by the failed workflow. Do not silently change tool versions during retry.
        & $choco install nsis --version=3.13.0 -y --no-progress | Out-Host
        return [int]$LASTEXITCODE
    } -Delay { param($seconds) Start-Sleep -Seconds $seconds }
}
