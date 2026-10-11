param([Parameter(Mandatory=$true)][string]$Bootstrapper, [switch]$Execute)
$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'buildspec.json') -Raw | ConvertFrom-Json
$file = Get-Item -LiteralPath $Bootstrapper
$hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
if ($hash -ne $spec.toolchain.sdk_installer_sha256 -or $file.VersionInfo.ProductVersion -ne $spec.toolchain.sdk_installer_product_version) { throw 'SDK bootstrapper hash/version mismatch.' }
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)') { throw 'A valid Microsoft Authenticode signature is required.' }
$drive = [IO.DriveInfo]::new('C:\')
if ($drive.AvailableFreeSpace -lt 45GB) { throw 'SDK setup needs room above the 40 GiB OS reserve.' }
$log = Join-Path $file.DirectoryName 'sdk-install.log'
$arguments = @('/quiet','/norestart','/log',$log,'/features') + @($spec.toolchain.sdk_features)
if (-not $Execute) {
    [ordered]@{execute=$false;sha256=$hash;version=$file.VersionInfo.ProductVersion;signature=[string]$signature.Status;arguments=$arguments} | ConvertTo-Json -Depth 4
    exit 0
}
$process = Start-Process -FilePath $file.FullName -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
[ordered]@{execute=$true;exit_code=$process.ExitCode;reboot_required=($process.ExitCode -in @(3010,1641));log=$log;features=$spec.toolchain.sdk_features} | ConvertTo-Json -Depth 4
if ($process.ExitCode -notin @(0,3010,1641)) { exit $process.ExitCode }
