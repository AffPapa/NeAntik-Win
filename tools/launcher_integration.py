"""Disposable Windows integration check for a *packaged* NeAntik browser launch.

Example:
  python tools/launcher_integration.py --portable-root C:\\path\\to\\NeAntikWin-portable-v0.7.0-preview --output C:\\path\\to\\report.json

The source portable folder is read only. Its Chromium engine is copied to a
fresh temporary root; Storage creates only synthetic profiles there. An owned
Windows Job gates the browser process before it starts and kills only its own
process tree at teardown. No external URL, user profile, or visible browser
window is used. The report checks launcher wiring, not anonymity or leaks.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
from nevision_win import APP_VERSION, AppPaths, BrowserLauncher, Storage  # noqa: E402
from profile_identity import identity_arguments, native_preview_identity  # noqa: E402
from browser_integration import GATED_CHROME_CODE, HarnessError, OwnedJob, require  # noqa: E402

ORIGINAL_POPEN = subprocess.Popen
EXPECTED_CONTENT_DEFAULTS = {
    "geolocation": 2, "notifications": 2, "media_stream_camera": 2, "media_stream_mic": 2,
}


def check_engine_tree(source: Path) -> None:
    """Reject links/reparse points before copying untrusted portable input."""
    require(source.is_dir() and not source.is_symlink(), "Portable Chromium engine is missing or linked")
    pending = [source]
    while pending:
        path = pending.pop()
        metadata = path.lstat()
        require(not path.is_symlink() and not getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "Portable Chromium engine contains a link/junction")
        require(stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode), "Engine contains a non-regular entry")
        if stat.S_ISDIR(metadata.st_mode):
            with os.scandir(path) as children:
                pending.extend(Path(child.path) for child in children)


def job_pids(job: OwnedJob) -> list[int]:
    class ProcessIds(ctypes.Structure):
        _fields_ = [("assigned", wintypes.DWORD), ("count", wintypes.DWORD),
                    ("pids", ctypes.c_size_t * 512)]

    result = ProcessIds()
    if not job.kernel.QueryInformationJobObject(job.handle, 3, ctypes.byref(result), ctypes.sizeof(result), None):
        raise ctypes.WinError(ctypes.get_last_error())
    require(result.count <= 512, "Too many processes in QA job")
    return [int(result.pids[index]) for index in range(result.count)]


def image_path(pid: int) -> Path | None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None  # A short-lived Chromium child may already have exited.
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            return None
        return Path(buffer.value)
    finally:
        kernel.CloseHandle(handle)


def launch_case(storage: Storage, launcher: BrowserLauncher, name: str,
                engine: Path, proxy_id: str | None,
                native_preview: bool = False) -> dict[str, Any]:
    profile_data: dict[str, Any] = {"name": f"Disposable launcher QA {name}", "proxy_id": proxy_id}
    if native_preview:
        profile_data["fingerprint"] = native_preview_identity(987654321)
    profile_id = storage.save_profile(profile_data)
    profile = storage.get_profile(profile_id)
    require(profile is not None, "Synthetic profile was not saved")
    job = OwnedJob()
    captured: list[str] = []
    seeded_preferences: bytes | None = None
    helper: subprocess.Popen[bytes] | None = None

    def owned_popen(arguments: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        nonlocal helper, seeded_preferences
        require(helper is None, "BrowserLauncher attempted multiple process launches")
        captured.extend(arguments)
        require(Path(arguments[0]).resolve() == engine.resolve(), "Launcher selected a different browser engine")
        # This callback runs at the exact BrowserLauncher -> Popen boundary:
        # verify the one-time defaults exist *before* Chromium can alter them.
        prefs_path = storage.profile_path(profile_id) / "Default" / "Preferences"
        require(prefs_path.is_file(), "Launcher did not seed new-profile Preferences before spawn")
        seeded_preferences = prefs_path.read_bytes()
        initial = json.loads(seeded_preferences)
        require(initial["profile"]["cookie_controls_mode"] == 1, "Third-party cookie default was not seeded")
        require(initial["net"]["network_prediction_options"] == 2, "Preloading was not disabled")
        require(initial["profile"]["default_content_setting_values"] == EXPECTED_CONTENT_DEFAULTS,
                "Permission defaults were not seeded")
        expected_downloads = str(storage.profile_path(profile_id).resolve() / "Downloads")
        require(initial.get("download", {}).get("default_directory") == expected_downloads,
                "Managed per-profile download directory was not seeded")
        require((storage.profile_path(profile_id) / "Downloads").is_dir(),
                "Managed per-profile download folder is missing")
        # BrowserLauncher has already prepared engine sandbox ACLs. The gate
        # ensures Chromium is born *after* the helper has joined the owned job.
        helper = ORIGINAL_POPEN(
            [sys.executable, "-I", "-S", "-c", GATED_CHROME_CODE, *arguments, "--headless", "about:blank"],
            cwd=kwargs.get("cwd"), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        try:
            job.assign(helper)
            require(helper.stdin is not None, "QA gate has no stdin")
            helper.stdin.write(b"G")
            helper.stdin.close()
        except BaseException:
            job.close()
            with contextlib.suppress(Exception):
                helper.wait(timeout=5)
            raise
        return helper

    observation: dict[str, Any] = {"case": name, "profile_id": profile_id,
                                   "proxy_assigned": bool(proxy_id), "native_preview": native_preview}
    try:
        with patch("nevision_win.subprocess.Popen", side_effect=owned_popen):
            process = launcher.launch(profile)
        require(process is helper, "Launcher returned a different process")
        deadline = time.monotonic() + 8
        engine_pids: list[int] = []
        while time.monotonic() < deadline:
            candidates = job_pids(job)
            engine_pids = [pid for pid in candidates if (path := image_path(pid)) is not None and path.resolve() == engine.resolve()]
            if engine_pids and storage._windows_chromium_lock_is_active(profile_id):
                break
            if helper.poll() is not None:
                break
            time.sleep(0.1)
        require(bool(engine_pids), "Owned job contains no bundled Chromium process")
        require(storage._windows_chromium_lock_is_active(profile_id), "Chromium did not lock its isolated profile")
        require(storage.get_profile(profile_id)["browser_family"] == "chromium", "Profile was not pinned to Chromium")
        web_rtc_flag = "--webrtc-ip-handling-policy=disable_non_proxied_udp"
        require((web_rtc_flag in captured) == bool(proxy_id), "WebRTC policy argument does not match proxy assignment")
        for flag in ("--proxy-bypass-list=<-loopback>", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", "--disable-quic"):
            require((flag in captured) == bool(proxy_id), f"Strict proxy flag does not match assignment: {flag}")
        require(f"--user-data-dir={storage.profile_path(profile_id)}" in captured, "Browser did not receive isolated user data path")
        expected_proxy = "--proxy-server=http://127.0.0.1:9"
        require((expected_proxy in captured) == bool(proxy_id), "Proxy argument does not match saved assignment")
        persona_flags = identity_arguments(profile_data["fingerprint"]) if native_preview else []
        require(all(flag in captured for flag in persona_flags), "Native persona arguments are missing")
        require(("--neantik-fingerprint-seed=987654321" in captured) == native_preview,
                "Native persona seed leaked into an ordinary profile or was omitted")
        require(seeded_preferences is not None, "Initial Preferences were not captured")
        prefs_path = storage.profile_path(profile_id) / "Default" / "Preferences"
        prefs_deadline = time.monotonic() + 3
        while not prefs_path.is_file() and time.monotonic() < prefs_deadline and helper.poll() is None:
            time.sleep(0.1)
        require(prefs_path.is_file(), "Initial Preferences disappeared during browser launch")
        parsed = json.loads(prefs_path.read_text(encoding="utf-8"))
        require(isinstance(parsed, dict), "Chromium Preferences is not a JSON object")
        persisted_prefs: dict[str, Any] = parsed
        require(persisted_prefs["profile"]["cookie_controls_mode"] == 1,
                "Chromium did not retain third-party cookie default")
        require(persisted_prefs["net"]["network_prediction_options"] == 2,
                "Chromium did not retain disabled preloading")
        persisted_permissions = persisted_prefs["profile"]["default_content_setting_values"]
        require(all(persisted_permissions.get(key) == value for key, value in EXPECTED_CONTENT_DEFAULTS.items()),
                "Chromium did not retain permission defaults")
        require(persisted_prefs.get("download", {}).get("default_directory") ==
                str(storage.profile_path(profile_id).resolve() / "Downloads"),
                "Chromium did not retain managed profile download directory")
        observation.update({"status": "passed", "helper_pid": helper.pid, "engine_pids": engine_pids,
                            "chromium_lock_active": True, "browser_family": "chromium",
                            "web_rtc_policy_argument": web_rtc_flag in captured,
                            "proxy_argument": expected_proxy in captured,
                            "preferences_inspection": {
                                "seeded_before_browser_spawn": True,
                                "file_present_after_launch": True,
                                "cookie_controls_mode": persisted_prefs["profile"]["cookie_controls_mode"],
                                "managed_downloads": True,
                                "permission_defaults": {key: persisted_permissions[key] for key in EXPECTED_CONTENT_DEFAULTS},
                                "webrtc_keys": sorted((persisted_prefs.get("webrtc") or {}).keys())
                                if isinstance(persisted_prefs.get("webrtc"), dict) else []}})
    finally:
        job.close()  # Kills this QA job and its descendants only.
        if helper is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                helper.wait(timeout=10)
        deadline = time.monotonic() + 5
        while storage._windows_chromium_lock_is_active(profile_id) and time.monotonic() < deadline:
            time.sleep(0.1)
        require(not storage._windows_chromium_lock_is_active(profile_id), "QA Chromium lock remained active after owned job close")
    return observation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable-root", required=True, type=Path, help="Unpacked release folder; it is never modified")
    parser.add_argument("--output", required=True, type=Path, help="New JSON report path")
    parser.add_argument("--native-persona", action="store_true",
                        help="Also test an opt-in persona against an exact staged schema-2 core")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This integration check requires Windows")
    source_root = args.portable_root.resolve(strict=True)
    source_engine = source_root / "Engine" / "Chromium"
    packaged_version = json.loads((source_root / "release-version.json").read_text(encoding="utf-8"))["version"]
    require(packaged_version == APP_VERSION, "Packaged release version differs from source launcher version")
    output = args.output.resolve()
    if not output.parent.is_dir() or output.exists():
        parser.error("Output parent must exist and report must not already exist")
    check_engine_tree(source_engine)
    report: dict[str, Any] = {"format": "neantik-packaged-launcher-integration-v1", "app_version": APP_VERSION,
                              "started_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
                              "source_portable_root": str(source_root), "cases": [],
                              "limitations": ["Only disposable about:blank headless launches; no public IP, DNS, WebRTC leak or anonymity test.",
                                              "WebRTC command-line policy is verified, not end-to-end ICE candidate behavior.",
                              "Privacy defaults are inspected in Preferences; the WebRTC policy is command-line, not a persisted preference.",
                                              "No installed Chrome/Edge, proxy authentication, extension or full GUI coverage."]}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-launcher-integration-") as qa_dir:
            qa_root = Path(qa_dir)
            target_engine = qa_root / "Engine" / "Chromium"
            target_engine.parent.mkdir()
            shutil.copytree(source_engine, target_engine)
            storage = Storage(AppPaths(qa_root))
            launcher = BrowserLauncher(storage)
            require(launcher.resolve_browser() == target_engine / "chrome.exe", "Copied portable engine was not discovered")
            if args.native_persona:
                require(launcher.native_persona_capabilities() is not None,
                        "Bundled engine does not have a verified schema-2 native persona receipt")
            launcher.ensure_bundled_sandbox_access(target_engine)
            report["cases"].append(launch_case(storage, launcher, "without_proxy", target_engine / "chrome.exe", None))
            proxy_id = storage.save_proxy({"name": "Unreachable local QA proxy", "scheme": "http", "host": "127.0.0.1", "port": 9})
            report["cases"].append(launch_case(storage, launcher, "with_proxy", target_engine / "chrome.exe", proxy_id))
            if args.native_persona:
                report["cases"].append(launch_case(storage, launcher, "native_without_proxy",
                                                   target_engine / "chrome.exe", None, True))
                report["cases"].append(launch_case(storage, launcher, "native_with_proxy",
                                                   target_engine / "chrome.exe", proxy_id, True))
            report["cleanup"] = "Only a new disposable QA root was removed; source portable folder was read-only."
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "report": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
