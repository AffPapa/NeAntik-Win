"""Disposable native-persona Canvas smoke test for an experimental Chromium core.

Only self-hosted loopback test content is opened. No real profile is used.
Different stable seeds are a functional test, not an anonymity guarantee.
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
from urllib.parse import parse_qs, urlsplit
import uuid

from browser_integration import OwnedJob, PIXEL, spawn_owned_browser


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "native_canvas_probe.html"
REQUIRED = ("repeatMatches", "regionMatches", "pngRepeatMatches",
            "pngDecodedMatches", "offscreenMatchesMain", "offscreenPngDecodedMatches",
            "workerMatchesMain", "exportPreservesBacking", "clearIsTransparent")


class ProbeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str):
        super().__init__(("127.0.0.1", 0), ProbeHandler)
        self.token = token
        self.ready = threading.Event()
        self.result: dict | None = None
        self.rejected_external_requests = 0


class ProbeHandler(BaseHTTPRequestHandler):
    server: ProbeServer

    def log_message(self, *_args: object) -> None:
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
            self.server.rejected_external_requests += 1
            return None
        if parse_qs(parsed.query).get("token") != [self.server.token]:
            return None
        return parsed.path

    def do_CONNECT(self) -> None:
        self.server.rejected_external_requests += 1
        self.reply(403, b"No external forwarding")

    def do_GET(self) -> None:
        route = self.route()
        if route == "/case":
            page = FIXTURE.read_text(encoding="utf-8").replace("__TOKEN__", self.server.token)
            self.reply(200, page.encode("utf-8"), "text/html; charset=utf-8")
        elif route == "/barrier":
            self.server.ready.wait(25)
            self.reply(200, PIXEL, "image/png")
        else:
            self.reply(404, b"Not found")

    def do_POST(self) -> None:
        if self.route() != "/report" or self.server.result is not None:
            self.reply(404, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid report length")
            result = json.loads(self.rfile.read(length))
            if not isinstance(result, dict):
                raise ValueError("Invalid report")
            self.server.result = result
            self.server.ready.set()
            self.reply(200, b"ok")
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def run_profile(chrome: Path, seed: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="neantik-native-canvas-qa-") as temporary:
        root = Path(temporary)
        server = ProbeServer(uuid.uuid4().hex)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        job = OwnedJob()
        process: subprocess.Popen[bytes] | None = None
        try:
            url = f"http://127.0.0.1:{server.server_port}/case?token={server.token}"
            arguments = [str(chrome), "--headless", "--dump-dom",
                         f"--user-data-dir={root / 'Profile'}", "--no-first-run",
                         "--no-default-browser-check", "--disable-background-networking",
                         "--disable-component-update", "--disable-sync", "--disable-quic",
                         f"--proxy-server=http://127.0.0.1:{server.server_port}",
                         "--proxy-bypass-list=127.0.0.1;localhost",
                         "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                         "--metrics-recording-only", f"--neantik-fingerprint-seed={seed}", url]
            process = spawn_owned_browser(arguments, root, job)
            stdout, stderr = process.communicate(input=b"G", timeout=45)
            if process.returncode != 0:
                detail = stderr.decode(errors="replace")
                raise RuntimeError(f"Browser exited {process.returncode}: {detail[:1200]} ... {detail[-300:]}")
            match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
            if not match:
                raise RuntimeError("Canvas probe did not return a result")
            result = json.loads(html.unescape(match.group(1)))
            if result != server.result:
                raise RuntimeError("Browser DOM and loopback report differ")
            if result.get("error"):
                raise RuntimeError(f"Canvas page failed: {result['error']}")
            if not isinstance(result, dict) or not all(result.get(key) is True for key in REQUIRED):
                raise RuntimeError("Canvas readback/export invariant failed")
            return result
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
    if os.name != "nt" or not args.chrome.is_file() or args.chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if not FIXTURE.is_file() or args.output.exists() or not args.output.parent.is_dir():
        parser.error("Probe fixture missing or output path invalid")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "experimental native persona, loopback only; no anonymity claim",
              "status": "started"}
    try:
        first = run_profile(args.chrome, 123456)
        same_seed = run_profile(args.chrome, 123456)
        other_seed = run_profile(args.chrome, 456789)
        report.update({"repeatable_across_profiles": first == same_seed,
                       "seed_changes_pixel_hash": first["pixelHash"] != other_seed["pixelHash"],
                       "seed_changes_png_hash": first["pngHash"] != other_seed["pngHash"],
                       "invariants": {key: first[key] and same_seed[key] and other_seed[key] for key in REQUIRED}})
        report["status"] = ("passed" if report["repeatable_across_profiles"] and
                            report["seed_changes_pixel_hash"] and report["seed_changes_png_hash"] and
                            all(report["invariants"].values()) else "failed")
    except Exception as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
