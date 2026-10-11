param(
    [Parameter(Mandatory=$true)][string]$Bootstrapper,
    [string]$InstallPath = 'C:\NeAntikToolchain\VS2026',
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'buildspec.json') -Raw | ConvertFrom-Json
$bootstrapperFile = Get-Item -LiteralPath $Bootstrapper
if ($bootstrapperFile.PSIsContainer) { throw 'Bootstrapper must be a file.' }
$hash = (Get-FileHash -LiteralPath $bootstrapperFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -ne $spec.toolchain.bootstrapper_sha256) { throw 'Bootstrapper SHA-256 does not match the pinned Microsoft download.' }
$signature = Get-AuthenticodeSignature -LiteralPath $bootstrapperFile.FullName
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)') { throw 'A valid Microsoft Authenticode signature is required.' }
if ($bootstrapperFile.VersionInfo.ProductVersion -ne $spec.toolchain.visual_studio_reference_version) { throw 'Bootstrapper ProductVersion differs from the pinned VS release.' }
$absoluteInstall = [IO.Path]::GetFullPath($InstallPath)
if ($absoluteInstall -match '\s' -or $absoluteInstall -eq [IO.Path]::GetPathRoot($absoluteInstall)) { throw 'Use a dedicated installation directory without spaces.' }
$drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($absoluteInstall))
if ($drive.AvailableFreeSpace -lt 60GB) { throw 'Allow at least 20 GiB for toolchain setup plus the 40 GiB OS reserve.' }
$arguments = @('--quiet','--wait','--norestart','--installPath',$absoluteInstall,'--add',$spec.toolchain.build_tools_workload)
foreach ($component in $spec.toolchain.components) { $arguments += @('--add',$component) }
$arguments += '--includeRecommended'
if (-not $Execute) {
    [ordered]@{execute=$false;bootstrapper=$bootstrapperFile.FullName;sha256=$hash;signature=[string]$signature.Status;product_version=$bootstrapperFile.VersionInfo.ProductVersion;arguments=$arguments;free_gib=[math]::Round($drive.AvailableFreeSpace/1GB,1)} | ConvertTo-Json -Depth 4
    exit 0
}
# User has authorized installation. No automatic reboot, uninstall or force-close.
$process = Start-Process -FilePath $bootstrapperFile.FullName -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
[ordered]@{execute=$true;exit_code=$process.ExitCode;reboot_required=($process.ExitCode -in @(3010,1641));install_path=$absoluteInstall;sha256=$hash} | ConvertTo-Json
if ($process.ExitCode -notin @(0,3010,1641)) { exit $process.ExitCode }
