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
    $testVersion = if ($Mode -eq 'chromium-dev') { '0.2.0-dev' } elseif ($Mode -like 'chromium-source-privacy-provenance*') { '0.8.5-preview' } elseif ($Mode -eq 'new-preview-without-core') { '0.5.0-preview' } elseif ($Mode -eq 'new-preview-051-without-core') { '0.5.1-preview' } elseif ($Mode -eq 'new-preview-060-without-core') { '0.6.0-preview' } elseif ($Mode -eq 'new-preview-070-without-core') { '0.7.0-preview' } elseif ($Mode -eq 'new-preview-071-without-core') { '0.7.1-preview' } elseif ($Mode -eq 'new-preview-090-without-core') { '0.9.0-preview' } else { '0.2.0-preview' }
    $folder = "NeVisionWin-portable-v$testVersion"
    $version = "{`"version`":`"$testVersion`",`"file_version`":[0,2,0,0],`"channel`":`"preview`"}"
    $payload = [ordered]@{
        'NeVisionWin.exe' = 'fixture executable, never launched'
        'release-version.json' = $version
        '_internal/release-version.json' = $version
        'build-provenance.json' = '{}'
        'runtime-components.json' = '{"licenses":["Python-LICENSE.txt","Tcl-license.terms","Tk-license.terms","OpenSSL-LICENSE.txt"]}'
        'CHANGELOG.md' = '# release fixture'
        'THIRD_PARTY_NOTICES.md' = '# notice fixture'
        'LICENSE' = 'Mozilla Public License Version 2.0 fixture'
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
    $chromiumMode = $Mode.StartsWith('chromium')
    if ($chromiumMode) {
        foreach ($member in @('chrome.exe', 'chrome.dll', 'icudtl.dat', 'resources.pak', 'LICENSE')) {
            $payload["Engine/Chromium/$member"] = "Synthetic Chromium fixture $member"
        }
        if ($Mode.StartsWith('chromium-source')) {
            foreach ($member in @('chrome_elf.dll', '155.0.8059.40.manifest', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
                $payload["Engine/Chromium/$member"] = "Synthetic Chromium fixture $member"
            }
        }
        $payload['Engine/Chromium/credits.html'] = '<!DOCTYPE html>' + ('C' * 110000)
        $engineReceipt = [ordered]@{ format = 'neantik-chromium-snapshot-stage-v1'; chromium_version = '157.0.8101.0';
            channel = 'continuous-snapshot-not-stable'; source_commit = 'a' * 40; snapshot_sha256 = 'b' * 64 }
        if ($Mode.StartsWith('chromium-source')) {
            $engineReceipt = [ordered]@{ format = 'neantik-chromium-source-build-v1'; chromium_version = '155.0.8059.40';
                channel = 'stable'; source_commit = 'a' * 40; source_tree = 'c' * 40; build_args_sha256 = 'd' * 64; build_patch_sha256 = 'e' * 64;
                license_sha256 = Get-ReleaseTextHash $payload['Engine/Chromium/LICENSE'];
                credits_sha256 = Get-ReleaseTextHash $payload['Engine/Chromium/credits.html'] }
            if ($Mode -like 'chromium-source-privacy*') { $engineReceipt.privacy_patch_sha256 = 'f' * 64 }
            if ($Mode -like 'chromium-source-privacy-native*') {
                $engineReceipt.native_persona_patch_sha256 = 'f' * 64
                $engineReceipt.native_persona_core_info = [ordered]@{ engine_id = 'neantik-chromium'; schema = 2;
                    version = '155.0.8059.40'; source_commit = 'a' * 40;
                    compiled_stage = 11
                    capabilities = [ordered]@{ stable_seed = $true; hardware_concurrency = $true; device_memory = $true;
                        canvas = $false; canvas_opaque_srgb_uint8 = $false;
                        canvas_site_scoped_experimental = $true; timezone = $true } }
                if ($Mode -eq 'chromium-source-privacy-native-bad-info') { $engineReceipt.native_persona_core_info.capabilities.timezone = $false }
                if ($Mode -eq 'chromium-source-privacy-native-old-schema') { $engineReceipt.native_persona_core_info.schema = 1 }
            }
        }
        if ($Mode -eq 'chromium-fake-stable-snapshot') { $engineReceipt.channel = 'stable' }
        if ($Mode -like 'chromium-source-privacy-provenance*') {
            $engineReceipt.locales = @('en-US.pak', 'ru.pak', 'th.pak')
            foreach ($locale in $engineReceipt.locales) { $payload["Engine/Chromium/locales/$locale"] = 'Synthetic locale fixture' }
        }
        $payload['Engine/Chromium/ENGINE_PROVENANCE.json'] = $engineReceipt | ConvertTo-Json -Compress
    }
    $sourceProvenanceMode = $Mode -like 'chromium-source-privacy-provenance*' -or $Mode -eq 'new-preview-090-without-core'
    if ($sourceProvenanceMode) {
        $sourceFiles = @([ordered]@{ path = 'nevision_win.py'; size_bytes = 7; sha256 = Get-ReleaseTextHash 'fixture' })
        $sourceTreeHash = Get-ReleaseTextHash ($sourceFiles | ConvertTo-Json -Depth 5 -Compress)
        $provenanceState = if ($Mode -eq 'chromium-source-privacy-provenance-state-mismatch') { 'modified' } else { 'clean' }
        $payload['build-provenance.json'] = ([ordered]@{ source_commit = 'a' * 40; source_state = $provenanceState;
            source_tree_sha256 = $sourceTreeHash; source_files = $sourceFiles } | ConvertTo-Json -Depth 5 -Compress)
    }
    $files = @($payload.Keys | ForEach-Object { [ordered]@{ path = $_; size_bytes = [System.Text.Encoding]::UTF8.GetByteCount($payload[$_]); sha256 = Get-ReleaseTextHash $payload[$_] } })
    $manifest = [ordered]@{ format = 'nevision-release-v1'; version = $testVersion; files = $files }
    if ($sourceProvenanceMode) {
        $manifest.source_state = 'clean'; $manifest.source_commit = 'a' * 40; $manifest.source_tree_sha256 = $sourceTreeHash
        if ($Mode -eq 'chromium-source-privacy-provenance-commit-mismatch') { $manifest.source_commit = 'b' * 40 }
        if ($Mode -eq 'chromium-source-privacy-provenance-tree-mismatch') { $manifest.source_tree_sha256 = 'b' * 64 }
        if ($Mode -eq 'chromium-source-privacy-provenance-tree-corrupt') {
            $payload['build-provenance.json'] = $payload['build-provenance.json'].Replace($sourceTreeHash, ('c' * 64))
            $files = @($payload.Keys | ForEach-Object { [ordered]@{ path = $_; size_bytes = [System.Text.Encoding]::UTF8.GetByteCount($payload[$_]); sha256 = Get-ReleaseTextHash $payload[$_] } })
            $manifest.files = $files
            $manifest.source_tree_sha256 = 'c' * 64
        }
    }
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
    if ($chromiumMode) {
        $manifest.native_core_bundled = $true
        $manifest.engine = [ordered]@{ name = 'Chromium'; version = '157.0.8101.0'; channel = 'continuous-snapshot-not-stable';
            source_commit = 'a' * 40; snapshot_sha256 = 'b' * 64 }
        if ($Mode.StartsWith('chromium-source')) {
            $manifest.engine = [ordered]@{ name = 'Chromium'; version = '155.0.8059.40'; channel = 'stable';
                source_commit = 'a' * 40; provenance_format = 'neantik-chromium-source-build-v1';
                source_tree = 'c' * 40; build_args_sha256 = 'd' * 64; build_patch_sha256 = 'e' * 64 }
            if ($Mode -like 'chromium-source-privacy*') {
                $manifest.engine.privacy_patch_sha256 = 'f' * 64
                $manifest.fingerprint_modification = $true
                if ($Mode -eq 'chromium-source-privacy-false') { $manifest.fingerprint_modification = $false }
                if ($Mode -eq 'chromium-source-privacy-mismatch') { $manifest.engine.privacy_patch_sha256 = '0' * 64 }
            }
            if ($Mode -like 'chromium-source-privacy-native*') {
                $manifest.engine.native_persona_patch_sha256 = 'f' * 64
                if ($Mode -eq 'chromium-source-privacy-native-mismatch') { $manifest.engine.native_persona_patch_sha256 = '0' * 64 }
            }
        }
        if ($Mode -eq 'chromium-fake-stable-snapshot') { $manifest.engine.channel = 'stable' }
    }
    if ($Mode -eq 'launcher-only') { $manifest.native_core_bundled = $false }
    if ($Mode -like 'chromium-source-privacy-provenance*' -or $Mode -in @('neantik', 'new-preview-without-core', 'new-preview-051-without-core', 'new-preview-060-without-core', 'new-preview-070-without-core', 'new-preview-071-without-core', 'new-preview-090-without-core')) {
        $folder = "NeAntikWin-portable-v$testVersion"
        $payload['NeAntikWin.exe'] = $payload['NeVisionWin.exe']
        $payload.Remove('NeVisionWin.exe')
        $files = @($payload.Keys | ForEach-Object { [ordered]@{ path = $_; size_bytes = [System.Text.Encoding]::UTF8.GetByteCount($payload[$_]); sha256 = Get-ReleaseTextHash $payload[$_] } })
        $manifest.files = $files
        $manifest.executable = 'NeAntikWin.exe'
        $manifest.product = 'NeAntik Win'
        if ($Mode -in @('new-preview-without-core', 'new-preview-051-without-core', 'new-preview-060-without-core', 'new-preview-070-without-core', 'new-preview-071-without-core', 'new-preview-090-without-core')) { $manifest.native_core_bundled = $false }
    }
    $payload['release-manifest.json'] = $manifest | ConvertTo-Json -Depth 5 -Compress
    $payload['SHA256SUMS.txt'] = ($files | ForEach-Object { "$($_.sha256)  $($_.path)" }) -join "`n"
    switch ($Mode) {
        'data' { $payload['Data/cookies.txt'] = 'private fixture' }
        'hash' { $payload['NeVisionWin.exe'] = $payload['NeVisionWin.exe'].Replace('fixture', 'damaged') }
        'missing-license' { $payload.Remove('licenses/Tcl-license.terms') }
        'missing-project-license' { $payload.Remove('LICENSE') }
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
Expect-Failure 'unrecognized custom engine release rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $native } 'engine|browser|core|native'
$chromiumDev = New-TestArchive 'chromium-dev'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $chromiumDev
$script:passed++
$chromiumPreview = New-TestArchive 'chromium-preview'
Expect-Failure 'development core cannot be public preview' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $chromiumPreview } 'Development Chromium snapshot'
$chromiumSource = New-TestArchive 'chromium-source'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $chromiumSource
$script:passed++
$chromiumSourcePrivacy = New-TestArchive 'chromium-source-privacy'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $chromiumSourcePrivacy
$script:passed++
$sourceProvenanceValid = New-TestArchive 'chromium-source-privacy-provenance-valid'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $sourceProvenanceValid
$script:passed++
foreach ($case in @('chromium-source-privacy-provenance-commit-mismatch', 'chromium-source-privacy-provenance-state-mismatch',
    'chromium-source-privacy-provenance-tree-mismatch', 'chromium-source-privacy-provenance-tree-corrupt')) {
    $archive = New-TestArchive $case
    Expect-Failure "archive $case rejected" { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $archive } 'source provenance|source tree provenance'
}
$chromiumNative = New-TestArchive 'chromium-source-privacy-native'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $chromiumNative
$script:passed++
foreach ($case in @('chromium-source-privacy-native-mismatch', 'chromium-source-privacy-native-bad-info', 'chromium-source-privacy-native-old-schema')) {
    $archive = New-TestArchive $case
    Expect-Failure "archive $case rejected" { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $archive } 'Native persona provenance'
}
foreach ($case in @(@('chromium-source-privacy-false', 'disclosed'), @('chromium-source-privacy-mismatch', 'provenance'))) {
    $archive = New-TestArchive $case[0]
    Expect-Failure "archive $($case[0]) rejected" { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $archive } $case[1]
}
$fakeStableSnapshot = New-TestArchive 'chromium-fake-stable-snapshot'
Expect-Failure 'snapshot cannot impersonate stable core' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $fakeStableSnapshot } 'Snapshot provenance'
$launcherOnly = New-TestArchive 'launcher-only'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $launcherOnly
$script:passed++
$renamed = New-TestArchive 'neantik'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $renamed
$script:passed++
$incompleteNewPreview = New-TestArchive 'new-preview-without-core'
Expect-Failure '0.5 portable archive without Chromium rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $incompleteNewPreview } 'must bundle Chromium'
$incompleteNewPreview051 = New-TestArchive 'new-preview-051-without-core'
Expect-Failure '0.5.1 portable archive without Chromium rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $incompleteNewPreview051 } 'must bundle Chromium'
$incompleteNewPreview060 = New-TestArchive 'new-preview-060-without-core'
Expect-Failure '0.6.0 portable archive without Chromium rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $incompleteNewPreview060 } 'must bundle Chromium'
$incompleteNewPreview070 = New-TestArchive 'new-preview-070-without-core'
Expect-Failure '0.7.0 portable archive without Chromium rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $incompleteNewPreview070 } 'must bundle Chromium'
$incompleteNewPreview071 = New-TestArchive 'new-preview-071-without-core'
Expect-Failure '0.7.1 portable archive without Chromium rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $incompleteNewPreview071 } 'must bundle Chromium'
$incompleteNewPreview090 = New-TestArchive 'new-preview-090-without-core'
Expect-Failure 'future 0.9 portable archive without Chromium rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $incompleteNewPreview090 } 'must bundle Chromium'
foreach ($case in @(@('data', 'Forbidden'), @('hash', 'mismatch'), @('missing-license', 'missing'), @('missing-project-license', 'missing LICENSE'), @('unlisted', 'Unlisted'), @('version', 'Inconsistent'), @('traversal', 'Unsafe'), @('duplicate', 'Duplicate'), @('secret', 'credential'))) {
    $archive = New-TestArchive $case[0]
    Expect-Failure "archive $($case[0]) rejected" { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $archive } $case[1]
}
foreach ($case in @(@('native-hash', 'engine|browser|core|native'), @('native-path', 'engine|browser|core|native'),
    @('native-license', 'engine|browser|core|native'), @('native-unlisted', 'engine|browser|core|native'), @('native-identity', 'engine|browser|core|native'),
    @('native-undeclared', 'engine|browser|core|native'), @('native-false', 'engine|browser|core|native'), @('native-manifest-hash', 'engine|browser|core|native'),
    @('native-qa', 'engine|browser|core|native'), @('native-flag-type', 'engine|browser|core|native'), @('native-schema-string', 'engine|browser|core|native'),
    @('native-schema-fraction', 'engine|browser|core|native'), @('native-schema-bool', 'engine|browser|core|native'))) {
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
Expect-Failure 'public portable version requires Chromium' { & (Join-Path $projectRoot 'build.ps1') -OutputDirectory $failedBuildOutput } 'requires EngineDirectory'
# Public packaging correctly requires a clean committed tree. Test the later
# PyInstaller failure branch in an isolated local clone instead of depending
# on whether the developer's working tree happens to be clean.
$cleanBuildRepo = Join-Path $testRoot 'clean-build-repo'
& git clone --local --no-hardlinks --quiet $projectRoot $cleanBuildRepo
if ($LASTEXITCODE -ne 0) { throw 'Cannot create clean local build-test clone.' }
Expect-Failure 'PyInstaller exit stops packaging' { & (Join-Path $cleanBuildRepo 'build.ps1') -EngineDirectory (Join-Path $testRoot 'not-used-before-freeze') -OutputDirectory $failedBuildOutput } 'PyInstaller failed \(exit 77\)'
if (@(Get-ChildItem -LiteralPath $failedBuildOutput -Filter '*.zip' -ErrorAction SilentlyContinue).Count) { throw 'Failed build left a publishable ZIP.' }
Remove-Item -LiteralPath Function:\python
Write-Output "Release tooling: PASS ($script:passed checks). Synthetic fixtures retained at $testRoot"
$global:LASTEXITCODE = 0
