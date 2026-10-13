"""Bounded A/B BrowserLauncher isolation check against an unpacked portable ZIP.

Example:
  python tools/concurrent_profile_integration.py --portable-root C:\\release\\NeAntikWin-portable --expected-chrome-sha256 HEX --output C:\\qa\\concurrent.json

Copies the verified engine into a new temporary root. Only synthetic profiles,
loopback HTTP and owned headless browser processes are used. This is one manager
instance, not a two-manager or public-network/privacy proof.
"""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import html
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nevision_win import APP_VERSION, AppPaths, BrowserLauncher, NeVisionError, Storage  # noqa: E402
from browser_integration import (EMPTY, PAGE, Handler, OwnedJob, GATED_CHROME_CODE,
                                 HarnessError, require)  # noqa: E402
from launcher_integration import check_engine_tree  # noqa: E402

REAL_POPEN = subprocess.Popen


class ConcurrentHandler(Handler):
    def do_GET(self) -> None:
        token, case, route = self._case()
        if case is None:
            self._reply(404, b"Not found")
        elif route == "/barrier":
            self.server.release.wait(25)
            self._reply(200, b"", "image/png")
        elif route == "/case":
            page = PAGE.replace("__TOKEN__", token).replace("__CONFIG__", json.dumps(case["config"]))
            self._reply(200, page.encode(), "text/html; charset=utf-8", nonce=token)
        elif route == "/nevision-qa-service-worker.js":
            self._reply(200, b"self.addEventListener('install', () => self.skipWaiting());",
                        "application/javascript; charset=utf-8")
        else:
            self._reply(404, b"Not found")


class ConcurrentServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), ConcurrentHandler)
        self.cases: dict[str, dict[str, Any]] = {}
        self.case_lock = threading.Lock()
        self.blocked_proxy_requests = 0
        self.release = threading.Event()

    def add_case(self, operation: str, value: str | None) -> tuple[str, str]:
        token = uuid.uuid4().hex
        with self.case_lock:
            self.cases[token] = {"config": {"token": token, "operation": operation, "value": value},
                                 "ready": threading.Event(), "result": None}
        return token, f"http://127.0.0.1:{self.server_port}/case?token={token}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assess(a: dict[str, Any], b: dict[str, Any], value_a: str, value_b: str) -> dict[str, bool]:
    """Pure verdicts; never store synthetic browser values in the public report."""
    fields = ("cookie", "local_storage", "indexed_db", "cache_storage")
    return {
        "a_initially_empty": a.get("before") == EMPTY,
        "b_initially_empty": b.get("before") == EMPTY,
        "a_owns_distinct_storage": all(a.get("after", {}).get(key) == value_a for key in fields),
        "b_owns_distinct_storage": all(b.get("after", {}).get(key) == value_b for key in fields),
        "a_b_not_equal": value_a != value_b and a.get("after") != b.get("after"),
        "both_service_workers": all(item.get("after", {}).get("service_worker") == "registered" for item in (a, b)),
        "both_namespaces": all(item.get("after", {}).get("indexed_db_namespace") is True and
                               item.get("after", {}).get("cache_namespace") is True for item in (a, b)),
        "no_page_errors": a.get("error") is None and b.get("error") is None,
    }


