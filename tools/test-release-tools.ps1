[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'release-helpers.ps1')
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('nevision-release-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$script:passed = 0

function Expect-Failure([string]$Name, [scriptblock]$Action, [string]$Pattern) {
    try { & $Action; throw "Test unexpectedly accepted: $Name" }
    catch {
        if ($_.Exception.Message -notmatch $Pattern) { throw "${Name}: wrong failure: $($_.Exception.Message)" }
        Write-Output "PASS $Name"
        $script:passed++
    }
}

function New-TestArchive([string]$Mode) {
    $folder = 'NeVisionWin-portable-v0.2.0-preview'
    $version = '{"version":"0.2.0-preview","file_version":[0,2,0,0],"channel":"preview"}'
    $payload = [ordered]@{
        'NeVisionWin.exe' = 'fixture executable, never launched'
        'release-version.json' = $version
        '_internal/release-version.json' = $version
        'build-provenance.json' = '{}'
        'runtime-components.json' = '{"licenses":["Python-LICENSE.txt","Tcl-license.terms","Tk-license.terms","OpenSSL-LICENSE.txt"]}'
        'CHANGELOG.md' = '# release fixture'
        'THIRD_PARTY_NOTICES.md' = '# notice fixture'
        'licenses/Python-LICENSE.txt' = 'Python license fixture'
        'licenses/Tcl-license.terms' = 'Tcl license fixture'
        'licenses/Tk-license.terms' = 'Tk license fixture'
        'licenses/OpenSSL-LICENSE.txt' = 'OpenSSL license fixture'
    }
    if ($Mode -eq 'secret') { $payload['CHANGELOG.md'] = 'ghp_' + ('a' * 32) }
    $nativeMode = $Mode.StartsWith('native')
    if ($nativeMode) {
        $coreFiles = [ordered]@{}
        foreach ($member in @('chrome.exe', 'chrome.dll', 'LICENSE', 'credits.html',
            'THIRD_PARTY_LICENSES.txt', 'DEPENDENCY_RECEIPT.json', 'BUILD_PROVENANCE.json')) {
            $payload["Engine/NeAntikChromium/$member"] = "Synthetic native fixture $member; never launched"
            $coreFiles[$member] = Get-ReleaseTextHash $payload["Engine/NeAntikChromium/$member"]
        }
        if ($Mode -eq 'native-valid') {
            $runtimePath = 'gen/third_party/devtools-frontend/src/front_end/models/logs/bundle.stamp'
            $payload["Engine/NeAntikChromium/$runtimePath"] = 'Required Chromium runtime resource fixture'
            $coreFiles[$runtimePath] = Get-ReleaseTextHash $payload["Engine/NeAntikChromium/$runtimePath"]
        }
        if ($Mode -eq 'native-hash') { $coreFiles['chrome.dll'] = '0' * 64 }
        if ($Mode -eq 'native-path') { $coreFiles['../escape'] = '0' * 64 }
        if ($Mode -eq 'native-license') { $coreFiles.Remove('credits.html'); $payload.Remove('Engine/NeAntikChromium/credits.html') }
        if ($Mode -eq 'native-unlisted') { $payload['Engine/NeAntikChromium/unlisted.pak'] = 'not in core inventory' }
        $coreManifest = [ordered]@{ format = 'neantik-native-core-v1'; engine_id = 'neantik-chromium';
            version = '155.0.8059.40'; source_commit = 'cfaadc5a132d78e1828635aa8405a499f3e14864'; schema = 1; files = $coreFiles }
        if ($Mode -eq 'native-identity') { $coreManifest.source_commit = '0' * 40 }
        if ($Mode -eq 'native-schema-string') { $coreManifest.schema = '1' }
        if ($Mode -eq 'native-schema-fraction') { $coreManifest.schema = 1.5 }
        if ($Mode -eq 'native-schema-bool') { $coreManifest.schema = $true }
        $payload['Engine/NeAntikChromium/core-manifest.json'] = $coreManifest | ConvertTo-Json -Depth 8 -Compress
    }
    $files = @($payload.Keys | ForEach-Object { [ordered]@{ path = $_; size_bytes = [System.Text.Encoding]::UTF8.GetByteCount($payload[$_]); sha256 = Get-ReleaseTextHash $payload[$_] } })
    $manifest = [ordered]@{ format = 'nevision-release-v1'; version = '0.2.0-preview'; files = $files }
    if ($nativeMode) {
        $manifest.native_core_bundled = $true
        $manifest.engine = [ordered]@{ engine_id = 'neantik-chromium'; version = '155.0.8059.40';
            source_commit = 'cfaadc5a132d78e1828635aa8405a499f3e14864';
            manifest_sha256 = Get-ReleaseTextHash $payload['Engine/NeAntikChromium/core-manifest.json'];
            qa_report_sha256 = 'a' * 64; qa_status = 'passed'; canvas_scope = 'opaque-srgb-uint8' }
        if ($Mode -eq 'native-undeclared') { $manifest.Remove('native_core_bundled') }
        if ($Mode -eq 'native-false') { $manifest.native_core_bundled = $false }
        if ($Mode -eq 'native-manifest-hash') { $manifest.engine.manifest_sha256 = '0' * 64 }
        if ($Mode -eq 'native-qa') { $manifest.engine.qa_status = 'failed' }
        if ($Mode -eq 'native-flag-type') { $manifest.native_core_bundled = 'true' }
    }
    if ($Mode -eq 'launcher-only') { $manifest.native_core_bundled = $false }
    if ($Mode -eq 'neantik') {
        $folder = 'NeAntikWin-portable-v0.2.0-preview'
        $payload['NeAntikWin.exe'] = $payload['NeVisionWin.exe']
        $payload.Remove('NeVisionWin.exe')
        $files = @($payload.Keys | ForEach-Object { [ordered]@{ path = $_; size_bytes = [System.Text.Encoding]::UTF8.GetByteCount($payload[$_]); sha256 = Get-ReleaseTextHash $payload[$_] } })
        $manifest.files = $files
        $manifest.executable = 'NeAntikWin.exe'
        $manifest.product = 'NeAntik Win'
    }
    $payload['release-manifest.json'] = $manifest | ConvertTo-Json -Depth 5 -Compress
    $payload['SHA256SUMS.txt'] = ($files | ForEach-Object { "$($_.sha256)  $($_.path)" }) -join "`n"
    switch ($Mode) {
        'data' { $payload['Data/cookies.txt'] = 'private fixture' }
        'hash' { $payload['NeVisionWin.exe'] = $payload['NeVisionWin.exe'].Replace('fixture', 'damaged') }
        'missing-license' { $payload.Remove('licenses/Tcl-license.terms') }
        'unlisted' { $payload['unexpected.txt'] = 'unlisted fixture' }
        'version' { $payload['release-version.json'] = $version.Replace('0.2.0-preview', '0.2.1-preview') }
        'traversal' { $payload['../escaped.txt'] = 'unsafe fixture' }
    }
    $path = Join-Path $testRoot "$Mode.zip"
    $zip = [System.IO.Compression.ZipFile]::Open($path, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($name in $payload.Keys) {
            $entry = $zip.CreateEntry("$folder/$name")
            $writer = [System.IO.StreamWriter]::new($entry.Open(), [System.Text.UTF8Encoding]::new($false))
            try { $writer.Write($payload[$name]) } finally { $writer.Dispose() }
        }
        if ($Mode -eq 'duplicate') {
            $entry = $zip.CreateEntry("$folder/nevisionwin.EXE")
            $writer = [System.IO.StreamWriter]::new($entry.Open())
            try { $writer.Write('duplicate fixture') } finally { $writer.Dispose() }
        }
    }
    finally { $zip.Dispose() }
    return $path
}

Assert-ReleaseChildPath (Join-Path $testRoot 'inside/release') $testRoot
Expect-Failure 'outside build target rejected' { Assert-ReleaseChildPath (Split-Path -Parent $testRoot) $testRoot } 'escapes'
Expect-Failure 'parent itself rejected' { Assert-ReleaseChildPath $testRoot $testRoot } 'escapes'
$valid = New-TestArchive 'valid'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $valid
$script:passed++
$native = New-TestArchive 'native-valid'
Expect-Failure 'custom engine release rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $native } 'Custom browser engines'
$launcherOnly = New-TestArchive 'launcher-only'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $launcherOnly
$script:passed++
$renamed = New-TestArchive 'neantik'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $renamed
$script:passed++
foreach ($case in @(@('data', 'Forbidden'), @('hash', 'mismatch'), @('missing-license', 'missing'), @('unlisted', 'Unlisted'), @('version', 'Inconsistent'), @('traversal', 'Unsafe'), @('duplicate', 'Duplicate'), @('secret', 'credential'))) {
    $archive = New-TestArchive $case[0]
    Expect-Failure "archive $($case[0]) rejected" { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $archive } $case[1]
}
foreach ($case in @(@('native-hash', 'Custom browser engines'), @('native-path', 'Custom browser engines'),
    @('native-license', 'Custom browser engines'), @('native-unlisted', 'Custom browser engines'), @('native-identity', 'Custom browser engines'),
    @('native-undeclared', 'Custom browser engines'), @('native-false', 'Custom browser engines'), @('native-manifest-hash', 'Custom browser engines'),
    @('native-qa', 'Custom browser engines'), @('native-flag-type', 'Custom browser engines'), @('native-schema-string', 'Custom browser engines'),
    @('native-schema-fraction', 'Custom browser engines'), @('native-schema-bool', 'Custom browser engines'))) {
    $archive = New-TestArchive $case[0]
    Expect-Failure "archive $($case[0]) rejected" { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $archive } $case[1]
}
[System.IO.File]::WriteAllText("$valid.sha256", ('0' * 64) + '  valid.zip')
Expect-Failure 'bad checksum sidecar rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $valid } 'checksum'

# The staged-only publication guard must inspect index blobs, not working-tree bytes.
$guardRepo = Join-Path $testRoot 'staged-guard'
New-Item -ItemType Directory -Path (Join-Path $guardRepo 'tools') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'check-public-repo.ps1') -Destination (Join-Path $guardRepo 'tools/check-public-repo.ps1')
& git -C $guardRepo init -q
if ($LASTEXITCODE -ne 0) { throw 'Cannot initialize staged guard test repository.' }
$fixture = Join-Path $guardRepo 'fixture.txt'
[System.IO.File]::WriteAllText($fixture, 'safe source')
& git -C $guardRepo add -- fixture.txt
if ($LASTEXITCODE -ne 0) { throw 'Cannot stage guard test fixture.' }
[System.IO.File]::WriteAllText($fixture, 'ghp_' + ('a' * 32))
try { & (Join-Path $guardRepo 'tools/check-public-repo.ps1') -StagedOnly }
finally { Set-Location -LiteralPath $projectRoot }
$script:passed++
& git -C $guardRepo add -- fixture.txt
if ($LASTEXITCODE -ne 0) { throw 'Cannot stage secret guard test fixture.' }
[System.IO.File]::WriteAllText($fixture, 'safe source')
try {
    Expect-Failure 'staged secret rejected despite clean working tree' {
        & (Join-Path $guardRepo 'tools/check-public-repo.ps1') -StagedOnly
    } 'Possible GitHub token'
}
finally { Set-Location -LiteralPath $projectRoot }

# Substitute only the native build command: no PyInstaller build is performed here.
$pythonExe = (Get-Command python -CommandType Application | Select-Object -First 1).Source
function python {
    if ($args.Count -gt 1 -and $args[0] -eq '-m' -and $args[1] -eq 'PyInstaller') { $global:LASTEXITCODE = 77; return }
    & $pythonExe @args
    $global:LASTEXITCODE = $LASTEXITCODE
}
$failedBuildOutput = Join-Path $testRoot 'failed-build'
Expect-Failure 'PyInstaller exit stops packaging' { & (Join-Path $projectRoot 'build.ps1') -OutputDirectory $failedBuildOutput } 'PyInstaller failed \(exit 77\)'
if (@(Get-ChildItem -LiteralPath $failedBuildOutput -Filter '*.zip' -ErrorAction SilentlyContinue).Count) { throw 'Failed build left a publishable ZIP.' }
Remove-Item -LiteralPath Function:\python
Write-Output "Release tooling: PASS ($script:passed checks). Synthetic fixtures retained at $testRoot"
$global:LASTEXITCODE = 0
