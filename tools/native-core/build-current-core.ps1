param(
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [ValidateSet('Configure','Build')][string]$Stage = 'Configure',
    [switch]$BuildBaseline,
    [string[]]$Targets = @('chrome','blink_common_unittests','blink_platform_unittests')
)
# Operates only on an already provisioned dedicated checkout. No installations,
# checkout downloads, deletions, global Git changes or machine settings.
$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'buildspec.json') -Raw | ConvertFrom-Json
$root = [IO.Path]::GetFullPath($BuildRoot)
if ($root -match '\s' -or $root -eq [IO.Path]::GetPathRoot($root)) { throw 'Use a dedicated absolute build directory without spaces.' }
$source = Join-Path $root 'chromium\src'
$depot = Join-Path $root 'depot_tools'
$localGitConfig = Join-Path $root 'gitconfig'
if (-not (Test-Path -LiteralPath $localGitConfig -PathType Leaf)) { throw 'Task-local gitconfig must be provisioned first; no user-global Git writes are allowed.' }
if (-not (Test-Path -LiteralPath (Join-Path $source '.git')) -or -not (Test-Path -LiteralPath (Join-Path $depot '.git'))) { throw 'Dedicated pinned Chromium and depot_tools checkouts must be provisioned first. See README.' }
$sourceHead = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceHead -ne $spec.chromium.commit) { throw 'Chromium HEAD does not match the exact pinned commit.' }
$depotHead = (& git -C $depot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $depotHead -ne $spec.depot_tools.commit) { throw 'depot_tools HEAD does not match its pinned commit.' }
$drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))
if ($drive.AvailableFreeSpace -le ($spec.resource_policy.os_reserve_gib * 1GB)) { throw 'The 40 GiB OS reserve has been reached. Stop without deleting user files.' }
if (-not $BuildBaseline -and @($spec.patch_contract.patch_series).Count -eq 0) { throw 'Native fingerprint patch series is not ready. Only explicit -BuildBaseline may compile unmodified Chromium.' }
$patchCheckArguments = @((Join-Path $PSScriptRoot 'verify-patch-series.py'),'--source',$source)
if ($BuildBaseline) { $patchCheckArguments += '--baseline' }
& python @patchCheckArguments
if ($LASTEXITCODE -ne 0) { throw 'Applied source and patch hashes did not pass exact verification.' }
$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'VS 2026 toolchain is missing.' }
$vsInstall = & $vswhere -latest -products '*' -version '[18.0,19.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 Microsoft.VisualStudio.Component.VC.ATLMFC -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $vsInstall) { throw 'VS 2026 C++/MFC/ATL installation not found.' }
$savedPath = $env:Path
$savedToolchain = $env:DEPOT_TOOLS_WIN_TOOLCHAIN
$savedUpdate = $env:DEPOT_TOOLS_UPDATE
$savedVs = $env:vs2026_install
$savedGitConfig = $env:GIT_CONFIG_GLOBAL
function Invoke-GuardedBuildProcess([string]$CommandLine) {
    # The PID is our new cmd wrapper, never a user's unrelated build process.
    $logDirectory = Join-Path $root 'logs'
    [IO.Directory]::CreateDirectory($logDirectory) | Out-Null
    $logPrefix = Join-Path $logDirectory ('native-' + $Stage.ToLowerInvariant() + '-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff'))
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/s','/c', $CommandLine) -WorkingDirectory $source -WindowStyle Hidden -PassThru -RedirectStandardOutput ($logPrefix + '.stdout.log') -RedirectStandardError ($logPrefix + '.stderr.log')
    Write-Output "Owned build PID $($process.Id); logs $logPrefix; live reserve $($spec.resource_policy.os_reserve_gib) GiB."
    while (-not $process.WaitForExit(2000)) {
        if ($drive.AvailableFreeSpace -le ($spec.resource_policy.os_reserve_gib * 1GB)) {
            & taskkill.exe /PID $process.Id /T /F | Out-Null
            $process.WaitForExit()
            throw 'Build stopped: live 40 GiB OS reserve reached. Only this build process tree was stopped; no files were deleted.'
        }
    }
    if ($process.ExitCode -ne 0) { throw "Native $Stage failed (exit $($process.ExitCode))." }
}
try {
    $env:Path = "$depot;$savedPath"
    $env:DEPOT_TOOLS_WIN_TOOLCHAIN = '0'
    $env:DEPOT_TOOLS_UPDATE = '0'
    $env:vs2026_install = $vsInstall
    $env:GIT_CONFIG_GLOBAL = $localGitConfig
    Push-Location -LiteralPath $source
    try {
        if ($Stage -eq 'Configure') {
            # GN accepts --args with nested quotes; use the checked argument set.
            $gnArgs = ($spec.gn_args -join ' ').Replace('"','\"')
            Invoke-GuardedBuildProcess ('""' + (Join-Path $depot 'gn.bat') + '" gen out\NeAntik "--args=' + $gnArgs + '""')
        } else {
            if ($Targets.Count -eq 0 -or @($Targets | Where-Object { $_ -notmatch '^[a-zA-Z0-9_]+$' }).Count -ne 0) { throw 'Build targets must be simple GN target names.' }
            Invoke-GuardedBuildProcess ('""' + (Join-Path $depot 'autoninja.bat') + '" -C out\NeAntik ' + ($Targets -join ' ') + ' -j' + $spec.resource_policy.jobs + '"')
        }
    } finally { Pop-Location }
} finally {
    $env:Path = $savedPath
    $env:DEPOT_TOOLS_WIN_TOOLCHAIN = $savedToolchain
    $env:DEPOT_TOOLS_UPDATE = $savedUpdate
    $env:vs2026_install = $savedVs
    $env:GIT_CONFIG_GLOBAL = $savedGitConfig
}
