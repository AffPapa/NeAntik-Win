"""Stage an official Chromium snapshot without build/test executables.

This is an engineering prototype tool. Continuous snapshots are not a stable
security update channel and must not be promoted as a production browser.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


ROOT_FILES = {
    "chrome.exe", "chrome.dll", "chrome_elf.dll", "chrome_wer.dll",
    "chrome_100_percent.pak", "chrome_200_percent.pak", "resources.pak",
    "icudtl.dat", "v8_context_snapshot.bin", "libEGL.dll", "libGLESv2.dll",
    "D3DCompiler_47.dll", "dxcompiler.dll", "vulkan-1.dll",
    "vk_swiftshader.dll", "vk_swiftshader_icd.json", "chrome_proxy.exe",
    "chrome_pwa_launcher.exe", "elevated_tracing_service.exe",
    "elevation_service.exe", "notification_helper.exe", "eventlog_provider.dll",
    "First Run",
}
RUNTIME_FOLDERS = {"locales", "MEIPreload", "IwaKeyDistribution"}
MAX_UNCOMPRESSED = 2_000_000_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stage(args: argparse.Namespace) -> dict[str, object]:
    archive = Path(args.snapshot_zip).resolve(strict=True)
    target = Path(args.output).resolve()
    if target.exists():
        raise ValueError(f"Output already exists (never overwritten): {target}")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
        raise ValueError("Expected SHA-256 must be 64 hexadecimal characters")
    actual = sha256(archive)
    if actual != args.sha256.lower():
        raise ValueError("Snapshot ZIP SHA-256 does not match the pinned value")
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        raise ValueError("Chromium source commit must be a full lowercase Git SHA")
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", args.version):
        raise ValueError("Invalid Chromium version")
    if not re.fullmatch(r"\d{4,8}", args.revision):
        raise ValueError("Invalid Chromium snapshot revision")
    revisions_url = f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{args.revision}/REVISIONS"
    with urllib.request.urlopen(revisions_url, timeout=30) as response:
        revisions = json.load(response)
    if str(revisions.get("chromium_revision")) != args.revision or revisions.get("got_revision") != args.commit:
        raise ValueError("Upstream REVISION metadata does not match the pinned source commit")

    expected_prefix = "chrome-win/"
    with zipfile.ZipFile(archive) as source:
        names = set(source.namelist())
        if f"{expected_prefix}{args.version}.manifest" not in names:
            raise ValueError("Snapshot version manifest is missing")
        entries: list[tuple[zipfile.ZipInfo, Path]] = []
        total = 0
        seen: set[str] = set()
        for entry in source.infolist():
            raw = entry.filename.replace("\\", "/")
            parts = PurePosixPath(raw).parts
            if not raw.startswith(expected_prefix) or any(part in {"", ".", ".."} for part in parts):
                raise ValueError(f"Unexpected ZIP path: {raw}")
            relative = PurePosixPath(raw[len(expected_prefix):])
            if raw.endswith("/") or relative == PurePosixPath("."):
                continue
            if len(relative.parts) == 1:
                allowed = relative.name in ROOT_FILES or relative.name == f"{args.version}.manifest"
            else:
                allowed = relative.parts[0] in RUNTIME_FOLDERS
            if not allowed:
                continue
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Symlink in browser archive: {raw}")
            key = str(relative).casefold()
            if key in seen:
                raise ValueError(f"Duplicate browser archive path: {raw}")
            seen.add(key)
            total += entry.file_size
            if total > MAX_UNCOMPRESSED:
                raise ValueError("Browser archive exceeds the uncompressed size limit")
            entries.append((entry, Path(*relative.parts)))

        required = {"chrome.exe", "chrome.dll", "icudtl.dat", "resources.pak"}
        if not required.issubset({str(path) for _, path in entries}):
            raise ValueError("Browser archive is missing essential runtime files")
        with tempfile.TemporaryDirectory(prefix="neantik-engine-") as temporary:
            staged = Path(temporary) / "Chromium"
            staged.mkdir()
            for entry, relative in entries:
                destination = staged / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as input_file, destination.open("xb") as output_file:
                    shutil.copyfileobj(input_file, output_file)

            license_url = f"https://chromium.googlesource.com/chromium/src/+/{args.commit}/LICENSE?format=TEXT"
            with urllib.request.urlopen(license_url, timeout=30) as response:
                license_bytes = base64.b64decode(response.read(), validate=True)
            if b"Redistribution and use in source and binary forms" not in license_bytes:
                raise ValueError("Retrieved Chromium license did not match expected text")
            (staged / "LICENSE").write_bytes(license_bytes)

            with tempfile.TemporaryDirectory(prefix="neantik-credits-") as profile:
                result = subprocess.run(
                    [str(staged / "chrome.exe"), f"--user-data-dir={profile}",
                     "--headless=new", "--no-first-run", "--disable-background-networking",
                     "--dump-dom", "chrome://credits/"],
                    capture_output=True, timeout=45, check=True,
                )
            if len(result.stdout) < 100_000 or b"<!DOCTYPE html" not in result.stdout[:1000]:
                raise ValueError("Could not extract the browser's third-party credits")
            (staged / "credits.html").write_bytes(result.stdout)
            receipt = {
                "format": "neantik-chromium-snapshot-stage-v1",
                "source": f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{args.revision}/chrome-win.zip",
                "snapshot_sha256": actual,
                "source_commit": args.commit,
                "revisions_url": revisions_url,
                "chromium_version": args.version,
                "channel": "continuous-snapshot-not-stable",
                "license_url": license_url,
                "credits_sha256": sha256(staged / "credits.html"),
                "runtime_file_count": len(entries),
            }
            (staged / "ENGINE_PROVENANCE.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged), str(target))
            return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-zip", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(stage(args), ensure_ascii=False))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        print(f"Engine staging failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
