"""Audit unpacked extension storage in disposable bundled-Chromium profiles.

The synthetic extension is loaded only by owned headless test processes. Its
source and markers are created in a temporary directory; no extension is
installed into a user's browser. Background requests hit a rejecting loopback
proxy. This tests one extension API on one machine, not general extension
safety or cross-machine portability.
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
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit
import uuid

from browser_integration import OwnedJob, configuration_clone, spawn_owned_browser
from nevision_win import AppPaths, Storage
from privacy_defaults import initialize_privacy_defaults


CONTENT_SCRIPT = r'''(async () => {
  const params = new URLSearchParams(location.search);
  const token = params.get('token');
  const write = params.get('write');
  try {
    const before = (await chrome.storage.local.get('marker')).marker ?? null;
    if (write !== null) await chrome.storage.local.set({marker: write});
    const after = (await chrome.storage.local.get('marker')).marker ?? null;
    const result = {token, before, after, extensionId: chrome.runtime.id, error: null};
    document.getElementById('result').textContent = JSON.stringify(result);
    await fetch(location.origin + '/report?token=' + encodeURIComponent(token), {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)
    });
  } catch (error) {
    document.getElementById('result').textContent = 'error:' + String(error);
  }
})();'''


class AuditServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), AuditHandler)
        self.cases: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.blocked_external = 0

    def add_case(self, marker: str | None) -> tuple[str, str]:
        token = uuid.uuid4().hex
        with self.lock:
            self.cases[token] = {"ready": threading.Event(), "result": None}
        query = f"token={token}" + (f"&write={marker}" if marker is not None else "")
        return token, f"http://127.0.0.1:{self.server_port}/case?{query}"


class AuditHandler(BaseHTTPRequestHandler):
    server: AuditServer

    def log_message(self, _format: str, *_args: object) -> None:
        pass

    def reply(self, status: int, body: bytes, mime: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def case(self) -> tuple[str, dict | None, str]:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            with self.server.lock:
                self.server.blocked_external += 1
            return "", None, ""
        token = parse_qs(parsed.query).get("token", [""])[0]
        with self.server.lock:
            return token, self.server.cases.get(token), parsed.path

    def do_CONNECT(self) -> None:
        with self.server.lock:
            self.server.blocked_external += 1
        self.reply(403, b"No forwarding")

    def do_GET(self) -> None:
        token, case, route = self.case()
        if case is None:
            self.reply(404, b"Not found")
        elif route == "/case":
            body = (f'<!doctype html><html><body><pre id="result">pending</pre>'
                    f'<img src="/barrier?token={token}" alt="barrier"></body></html>').encode()
            self.reply(200, body, "text/html; charset=utf-8")
        elif route == "/barrier":
            case["ready"].wait(20)
            self.reply(200, b"", "image/png")
        else:
            self.reply(404, b"Not found")

    def do_POST(self) -> None:
        token, case, route = self.case()
        if case is None or route != "/report":
            self.reply(404, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError("Invalid report length")
            result = json.loads(self.rfile.read(length))
            if not isinstance(result, dict) or result.get("token") != token:
                raise ValueError("Invalid token")
            with self.server.lock:
                if case["result"] is not None:
                    raise ValueError("Duplicate result")
                case["result"] = result
            self.reply(200, b"ok")
            case["ready"].set()
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def make_extension(folder: Path) -> None:
    folder.mkdir()
    manifest = {
        "manifest_version": 3,
        "name": "NeAntik disposable storage test",
        "version": "1.0",
        "permissions": ["storage"],
        "host_permissions": ["http://127.0.0.1/*"],
        "content_scripts": [{"matches": ["http://127.0.0.1/*"],
                             "js": ["content.js"], "run_at": "document_end"}],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "content.js").write_text(CONTENT_SCRIPT, encoding="utf-8")


def visit(chrome: Path, profile: Path, extension: Path, server: AuditServer,
          marker: str | None) -> dict:
    initialize_privacy_defaults(profile)
    if not (profile / "Default" / "Preferences").is_file():
        raise RuntimeError("Disposable Chromium Preferences are missing")
    token, url = server.add_case(marker)
    arguments = [str(chrome), "--headless", "--dump-dom", "--virtual-time-budget=5000",
                 f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                 "--disable-background-networking", "--disable-component-update", "--disable-sync",
                 f"--disable-extensions-except={extension}", f"--load-extension={extension}",
                 f"--proxy-server=http://127.0.0.1:{server.server_port}",
                 "--proxy-bypass-list=127.0.0.1;localhost",
                 "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", url]
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = spawn_owned_browser(arguments, profile.parent, job)
        stdout, stderr = process.communicate(input=b"G", timeout=45)
        if process.returncode != 0:
            raise RuntimeError(f"Chromium exit {process.returncode}: {stderr.decode(errors='replace')[-300:]}")
        with server.lock:
            result = server.cases[token]["result"]
        if not isinstance(result, dict) or result.get("error") is not None:
            raise RuntimeError("The test extension did not report a result")
        match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
        if not match or json.loads(html.unescape(match.group(1))) != result:
            raise RuntimeError("Browser DOM and extension report differ")
        return result
    finally:
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def evaluate(results: dict[str, dict], marker_a: str, marker_b: str) -> dict[str, bool]:
    extension_ids = {item.get("extensionId") for item in results.values()}
    return {
        "same_synthetic_extension_loaded": len(extension_ids) == 1
        and all(isinstance(value, str) and len(value) == 32 for value in extension_ids),
        "a_starts_clean_and_writes": results["a_write"].get("before") is None
        and results["a_write"].get("after") == marker_a,
        "b_cannot_read_a": results["b_read"].get("before") is None
        and results["b_read"].get("after") is None,
        "b_writes_distinct_value": results["b_write"].get("before") is None
        and results["b_write"].get("after") == marker_b,
        "b_restart_retains_own_value": results["b_again"].get("before") == marker_b
        and results["b_again"].get("after") == marker_b,
        "a_restart_retains_own_value": results["a_again"].get("before") == marker_a
        and results["a_again"].get("after") == marker_a,
        "restored_a_retains_extension_value": results["restored"].get("before") == marker_a
        and results["restored"].get("after") == marker_a,
        "clean_clone_has_no_extension_value": results["clean_clone"].get("before") is None
        and results["clean_clone"].get("after") is None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chrome = args.chrome.resolve()
    if os.name != "nt" or not chrome.is_file() or chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be new and its parent must exist")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "synthetic unpacked extension, disposable profiles, one Windows host",
              "status": "started"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-extension-isolation-") as temporary:
            root = Path(temporary)
            extension = root / "extension"
            make_extension(extension)
            storage = Storage(AppPaths(root / "portable"))
            a = storage.save_profile({"name": "Extension A"})
            b = storage.save_profile({"name": "Extension B"})
            server = AuditServer()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                marker_a, marker_b = "A-" + uuid.uuid4().hex[:12], "B-" + uuid.uuid4().hex[:12]
                results = {
                    "a_write": visit(chrome, storage.profile_path(a), extension, server, marker_a),
                    "b_read": visit(chrome, storage.profile_path(b), extension, server, None),
                    "b_write": visit(chrome, storage.profile_path(b), extension, server, marker_b),
                    "b_again": visit(chrome, storage.profile_path(b), extension, server, None),
                    "a_again": visit(chrome, storage.profile_path(a), extension, server, None),
                }
                backup = storage.backup_profile(a)
                restored = storage.restore_profile(backup, "Restored extension A")
                clean, _clone_status = configuration_clone(storage, a)
                results["restored"] = visit(chrome, storage.profile_path(restored), extension, server, None)
                results["clean_clone"] = visit(chrome, storage.profile_path(clean), extension, server, None)
                report["checks"] = evaluate(results, marker_a, marker_b)
                report["blocked_background_requests"] = server.blocked_external
                report["status"] = "passed" if all(report["checks"].values()) else "failed"
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
    except Exception as error:
        report["status"] = "inconclusive"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks"),
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
