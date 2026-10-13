"""Manual, read-only second-Windows-host gate for one immutable public ZIP.

The operator supplies the published tag, exact ZIP SHA-256 and binary source
commit. No unverified archive content is executed. Only synthetic loopback
storage is exercised; this is not cross-account migration or anonymity QA.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

from benchmark_packaged_startup import extract_verified, sha256


REPOSITORY = "AffPapa/NeAntik-Win"
MAX_ARCHIVE_BYTES = 700 * 1024 * 1024
TAG_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+-preview\Z")
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


def validated_inputs(tag: str, archive_sha256: str, source_commit: str) -> tuple[str, str, str]:
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError("Expected a literal vX.Y.Z-preview release tag")
    if not SHA_PATTERN.fullmatch(archive_sha256):
        raise ValueError("Expected a lowercase 64-digit ZIP SHA-256")
    if not COMMIT_PATTERN.fullmatch(source_commit):
        raise ValueError("Expected a lowercase 40-digit source commit")
    return tag, archive_sha256, source_commit


def release_asset(tag: str) -> tuple[str, str]:
    # The validated literal tag identifies one public release URL; a missing
    # tag/asset fails download. The caller-pinned hash authenticates its bytes.
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError("Invalid release tag")
    asset_name = f"NeAntikWin-portable-{tag}.zip"
    return f"https://github.com/{REPOSITORY}/releases/download/{tag}/{asset_name}", asset_name


def download_exact(url: str, destination: Path, expected_sha256: str) -> None:
    request = urllib.request.Request(url, headers={
        "Accept": "application/octet-stream",
        "User-Agent": "NeAntik-public-portable-second-host-gate",
    })
    digest = hashlib.sha256()
    written = 0
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("xb") as stream:
        if response.status != 200:
            raise ValueError("Public ZIP download failed")
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            written += len(block)
            if written > MAX_ARCHIVE_BYTES:
                raise ValueError("Public ZIP exceeded size limit")
            stream.write(block)
            digest.update(block)
    if not written or digest.hexdigest() != expected_sha256:
        raise ValueError("Public ZIP SHA-256 mismatch")


def checked_process(arguments: list[str], *, cwd: Path, timeout: int,
                    environment: dict[str, str] | None = None) -> None:
    # Never echo subprocess output: both EXE and harness may expose paths or
    # synthetic storage. The bounded gate reports only the resulting status.
    completed = subprocess.run(arguments, cwd=cwd, env=environment,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=timeout, check=False)
    if completed.returncode:
        raise RuntimeError("A packaged QA subprocess failed")


def assert_runner_source_matches_release(repository: Path, portable_root: Path) -> None:
    source_provenance = json.loads((portable_root / "build-provenance.json").read_text(encoding="utf-8"))
    source_files = source_provenance.get("source_files")
    if not isinstance(source_files, list):
        raise ValueError("Release source provenance is incomplete")
    source_hashes = {item.get("path"): item.get("sha256") for item in source_files
                     if isinstance(item, dict)}
    # The harness is from the trusted workflow checkout (never an arbitrary
    # dispatch-supplied ref). Product modules must match release build inputs.
    for filename in ("nevision_win.py", "profile_identity.py", "privacy_defaults.py",
                     "release-version.json"):
        expected = source_hashes.get(filename)
        if not isinstance(expected, str) or sha256(repository / filename) != expected:
            raise ValueError("Runner product source differs from the verified release")


def bundled_chromium(portable_root: Path) -> tuple[Path, Path]:
    engine = portable_root / "Engine" / "Chromium"
    chrome = engine / "chrome.exe"
    if not chrome.is_file() or engine.resolve().parent != (portable_root / "Engine").resolve():
        raise ValueError("Verified archive has no bundled Chromium at the expected path")
    return engine, chrome


def verifier_failure_line(verifier: Path, archive: Path) -> str:
    """Report only the public verifier's failing line, never its raw output."""
    script = ("Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop; "
              "try { & '" + str(verifier).replace("'", "''") + "' -ArchivePath '" +
              str(archive).replace("'", "''") + "' | Out-Null } "
              "catch { Write-Output ('line=' + $_.InvocationInfo.ScriptLineNumber); exit 1 }")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            timeout=180, check=False)
    match = re.search(r"(?m)^line=([0-9]{1,4})$", result.stdout)
    return match.group(1) if match else "unknown"


