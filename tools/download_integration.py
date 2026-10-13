"""Disposable real-Chromium download routing and portable-move check.

Only a loopback page and synthetic 4 KiB file are served. Browser processes
are owned by Windows Jobs; no existing profile or system Downloads directory
is touched. This checks new managed profiles, not legacy/custom paths or GUI.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from privacy_defaults import ensure_managed_download_directory, initialize_privacy_defaults


class DownloadServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), DownloadHandler)
        self.cases: dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.rejected = 0

    def add_case(self) -> tuple[str, str]:
        token = uuid.uuid4().hex
        with self.lock:
            self.cases[token] = threading.Event()
        return token, f"http://127.0.0.1:{self.server_port}/case?token={token}"


class DownloadHandler(BaseHTTPRequestHandler):
    server: DownloadServer

    def log_message(self, *_args: object) -> None:
        pass

    def do_CONNECT(self) -> None:
        with self.server.lock:
            self.server.rejected += 1
        self.send_error(403)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            with self.server.lock:
                self.server.rejected += 1
            self.send_error(403)
            return
        token = parse_qs(parsed.query).get("token", [""])[0]
        with self.server.lock:
            ready = self.server.cases.get(token)
        if ready is None:
            self.send_error(404)
            return
        filename = f"neantik-qa-{token[:12]}.bin"
        if parsed.path == "/case":
            page = ("<!doctype html><meta charset=utf-8><title>Disposable download QA</title>"
                    f"<img src='/barrier?token={token}' alt='barrier'>"
                    f"<a id='download' href='/file?token={token}' download='{filename}'>Synthetic file</a>"
                    "<script>document.getElementById('download').click();</script>")
            body = page.encode("utf-8")
            mime = "text/html; charset=utf-8"
        elif parsed.path == "/file":
            body = ("NeAntik disposable download " + token + "\n").encode("ascii") * 80
            mime = "application/octet-stream"
            ready.set()
        elif parsed.path == "/barrier":
            ready.wait(12)
            time.sleep(1)
            body = b""
            mime = "image/png"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if parsed.path == "/file":
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def run_browser(chrome: Path, root: Path, profile: Path,
                server: DownloadServer, report: dict) -> tuple[str, bytes]:
    if not profile.is_dir():
        if not initialize_privacy_defaults(profile):
            raise RuntimeError("Could not initialize disposable profile")
    if not ensure_managed_download_directory(profile):
        raise RuntimeError("Managed Downloads binding absent or overridden")
    token, url = server.add_case()
    expected = ("NeAntik disposable download " + token + "\n").encode("ascii") * 80
    arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync", "--disable-quic",
                 "--metrics-recording-only", f"--proxy-server=http://127.0.0.1:{server.server_port}",
                 "--proxy-bypass-list=127.0.0.1;localhost",
                 "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", url]
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    path = profile / "Downloads" / f"neantik-qa-{token[:12]}.bin"
    matched = False
    try:
        process = spawn_owned_browser(arguments, root, job)
        process.stdin.write(b"G")
        process.stdin.flush()
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                matched = server.cases[token].is_set() and path.is_file() and path.read_bytes() == expected
            except (OSError, PermissionError):
                matched = False
            if matched:
                break
            if process.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
    if not matched:
        raise RuntimeError("Synthetic download did not appear with expected bytes in the managed profile folder")
    report["cases"].append({"profile": profile.name, "bytes": len(expected),
                            "download_in_managed_folder": True})
    return path.name, expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or not args.chrome.is_file() or args.chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be a new file in an existing directory")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "new managed portable profiles; synthetic loopback downloads; one Windows host",
              "cases": [], "status": "started"}
    root = Path(tempfile.mkdtemp(prefix="neantik-download-qa-"))
    try:
        try:
            server = DownloadServer()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                a, b = root / "A", root / "B"
                a_name, _ = run_browser(args.chrome, root, a, server, report)
                b_name, _ = run_browser(args.chrome, root, b, server, report)
                if (b / "Downloads" / a_name).exists() or (a / "Downloads" / b_name).exists():
                    raise RuntimeError("Synthetic download crossed profiles")
                moved = root / "A-moved"
                if a.resolve().parent != root.resolve() or moved.resolve().parent != root.resolve() or a.is_symlink():
                    raise RuntimeError("Unsafe disposable profile move")
                shutil.move(a, moved)
                if not ensure_managed_download_directory(moved):
                    raise RuntimeError("Managed download path did not rebase after portable move")
                moved_name, _ = run_browser(args.chrome, root, moved, server, report)
                if not (moved / "Downloads" / a_name).is_file() or not (moved / "Downloads" / moved_name).is_file():
                    raise RuntimeError("Portable move lost or misplaced a download")
                report["profile_isolation"] = True
                report["portable_rebase"] = True
                report["rejected_background_proxy_requests"] = server.rejected
                report["status"] = "passed"
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
        finally:
            # Chromium may release its Session files just after the owned job closes.
            # Delete only this harness-created temp root, after validating its boundary.
            temp_parent = Path(tempfile.gettempdir()).resolve()
            if root.resolve().parent != temp_parent or not root.name.startswith("neantik-download-qa-") or root.is_symlink():
                raise RuntimeError("Unsafe download QA cleanup target")
            cleanup_error = None
            for _ in range(20):
                try:
                    shutil.rmtree(root)
                    cleanup_error = None
                    break
                except PermissionError as error:
                    cleanup_error = error
                    time.sleep(0.25)
            if cleanup_error is not None:
                raise RuntimeError(f"Temporary download QA files remain locked: {cleanup_error}")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
