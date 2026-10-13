"""Five ordinary portable-manager starts in an isolated, disposable extraction.

This measures the first observed visible main window, not full UI readiness,
browser startup, a cold OS cache, or another Windows host. No user Data is read.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile


MAX_UNCOMPRESSED = 4 * 1024**3
EXE_NAME = "NeAntikWin.exe"
WINDOW_PREFIX = "NeAntik Win "
WINDOW_TIMEOUT_SECONDS = 30
IDLE_SECONDS = 5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_members(archive: zipfile.ZipFile) -> tuple[str, list[zipfile.ZipInfo]]:
    """Fail closed before extracting any member, including Windows path quirks."""
    members = archive.infolist()
    if not members:
        raise ValueError("Empty archive")
    roots: set[str] = set()
    seen: set[str] = set()
    total = 0
    for item in members:
        raw = item.filename
        path = raw.rstrip("/")
        parts = path.split("/")
        if (not path or raw.startswith("/") or "\\" in raw or ":" in raw or
                any(not part or part in (".", "..") or part.endswith((".", " ")) or
                    re.search(r'[\x00-\x1f<>"|?*]', part) or
                    re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I)
                    for part in parts)):
            raise ValueError("Unsafe archive member")
        mode = (item.external_attr >> 16) & 0o170000
        if mode not in (0, 0o040000, 0o100000) or (item.external_attr & 0x400):
            raise ValueError("Archive link or special member")
        normalized = path.casefold()
        if normalized in seen:
            raise ValueError("Duplicate archive member")
        seen.add(normalized)
        roots.add(parts[0])
        if len(parts) > 1 and parts[1].casefold() in {"data", "profiles", "backups", "logs"}:
            raise ValueError("Archive includes runtime data")
        total += item.file_size
        if total > MAX_UNCOMPRESSED:
            raise ValueError("Archive exceeds expansion limit")
    if len(roots) != 1:
        raise ValueError("Archive must have one root")
    root = roots.pop()
    if f"{root}/{EXE_NAME}".casefold() not in seen:
        raise ValueError("Portable executable missing")
    return root, members


def extract_verified(archive_path: Path, destination: Path, expected_sha256: str,
                     verifier: Path) -> tuple[Path, dict]:
    actual_hash = sha256(archive_path)
    if actual_hash != expected_sha256.lower():
        raise ValueError("ZIP SHA-256 mismatch")
    # The release verifier checks manifest hashes, provenance, licenses and
    # forbidden data. Suppress its output because this harness reports only an
    # allowlisted summary; a failed verifier must never be bypassed.
    # Python launched from PowerShell can inherit a module-autoload-disabled
    # environment. Import the verifier's stock utility module explicitly.
    quoted_verifier = str(verifier.resolve(strict=True)).replace("'", "''")
    quoted_archive = str(archive_path.resolve(strict=True)).replace("'", "''")
    command = ("Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop; "
               f"& '{quoted_verifier}' -ArchivePath '{quoted_archive}'")
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    checked = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                              "-EncodedCommand", encoded],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=180, check=False)
    if checked.returncode:
        raise ValueError("Release archive verifier failed")
    with zipfile.ZipFile(archive_path) as archive:
        root, members = validate_members(archive)
        manifest_member = f"{root}/release-manifest.json"
        if manifest_member not in archive.namelist():
            raise ValueError("Release manifest missing")
        manifest = json.loads(archive.read(manifest_member))
        if manifest.get("executable") != EXE_NAME:
            raise ValueError("Unexpected release executable")
        commit = manifest.get("source_commit")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid source commit")
        for item in members:
            target = destination.joinpath(*item.filename.rstrip("/").split("/"))
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("xb") as sink:
                    shutil.copyfileobj(source, sink, 1024 * 1024)
    executable = destination / root / EXE_NAME
    if not executable.is_file() or executable.is_symlink():
        raise ValueError("Extracted portable executable missing")
    return executable, {"version": manifest["version"], "source_commit": commit,
                        "zip_sha256": actual_hash, "exe_sha256": sha256(executable),
                        "zip_size_bytes": archive_path.stat().st_size,
                        "archive_members": len(members)}


def visible_main_windows(pid: int) -> list[int]:
    if sys.platform != "win32":
        raise OSError("Windows is required")
    user32 = ctypes.windll.user32
    found: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    def inspect(hwnd: int, unused: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                title = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, title, length + 1)
                if title.value.startswith(WINDOW_PREFIX):
                    found.append(hwnd)
        return True

    callback = callback_type(inspect)
    if not user32.EnumWindows(callback, 0):
        raise OSError("EnumWindows failed")
    return found


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def memory_sample(pid: int) -> dict[str, int]:
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD)
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
    if not handle:
        raise OSError("Cannot open owned process for memory sample")
    try:
        sample = ProcessMemoryCounters()
        sample.cb = ctypes.sizeof(sample)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(sample), sample.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return {"working_set_bytes": int(sample.WorkingSetSize),
                "private_bytes": int(sample.PrivateUsage)}
    finally:
        kernel32.CloseHandle(handle)


def run_once(executable: Path) -> dict:
    started = time.perf_counter()
    process = subprocess.Popen([str(executable)], cwd=executable.parent,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    visible: list[int] = []
    try:
        deadline = started + WINDOW_TIMEOUT_SECONDS
        while time.perf_counter() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Manager exited before visible window")
            visible = visible_main_windows(process.pid)
            if visible:
                break
            time.sleep(.025)
        if not visible:
            raise TimeoutError("Visible main window not observed")
        window_ms = round((time.perf_counter() - started) * 1000, 3)
        startup_memory = memory_sample(process.pid)
        time.sleep(IDLE_SECONDS)
        if process.poll() is not None:
            raise RuntimeError("Manager exited during idle interval")
        idle_memory = memory_sample(process.pid)
        return {"window_observed_ms": window_ms, "memory_at_window": startup_memory,
                "memory_after_idle": idle_memory, "idle_seconds": IDLE_SECONDS}
    finally:
        # Only the process launched by this function is closed. Never enumerate
        # or terminate other NeAntik windows, user browsers or user profiles.
        if process.poll() is None:
            try:
                windows = visible_main_windows(process.pid)
            except OSError:
                windows = []
            for hwnd in windows:
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def summarize(samples: list[dict]) -> dict:
    times = [sample["window_observed_ms"] for sample in samples]
    return {"runs": len(times), "median_window_observed_ms": round(statistics.median(times), 3),
            "min_window_observed_ms": min(times), "max_window_observed_ms": max(times),
            "spread_window_observed_ms": round(max(times) - min(times), 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows is required")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
        parser.error("--sha256 must be a SHA-256 digest")
    archive_path = args.zip.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or not output.parent.is_dir():
        parser.error("Output must be a new filename in an existing directory")
    verifier = Path(__file__).with_name("verify-release-archive.ps1")
    if not verifier.is_file():
        raise ValueError("Release verifier missing")
    with tempfile.TemporaryDirectory(prefix="neantik-packaged-startup-") as folder:
        root = Path(folder)
        executable, provenance = extract_verified(archive_path, root, args.sha256, verifier)
        samples = [run_once(executable) for _ in range(5)]
        report = {"format": "neantik-packaged-startup-v1", "status": "passed",
                  **provenance, "host": {"windows": sys.getwindowsversion().build,
                                          "logical_cpus": os.cpu_count()},
                  "measurements": samples, "summary": summarize(samples),
                  "scope": "five sequential ordinary starts from one disposable ZIP extraction; manager only",
                  "limitations": ["Ordinary/warm-cache observations; no true cold OS-cache measurement.",
                                  "Visible titled window is not proof of full UI readiness.",
                                  "Only manager PID memory is sampled; child Chromium is not launched or counted.",
                                  "Single Windows host; no Windows 10 or accessibility result."]}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print("Packaged startup: PASS (5 ordinary manager launches); report written")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, TimeoutError, zipfile.BadZipFile,
            subprocess.TimeoutExpired) as error:
        print(f"Packaged startup: INCONCLUSIVE ({type(error).__name__})", file=sys.stderr)
        raise SystemExit(2)
