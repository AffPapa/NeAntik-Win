[CmdletBinding()]
param(
    # Every normal build now uses a new empty workspace; retained for compatibility.
    [switch]$Clean,
    [switch]$PackageOnly,
    [string]$EngineDirectory,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
. (Join-Path $projectRoot 'tools/release-helpers.ps1')
$release = Get-Content -LiteralPath (Join-Path $projectRoot 'release-version.json') -Raw | ConvertFrom-Json
$releaseVersion = [string]$release.version
if ($releaseVersion -notmatch '^\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?$') { throw 'Invalid release-version.json.' }
if ($Clean -and $PackageOnly) { throw '-Clean and -PackageOnly cannot be used together.' }
if ($PackageOnly -and $EngineDirectory) { throw '-EngineDirectory is only valid for a fresh build.' }
if ($releaseVersion -eq '0.5.0-preview' -and -not $EngineDirectory -and -not $PackageOnly) {
    throw 'NeAntik Win 0.5.0-preview requires EngineDirectory: publish only the complete Chromium portable build.'
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot 'release' }
$releaseParent = [System.IO.Path]::GetFullPath($OutputDirectory)
$releaseName = "NeAntikWin-portable-v$releaseVersion"
$releaseRoot = Join-Path $releaseParent $releaseName
$archivePath = Join-Path $releaseParent "$releaseName.zip"
Assert-ReleaseChildPath $releaseRoot $releaseParent
Assert-ReleaseChildPath $archivePath $releaseParent
foreach ($existing in @($archivePath, "$archivePath.sha256", (Join-Path $releaseParent "$releaseName.manifest.json"))) {
    if (Test-Path -LiteralPath $existing) { throw "Versioned artifacts are immutable. Choose a new version or another output directory: $existing" }
}
if (Test-Path -LiteralPath (Join-Path $releaseRoot 'Data')) { throw 'Release folder contains user Data. Use a separate output directory; user data is never removed automatically.' }
New-Item -ItemType Directory -Path $releaseParent -Force | Out-Null

if (-not $PackageOnly) {
    if (Test-Path -LiteralPath $releaseRoot) { throw "Release folder already exists. Use a new empty output directory: $releaseRoot" }
    $buildParent = Join-Path $projectRoot 'build'
    $buildRoot = Join-Path $buildParent ("package-" + [guid]::NewGuid().ToString('N'))
    Assert-ReleaseChildPath $buildRoot $buildParent
    $sourceRoot = Join-Path $buildRoot 'source'
    $distRoot = Join-Path $buildRoot 'dist'
    $workRoot = Join-Path $buildRoot 'work'
    $metadataRoot = Join-Path $buildRoot 'metadata'
    New-Item -ItemType Directory -Path $sourceRoot, $workRoot -Force | Out-Null
    Write-Output "Isolated build workspace: $buildRoot"
    $sourceItems = @('nevision_win.py', 'profile_identity.py', 'release-version.json', 'requirements-build.txt', 'assets',
        'README.md', 'SECURITY_AND_SCOPE.md', 'ARCHITECTURE.md', 'RELEASE_CHECKLIST.md', 'CHANGELOG.md', 'THIRD_PARTY_NOTICES.md')
    foreach ($relative in $sourceItems) {
        $source = Join-Path $projectRoot $relative
        if (-not (Test-Path -LiteralPath $source)) { throw "Required release input missing: $relative" }
        $sourceEntries = @((Get-Item -LiteralPath $source -Force)) + @(Get-ChildItem -LiteralPath $source -Recurse -Force -ErrorAction SilentlyContinue)
        if ($sourceEntries | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }) { throw "Release source contains a reparse point: $relative" }
        Copy-Item -LiteralPath $source -Destination $sourceRoot -Recurse
    }
    & python (Join-Path $projectRoot 'tools/prepare-build-metadata.py') --version-file (Join-Path $sourceRoot 'release-version.json') --output $metadataRoot
    if ($LASTEXITCODE -ne 0) { throw "Metadata preparation failed (exit $LASTEXITCODE). No release was packaged." }
    $assetsRoot = Join-Path $sourceRoot 'assets'
    $frozenVersion = Join-Path $sourceRoot 'release-version.json'
    & python -m PyInstaller --noconfirm --clean --noupx --onedir --windowed `
        --name NeAntikWin --icon (Join-Path $assetsRoot 'nevision.ico') `
        --version-file (Join-Path $metadataRoot 'windows-version-info.txt') `
        --add-data "$assetsRoot;assets" --add-data "$frozenVersion;." --hidden-import win32crypt `
        --distpath $distRoot --workpath $workRoot --specpath $workRoot (Join-Path $sourceRoot 'nevision_win.py')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE). No release packaged; inspect $buildRoot" }
    $builtRoot = Join-Path $distRoot 'NeAntikWin'
    Assert-ReleaseExeVersion (Join-Path $builtRoot 'NeAntikWin.exe') $release
    Copy-Item -LiteralPath $builtRoot -Destination $releaseRoot -Recurse
    foreach ($relative in $sourceItems | Where-Object { $_ -like '*.md' -or $_ -eq 'release-version.json' }) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $relative) -Destination (Join-Path $releaseRoot $relative)
    }
    Copy-Item -LiteralPath (Join-Path $metadataRoot 'licenses') -Destination $releaseRoot -Recurse
    Copy-Item -LiteralPath (Join-Path $metadataRoot 'runtime-components.json') -Destination $releaseRoot
    if ($EngineDirectory) {
        $engineSource = (Resolve-Path -LiteralPath $EngineDirectory -ErrorAction Stop).Path
        $engineItem = Get-Item -LiteralPath $engineSource -Force
        if (-not $engineItem.PSIsContainer -or ($engineItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw 'EngineDirectory must be a real directory.' }
        $engineEntries = @(Get-ChildItem -LiteralPath $engineSource -Recurse -Force)
        if ($engineEntries | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }) { throw 'EngineDirectory contains a reparse point.' }
        foreach ($required in @('chrome.exe', 'chrome.dll', 'icudtl.dat', 'resources.pak', 'LICENSE', 'credits.html', 'ENGINE_PROVENANCE.json')) {
            if (-not (Test-Path -LiteralPath (Join-Path $engineSource $required) -PathType Leaf)) { throw "Browser engine is missing $required" }
        }
        $engineReceipt = Get-Content -LiteralPath (Join-Path $engineSource 'ENGINE_PROVENANCE.json') -Raw | ConvertFrom-Json
        if ($engineReceipt.format -notin @('neantik-chromium-snapshot-stage-v1', 'neantik-chromium-source-build-v1')) { throw 'Unknown browser engine provenance format.' }
        if ($engineReceipt.format -eq 'neantik-chromium-snapshot-stage-v1' -and $engineReceipt.channel -eq 'stable') { throw 'A continuous snapshot cannot claim the stable channel.' }
        if ($engineReceipt.format -eq 'neantik-chromium-source-build-v1' -and $engineReceipt.channel -ne 'stable') { throw 'A stable source build has inconsistent provenance.' }
        if ($engineReceipt.channel -ne 'stable' -and $releaseVersion -notmatch '-dev$') { throw 'A non-stable Chromium snapshot can only be packaged in a local -dev build.' }
        $actualCoreVersion = (Get-Item -LiteralPath (Join-Path $engineSource 'chrome.exe')).VersionInfo.ProductVersion
        if ($actualCoreVersion -ne $engineReceipt.chromium_version) { throw 'Browser engine version does not match its provenance.' }
        $actualCreditsHash = (Get-FileHash -LiteralPath (Join-Path $engineSource 'credits.html') -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualCreditsHash -ne $engineReceipt.credits_sha256) { throw 'Browser engine credits do not match provenance.' }
        if ($engineReceipt.format -eq 'neantik-chromium-source-build-v1') {
            foreach ($required in @('chrome_elf.dll', "$($engineReceipt.chromium_version).manifest", 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
                if (-not (Test-Path -LiteralPath (Join-Path $engineSource $required) -PathType Leaf)) { throw "Source-built browser engine is missing $required" }
            }
            if ($engineReceipt.source_commit -notmatch '^[0-9a-f]{40}$' -or $engineReceipt.source_tree -notmatch '^[0-9a-f]{40}$' -or
                $engineReceipt.build_args_sha256 -notmatch '^[0-9a-f]{64}$' -or
                ($engineReceipt.build_patch_sha256 -and $engineReceipt.build_patch_sha256 -notmatch '^[0-9a-f]{64}$')) { throw 'Source-built browser provenance is incomplete.' }
            $actualLicenseHash = (Get-FileHash -LiteralPath (Join-Path $engineSource 'LICENSE') -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actualLicenseHash -ne $engineReceipt.license_sha256) { throw 'Browser engine license does not match provenance.' }
        }
        $engineParent = Join-Path $releaseRoot 'Engine'
        New-Item -ItemType Directory -Path $engineParent | Out-Null
        Copy-Item -LiteralPath $engineSource -Destination (Join-Path $engineParent 'Chromium') -Recurse
    }
    $sourceFiles = @(Get-ReleaseTreeManifest $sourceRoot)
    $sourceHash = Get-ReleaseTextHash ($sourceFiles | ConvertTo-Json -Depth 5 -Compress)
    $commit = & git -C $projectRoot rev-parse --quiet --verify HEAD
    if ($LASTEXITCODE -ne 0) { $commit = $null }
    $gitStatus = & git -C $projectRoot status --porcelain --untracked-files=normal
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read source Git state.' }
    $sourceState = if (-not $commit) { 'uncommitted' } elseif ($gitStatus) { 'modified' } else { 'clean' }
    Write-ReleaseJson ([ordered]@{ source_commit = $commit; source_state = $sourceState; source_tree_sha256 = $sourceHash; source_files = $sourceFiles }) (Join-Path $releaseRoot 'build-provenance.json')
}

