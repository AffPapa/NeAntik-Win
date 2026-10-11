[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'release-helpers.ps1')
Add-Type -AssemblyName System.IO.Compression.FileSystem
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
    $files = @($payload.Keys | ForEach-Object { [ordered]@{ path = $_; size_bytes = [System.Text.Encoding]::UTF8.GetByteCount($payload[$_]); sha256 = Get-ReleaseTextHash $payload[$_] } })
    $manifest = [ordered]@{ format = 'nevision-release-v1'; version = '0.2.0-preview'; files = $files }
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
$renamed = New-TestArchive 'neantik'
& (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $renamed
$script:passed++
foreach ($case in @(@('data', 'Forbidden'), @('hash', 'mismatch'), @('missing-license', 'missing'), @('unlisted', 'Unlisted'), @('version', 'Inconsistent'), @('traversal', 'Unsafe'), @('duplicate', 'Duplicate'), @('secret', 'credential'))) {
    $archive = New-TestArchive $case[0]
    Expect-Failure "archive $($case[0]) rejected" { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $archive } $case[1]
}
[System.IO.File]::WriteAllText("$valid.sha256", ('0' * 64) + '  valid.zip')
Expect-Failure 'bad checksum sidecar rejected' { & (Join-Path $PSScriptRoot 'verify-release-archive.ps1') -ArchivePath $valid } 'checksum'

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
