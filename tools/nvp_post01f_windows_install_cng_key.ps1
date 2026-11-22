# POST-01F Windows installation-time SCM signer provisioning, NOT a worker command.
# Must run once as trusted installer admin. Never rotate or export a private key.
# Actual physical Windows owner acceptance and restore/upgrade policy OPEN.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
  throw 'Native Windows installation only'
}
$id=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Trusted administrator is required to provision the SCM machine signer'
}
$keyName='NVP-POST01F-LTX-SCM-PICTURE-P256-v2'
$trustKey='HKLM:\SOFTWARE\NVP\POST01F\SignerTrust'
$namespace='nvp.post01f.scm_cng_p256_picture_result.v2'
$provider=[Security.Cryptography.CngProvider]::MicrosoftSoftwareKeyStorageProvider
$existing=$null
try {
  $existing=[Security.Cryptography.CngKey]::Open($keyName,$provider,
      [Security.Cryptography.CngKeyOpenOptions]::MachineKey)
} catch [Security.Cryptography.CryptographicException] {
  # Absence is expected on first authorized install; other native failures
  # will independently refuse the subsequent machine-key creation.
}
if ($null -ne $existing) {
  $existing.Dispose()
  throw 'Machine key already exists: never replace, rekey, downgrade or silently rotate'
}
if (Test-Path -LiteralPath $trustKey) {
  throw 'Pinned SCM trust already exists: installation cannot overwrite trust anchor'
}
$options=[Security.Cryptography.CngKeyCreationParameters]::new()
$options.Provider=$provider
$options.KeyCreationOptions=[Security.Cryptography.CngKeyCreationOptions]::MachineKey
$options.ExportPolicy=[Security.Cryptography.CngExportPolicies]::None
$options.KeyUsage=[Security.Cryptography.CngKeyUsages]::Signing
$key=[Security.Cryptography.CngKey]::Create(
    [Security.Cryptography.CngAlgorithm]::ECDsaP256,$keyName,$options)
try {
  $privateFile=Join-Path $env:ProgramData ('Microsoft\Crypto\Keys\'+$key.UniqueName)
  if (-not (Test-Path -LiteralPath $privateFile -PathType Leaf)) {
    throw 'Cannot find non-exportable machine KSP key to enforce its ACL'
  }
  # No user/AppContainer/desktop account receives machine private-key read.
  & icacls.exe $privateFile /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F'
  if ($LASTEXITCODE -ne 0) { throw 'SCM-only machine key ACL confinement failed' }
  $ec=[Security.Cryptography.ECDsaCng]::new($key)
  try {
    $p=$ec.ExportParameters($false)
    if ($p.Q.X.Length -ne 32 -or $p.Q.Y.Length -ne 32) {
      throw 'Noncanonical P-256 signer public key'
    }
    [byte[]]$bytes=@(4)+@($p.Q.X)+@($p.Q.Y)
    $pubHex=[Convert]::ToHexString($bytes).ToLowerInvariant()
    if ($pubHex.Length -ne 130) { throw 'Invalid machine key public point length' }
  } finally { $ec.Dispose() }
  New-Item -Path $trustKey -Force -ErrorAction Stop | Out-Null
  New-ItemProperty -Path $trustKey -Name 'Format' -Value $namespace -PropertyType String -Force | Out-Null
  New-ItemProperty -Path $trustKey -Name 'PublicP256X962Hex' -Value $pubHex -PropertyType String -Force | Out-Null
  Write-Output 'NVP POST01F native SCM signer machine public key installed and pinned; no private material exported.'
} catch {
  # Fail closed: intentionally do not delete possibly half-created key or
  # trust; explicit audited recovery is required, not an automatic retry.
  throw
} finally {
  $key.Dispose()
}
