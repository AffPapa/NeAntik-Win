"""Loopback-only V4 Canvas context gate; not an anonymity certificate.

One disposable saved profile is opened twice. Each session measures one scene
in a main frame, a same-site cross-origin iframe, a cross-site iframe and
dedicated/shared/service workers. Raw Canvas hashes remain in process memory;
only aggregate checks and binary hashes are written. An unmeasured worker is
NOT RUN and can never make this gate pass.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from start_page_network_audit import RejectingProxy


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "native_canvas_v4_context.html"
CONTEXTS = ("main", "sameSiteFrame", "crossSiteFrame", "dedicatedWorker",
            "sharedWorker", "serviceWorker")
TOP_LEVEL_SITE_CONTEXTS = ("sameSiteFrame", "crossSiteFrame", "dedicatedWorker",
                           "sharedWorker", "serviceWorker")
SURFACES = ("pixelHash", "pngHash")
SESSION_COUNT = 2


class Inconclusive(RuntimeError):
    """The probe did not yield complete, trustworthy observations."""


def _worker_source() -> bytes:
    text = FIXTURE.read_text(encoding="utf-8")
    match = re.search(r'<script id="canvas-worker-source" type="text/plain">(.*?)</script>',
                      text, re.S)
    if not match:
        raise Inconclusive("worker_fixture_missing")
    return match.group(1).encode("utf-8")


class ContextServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, hostname: str, token: str, role: str, config: dict):
        super().__init__(("127.0.0.1", 0), ContextHandler)
        self.hostname = hostname
        self.token = token
        self.role = role
        self.config = config
        self.result: dict | None = None
        self.ready = threading.Event()


class ContextHandler(BaseHTTPRequestHandler):
    server: ContextServer

    def log_message(self, *_args: object) -> None:
        pass

    def reply(self, status: int, content: bytes, mime: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def route(self) -> str | None:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            return None  # This server never acts as an external proxy.
        if self.headers.get("Host") != f"{self.server.hostname}:{self.server.server_port}":
            return None
        if parse_qs(parsed.query).get("token") != [self.server.token]:
            return None
        return parsed.path

    def do_CONNECT(self) -> None:
        self.reply(403, b"No forwarding")

    def do_GET(self) -> None:
        route = self.route()
        if route in ("/main", "/frame") and route == "/" + self.server.role:
            config = {**self.server.config, "role": self.server.role}
            encoded = json.dumps(config, separators=(",", ":")).replace("<", "\\u003c")
            page = FIXTURE.read_text(encoding="utf-8").replace("__CONFIG__", encoded)
            self.reply(200, page.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/canvas-worker.js" and self.server.role == "main":
            self.reply(200, _worker_source(), "application/javascript; charset=utf-8")
        else:
            self.reply(404, b"Not found")

    def do_POST(self) -> None:
        if self.server.role != "main" or self.route() != "/report" or self.server.result is not None:
            self.reply(404, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid report size")
            result = json.loads(self.rfile.read(length))
            if not isinstance(result, dict) or result.get("token") != self.server.token:
                raise ValueError("Invalid report identity")
            if not isinstance(result.get("contexts"), dict):
                raise ValueError("Invalid context map")
            self.server.result = result
            self.server.ready.set()
            self.reply(200, b"ok")
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def validate_session(value: object) -> dict[str, dict]:
    if not isinstance(value, dict) or not isinstance(value.get("contexts"), dict):
        raise Inconclusive("context_report_missing")
    contexts = value["contexts"]
    if set(contexts) != set(CONTEXTS):
        raise Inconclusive("context_matrix_incomplete")
    for name in CONTEXTS:
        entry = contexts[name]
        if not isinstance(entry, dict):
            raise Inconclusive("context_measurement_invalid")
        if entry.get("unavailable") is True:
            continue
        if entry.get("error") is True:
            category = entry.get("errorClass")
            if category not in ("TypeError", "SecurityError", "InvalidStateError",
                                "NotSupportedError", "AbortError", "Error",
                                "NoInstallingWorker", "ActivationTimeout",
                                "ServiceReplyTimeout", "WorkerReplyTimeout"):
                category = "unspecified"
            raise Inconclusive(f"context_script_error_{name}_{category}")
        if any(type(entry.get(surface)) is not int or
               not 0 <= entry[surface] <= 0xFFFFFFFF for surface in SURFACES):
            raise Inconclusive("context_surface_missing")
    return contexts


def summarize(sessions: list[dict]) -> dict:
    if len(sessions) != SESSION_COUNT:
        raise Inconclusive("saved_profile_restart_missing")
    measurements = [validate_session(value) for value in sessions]
    context_status = {name: ("NOT RUN" if any(
        result[name].get("unavailable") is True for result in measurements) else "MEASURED")
        for name in CONTEXTS}
    checks = {}
    # A third-party iframe is partitioned by its top-level site. It should
    # match the main frame here; a separate top-level site is tested by the
    # two-site V4 gate.
    for name in TOP_LEVEL_SITE_CONTEXTS:
        if context_status[name] == "MEASURED" and context_status["main"] == "MEASURED":
            checks[f"{name}_matches_main"] = all(
                result[name][surface] == result["main"][surface]
                for result in measurements for surface in SURFACES)
    for name in CONTEXTS:
        if context_status[name] == "MEASURED":
            checks[f"{name}_changes_after_restart"] = all(
                measurements[0][name][surface] != measurements[1][name][surface]
                for surface in SURFACES)
    all_measured = all(value == "MEASURED" for value in context_status.values())
    status = "FAIL" if any(value is False for value in checks.values()) else (
        "PASS" if all_measured and len(checks) == 11 else "INCONCLUSIVE")
    return {"status": status, "sessions": SESSION_COUNT,
            "context_status": context_status, "checks": checks,
            "scope": "one saved synthetic profile, two launches, loopback sites only"}


def _launch(chrome: Path, profile: Path, root: Path, job: OwnedJob,
            url: str, proxy_port: int) -> subprocess.Popen[bytes]:
    arguments = [str(chrome), "--headless=new", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync", "--disable-quic",
                 "--metrics-recording-only", f"--proxy-server=http://127.0.0.1:{proxy_port}",
                 "--proxy-bypass-list=127.0.0.1;localhost",
                 "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
                 "--neantik-fingerprint-seed=1597331", url]
    process = spawn_owned_browser(arguments, root, job)
    assert process.stdin is not None
    process.stdin.write(b"G")
    process.stdin.flush()
    process.stdin.close()
    process.stdin = None
    return process


def _one_session(chrome: Path, profile: Path, root: Path) -> dict:
    token = uuid.uuid4().hex
    config: dict = {"token": token}
    servers = [ContextServer("127.0.0.1", token, "main", config),
               ContextServer("127.0.0.1", token, "frame", config),
               ContextServer("localhost", token, "frame", config)]
    main, same, cross = servers
    origin = f"http://127.0.0.1:{main.server_port}"
    config.update({"parentOrigin": origin,
                   "sameSiteOrigin": f"http://127.0.0.1:{same.server_port}",
                   "crossSiteOrigin": f"http://localhost:{cross.server_port}",
                   "sameSiteUrl": f"http://127.0.0.1:{same.server_port}/frame?token={token}",
                   "crossSiteUrl": f"http://localhost:{cross.server_port}/frame?token={token}",
                   "workerUrl": f"/canvas-worker.js?token={token}"})
    proxy = RejectingProxy()
    listeners = [*servers, proxy]
    threads = [threading.Thread(target=listener.serve_forever, daemon=True)
               for listener in listeners]
    for thread in threads:
        thread.start()
    job: OwnedJob | None = None
    process: subprocess.Popen[bytes] | None = None
    try:
        job = OwnedJob()
        process = _launch(chrome, profile, root, job,
                          f"{origin}/main?token={token}", proxy.server_port)
        if not main.ready.wait(80):
            raise Inconclusive("loopback_context_probe_timeout")
        if process.poll() is not None:
            raise Inconclusive("browser_exited_during_context_probe")
        validate_session(main.result)
        return main.result
    finally:
        if job is not None:
            job.close()
        if process is not None:
            try:
                process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=8)
        for listener in listeners:
            listener.shutdown()
            listener.server_close()
        for thread in threads:
            thread.join(timeout=5)


def measure(chrome: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="neantik-v4-context-qa-") as temporary:
        root = Path(temporary)
        profile = root / "synthetic-saved-profile"
        sessions = []
        for _ in range(SESSION_COUNT):
            sessions.append(_one_session(chrome, profile, root))
            deadline = time.monotonic() + 8
            while (profile / "SingletonLock").exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            if (profile / "SingletonLock").exists():
                raise Inconclusive("saved_profile_still_locked")
        return summarize(sessions)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = args.chrome.with_name("chrome.dll")
    if (os.name != "nt" or args.chrome.name.lower() != "chrome.exe" or
            not args.chrome.is_file() or not core.is_file()):
        parser.error("Existing Windows chrome.exe and adjacent chrome.dll required")
    if not FIXTURE.is_file() or args.output.exists() or not args.output.parent.is_dir():
        parser.error("Fixture missing or output path invalid/already exists")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "INCONCLUSIVE", "chrome_exe_sha256": _sha256(args.chrome),
              "chrome_dll_sha256": _sha256(core)}
    try:
        report.update(measure(args.chrome))
    except Inconclusive as error:
        report["reason_code"] = str(error)
    except Exception as error:
        report["reason_code"] = f"harness_{type(error).__name__}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.output),
                      "reason_code": report.get("reason_code")}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2}.get(report["status"], 3)


if __name__ == "__main__":
    raise SystemExit(main())
