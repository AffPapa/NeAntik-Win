[CmdletBinding()]
param(
    [switch]$StagedOnly,
    [ValidateRange(1, 100)]
    [int]$MaxFileSizeMb = 10
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.git'))) {
    throw 'Run this guard from the standalone NeVision Win Git repository.'
}

if ($StagedOnly) {
    $candidatePaths = @(& git diff --cached --name-only --diff-filter=ACMR)
}
else {
    $candidatePaths = @(& git ls-files --cached --others --exclude-standard)
}

$candidatePaths = @($candidatePaths | Where-Object { $_ -and $_.Trim() } | Sort-Object -Unique)
if ($candidatePaths.Count -eq 0) {
    throw 'No publishable files were found. Stage the intended source files first, then rerun with -StagedOnly.'
}

$forbiddenPath = '^(?i:(Data|data|build|dist|release|Engine|logs|outputs|storage)(/|$))|(^|/)(?i:tdata|secrets)(/|$)'
$forbiddenFile = '(?i)(^|/)(\.env($|\.)|.*\.(db|sqlite|sqlite3|sqlite-shm|sqlite-wal|session|zip|7z|tar|gz|partial|sha256|exe|dll|pdb|pfx|p12|pem|key|kdbx))$'
$secretPatterns = @(
    @{ Name = 'GitHub token'; Pattern = '\bgh[pousr]_[A-Za-z0-9_]{20,}\b' },
    @{ Name = 'GitHub fine-grained token'; Pattern = '\bgithub_pat_[A-Za-z0-9_]{20,}\b' },
    @{ Name = 'OpenAI API key'; Pattern = '\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b' },
    @{ Name = 'AWS access key'; Pattern = '\bAKIA[0-9A-Z]{16}\b' },
    @{ Name = 'Slack token'; Pattern = '\bxox[baprs]-[A-Za-z0-9-]{10,}\b' },
    @{ Name = 'Telegram bot token'; Pattern = '\b\d{8,12}:[A-Za-z0-9_-]{30,}\b' },
    @{ Name = 'Private key block'; Pattern = '-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----' },
    @{ Name = 'Hard-coded credential assignment'; Pattern = '(?im)^\s*(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*["''][^"''\r\n]{8,}["'']' }
)
$textExtensions = @('.py', '.ps1', '.md', '.txt', '.yml', '.yaml', '.json', '.svg', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.html', '.css', '.toml', '.csv', '.ini', '.cfg', '.terms', '.patch', '.diff', '.cc', '.h', '.cpp', '.inc', '.gn', '.gni', '.gitignore', '.gitattributes')
$failures = New-Object System.Collections.Generic.List[string]
$maxBytes = $MaxFileSizeMb * 1MB

foreach ($relativePath in $candidatePaths) {
    $normalized = $relativePath.Replace('\', '/')
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        $failures.Add("Missing candidate file: $normalized")
        continue
    }

    if ($normalized -match $forbiddenPath -or $normalized -match $forbiddenFile) {
        $failures.Add("Forbidden publish path: $normalized")
        continue
    }

    $file = Get-Item -LiteralPath $fullPath
    if ($file.Length -gt $maxBytes) {
        $failures.Add("File exceeds $MaxFileSizeMb MB publication limit: $normalized")
        continue
    }

    $extension = [System.IO.Path]::GetExtension($file.Name).ToLowerInvariant()
    if ($file.Name -in @('.gitignore', '.gitattributes', '_headers', 'LICENSE') -or $extension -in @('.jsonc', '.webmanifest') -or $textExtensions -contains $extension) {
        $content = Get-Content -LiteralPath $fullPath -Raw -Encoding UTF8
        foreach ($rule in $secretPatterns) {
            if ([regex]::IsMatch($content, $rule.Pattern)) {
                $failures.Add("Possible $($rule.Name) in $normalized")
            }
        }
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    throw "Public repository guard failed with $($failures.Count) finding(s). Remove the files or redact/rotate the secret before commit."
}

Write-Output "Public repository guard: PASS ($($candidatePaths.Count) files, max $MaxFileSizeMb MB each)."
