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
        if ($path -match '^[^/]+/(Data|Profiles|Backups|Logs)(/|$)' -or $path -match '(^|/)secrets(/|$)' -or
            $path -match '(^|/)(\.env($|\.)|.*\.(db|sqlite|sqlite3|sqlite-wal|sqlite-shm|pfx|p12|pem|key|session))$') { throw "Forbidden release data: $path" }
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
    if ($version.version -eq '0.5.0-preview' -and -not $manifest.native_core_bundled) { throw '0.5.0-preview must bundle Chromium.' }
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
    $engineEntries = @($entries.Keys | Where-Object { $_ -match ('^' + [regex]::Escape($root) + '/Engine/') })
    $hasNativeField = $manifest.PSObject.Properties.Name -contains 'native_core_bundled'
    if ($hasNativeField -and $manifest.native_core_bundled -isnot [bool]) { throw 'native_core_bundled must be a boolean.' }
    if ($engineEntries.Count -gt 0) {
        if (-not $hasNativeField -or -not $manifest.native_core_bundled -or -not ($manifest.PSObject.Properties.Name -contains 'engine')) { throw 'Bundled Chromium requires explicit engine provenance.' }
        $prefix = "$root/Engine/Chromium/"
        if ($engineEntries | Where-Object { -not $_.StartsWith($prefix, [StringComparison]::Ordinal) }) { throw 'Unexpected engine folder.' }
        $allowedRoot = @('chrome.exe', 'chrome.dll', 'chrome_elf.dll', 'chrome_wer.dll', 'chrome_100_percent.pak',
            'chrome_200_percent.pak', 'resources.pak', 'icudtl.dat', 'v8_context_snapshot.bin', 'libEGL.dll',
            'libGLESv2.dll', 'D3DCompiler_47.dll', 'dxcompiler.dll', 'vulkan-1.dll', 'vk_swiftshader.dll',
            'vk_swiftshader_icd.json', 'chrome_proxy.exe', 'chrome_pwa_launcher.exe', 'elevated_tracing_service.exe',
            'elevation_service.exe', 'notification_helper.exe', 'eventlog_provider.dll', 'First Run',
            'chrome.VisualElementsManifest.xml', 'msvcp140.dll', 'msvcp140_atomic_wait.dll',
            'vcruntime140.dll', 'vcruntime140_1.dll', 'vccorlib140.dll',
            'LICENSE', 'credits.html', 'ENGINE_PROVENANCE.json')
        foreach ($enginePath in $engineEntries) {
            $relative = $enginePath.Substring($prefix.Length)
            if ($relative -notmatch '/') {
                if ($relative -notin $allowedRoot -and $relative -notmatch '^\d+\.\d+\.\d+\.\d+\.manifest$') { throw "Unexpected engine file: $relative" }
            } else {
                $segments = $relative.Split('/')
                if ($segments[0] -notin @('locales', 'MEIPreload', 'IwaKeyDistribution') -or $relative -notmatch '\.(pak|pb|json)$') { throw "Unexpected engine resource: $relative" }
            }
        }
        foreach ($required in @('chrome.exe', 'chrome.dll', 'icudtl.dat', 'resources.pak', 'LICENSE', 'credits.html', 'ENGINE_PROVENANCE.json')) {
            if (-not $entries.ContainsKey("$prefix$required")) { throw "Bundled browser is missing $required" }
        }
        if ($engineEntries | Where-Object { $_ -match '\.(pdb|obj|ilk|lib)$' -or $_ -match '/(setup|interactive_ui_tests|unit_tests)\.exe$' }) { throw 'Build/test files are forbidden in the portable engine.' }
        $engineReceipt = Read-ArchiveText $entries["${prefix}ENGINE_PROVENANCE.json"] | ConvertFrom-Json
        $manifestProvenanceFormat = if ($manifest.engine.PSObject.Properties.Name -contains 'provenance_format') { $manifest.engine.provenance_format } else { 'neantik-chromium-snapshot-stage-v1' }
        if ($engineReceipt.format -notin @('neantik-chromium-snapshot-stage-v1', 'neantik-chromium-source-build-v1') -or
            $manifest.engine.name -ne 'Chromium' -or $manifestProvenanceFormat -ne $engineReceipt.format -or
            $manifest.engine.version -ne $engineReceipt.chromium_version -or $manifest.engine.channel -ne $engineReceipt.channel -or
            $manifest.engine.source_commit -ne $engineReceipt.source_commit) { throw 'Browser provenance does not match release manifest.' }
        if ($engineReceipt.format -eq 'neantik-chromium-snapshot-stage-v1') {
            if ($engineReceipt.channel -eq 'stable' -or $manifest.engine.snapshot_sha256 -ne $engineReceipt.snapshot_sha256) { throw 'Snapshot provenance cannot claim a stable build.' }
        } else {
            foreach ($required in @('chrome_elf.dll', "$($engineReceipt.chromium_version).manifest", 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
                if (-not $entries.ContainsKey("${prefix}$required")) { throw "Source-built Chromium is missing $required" }
            }
            if ($engineReceipt.channel -ne 'stable' -or $manifest.engine.source_tree -ne $engineReceipt.source_tree -or
                $manifest.engine.build_args_sha256 -ne $engineReceipt.build_args_sha256 -or
                $manifest.engine.build_patch_sha256 -ne $engineReceipt.build_patch_sha256 -or
                $engineReceipt.source_tree -notmatch '^[0-9a-f]{40}$' -or $engineReceipt.build_args_sha256 -notmatch '^[0-9a-f]{64}$' -or
                ($engineReceipt.build_patch_sha256 -and $engineReceipt.build_patch_sha256 -notmatch '^[0-9a-f]{64}$') -or
                (Get-ArchiveHash $entries["${prefix}LICENSE"]) -ne $engineReceipt.license_sha256) { throw 'Source-built Chromium provenance is invalid.' }
        }
        if ($engineReceipt.format -eq 'neantik-chromium-source-build-v1' -or $engineReceipt.PSObject.Properties.Name -contains 'credits_sha256') {
            if ((Get-ArchiveHash $entries["${prefix}credits.html"]) -ne $engineReceipt.credits_sha256) { throw 'Browser credits do not match provenance.' }
        }
        if ($engineReceipt.channel -ne 'stable' -and $manifest.version -notmatch '-dev$') { throw 'Development Chromium snapshot cannot be a public preview/stable release.' }
        if ($entries["${prefix}credits.html"].Length -lt 100KB) { throw 'Browser third-party credits are incomplete.' }
    } elseif (($hasNativeField -and $manifest.native_core_bundled) -or ($manifest.PSObject.Properties.Name -contains 'engine')) {
        throw 'Engine metadata is present without a bundled browser.'
    }
    $hasFingerprintField = $manifest.PSObject.Properties.Name -contains 'fingerprint_modification'
    if ($hasFingerprintField -and $manifest.fingerprint_modification -isnot [bool]) { throw 'fingerprint_modification must be a boolean.' }
    if ($hasFingerprintField -and $manifest.fingerprint_modification) { throw 'Fingerprint modification is not part of this release.' }
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
