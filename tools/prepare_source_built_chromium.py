"""Stage a locally built Chromium runtime for a portable release.

The source checkout must be at a pinned upstream commit. Only explicitly
approved build-compatibility patches may differ from that commit.
This tool never changes the source checkout or the build output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from prepare_bundled_chromium import ROOT_FILES, RUNTIME_FOLDERS, MAX_UNCOMPRESSED, sha256

SOURCE_RUNTIME_FILES = {
    "chrome.VisualElementsManifest.xml",
    "msvcp140.dll", "msvcp140_atomic_wait.dll", "vcruntime140.dll",
    "vcruntime140_1.dll", "vccorlib140.dll",
}
PORTABLE_LOCALES = {"en-US.pak", "ru.pak", "th.pak"}


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True, encoding="utf-8").strip()


def extract_credits(chrome: Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="neantik-credits-") as profile:
        result = subprocess.run(
            [str(chrome), f"--user-data-dir={profile}",
             "--headless=new", "--no-first-run", "--disable-background-networking",
             "--dump-dom", "chrome://credits/"],
            capture_output=True, timeout=60, check=True,
        )
    return result.stdout


def grant_sandbox_read_access(engine: Path) -> None:
    """Let Windows AppContainer children read public engine files, not Data/."""
    if sys.platform != "win32":
        return
    result = subprocess.run(
        ["icacls.exe", str(engine), "/grant:r", "*S-1-15-2-1:(OI)(CI)RX", "/T"],
        capture_output=True, text=True, timeout=45,
    )
    if result.returncode:
        raise ValueError("Could not grant AppContainer read access to staged Chromium")


def stage(args: argparse.Namespace) -> dict[str, object]:
    source = Path(args.source_root).resolve(strict=True)
    build = Path(args.build_root).resolve(strict=True)
    target = Path(args.output).resolve()
    if target.exists():
        raise ValueError(f"Output already exists (never overwritten): {target}")
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        raise ValueError("Expected source commit must be a full lowercase Git SHA")
    if git(source, "rev-parse", "HEAD") != args.commit:
        raise ValueError("Chromium checkout is not at the pinned source commit")
    if git(source, "diff", "--cached", "--name-only"):
        raise ValueError("Chromium checkout has staged source changes")
    changed = set(filter(None, git(source, "diff", "HEAD", "--name-only").splitlines()))
    if changed - {"DEPS", "build/toolchain/win/midl.py"}:
        raise ValueError(f"Unapproved Chromium source changes: {sorted(changed)}")
    patch_bytes = subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--binary", "--", "DEPS", "build/toolchain/win/midl.py"])
    patch_hash = hashlib.sha256(patch_bytes).hexdigest() if patch_bytes else None
    if patch_hash != args.approved_build_patch_sha256:
        raise ValueError("Chromium build-compatibility patch differs from approved SHA-256")
    version_file = source / "chrome" / "VERSION"
    version_parts = dict(line.split("=", 1) for line in version_file.read_text(encoding="utf-8").splitlines() if "=" in line)
    version = ".".join(version_parts[key] for key in ("MAJOR", "MINOR", "BUILD", "PATCH"))
    if version != args.version:
        raise ValueError(f"Pinned Chromium version differs from source: {version}")
    gn_args = build / "args.gn"
    settings = gn_args.read_text(encoding="utf-8")
    if 'is_debug = false' not in settings or 'is_component_build = false' not in settings or 'is_chrome_branded = false' not in settings:
        raise ValueError("Build must be a release-style unbranded monolithic Chromium")

    entries: list[tuple[Path, Path]] = []
    total = 0
    version_manifest = f"{version}.manifest"
    for item in build.iterdir():
        if item.is_file() and item.name in (ROOT_FILES | SOURCE_RUNTIME_FILES | {version_manifest}):
            entries.append((item, Path(item.name)))
        elif item.is_dir() and item.name in RUNTIME_FOLDERS:
            for child in item.rglob("*"):
                if child.is_file() and child.suffix.lower() in {".pak", ".pb", ".json"}:
                    if item.name == "locales" and child.name not in PORTABLE_LOCALES:
                        continue
                    entries.append((child, child.relative_to(build)))
    required = {"chrome.exe", "chrome.dll", "chrome_elf.dll", "icudtl.dat", "resources.pak", version_manifest,
                "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"}
    if not required.issubset({str(relative) for _, relative in entries}):
        raise ValueError("Build output is missing essential Chromium runtime files")
    staged_locales = {relative.name for _, relative in entries if relative.parent == Path("locales")}
    if staged_locales != PORTABLE_LOCALES:
        raise ValueError(f"Build output lacks required portable locale packs: {sorted(PORTABLE_LOCALES - staged_locales)}")
    for item, _ in entries:
        if item.is_symlink():
            raise ValueError(f"Symlink in Chromium runtime: {item}")
        total += item.stat().st_size
        if total > MAX_UNCOMPRESSED:
            raise ValueError("Chromium runtime exceeds the uncompressed size limit")

    with tempfile.TemporaryDirectory(prefix="neantik-clean-chromium-") as temporary:
        staged = Path(temporary) / "Chromium"
        staged.mkdir()
        for item, relative in entries:
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
        shutil.copy2(source / "LICENSE", staged / "LICENSE")
        grant_sandbox_read_access(staged)
        credits = extract_credits(staged / "chrome.exe")
        if len(credits) < 100_000 or b"<!DOCTYPE html" not in credits[:1000]:
            raise ValueError("Could not extract Chromium third-party credits")
        (staged / "credits.html").write_bytes(credits)
        receipt = {
            "format": "neantik-chromium-source-build-v1",
            "channel": "stable",
            "source": f"https://chromium.googlesource.com/chromium/src/+/{args.commit}",
            "source_commit": args.commit,
            "source_tree": git(source, "rev-parse", "HEAD^{tree}"),
            "build_patch_sha256": patch_hash or "",
            "chromium_version": version,
            "build_args_sha256": sha256(gn_args),
            "runtime_file_count": len(entries),
            "locales": sorted(staged_locales),
            "license_sha256": sha256(staged / "LICENSE"),
            "credits_sha256": sha256(staged / "credits.html"),
        }
        (staged / "ENGINE_PROVENANCE.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), str(target))
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--build-root", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--approved-build-patch-sha256", default=None)
    try:
        print(json.dumps(stage(parser.parse_args()), ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Source-built Chromium staging failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
