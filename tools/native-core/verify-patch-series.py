"""Verify an already applied native patch series; does not apply, reset or stage."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


def digest(path: Path) -> str:
    with path.open("rb") as source:
        result = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def safe_file(root: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw or ":" in raw or "\x00" in raw:
        raise ValueError("Invalid relative patch/source path")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in raw.split("/")):
        raise ValueError("Patch/source path must remain inside its root")
    path = root.joinpath(*relative.parts)
    cursor = path
    while cursor != root:
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError("Patch/source paths cannot traverse symlinks or junctions")
        cursor = cursor.parent
    if root.resolve() not in path.resolve().parents or not path.is_file():
        raise ValueError("Required patch/source file is missing or outside root")
    return path


def git(source: Path, *arguments: str) -> bytes:
    result = subprocess.run(["git", "-C", str(source), *arguments], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"Git verification failed: {' '.join(arguments[:3])}: {result.stderr.decode('utf-8', 'replace')[:1000]}")
    return result.stdout


def verify(source: Path, repository: Path, spec: dict, baseline: bool = False) -> dict:
    source, repository = source.resolve(), repository.resolve()
    head = git(source, "rev-parse", "HEAD").decode().strip()
    if head != spec["chromium"]["commit"]:
        raise ValueError("Source HEAD does not match the pinned Chromium commit")
    tracked = {item for item in git(source, "diff", "HEAD", "--name-only", "-z").decode().split("\x00") if item}
    untracked = {item for item in git(source, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\x00") if item}
    if baseline:
        if tracked or untracked:
            raise ValueError("An upstream baseline must have no tracked or untracked source changes")
        return {"mode": "baseline", "source_commit": head, "native_fingerprint": False}
    contract = spec["patch_contract"]
    series, postimages = contract.get("patch_series"), contract.get("postimage_sha256")
    if not isinstance(series, list) or not series or not isinstance(postimages, dict) or not postimages:
        raise ValueError("A hashed native patch series and postimage file hashes are required")
    patches = []
    for entry in series:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"} or not re.fullmatch("[a-f0-9]{64}", str(entry.get("sha256"))):
            raise ValueError("Patch entries must contain exact repository-relative path and SHA-256")
        path = safe_file(repository, entry["path"])
        if digest(path) != entry["sha256"]:
            raise ValueError("Native patch SHA-256 mismatch")
        patches.append(path)
    if set(postimages) != tracked | untracked:
        raise ValueError("Actual source delta does not equal the exact native postimage allowlist")
    for raw, expected in postimages.items():
        if not isinstance(expected, str) or not re.fullmatch("[a-f0-9]{64}", expected) or digest(safe_file(source, raw)) != expected:
            raise ValueError("Applied native source postimage SHA-256 mismatch")
    # git apply --check with several overlapping patches does not simulate
    # sequential reversal. Prove the series in a small disposable fixture;
    # never change the real checkout, its index or its tracked files.
    with tempfile.TemporaryDirectory(prefix="neantik-native-patch-proof-") as temporary:
        fixture = Path(temporary)
        git(fixture, "init", "-q")
        git(fixture, "config", "core.autocrlf", "false")
        for raw in postimages:
            target = fixture.joinpath(*PurePosixPath(raw).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(safe_file(source, raw).read_bytes())
        for patch in reversed(patches):
            git(fixture, "apply", "--reverse", "--check", str(patch))
            git(fixture, "apply", "--reverse", str(patch))
        for raw in tracked:
            target = fixture.joinpath(*PurePosixPath(raw).parts)
            if not target.is_file() or target.read_bytes() != git(source, "show", f"HEAD:{raw}"):
                raise ValueError("Reversed patch series does not recover the pinned upstream source")
        if any(fixture.joinpath(*PurePosixPath(raw).parts).exists() for raw in untracked):
            raise ValueError("Reversed patch series leaves unexpected new source files")
    return {"mode": "native-uncompiled", "source_commit": head, "patch_count": len(patches),
            "verified_postimages": len(postimages), "native_fingerprint_tested": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--spec", type=Path, default=Path(__file__).with_name("buildspec.json"))
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.source, Path(__file__).resolve().parents[2], json.loads(args.spec.read_text(encoding="utf-8")), args.baseline)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"Native patch verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
