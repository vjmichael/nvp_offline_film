$ErrorActionPreference='Stop'
. "$PSScriptRoot/nvp_ci_nsis.ps1"
function Assert-Equal($actual,$expected) { if ($actual -ne $expected) { throw "Expected $expected, got $actual" } }
$script:count=0
$r=Invoke-NvpNsisProvisioning -Probe {'existing'} -Install {throw 'must not download'} -Delay {throw 'must not delay'}
Assert-Equal $r 'existing'; Write-Host 'PASS existing compiler; no download'
$script:count=0;$script:waits=0
$r=Invoke-NvpNsisProvisioning -Probe {if($script:count -eq 2){'compiler'}} -Install {$script:count++;if($script:count -eq 1){1}else{0}} -Delay {param($sec) $script:waits++;Assert-Equal $sec 15}
Assert-Equal $r 'compiler';Assert-Equal $script:count 2;Assert-Equal $script:waits 1;Write-Host 'PASS transient package failure recovered'
$script:count=0;$script:waits=0;$failed=$false
try { $null=Invoke-NvpNsisProvisioning -Probe {$null} -Install {$script:count++;1} -Delay {$script:waits++} } catch { if($_.Exception.Message -notmatch 'bounded retries'){throw};$failed=$true }
Assert-Equal $failed $true;Assert-Equal $script:count 3;Assert-Equal $script:waits 2;Write-Host 'PASS exhausted retries fail closed'
$script:count=0;$failed=$false
try { $null=Invoke-NvpNsisProvisioning -Probe {$null} -Install {$script:count++;0} -Delay {} } catch { if($_.Exception.Message -notmatch 'bounded retries'){throw};$failed=$true }
Assert-Equal $failed $true;Assert-Equal $script:count 3;Write-Host 'PASS successful package status without compiler fails closed'
$failed=$false
try { $null=Invoke-NvpNsisProvisioning -Probe {throw 'untrusted compiler'} -Install {throw 'must not replace'} -Delay {} } catch { if($_.Exception.Message -ne 'untrusted compiler'){throw};$failed=$true }
Assert-Equal $failed $true;Write-Host 'PASS invalid compiler is not silently replaced'
