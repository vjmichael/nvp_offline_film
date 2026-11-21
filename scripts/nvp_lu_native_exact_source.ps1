# NVP-owned Windows MSVC Rust/prost acceptance against exact upstream source.
param([Parameter(Mandatory=$true)][string]$LuRepo)
$ErrorActionPreference='Stop'
$expected='9f43d078aa5e979de0ff72ca4c19e8c5829572af'
$expectedProto='4e01d921197fb1c58c99958479b1cede36e13c9a'
$relative='src-tauri/lu-core/proto/lu/workspace/v0/workspace.proto'
if (-not [System.Environment]::OSVersion.Platform.Equals([System.PlatformID]::Win32NT)) {
    throw 'BLOCKED: this admission script must run on actual Windows'
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'BLOCKED: git absent' }
if (-not (Test-Path -LiteralPath (Join-Path $LuRepo '.git'))) { throw 'BLOCKED: complete pinned Lu checkout missing' }
$actual=(& git -C $LuRepo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actual -cne $expected) { throw 'DENIED: Lu exact-source commit mismatch' }
$blob=(& git -C $LuRepo rev-parse "HEAD:$relative").Trim()
if ($LASTEXITCODE -ne 0 -or $blob -cne $expectedProto) { throw 'DENIED: Lu workspace.proto Git blob mismatch' }
& git -C $LuRepo diff --quiet -- $relative
if ($LASTEXITCODE -ne 0) { throw 'DENIED: modified Lu workspace.proto' }
$env:LU_WORKSPACE_PROTO=Join-Path $LuRepo ($relative -replace '/', '\')
if (-not (Test-Path -LiteralPath $env:LU_WORKSPACE_PROTO -PathType Leaf)) { throw 'DENIED: Lu schema missing' }
if (-not (Get-Command cargo -ErrorAction SilentlyContinue) -or -not (Get-Command rustc -ErrorAction SilentlyContinue)) {
    throw 'BLOCKED: native Windows Rust toolchain unavailable'
}
$root=Split-Path -Parent $PSScriptRoot
$crate=Join-Path $root 'native/nvp_lu_ipc_client'
if (-not (Test-Path -LiteralPath (Join-Path $crate 'Cargo.lock') -PathType Leaf)) {
    throw 'BLOCKED: reviewed NVP Cargo.lock missing; no invented --locked acceptance'
}
Push-Location $crate
try {
    & cargo test --locked --offline --all-targets
    if ($LASTEXITCODE -ne 0) { throw 'FAILED: genuine Windows Rust/prost qualification' }
    Write-Output "NVP_NATIVE_WINDOWS_RUST_PROST_PASS Lu=$actual Proto=$blob (NOT signed installed Lu/NVP Health)"
} finally { Pop-Location }
