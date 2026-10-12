"""Loopback-only audit of fingerprint consistency across browser contexts.

This is an observation tool, not fingerprint spoofing or an anonymity test.
It launches two fresh Chromium profiles in owned Windows Jobs, never touches
user data, and rejects any attempted proxy request to an external origin.
The JSON report may reveal local device traits; keep it private.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
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
from privacy_defaults import initialize_privacy_defaults


PAGE = r'''<!doctype html><html><head><meta charset="utf-8"></head>
<body><pre id="result">pending</pre><img src="/barrier?token=__TOKEN__" alt="load barrier">
<script>
(async () => {
  const token = '__TOKEN__';
  const surface = (view) => ({
    userAgent: view.navigator.userAgent,
    platform: view.navigator.platform,
    language: view.navigator.language,
    languages: Array.from(view.navigator.languages || []),
    hardwareConcurrency: view.navigator.hardwareConcurrency,
    deviceMemory: view.navigator.deviceMemory ?? null,
    timezone: new view.Intl.DateTimeFormat().resolvedOptions().timeZone,
    screen: [view.screen.width, view.screen.height, view.screen.colorDepth],
    devicePixelRatio: view.devicePixelRatio,
  });
  const main = surface(window);
  const frame = document.createElement('iframe');
  frame.src = '/frame?token=' + token;
  const frameReady = new Promise((resolve, reject) => {
    frame.onload = resolve;
    frame.onerror = reject;
  });
  document.body.append(frame);
  await frameReady;
  const iframe = surface(frame.contentWindow);
  const worker = await new Promise((resolve, reject) => {
    const target = new Worker('/worker.js?token=' + token);
    const timeout = setTimeout(() => { target.terminate(); reject(new Error('worker timeout')); }, 5000);
    target.onmessage = (event) => { clearTimeout(timeout); target.terminate(); resolve(event.data); };
    target.onerror = (error) => { clearTimeout(timeout); target.terminate(); reject(error); };
  });
  const result = {token, main, iframe, worker};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})().catch(error => { document.getElementById('result').textContent = 'error:' + String(error); });
</script></body></html>'''

WORKER = r'''postMessage({
  userAgent: navigator.userAgent,
  platform: navigator.platform,
  language: navigator.language,
  languages: Array.from(navigator.languages || []),
  hardwareConcurrency: navigator.hardwareConcurrency,
  deviceMemory: navigator.deviceMemory ?? null,
  timezone: new Intl.DateTimeFormat().resolvedOptions().timeZone,
});'''


class AuditServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str):
        super().__init__(("127.0.0.1", 0), AuditHandler)
        self.token = token
        self.result: dict | None = None
        self.ready = threading.Event()
        self.external_attempts = 0
        self.headers_seen: dict[str, str | None] = {}


class AuditHandler(BaseHTTPRequestHandler):
    server: AuditServer

    def log_message(self, _format: str, *args: object) -> None:
        pass

    def reply(self, status: int, content: bytes, mime: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def route(self) -> str | None:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            self.server.external_attempts += 1
            return None
        if parse_qs(parsed.query).get("token") != [self.server.token]:
            return None
        return parsed.path

    def do_CONNECT(self) -> None:
        self.server.external_attempts += 1
        self.reply(403, b"No external forwarding")

    def do_GET(self) -> None:
        route = self.route()
        if route == "/case":
            self.server.headers_seen = {
                "userAgent": self.headers.get("User-Agent"),
                "acceptLanguage": self.headers.get("Accept-Language"),
                "secChUa": self.headers.get("Sec-CH-UA"),
            }
            self.reply(200, PAGE.replace("__TOKEN__", self.server.token).encode(), "text/html; charset=utf-8")
        elif route == "/frame":
            self.reply(200, b"<!doctype html><html><body>frame</body></html>", "text/html; charset=utf-8")
        elif route == "/worker.js":
            self.reply(200, WORKER.encode(), "application/javascript; charset=utf-8")
        elif route == "/barrier":
            self.server.ready.wait(20)
            self.reply(200, b"", "image/png")
        else:
            self.reply(404, b"Not found")

    def do_POST(self) -> None:
        if self.route() != "/report" or self.server.result is not None:
            self.reply(404, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Invalid report length")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict) or value.get("token") != self.server.token:
                raise ValueError("Invalid report identity")
            self.server.result = value
            self.reply(200, b"ok")
            self.server.ready.set()
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def audit_profile(chrome: Path, root: Path) -> dict:
    profile = root / "Profile"
    if not initialize_privacy_defaults(profile):
        raise RuntimeError("Could not initialize a fresh profile")
    token = uuid.uuid4().hex
    server = AuditServer(token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        url = f"http://127.0.0.1:{server.server_port}/case?token={token}"
        arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                     "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                     "--disable-component-update", "--disable-sync", "--disable-quic",
                     "--metrics-recording-only", f"--proxy-server=http://127.0.0.1:{server.server_port}",
                     "--proxy-bypass-list=127.0.0.1;localhost",
                     "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", url]
        process = spawn_owned_browser(arguments, root, job)
        stdout, stderr = process.communicate(input=b"G", timeout=45)
        if process.returncode != 0:
            raise RuntimeError(f"Chromium exit {process.returncode}: {stderr.decode(errors='replace')[-500:]}")
        result = server.result
        if not isinstance(result, dict):
            raise RuntimeError("The local audit page did not report results")
        match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
        if not match or json.loads(html.unescape(match.group(1))) != result:
            raise RuntimeError("Browser DOM and local report differ")
        if result.get("token") != token:
            raise RuntimeError("Report token mismatch")
        result.pop("token")
        return {"surfaces": result, "http": server.headers_seen,
                "blocked_external_requests": server.external_attempts}
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chrome = args.chrome.resolve()
    if os.name != "nt" or not chrome.is_file() or chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if args.output.exists():
        parser.error("Refusing to overwrite an existing audit report")
    reports = []
    for _ in range(2):
        with tempfile.TemporaryDirectory(prefix="neantik-fingerprint-audit-") as temporary:
            reports.append(audit_profile(chrome, Path(temporary)))
    keys = ("userAgent", "platform", "language", "languages", "hardwareConcurrency",
            "deviceMemory", "timezone")
    consistency = []
    for report in reports:
        surfaces = report["surfaces"]
        consistency.append({
            "main_iframe": surfaces["main"] == surfaces["iframe"],
            "main_worker_common": all(surfaces["main"].get(key) == surfaces["worker"].get(key) for key in keys),
            "js_http_user_agent": surfaces["main"]["userAgent"] == report["http"]["userAgent"],
        })
    output = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "two disposable profiles; loopback only; no public leak or anonymity conclusion",
              "profile_surfaces_equal": reports[0]["surfaces"] == reports[1]["surfaces"],
              "context_consistency": consistency, "profiles": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "profile_surfaces_equal": output["profile_surfaces_equal"],
                      "context_consistency": consistency}, ensure_ascii=False))
    return 0 if all(all(item.values()) for item in consistency) else 1


if __name__ == "__main__":
    raise SystemExit(main())
