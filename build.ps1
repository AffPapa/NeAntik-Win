[CmdletBinding()]
param(
    # Every normal build now uses a new empty workspace; retained for compatibility.
    [switch]$Clean,
    [switch]$PackageOnly,
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
if (Test-Path -LiteralPath (Join-Path $releaseRoot 'Engine')) { throw 'This edition is ordinary-browser-only; custom browser engines are not accepted in the release.' }
$files = @(Get-ReleaseTreeManifest $releaseRoot @('release-manifest.json', 'SHA256SUMS.txt'))
$manifest = [ordered]@{
    format = 'nevision-release-v1'; product = 'NeAntik Win'; executable = 'NeAntikWin.exe'; version = $releaseVersion; channel = $release.channel
    built_at_utc = [DateTime]::UtcNow.ToString('o'); architecture = 'x64'
    source_commit = $provenance.source_commit; source_state = $provenance.source_state; source_tree_sha256 = $provenance.source_tree_sha256
    operating_systems = @('Windows x64')
    tested_os = 'Windows 11 Pro x64 10.0.26200'; unverified_os = @('Windows 10', 'Windows ARM64')
    browser_strategy = 'Portable local profile manager; launches installed stock Chrome or Edge. No custom engine or fingerprint modification is included.'
    native_core_bundled = $false
    fingerprint_modification = $false
    schema_version = '1'; backup_format = 'nevision-profile-backup-v1 (ordinary profiles only)'
    signature_status = [string](Get-AuthenticodeSignature -LiteralPath $exePath).Status
    release_notes = 'CHANGELOG.md'; runtime = $runtime; files = $files
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
