param(
    [string]$BuildRoot = 'C:\NeAntikCoreBuild',
    [switch]$RequireReady
)
$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'buildspec.json') -Raw | ConvertFrom-Json
$absoluteRoot = [IO.Path]::GetFullPath($BuildRoot)
$drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($absoluteRoot))
$hostInfo = Get-CimInstance Win32_ComputerSystem
$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$visualStudio = $null
if (Test-Path -LiteralPath $vswhere) {
    $vsOutput = & $vswhere -latest -products '*' -version '[18.0,19.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 Microsoft.VisualStudio.Component.VC.ATLMFC -format json
    if ($LASTEXITCODE -eq 0 -and $vsOutput) {
        $visualStudio = @($vsOutput | ConvertFrom-Json) | Where-Object { $_.installationPath } | Select-Object -First 1
    }
}
$sdkRoot = 'C:\Program Files (x86)\Windows Kits\10'
$sdkRc = Join-Path $sdkRoot 'bin\10.0.28000.0\x64\rc.exe'
$debugger = Join-Path $sdkRoot 'Debuggers\x64\cdb.exe'
$sdkVersion = if (Test-Path -LiteralPath $sdkRc) { (Get-Item -LiteralPath $sdkRc).VersionInfo.FileVersion } else { $null }
$debuggerVersion = if (Test-Path -LiteralPath $debugger) { (Get-Item -LiteralPath $debugger).VersionInfo.FileVersion } else { $null }
$missing = [Collections.Generic.List[string]]::new()
if ($drive.DriveFormat -ne 'NTFS') { $missing.Add('NTFS build drive required') }
if ($absoluteRoot -match '\s') { $missing.Add('Build path must not contain spaces') }
$sourceDownloaded = Test-Path -LiteralPath (Join-Path $absoluteRoot 'chromium\src\.git')
$requiredFreeGiB = if ($sourceDownloaded) { $spec.resource_policy.minimum_free_gib_before_build } else { $spec.resource_policy.minimum_free_gib_before_checkout }
if ($drive.AvailableFreeSpace -lt ($requiredFreeGiB * 1GB)) { $missing.Add("Less than $requiredFreeGiB GiB required for the current build phase remains") }
if ($hostInfo.TotalPhysicalMemory -lt ($spec.resource_policy.memory_gib_minimum * 1GB)) { $missing.Add('Project memory minimum not met') }
if (-not $visualStudio) { $missing.Add('VS 2026 x64 C++ tools and MFC/ATL not found') }
if (-not $sdkVersion) { $missing.Add('Windows SDK 28000 RC tool not found; exact 28000.2270 install must be recorded') }
if (-not $debuggerVersion) { $missing.Add('Windows SDK x64 debugging tools not found') }
if ($sdkVersion -and [version]($sdkVersion.Split(' ')[0]) -lt [version]$spec.toolchain.sdk_version) { $missing.Add('Installed SDK is below the pinned SDK requirement') }
if ($debuggerVersion -and [version]($debuggerVersion.Split(' ')[0]) -lt [version]$spec.toolchain.sdk_debugger_minimum) { $missing.Add('Installed debugging tools are below the pinned requirement') }
if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { $missing.Add('Git not found') }
$report = [ordered]@{
    build_ready = ($missing.Count -eq 0)
    build_root = $absoluteRoot
    filesystem = $drive.DriveFormat
    free_gib = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    ram_gib = [math]::Round($hostInfo.TotalPhysicalMemory / 1GB, 1)
    logical_processors = $hostInfo.NumberOfLogicalProcessors
    chromium_version = $spec.chromium.version
    chromium_commit = $spec.chromium.commit
    visual_studio = $visualStudio
    sdk_rc_file_version = $sdkVersion
    debugger_file_version = $debuggerVersion
    missing = @($missing)
    source_downloaded = $sourceDownloaded
    toolchain_installed_by_script = $false
}
$report | ConvertTo-Json -Depth 6
if ($RequireReady -and $missing.Count -gt 0) { exit 2 }
