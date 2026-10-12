"""Stage a locally built Chromium runtime for a portable release.

The source checkout must be at a pinned upstream commit. Only explicitly
approved build-compatibility and privacy-baseline patches may differ from it.
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
from export_native_persona_patch import export as export_native_persona_patch

SOURCE_RUNTIME_FILES = {
    "chrome.VisualElementsManifest.xml",
    "msvcp140.dll", "msvcp140_atomic_wait.dll", "vcruntime140.dll",
    "vcruntime140_1.dll", "vccorlib140.dll",
}
PORTABLE_LOCALES = {"en-US.pak", "ru.pak", "th.pak"}
BUILD_PATCH_FILES = {"DEPS", "build/toolchain/win/midl.py"}
PRIVACY_PATCH_FILES = {
    "third_party/blink/common/device_memory/approximated_device_memory.cc",
    "third_party/blink/common/device_memory/approximated_device_memory_unittest.cc",
    "third_party/blink/renderer/core/frame/navigator_concurrent_hardware.cc",
}


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


_DYNAMIC_CREDITS_THEME = re.compile(
    rb'<link href="chrome://theme/colors\.css\?sets=ui%2Cchrome&amp;version=[0-9]+" '
    rb'rel="stylesheet" type="text/css">'
)


def normalize_credits_html(credits: bytes) -> bytes:
    """Remove Chromium's per-run theme URL from the offline credits copy."""
    theme_marker = b'chrome://theme/colors.css?'
    matches = _DYNAMIC_CREDITS_THEME.findall(credits)
    if theme_marker in credits and len(matches) != 1:
        raise ValueError("Unexpected dynamic Chromium theme URL in credits")
    return _DYNAMIC_CREDITS_THEME.sub(b"", credits)


def probe_native_core(chrome: Path, version: str, commit: str) -> dict[str, object]:
    """Read a compiled capability handshake, not just a source-file claim."""
    with tempfile.TemporaryDirectory(prefix="neantik-native-core-probe-") as temporary:
        root = Path(temporary)
        output = root / "core-info.json"
        result = subprocess.run(
            [str(chrome), "--headless", f"--user-data-dir={root / 'Profile'}",
             "--no-first-run", "--disable-background-networking",
             f"--neantik-core-info={output}"],
            capture_output=True, timeout=20, check=False,
        )
        if result.returncode != 0 or not output.is_file():
            raise ValueError("Built Chromium lacks the native persona core handshake")
        info = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(info, dict) or info.get("engine_id") != "neantik-chromium" or info.get("schema") != 2:
        raise ValueError("Invalid native persona core identity")
    if info.get("version") != version or info.get("source_commit") != commit:
        raise ValueError("Native persona core version or source commit differs")
    capabilities = info.get("capabilities")
    required = ("stable_seed", "hardware_concurrency", "device_memory",
                "canvas_opaque_srgb_uint8", "timezone")
    if not isinstance(capabilities, dict) or not all(capabilities.get(key) is True for key in required):
        raise ValueError("Native persona core lacks required compiled capabilities")
    return info


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
    native_hash: str | None = None
    native_requested = bool(getattr(args, "approved_native_patch_sha256", None) or
                            getattr(args, "native_patch_file", None))
    if native_requested:
        if args.approved_privacy_patch_sha256 or args.privacy_patch_file:
            raise ValueError("Baseline and native persona patches are mutually exclusive")
        native_bytes = export_native_persona_patch(source)
        native_hash = hashlib.sha256(native_bytes).hexdigest()
        if native_hash != args.approved_native_patch_sha256:
            raise ValueError("Native persona source patch differs from approved SHA-256")
        if not args.native_patch_file or Path(args.native_patch_file).resolve(strict=True).read_bytes() != native_bytes:
            raise ValueError("Published native persona patch differs from the source diff")
    else:
        untracked = set(filter(None, git(source, "ls-files", "--others", "--exclude-standard").splitlines()))
        if untracked:
            raise ValueError(f"Unapproved untracked Chromium source files: {sorted(untracked)}")
        changed = set(filter(None, git(source, "diff", "HEAD", "--name-only").splitlines()))
        if changed - (BUILD_PATCH_FILES | PRIVACY_PATCH_FILES):
            raise ValueError(f"Unapproved Chromium source changes: {sorted(changed)}")
    patch_bytes = subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--binary", "--", *sorted(BUILD_PATCH_FILES)])
    patch_hash = hashlib.sha256(patch_bytes).hexdigest() if patch_bytes else None
    if patch_hash != args.approved_build_patch_sha256:
        raise ValueError("Chromium build-compatibility patch differs from approved SHA-256")
    if native_requested:
        privacy_hash = native_hash
    else:
        privacy_bytes = subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--binary", "--", *sorted(PRIVACY_PATCH_FILES)])
        privacy_hash = hashlib.sha256(privacy_bytes).hexdigest() if privacy_bytes else None
        if privacy_hash != args.approved_privacy_patch_sha256:
            raise ValueError("Chromium privacy patch differs from approved SHA-256")
        if privacy_hash:
            if not args.privacy_patch_file:
                raise ValueError("A public privacy patch file is required for modified browser runtime")
            patch_file = Path(args.privacy_patch_file).resolve(strict=True)
            if patch_file.read_bytes() != privacy_bytes:
                raise ValueError("Public privacy patch bytes differ from the approved source diff")
            subprocess.run(["git", "-C", str(source), "apply", "--reverse", "--check", str(patch_file)],
                           check=True, capture_output=True)
        elif args.privacy_patch_file:
            raise ValueError("Privacy patch file provided but browser runtime is unchanged")
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
        credits = normalize_credits_html(extract_credits(staged / "chrome.exe"))
        if len(credits) < 100_000 or b"<!DOCTYPE html" not in credits[:1000]:
            raise ValueError("Could not extract Chromium third-party credits")
        (staged / "credits.html").write_bytes(credits)
        native_core_info = probe_native_core(staged / "chrome.exe", version, args.commit) if native_requested else None
        receipt = {
            "format": "neantik-chromium-source-build-v1",
            "channel": "stable",
            "source": f"https://chromium.googlesource.com/chromium/src/+/{args.commit}",
            "source_commit": args.commit,
            "source_tree": git(source, "rev-parse", "HEAD^{tree}"),
            "build_patch_sha256": patch_hash or "",
            "privacy_patch_sha256": privacy_hash or "",
            "native_persona_patch_sha256": native_hash or "",
            "native_persona_core_info": native_core_info,
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
    parser.add_argument("--approved-privacy-patch-sha256", default=None)
    parser.add_argument("--privacy-patch-file", default=None)
    parser.add_argument("--approved-native-patch-sha256", default=None)
    parser.add_argument("--native-patch-file", default=None)
    try:
        print(json.dumps(stage(parser.parse_args()), ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Source-built Chromium staging failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
