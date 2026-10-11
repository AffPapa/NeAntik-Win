# Shared build primitives. No recursive deletion is used by the release pipeline.
function Assert-ReleaseChildPath([string]$Path, [string]$Parent) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $base = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    $prefix = $base + [System.IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw "Build target escapes its exact parent: $full" }
    $current = $full
    while ($current -and $current.Length -ge $base.Length) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw "Build target contains a reparse point: $current" }
        }
        $current = Split-Path -Parent $current
    }
}

function Write-ReleaseJson($Value, [string]$Path) {
    [System.IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12) + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}

function Get-ReleaseTreeManifest([string]$Root, [string[]]$Exclude = @()) {
    $prefix = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    foreach ($file in (Get-ChildItem -LiteralPath $Root -File -Recurse | Sort-Object FullName)) {
        $relative = $file.FullName.Substring($prefix.Length).Replace('\', '/')
        if ($relative -notin $Exclude) {
            [ordered]@{ path = $relative; size_bytes = $file.Length; sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
        }
    }
}

function Get-ReleaseTextHash([string]$Text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Assert-ReleaseExeVersion([string]$Path, $Release) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "No release executable: $Path" }
    $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($Path)
    if ($info.ProductVersion -ne $Release.version -or $info.FileVersion -ne ($Release.file_version -join '.')) { throw 'EXE version metadata does not match release-version.json.' }
}
