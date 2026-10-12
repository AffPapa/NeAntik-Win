"""Disposable, loopback-only browser check of new-profile privacy defaults.

Usage: python tools/privacy_browser_integration.py --chrome PATH [--report PATH]
No user profile or public site is touched. A freshly created user-data-dir is
used with the gated Windows Job launcher from browser_integration.py.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
from privacy_defaults import initialize_privacy_defaults  # noqa: E402
from browser_integration import OwnedJob, spawn_owned_browser  # noqa: E402


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Privacy defaults QA</title></head>
<body><pre id="result">pending</pre><img src="/barrier?token=__TOKEN__" alt="load barrier">
<script nonce="__TOKEN__">
(async () => {
  const token = '__TOKEN__';
  const names = ['geolocation', 'notifications', 'camera', 'microphone'];
  const states = {};
  for (const name of names) {
    try { states[name] = (await navigator.permissions.query({name})).state; }
    catch (error) { states[name] = 'error:' + String(error); }
  }
  const result = {token, states, origin: location.origin};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})();
</script></body></html>"""


class PrivacyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str):
        super().__init__(("127.0.0.1", 0), PrivacyHandler)
        self.token = token
        self.result: dict | None = None
        self.ready = threading.Event()
        self.blocked_proxy_requests = 0


class PrivacyHandler(BaseHTTPRequestHandler):
    server: PrivacyServer

    def log_message(self, _format: str, *args: object) -> None:
        pass

    def reply(self, status: int, content: bytes, mime: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        if mime.startswith("text/html"):
            token = self.server.token
            self.send_header("Content-Security-Policy",
                             f"default-src 'none'; script-src 'nonce-{token}'; img-src 'self'; connect-src 'self'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def route(self) -> str | None:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            self.server.blocked_proxy_requests += 1
            return None
        if parse_qs(parsed.query).get("token") != [self.server.token]:
            return None
        return parsed.path

    def do_CONNECT(self) -> None:
        self.server.blocked_proxy_requests += 1
        self.reply(403, b"No external forwarding")

    def do_GET(self) -> None:
        route = self.route()
        if route == "/case":
            self.reply(200, PAGE.replace("__TOKEN__", self.server.token).encode("utf-8"),
                       "text/html; charset=utf-8")
        elif route == "/barrier":
            self.server.ready.wait(25)
            self.reply(200, b"", "image/png")
        else:
            self.reply(404, b"Not found")

    def do_POST(self) -> None:
        if self.route() != "/report":
            self.reply(404, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192 or self.server.result is not None:
                raise ValueError("Invalid report length or duplicate")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or body.get("token") != self.server.token:
                raise ValueError("Invalid report identity")
            self.server.result = body
            self.reply(200, b"ok")
            self.server.ready.set()
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def run(chrome: Path) -> dict:
    if os.name != "nt":
        raise RuntimeError("This gated release integration is Windows-only")
    if not chrome.is_file() or chrome.name.lower() != "chrome.exe":
        raise ValueError("--chrome must name an existing chrome.exe")
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "chrome": str(chrome.resolve()),
        "test_scope": "disposable-profile, loopback-only, headless Chromium",
        "third_party_cookie_network_behavior": "unverified; preference presence alone is not a network behavior test",
        "status": "started",
    }
    with tempfile.TemporaryDirectory(prefix="neantik-privacy-qa-") as temporary:
        root = Path(temporary)
        profile = root / "Profile"
        if not initialize_privacy_defaults(profile):
            raise RuntimeError("Fresh profile defaults were not installed")
        preference_file = profile / "Default" / "Preferences"
        initial = json.loads(preference_file.read_text("utf-8"))
        token = uuid.uuid4().hex
        server = PrivacyServer(token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        job = OwnedJob()
        process: subprocess.Popen[bytes] | None = None
        started = time.monotonic()
        try:
            url = f"http://127.0.0.1:{server.server_port}/case?token={token}"
            arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                         "--no-first-run", "--no-default-browser-check",
                         "--disable-background-networking", "--disable-component-update",
                         "--disable-sync", "--disable-quic", "--metrics-recording-only",
                         f"--proxy-server=http://127.0.0.1:{server.server_port}",
                         "--proxy-bypass-list=127.0.0.1;localhost",
                         "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", url]
            process = spawn_owned_browser(arguments, root, job)
            stdout, stderr = process.communicate(input=b"G", timeout=45)
            report["elapsed_seconds"] = round(time.monotonic() - started, 3)
            report["return_code"] = process.returncode
            report["stderr_excerpt"] = stderr.decode("utf-8", errors="replace")[-1000:]
            if process.returncode != 0:
                raise RuntimeError(f"Chromium exited {process.returncode}")
            deadline = time.monotonic() + 5
            while job.active_count() and time.monotonic() < deadline:
                time.sleep(0.1)
            if job.active_count():
                raise RuntimeError("Owned browser descendants did not exit naturally")
            result = server.result
            if not isinstance(result, dict):
                raise RuntimeError("Page did not submit a loopback result")
            match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
            if not match or json.loads(html.unescape(match.group(1))) != result:
                raise RuntimeError("Browser DOM and loopback report differ")
            if result.get("origin") != f"http://127.0.0.1:{server.server_port}":
                raise RuntimeError("Unexpected test page origin")
            report["permission_states"] = result.get("states")
            expected = {name: "denied" for name in ("geolocation", "notifications", "camera", "microphone")}
            report["permissions_denied"] = result.get("states") == expected
            after = json.loads(preference_file.read_text("utf-8"))
            profile_preferences = after.get("profile", {})
            report["cookie_controls_mode_after_startup"] = profile_preferences.get("cookie_controls_mode")
            report["content_settings_after_startup"] = profile_preferences.get("default_content_setting_values")
            report["preferences_survived_startup"] = (
                profile_preferences.get("cookie_controls_mode") == initial["profile"]["cookie_controls_mode"]
                and all(profile_preferences.get("default_content_setting_values", {}).get(key) == value
                        for key, value in initial["profile"]["default_content_setting_values"].items())
            )
            report["blocked_external_proxy_requests"] = server.blocked_proxy_requests
            report["status"] = "passed" if (report["permissions_denied"] and report["preferences_survived_startup"]) else "failed"
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
            job.close()
            if process is not None:
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.chrome)
    except Exception as error:
        report = {"status": "failed", "error": f"{type(error).__name__}: {error}",
                  "third_party_cookie_network_behavior": "unverified"}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