class ManagerSubprocessProxy:
    def __init__(self, callback: Any) -> None:
        self.callback = callback

    def __getattr__(self, name: str) -> Any:
        return getattr(subprocess, name)

    def Popen(self, args: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        return self.callback(args, **kwargs)


def launch(storage: Storage, launcher: BrowserLauncher, profile_id: str, url: str,
           server: ConcurrentServer, engine: Path) -> tuple[subprocess.Popen[bytes], OwnedJob]:
    job = OwnedJob()
    helper: subprocess.Popen[bytes] | None = None

    def owned(args: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        nonlocal helper
        require(helper is None, "Launcher attempted multiple process launches")
        require(Path(args[0]).resolve() == engine.resolve(), "Launcher selected a different engine")
        require(f"--user-data-dir={storage.profile_path(profile_id)}" in args,
                "Launcher used the wrong profile directory")
        # These QA-only flags route unsolicited traffic to the rejecting local
        # server. The product's no-proxy behavior is not changed or certified.
        gated_args = [*args, "--headless", "--dump-dom", "--disable-background-networking",
                      "--disable-component-update", "--disable-sync", "--disable-quic",
                      f"--proxy-server=http://127.0.0.1:{server.server_port}",
                      "--proxy-bypass-list=127.0.0.1;localhost",
                      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", url]
        helper = REAL_POPEN([sys.executable, "-I", "-S", "-c", GATED_CHROME_CODE, *gated_args],
                            cwd=kwargs.get("cwd"), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        try:
            job.assign(helper)
            require(helper.stdin is not None, "Owned helper has no release gate")
            helper.stdin.write(b"G")
            helper.stdin.close()
            helper.stdin = None
        except BaseException:
            job.close()
            with contextlib.suppress(Exception):
                helper.wait(timeout=5)
            raise
        return helper

    try:
        with patch("nevision_win.subprocess", ManagerSubprocessProxy(owned)):
            returned = launcher.launch(storage.get_profile(profile_id))
        require(returned is helper and helper is not None, "Launcher returned a different process")
        return helper, job
    except BaseException:
        job.close()
        if helper is not None:
            with contextlib.suppress(Exception):
                helper.communicate(timeout=5)
        raise


def wait_result(server: ConcurrentServer, token: str, timeout: float = 20) -> dict[str, Any]:
    case = server.cases[token]
    require(case["ready"].wait(timeout), "Browser did not finish the loopback page")
    with server.case_lock:
        result = case["result"]
    require(isinstance(result, dict) and result.get("token") == token, "Missing or mismatched page result")
    return result


def busy_profile_operations_are_rejected(storage: Storage, launcher: BrowserLauncher,
                                         profile_id: str) -> dict[str, bool]:
    """Exercise real busy-profile guards without allowing an unowned second spawn."""
    checks: dict[str, bool] = {}

    def forbidden_spawn(_args: list[str], **_kwargs: Any) -> subprocess.Popen[bytes]:
        raise HarnessError("Duplicate launch reached process creation")

    with patch("nevision_win.subprocess", ManagerSubprocessProxy(forbidden_spawn)):
        try:
            launcher.launch(storage.get_profile(profile_id))
        except NeVisionError:
            checks["duplicate_a_launch_rejected"] = True
        else:
            checks["duplicate_a_launch_rejected"] = False
    for label, operation in (("backup_a_while_busy_rejected", storage.backup_profile),
                             ("delete_a_while_busy_rejected", storage.delete_profile)):
        try:
            operation(profile_id)
        except NeVisionError:
            checks[label] = True
        else:
            checks[label] = False
    checks["busy_a_profile_preserved"] = storage.get_profile(profile_id) is not None and storage.profile_path(profile_id).is_dir()
    return checks


def run(source_root: Path, expected_hash: str, report: dict[str, Any]) -> None:
    source_engine = source_root / "Engine" / "Chromium"
    check_engine_tree(source_engine)
    require(sha256(source_engine / "chrome.exe") == expected_hash, "Packaged chrome.exe SHA-256 mismatch")
    version = json.loads((source_root / "release-version.json").read_text(encoding="utf-8"))["version"]
    require(version == APP_VERSION, "Packaged version differs from source launcher")
    report["chrome_sha256"] = expected_hash
    with tempfile.TemporaryDirectory(prefix="neantik-concurrent-profiles-") as qa_dir:
        qa_root = Path(qa_dir)
        engine = qa_root / "Engine" / "Chromium" / "chrome.exe"
        engine.parent.parent.mkdir(parents=True)
        shutil.copytree(source_engine, engine.parent)
        require(sha256(engine) == expected_hash, "Copied engine hash mismatch")
        storage = Storage(AppPaths(qa_root))
        launcher = BrowserLauncher(storage)
        require(launcher.resolve_browser() == engine, "Bundled engine was not discovered")
        ids = [storage.save_profile({"name": f"Synthetic concurrent {side}"}) for side in ("A", "B")]
        require(ids[0] != ids[1] and storage.profile_path(ids[0]) != storage.profile_path(ids[1]),
                "Profiles do not have distinct data directories")
        server = ConcurrentServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        running: list[tuple[subprocess.Popen[bytes], OwnedJob]] = []
        try:
            nonce = uuid.uuid4().hex[:12]
            values = [f"A-{nonce}", f"B-{nonce}"]
            tokens_urls = [server.add_case("write", value) for value in values]
            # The first browser is held at a load barrier while the second
            # launches. Both page reports and both Chromium locks must coexist.
            for profile_id, (_, url) in zip(ids, tokens_urls):
                running.append(launch(storage, launcher, profile_id, url, server, engine))
            results = [wait_result(server, token) for token, _ in tokens_urls]
            report["checks"]["both_running_during_overlap"] = all(process.poll() is None for process, _ in running)
            report["checks"]["both_profile_locks_active"] = all(storage._windows_chromium_lock_is_active(pid) for pid in ids)
            if report["checks"]["both_profile_locks_active"]:
                report["checks"].update(busy_profile_operations_are_rejected(storage, launcher, ids[0]))
            report["checks"].update(assess(results[0], results[1], values[0], values[1]))
            server.release.set()
            dom_results_match = []
            for (process, job), result in zip(running, results):
                stdout, _ = process.communicate(timeout=35)
                require(process.returncode == 0, "Headless browser exited abnormally")
                match = re.search(r'<pre id="nevision-result">(.*?)</pre>',
                                  stdout.decode("utf-8", errors="replace"), re.S)
                require(match is not None, "Missing dump-dom result")
                dom_results_match.append(json.loads(html.unescape(match.group(1))) == result)
                deadline = time.monotonic() + 5
                while job.active_count() and time.monotonic() < deadline:
                    time.sleep(0.1)
                require(job.active_count() == 0, "Owned browser descendants did not exit")
            report["checks"]["both_locks_released"] = all(not storage._windows_chromium_lock_is_active(pid) for pid in ids)
            report["checks"]["both_pinned_to_bundled_core"] = all(storage.get_profile(pid)["browser_family"] == "chromium" for pid in ids)
            report["checks"]["both_dom_reports_match_loopback"] = all(dom_results_match)
            require(all(report["checks"].values()), "One or more concurrent-profile assertions failed")
        finally:
            server.release.set()
            for process, job in running:
                job.close()  # Only this harness's descendants.
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.communicate(timeout=5)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable-root", required=True, type=Path)
    parser.add_argument("--expected-chrome-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This gate requires Windows")
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_chrome_sha256):
        parser.error("Expected browser SHA-256 must be a lowercase hex digest")
    source_root = args.portable_root.resolve(strict=True)
    output = args.output.resolve()
    if not output.parent.is_dir() or output.exists():
        parser.error("Output directory must exist and report must be a new file")
    report: dict[str, Any] = {"format": "neantik-concurrent-profile-integration-v1",
                              "app_version": APP_VERSION, "status": "running", "checks": {},
                              "started_utc": datetime.now(timezone.utc).isoformat(),
                              "limitations": ["One manager instance, not two-manager concurrency or GUI coverage.",
                                              "Synthetic loopback storage only; no public network, DNS/UDP, fingerprint or anonymity proof.",
                                              "QA flags restrict unsolicited traffic; they do not certify product proxy behavior."]}
    try:
        run(source_root, args.expected_chrome_sha256, report)
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
                      "failed_checks": [name for name, passed in report["checks"].items() if not passed],
                      "report": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
