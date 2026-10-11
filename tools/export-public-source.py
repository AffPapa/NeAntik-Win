"""Export reviewed source types into a new folder; never export runtime data.

No Git operations, network calls or third-party dependencies. Secret expressions
come from the existing PowerShell publication guard, keeping one rule inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

ROOT_FILES = {
    '.gitattributes', '.gitignore', 'nevision_win.py', 'neantik_win.py',
    'test_nevision_win.py', 'test_neantik_win.py', 'browser_engine.py',
    'test_browser_engine.py', 'current_core.py', 'test_current_core.py',
    'release-version.json', 'requirements-build.txt',
    'requirements-dev.txt', 'requirements-engine.txt', 'requirements.txt', 'build.ps1', 'LICENSE',
    'LICENSE.txt', 'LICENSE.md', 'NOTICE', 'NOTICE.txt', 'pyproject.toml',
}
TEXT_SUFFIXES = {'.py', '.ps1', '.md', '.txt', '.yml', '.yaml', '.json',
    '.svg', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.html', '.css',
    '.toml', '.csv', '.ini', '.cfg', '.terms', '.jsonc', '.webmanifest', '.inc'}
BINARY_SUFFIXES = {'.ico', '.png'}
FORBIDDEN_PARTS = {'.git', 'data', 'build', 'dist', 'release', 'engine',
    'logs', 'outputs', 'storage', 'tdata', 'secrets', '__pycache__', '.venv',
    'venv', '.pytest_cache', 'node_modules'}
USER_PATH = re.compile(r'(?i)\b[A-Z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)[^\\/\s"\'<>]+')
MAX_BYTES = 10 * 1024 * 1024


def secret_rules(root: Path) -> list[tuple[str, re.Pattern[str]]]:
    guard = (root / 'tools' / 'check-public-repo.ps1').read_text(encoding='utf-8-sig')
    # PowerShell single-quoted literals escape apostrophes by doubling them.
    entries = re.findall(r"@\{\s*Name = '((?:[^']|'')*)'; Pattern = '((?:[^']|'')*)'\s*\}", guard)
    if not entries:
        raise ValueError('Cannot load secret rules from publication guard')
    return [(name.replace("''", "'"), re.compile(pattern.replace("''", "'")))
            for name, pattern in entries]


def allowed(relative: Path) -> bool:
    parts = relative.parts
    if any(p.lower() in FORBIDDEN_PARTS for p in parts):
        return False
    if any(p.lower().startswith('.env') for p in parts):
        return False
    suffix = relative.suffix.lower()
    if len(parts) == 1:
        return relative.name in ROOT_FILES or suffix == '.md'
    top = parts[0].lower()
    if relative.as_posix() == 'core/native/LICENSE':
        return True
    if top == 'website':
        return suffix in TEXT_SUFFIXES | BINARY_SUFFIXES or relative.as_posix() == 'website/public/_headers'
    if top == 'docs':
        return not (len(parts) > 1 and parts[1].lower() == 'qa') and suffix in {'.md', '.csv'}
    if top == 'assets':
        return suffix in TEXT_SUFFIXES | BINARY_SUFFIXES
    if top in {'tools', 'tests', '.github', 'fixtures', 'core'}:
        return suffix in TEXT_SUFFIXES | {'.patch', '.diff', '.cc', '.h', '.gn', '.gni'}
    return False


def collect(root: Path) -> list[tuple[Path, bytes]]:
    rules = secret_rules(root)
    files = []
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d.lower() not in FORBIDDEN_PARTS)
        for name in sorted(names):
            path = Path(current) / name
            relative = path.relative_to(root)
            if not allowed(relative):
                continue
            # Reject every ancestor reparse point as well as the file itself.
            for component in (path, *path.parents):
                if component == root.parent:
                    break
                info = component.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise ValueError(f'Reparse point in selected source: {relative.as_posix()}')
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError(f'Invalid or oversized source: {relative.as_posix()}')
            data = path.read_bytes()
            if path.suffix.lower() not in BINARY_SUFFIXES:
                text = data.decode('utf-8-sig')
                for rule_name, expression in rules:
                    if expression.search(text):
                        raise ValueError(f'Possible {rule_name} in {relative.as_posix()}')
                text = USER_PATH.sub('<user-profile>', text)
                data = text.encode('utf-8')
            files.append((relative, data))
    if not any(path.name in {'nevision_win.py', 'neantik_win.py'} for path, _ in files):
        raise ValueError('Application source missing')
    if not any(path.as_posix() == 'release-version.json' for path, _ in files):
        raise ValueError('Release metadata missing')
    return sorted(files, key=lambda item: item[0].as_posix())


def export(root: Path, destination: Path) -> dict:
    root = root.resolve(strict=True)
    destination = destination.resolve()
    if destination == root or root in destination.parents:
        raise ValueError('Export destination must be outside source tree')
    if destination.exists():
        raise ValueError('Export destination already exists; use a new folder')
    files = collect(root)  # Validate every selected input before writing anything.
    if not any(path.name.lower().startswith('license') and len(path.parts) == 1 for path, _ in files):
        files.append((Path('SOURCE_LICENSE_NOTICE.txt'), (
            'No project source license has been explicitly selected.\n'
            'Publication does not grant a general permission to reuse the project source or branding.\n'
            'Third-party components retain their respective licenses and notices.\n'
        ).encode('utf-8')))
    manifest = {'format': 'neantik-public-source-export-v1', 'files': [
        {'path': path.as_posix(), 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        for path, data in files], 'transient_qa_reports_included': False}
    destination.mkdir(parents=True, exist_ok=False)
    for relative, data in files:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    (destination / 'export-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = export(args.source, args.destination)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, f'Source export failed: {exc}\n')
    print(f"Public source export: PASS ({len(result['files'])} files). No Git operation performed.")
