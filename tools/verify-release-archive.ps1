[CmdletBinding()]
param([Parameter(Mandatory)][string]$ArchivePath)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$resolvedArchive = (Resolve-Path -LiteralPath $ArchivePath -ErrorAction Stop).Path
if ([System.IO.Path]::GetExtension($resolvedArchive).ToLowerInvariant() -ne '.zip') { throw 'Expected a .zip portable archive.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Read-ArchiveText($Entry) {
    if ($Entry.Length -gt 8MB) { throw "Release metadata is unexpectedly large: $($Entry.FullName)" }
    $reader = [System.IO.StreamReader]::new($Entry.Open(), [System.Text.UTF8Encoding]::new($false, $true))
    try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}

function Get-ArchiveHash($Entry) {
    $stream = $Entry.Open()
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Assert-RelativeReleasePath([string]$Path) {
    if (-not $Path -or $Path.Contains('\') -or $Path.StartsWith('/') -or $Path.Contains(':')) { throw "Unsafe manifest path: $Path" }
    foreach ($part in $Path.Split('/')) {
        if (-not $part -or $part -in @('.', '..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or
            $part -match '[\x00-\x1f<>"|?*]' -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])($|\.)') { throw "Unsafe manifest path: $Path" }
    }
}

$archive = [System.IO.Compression.ZipFile]::OpenRead($resolvedArchive)
try {
    $entries = @{}
    $root = $null
    foreach ($entry in $archive.Entries) {
        $path = $entry.FullName.Replace('\', '/')
        $parts = $path.Split('/')
        if ($path.StartsWith('/') -or $path.Contains(':') -or '..' -in $parts -or '.' -in $parts) { throw "Unsafe archive path: $path" }
        Assert-RelativeReleasePath $path.TrimEnd('/')
        if (-not $root) { $root = $parts[0] }
        if ($parts[0] -ne $root) { throw 'Release ZIP must have exactly one root directory.' }
        if ($path -match '(^|/)(Data|Profiles|Backups|Logs|secrets)(/|$)' -or $path -match '(^|/)(\.env($|\.)|.*\.(db|sqlite|sqlite3|sqlite-wal|sqlite-shm|pfx|p12|pem|key|session))$') { throw "Forbidden release data: $path" }
        if ($path.EndsWith('/')) { continue }
        if ($entries.ContainsKey($path)) { throw "Duplicate/case-colliding archive path: $path" }
        $entries[$path] = $entry
    }
    foreach ($required in @('_internal/release-version.json', 'release-version.json', 'release-manifest.json', 'build-provenance.json', 'runtime-components.json', 'SHA256SUMS.txt', 'CHANGELOG.md', 'THIRD_PARTY_NOTICES.md', 'licenses/Python-LICENSE.txt', 'licenses/Tcl-license.terms', 'licenses/Tk-license.terms', 'licenses/OpenSSL-LICENSE.txt')) {
        if (-not $entries.ContainsKey("$root/$required")) { throw "Release is missing $required" }
    }
    $manifest = Read-ArchiveText $entries["$root/release-manifest.json"] | ConvertFrom-Json
    $exeName = if ($manifest.PSObject.Properties.Name -contains 'executable') { [string]$manifest.executable } else { 'NeVisionWin.exe' }
    if ($exeName -notin @('NeVisionWin.exe', 'NeAntikWin.exe') -or -not $entries.ContainsKey("$root/$exeName")) { throw 'Release executable is missing or invalid.' }
    $version = Read-ArchiveText $entries["$root/release-version.json"] | ConvertFrom-Json
    $frozen = Read-ArchiveText $entries["$root/_internal/release-version.json"] | ConvertFrom-Json
    if ($manifest.format -ne 'nevision-release-v1' -or $manifest.version -ne $version.version -or $version.version -ne $frozen.version) { throw 'Inconsistent release manifest or version.' }
    $productBase = [System.IO.Path]::GetFileNameWithoutExtension($exeName)
    if ($root -ne "$productBase-portable-v$($version.version)") { throw 'Archive root does not match release version.' }
    $listed = @{}
    foreach ($file in $manifest.files) {
        Assert-RelativeReleasePath ([string]$file.path)
        $path = "$root/$($file.path)"
        if ($listed.ContainsKey($path)) { throw "Duplicate manifest path: $path" }
        $listed[$path] = $true
        if (-not $entries.ContainsKey($path)) { throw "Manifest file is missing: $path" }
        $entry = $entries[$path]
        if ($entry.Length -ne $file.size_bytes) { throw "Size mismatch: $path" }
        $stream = $entry.Open()
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { $actual = ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose(); $stream.Dispose() }
        if ($actual -ne $file.sha256) { throw "Hash mismatch: $path" }
    }
    foreach ($path in $entries.Keys) {
        if ($path -notin @("$root/release-manifest.json", "$root/SHA256SUMS.txt") -and -not $listed.ContainsKey($path)) { throw "Unlisted archive file: $path" }
    }
    $expectedChecksums = @($manifest.files | ForEach-Object { "$($_.sha256)  $($_.path)" }) -join "`n"
    $actualChecksums = (Read-ArchiveText $entries["$root/SHA256SUMS.txt"]).Replace("`r`n", "`n").TrimEnd("`n")
    if ($actualChecksums -ne $expectedChecksums) { throw 'Internal checksum list disagrees with release manifest.' }
    $runtime = Read-ArchiveText $entries["$root/runtime-components.json"] | ConvertFrom-Json
    foreach ($license in $runtime.licenses) {
        if (-not $entries.ContainsKey("$root/licenses/$license")) { throw "Runtime license is missing: $license" }
    }
    # A launcher-only archive is valid; an engine payload must never silently
    # masquerade as one. Legacy archives without native metadata remain valid.
    $enginePrefix = "$root/Engine/NeAntikChromium/"
    $engineEntries = @($entries.Keys | Where-Object { $_.StartsWith($enginePrefix, [StringComparison]::OrdinalIgnoreCase) })
    $hasNativeField = $manifest.PSObject.Properties.Name -contains 'native_core_bundled'
    if ($hasNativeField -and $manifest.native_core_bundled -isnot [bool]) { throw 'native_core_bundled must be a boolean.' }
    $nativeBundled = $hasNativeField -and $manifest.native_core_bundled
    if ($engineEntries.Count -and -not $nativeBundled) { throw 'Native engine payload requires native_core_bundled=true.' }
    if ($nativeBundled) {
        if (-not $engineEntries.Count -or $manifest.PSObject.Properties.Name -notcontains 'engine') { throw 'Native release is missing engine metadata or payload.' }
        $engine = $manifest.engine
        $pinnedCommit = 'cfaadc5a132d78e1828635aa8405a499f3e14864'
        if ($engine.engine_id -ne 'neantik-chromium' -or $engine.version -ne '155.0.8059.40' -or $engine.source_commit -ne $pinnedCommit -or
            $engine.qa_status -ne 'passed' -or $engine.canvas_scope -ne 'opaque-srgb-uint8' -or
            $engine.manifest_sha256 -cnotmatch '^[a-f0-9]{64}$' -or $engine.qa_report_sha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Invalid native release evidence metadata.' }
        $coreManifestPath = "${enginePrefix}core-manifest.json"
        if (-not $entries.ContainsKey($coreManifestPath)) { throw 'Native core manifest is missing.' }
        if ((Get-ArchiveHash $entries[$coreManifestPath]) -cne $engine.manifest_sha256) { throw 'Native core manifest hash mismatch.' }
        $core = Read-ArchiveText $entries[$coreManifestPath] | ConvertFrom-Json
        if ($core.format -ne 'neantik-native-core-v1' -or $core.engine_id -ne 'neantik-chromium' -or
            $core.version -ne '155.0.8059.40' -or $core.source_commit -ne $pinnedCommit -or
            ($core.schema -isnot [int] -and $core.schema -isnot [long]) -or $core.schema -ne 1 -or $null -eq $core.files -or
            $core.files -isnot [System.Management.Automation.PSCustomObject]) { throw 'Unknown native core manifest identity or file map.' }
        $coreListed = @{}
        foreach ($property in $core.files.PSObject.Properties) {
            $relative = [string]$property.Name
            Assert-RelativeReleasePath $relative
            if ($relative -ieq 'core-manifest.json' -or $coreListed.ContainsKey($relative)) { throw 'Duplicate or self-referential native core path.' }
            $coreListed[$relative] = $true
            $full = "$enginePrefix$relative"
            if ($property.Value -isnot [string] -or $property.Value -cnotmatch '^[a-f0-9]{64}$' -or -not $entries.ContainsKey($full)) { throw "Native core file missing or invalid: $relative" }
            if ((Get-ArchiveHash $entries[$full]) -cne $property.Value) { throw "Native core payload hash mismatch: $relative" }
        }
        foreach ($requiredNative in @('chrome.exe', 'chrome.dll', 'LICENSE', 'credits.html',
            'THIRD_PARTY_LICENSES.txt', 'DEPENDENCY_RECEIPT.json', 'BUILD_PROVENANCE.json')) {
            if (-not $coreListed.ContainsKey($requiredNative)) { throw "Native core required runtime/license missing: $requiredNative" }
        }
        foreach ($full in $engineEntries) {
            $relative = $full.Substring($enginePrefix.Length)
            if ($relative -ine 'core-manifest.json' -and -not $coreListed.ContainsKey($relative)) { throw "Unlisted native engine file: $relative" }
        }
    }
    # High-confidence patterns supplement the source scan and runtime-path guard.
    # Never print matched values; a clean regex scan is not a proof of no secrets.
    $secretPattern = '\bgh[pousr]_[A-Za-z0-9_]{20,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|\bAKIA[0-9A-Z]{16}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b|-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----'
    foreach ($path in $entries.Keys) {
        if ($path -match '\.(md|txt|json|yml|yaml|py|ps1|env)$' -and $entries[$path].Length -le 8MB) {
            if ((Read-ArchiveText $entries[$path]) -match $secretPattern) { throw "Possible credential in release text: $path" }
        }
    }
}
finally { $archive.Dispose() }

$hash = (Get-FileHash -LiteralPath $resolvedArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if (Test-Path -LiteralPath "$resolvedArchive.sha256") {
    $checksum = (Get-Content -LiteralPath "$resolvedArchive.sha256" -Raw).Trim()
    if ($checksum -notmatch '^([0-9a-fA-F]{64})\s+' -or $Matches[1] -ne $hash) { throw 'Archive checksum sidecar mismatch.' }
}
$sidecar = [System.IO.Path]::ChangeExtension($resolvedArchive, '.manifest.json')
if (Test-Path -LiteralPath $sidecar) {
    $published = Get-Content -LiteralPath $sidecar -Raw | ConvertFrom-Json
    if ($published.archive.sha256 -ne $hash -or $published.archive.size_bytes -ne (Get-Item -LiteralPath $resolvedArchive).Length -or $published.version -ne $manifest.version) { throw 'Archive release manifest sidecar mismatch.' }
}
Write-Output "Release archive check: PASS ($($entries.Count) files, $($manifest.version))"
Write-Output "SHA256  $hash  $(Split-Path -Leaf $resolvedArchive)"