def run(tag: str, archive_sha256: str, source_commit: str) -> dict[str, str | int]:
    tag, archive_sha256, source_commit = validated_inputs(tag, archive_sha256, source_commit)
    if os.name != "nt":
        raise RuntimeError("This gate requires a Windows host")
    repository = Path(__file__).resolve().parents[1]
    runner_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True,
        stderr=subprocess.DEVNULL, timeout=10).strip()
    url, asset_name = release_asset(tag)
    with tempfile.TemporaryDirectory(prefix="neantik-second-host-") as temporary:
        root = Path(temporary)
        archive = root / asset_name
        print("Gate stage: download", flush=True)
        download_exact(url, archive, archive_sha256)
        extraction = root / "extracted"
        extraction.mkdir()
        verifier = repository / "tools" / "verify-release-archive.ps1"
        print("Gate stage: archive verification and extraction", flush=True)
        try:
            executable, provenance = extract_verified(archive, extraction, archive_sha256, verifier)
        except ValueError as error:
            if str(error) == "Release archive verifier failed":
                print(f"Archive verifier failure line: {verifier_failure_line(verifier, archive)}", flush=True)
            raise
        if (provenance["version"] != tag.removeprefix("v") or
                provenance["source_commit"] != source_commit):
            raise ValueError("Verified archive version or source commit differs")
        portable_root = executable.parent.resolve()
        print("Gate stage: source provenance", flush=True)
        assert_runner_source_matches_release(repository, portable_root)
        print("Gate stage: bundled Chromium layout", flush=True)
        engine, chrome = bundled_chromium(portable_root)
        # Chromium's AppContainer children need read/execute access to this
        # public engine tree only. Never grant access to Data or the user tree.
        print("Gate stage: AppContainer ACL", flush=True)
        checked_process(["icacls.exe", str(engine), "/grant:r",
                         "*S-1-15-2-1:(OI)(CI)RX", "/T"], cwd=root, timeout=120)
        print("Gate stage: packaged self-test", flush=True)
        checked_process([str(executable), "--self-test"], cwd=portable_root, timeout=120)
        harness_tmp = root / "harness-temp"
        harness_tmp.mkdir()
        report = root / "storage-report.json"
        environment = os.environ.copy()
        environment["TMP"] = str(harness_tmp)
        environment["TEMP"] = str(harness_tmp)
        print("Gate stage: synthetic loopback storage", flush=True)
        checked_process([sys.executable, str(repository / "tools" / "browser_integration.py"),
                         "--chrome", str(chrome), "--output", str(report)],
                        cwd=repository, timeout=480, environment=environment)
        # Read only allowlisted aggregate fields. Do not publish the raw report.
        outcome = json.loads(report.read_text(encoding="utf-8"))
        assertions = outcome.get("assertions")
        visits = outcome.get("visits")
        if (outcome.get("status") != "passed" or not isinstance(assertions, list) or
                len(assertions) < 15 or not all(item.get("passed") is True for item in assertions) or
                not isinstance(visits, list) or len(visits) < 6):
            raise RuntimeError("Loopback storage report did not pass the expected assertions")
        return {"tag": tag, "source_commit": source_commit, "runner_commit": runner_commit,
                "zip_sha256": archive_sha256,
                "exe_sha256": provenance["exe_sha256"],
                "chrome_sha256": sha256(chrome),
                "storage_assertions": len(assertions), "storage_visits": len(visits)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    try:
        result = run(args.tag, args.sha256, args.source_commit)
    except Exception as error:
        # No exception text: URLs, runtime paths and raw browser output must
        # not enter the public Actions log. Exit nonzero is authoritative FAIL.
        print(f"Second-host portable gate: FAIL ({type(error).__name__})", file=sys.stderr)
        return 1
    print("Second-host portable gate: PASS")
    print(f"Release {result['tag']} source {result['source_commit']}")
    print(f"QA harness checkout {result['runner_commit']}")
    print(f"ZIP SHA-256 {result['zip_sha256']}")
    print(f"EXE SHA-256 {result['exe_sha256']}")
    print(f"Chromium SHA-256 {result['chrome_sha256']}")
    print(f"Synthetic loopback storage: {result['storage_assertions']} assertions, "
          f"{result['storage_visits']} visits")
    print("Scope: one hosted Windows account; not another user's account, GUI, or external privacy proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