$exePath = Join-Path $releaseRoot 'NeAntikWin.exe'
Assert-ReleaseExeVersion $exePath $release
$packagedVersion = Get-Content -LiteralPath (Join-Path $releaseRoot '_internal/release-version.json') -Raw | ConvertFrom-Json
if ($packagedVersion.version -ne $releaseVersion) { throw 'Bundled application version disagrees with release.' }
$provenance = Get-Content -LiteralPath (Join-Path $releaseRoot 'build-provenance.json') -Raw | ConvertFrom-Json
$runtime = Get-Content -LiteralPath (Join-Path $releaseRoot 'runtime-components.json') -Raw | ConvertFrom-Json
$hasEngine = Test-Path -LiteralPath (Join-Path $releaseRoot 'Engine/Chromium/chrome.exe') -PathType Leaf
if ($hasEngine) {
    $engineReceipt = Get-Content -LiteralPath (Join-Path $releaseRoot 'Engine/Chromium/ENGINE_PROVENANCE.json') -Raw | ConvertFrom-Json
} elseif (Test-Path -LiteralPath (Join-Path $releaseRoot 'Engine')) {
    throw 'Incomplete browser engine folder.'
}
$files = @(Get-ReleaseTreeManifest $releaseRoot @('release-manifest.json', 'SHA256SUMS.txt'))
$manifest = [ordered]@{
    format = 'nevision-release-v1'; product = 'NeAntik Win'; executable = 'NeAntikWin.exe'; version = $releaseVersion; channel = $release.channel
    built_at_utc = [DateTime]::UtcNow.ToString('o'); architecture = 'x64'
    source_commit = $provenance.source_commit; source_state = $provenance.source_state; source_tree_sha256 = $provenance.source_tree_sha256
    operating_systems = @('Windows x64')
    tested_os = 'Windows 11 Pro x64 10.0.26200'; unverified_os = @('Windows 10', 'Windows ARM64')
    browser_strategy = if ($hasEngine) { 'Portable local profile manager with bundled unbranded Chromium; installed Chrome or Edge remains available for older pinned profiles. No fingerprint modification.' } else { 'Portable local profile manager; launches installed stock Chrome or Edge. No browser engine or fingerprint modification is included.' }
    native_core_bundled = [bool]$hasEngine
    fingerprint_modification = $false
    schema_version = '1'; backup_format = 'nevision-profile-backup-v1 (ordinary profiles only)'
    signature_status = [string](Get-AuthenticodeSignature -LiteralPath $exePath).Status
    release_notes = 'CHANGELOG.md'; runtime = $runtime; files = $files
}
if ($hasEngine) {
    $manifest.engine = [ordered]@{ name = 'Chromium'; version = [string]$engineReceipt.chromium_version; channel = [string]$engineReceipt.channel; source_commit = [string]$engineReceipt.source_commit; provenance_format = [string]$engineReceipt.format }
    if ($engineReceipt.format -eq 'neantik-chromium-snapshot-stage-v1') { $manifest.engine.snapshot_sha256 = [string]$engineReceipt.snapshot_sha256 }
    else { $manifest.engine.source_tree = [string]$engineReceipt.source_tree; $manifest.engine.build_args_sha256 = [string]$engineReceipt.build_args_sha256; $manifest.engine.build_patch_sha256 = [string]$engineReceipt.build_patch_sha256 }
}
Write-ReleaseJson $manifest (Join-Path $releaseRoot 'release-manifest.json')
$hashLines = @($files | ForEach-Object { "$($_.sha256)  $($_.path)" })
[System.IO.File]::WriteAllLines((Join-Path $releaseRoot 'SHA256SUMS.txt'), $hashLines, [System.Text.UTF8Encoding]::new($false))
# Test a separate extracted copy. GUI startup must not populate the shipping folder.
$partialArchivePath = Join-Path $releaseParent (".$releaseName." + [guid]::NewGuid().ToString('N') + '.partial.zip')
Assert-ReleaseChildPath $partialArchivePath $releaseParent
Compress-Archive -LiteralPath $releaseRoot -DestinationPath $partialArchivePath -CompressionLevel Optimal
& (Join-Path $projectRoot 'tools/verify-release-archive.ps1') -ArchivePath $partialArchivePath
# Publishing the final filename is the last step after archive integrity validation.
Move-Item -LiteralPath $partialArchivePath -Destination $archivePath -ErrorAction Stop
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText("$archivePath.sha256", "$archiveHash  $releaseName.zip`n", [System.Text.Encoding]::ASCII)
$manifest.archive = [ordered]@{ filename = "$releaseName.zip"; size_bytes = (Get-Item -LiteralPath $archivePath).Length; sha256 = $archiveHash; download_url = $null }
Write-ReleaseJson $manifest (Join-Path $releaseParent "$releaseName.manifest.json")
Write-Output "Portable archive: $archivePath"
Write-Output "Archive SHA-256: $archiveHash"
Write-Output 'Next: unpack separately, run EXE self-test and GUI smoke, verify public download, then update the site.'
