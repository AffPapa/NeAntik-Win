"""Compare Chromium's built-in Canvas readback switch with a positive control.

Disposable loopback pages and profiles only. This is a coverage and compatibility
probe, not an anonymity test; raw reports stay outside the public repository.
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
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from browser_integration import OwnedJob, spawn_owned_browser


PAGE = r'''<!doctype html><meta charset="utf-8"><pre id="result">pending</pre>
<img src="/barrier?token=__TOKEN__" alt="load barrier"><script>
(async () => {
  const token = '__TOKEN__';
  const mark = phase => fetch('/phase?token=' + token, {method: 'POST', body: phase});
  await mark('script-start');
  const outcome = (action) => { try { return action() ? 'allowed' : 'empty'; }
    catch (error) { return error.name || 'error'; } };
  const canvas = document.createElement('canvas');
  canvas.width = 16; canvas.height = 16;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'red'; ctx.fillRect(0, 0, 16, 16);
  const canvas2dPixels = outcome(() => ctx.getImageData(0, 0, 1, 1).data.length);
  const canvas2dDataUrl = outcome(() => canvas.toDataURL().startsWith('data:image/png'));
  await mark('canvas2d:' + canvas2dPixels + ':' + canvas2dDataUrl);
  const workerCanvas2dPixels = await new Promise((resolve, reject) => {
    const worker = new Worker('/worker.js?token=' + token);
    const timeout = setTimeout(() => { worker.terminate(); reject(new Error('worker timeout')); }, 5000);
    worker.onmessage = event => { clearTimeout(timeout); worker.terminate(); resolve(event.data); };
    worker.onerror = error => { clearTimeout(timeout); worker.terminate(); reject(error); };
  });
  await mark('worker:' + workerCanvas2dPixels);
  await mark('webgl-start');
  const gl = document.createElement('canvas').getContext('webgl');
  await mark('webgl-created');
  const webglReadPixels = gl ? outcome(() => {
    const pixels = new Uint8Array(4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    return gl.getError() === gl.NO_ERROR;
  }) : 'unavailable';
  const result = {token, canvas2dPixels, canvas2dDataUrl, workerCanvas2dPixels, webglReadPixels};
  await mark('webgl');
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})().catch(async error => {
  const result = {token: '__TOKEN__', error: String(error)};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=__TOKEN__', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
});
</script>'''

WORKER = r'''const canvas = new OffscreenCanvas(16, 16);
const ctx = canvas.getContext('2d');
ctx.fillStyle = 'red'; ctx.fillRect(0, 0, 16, 16);
try { postMessage(ctx.getImageData(0, 0, 1, 1).data.length ? 'allowed' : 'empty'); }
catch (error) { postMessage(error.name || 'error'); }'''


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str):
        super().__init__(("127.0.0.1", 0), Handler)
        self.token = token
        self.result: dict | None = None
        self.ready = threading.Event()
        self.rejected_external_requests = 0
        self.phases: list[str] = []


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *_args: object) -> None:
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
            self.reply(200, PAGE.replace("__TOKEN__", self.server.token).encode(),
                       "text/html; charset=utf-8")
        elif route == "/worker.js":
            self.reply(200, WORKER.encode(), "application/javascript; charset=utf-8")
        elif route == "/barrier":
            self.server.ready.wait(20)
            self.reply(200, b"", "image/png")
        else:
            self.reply(404, b"Not found")

    def do_POST(self) -> None:
        if self.route() == "/phase":
            size = int(self.headers.get("Content-Length", "0"))
            if 0 < size <= 64:
                self.server.phases.append(self.rfile.read(size).decode("ascii", errors="replace"))
                self.reply(200, b"ok")
            else:
                self.reply(400, b"Invalid phase")
            return
        if self.route() != "/report" or self.server.result is not None:
            self.reply(404, b"Not found")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("Invalid report size")
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict) or value.get("token") != self.server.token:
                raise ValueError("Invalid report identity")
            self.server.result = value
            self.server.ready.set()
            self.reply(200, b"ok")
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def run_case(chrome: Path, blocked: bool) -> dict:
    root = Path(tempfile.mkdtemp(prefix="neantik-canvas-policy-qa-"))
    try:
        token = uuid.uuid4().hex
        server = Server(token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        job = OwnedJob()
        process: subprocess.Popen[bytes] | None = None
        try:
            url = f"http://127.0.0.1:{server.server_port}/case?token={token}"
            args = [str(chrome), "--headless", "--dump-dom",
                    f"--user-data-dir={root / 'Profile'}", "--no-first-run",
                    "--no-default-browser-check", "--disable-background-networking",
                    "--disable-component-update", "--disable-sync", "--disable-quic",
                    f"--proxy-server=http://127.0.0.1:{server.server_port}",
                    "--proxy-bypass-list=127.0.0.1;localhost",
                    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                    "--metrics-recording-only"]
            if blocked:
                args.append("--disable-reading-from-canvas")
            args.append(url)
            process = spawn_owned_browser(args, root, job)
            try:
                stdout, stderr = process.communicate(input=b"G", timeout=25)
            except subprocess.TimeoutExpired as error:
                return {"blocked_switch": blocked, "timed_out": True,
                        "phases": list(server.phases), "outcomes": {},
                        "rejected_external_requests": server.rejected_external_requests}
            if process.returncode != 0:
                raise RuntimeError(f"Chromium exit {process.returncode}: {stderr.decode(errors='replace')[-400:]}")
            result = server.result
            if not isinstance(result, dict):
                raise RuntimeError("Local Canvas page did not report")
            match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
            if not match or json.loads(html.unescape(match.group(1))) != result:
                raise RuntimeError("Browser DOM and loopback report differ")
            return {"blocked_switch": blocked, "outcomes": {key: value for key, value in result.items() if key != "token"},
                    "rejected_external_requests": server.rejected_external_requests}
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
            job.close()
            if process is not None:
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            server.shutdown(); server.server_close(); thread.join(timeout=5)
    finally:
        temp_parent = Path(tempfile.gettempdir()).resolve()
        if root.resolve().parent != temp_parent or not root.name.startswith("neantik-canvas-policy-qa-") or root.is_symlink():
            raise RuntimeError("Unsafe Canvas QA cleanup target")
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
            raise RuntimeError(f"Canvas QA files remain locked: {cleanup_error}")


def evaluate(control: dict, blocked: dict) -> dict[str, bool]:
    control_outcomes = control.get("outcomes", {})
    blocked_outcomes = blocked.get("outcomes", {})
    blocked_phases = blocked.get("phases", [])
    return {
        "control_canvas2d_readable": control_outcomes.get("canvas2dPixels") == "allowed"
        and control_outcomes.get("canvas2dDataUrl") == "allowed"
        and control_outcomes.get("workerCanvas2dPixels") == "allowed",
        "switch_blocks_canvas2d": (
            blocked_outcomes.get("canvas2dPixels") == "SecurityError"
            and blocked_outcomes.get("canvas2dDataUrl") == "SecurityError"
            and blocked_outcomes.get("workerCanvas2dPixels") == "SecurityError"
        ) or (
            "canvas2d:SecurityError:SecurityError" in blocked_phases
            and "worker:SecurityError" in blocked_phases
        ),
        "control_webgl_readable": control_outcomes.get("webglReadPixels") == "allowed",
        "switch_blocks_webgl_without_hang": not blocked.get("timed_out", False)
        and blocked_outcomes.get("webglReadPixels") != "allowed",
    }


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
              "scope": "one bundled Chromium core, disposable loopback pages and profiles; no anonymity claim"}
    try:
        control = run_case(args.chrome, False)
        report["cases"] = [control]
        blocked = run_case(args.chrome, True)
        report["cases"] = [control, blocked]
        report["checks"] = evaluate(control, blocked)
        report["status"] = "passed" if all(report["checks"].values()) else "partial"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks"),
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
