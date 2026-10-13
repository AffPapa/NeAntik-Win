"""Bounded stock/public WebGL consistency gate on disposable loopback profiles.

Reports contain verdicts and binary hashes, not raw graphics traits. This
checks accidental divergence, not anonymity, anti-linkability or spoofing.
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

from browser_integration import OwnedJob, spawn_owned_browser
from native_persona_context_audit import prepare_disposable_engine
from profile_identity import identity_arguments, native_preview_identity
from v5_optin_cross_surface_gate import PATCH, _read_receipt, receipt_checks, sha256


SOURCE_ROOT = Path(__file__).resolve().parents[1]
MODES = ("stock", "ordinary", "optin")
CONTEXTS = ("webgl", "webgl2")
RUNS_PER_MODE = 2
MAX_RUN_SECONDS = 40

PAGE = r'''<!doctype html><html><meta charset="utf-8"><pre id="result">pending</pre>
<img src="/barrier?token=__TOKEN__" alt="load barrier"><script>
(async () => {
  const token = '__TOKEN__';
  const digest = async value => {
    const bytes = new TextEncoder().encode(JSON.stringify(value));
    const hash = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(hash), x => x.toString(16).padStart(2, '0')).join('');
  };
  const probe = async kind => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 8;
    const gl = canvas.getContext(kind, {preserveDrawingBuffer: true});
    if (!gl || gl.isContextLost()) return {status: 'unsupported'};
    try {
      const debug = gl.getExtension('WEBGL_debug_renderer_info');
      const parameters = [gl.VENDOR, gl.RENDERER, gl.VERSION, gl.SHADING_LANGUAGE_VERSION,
        gl.MAX_TEXTURE_SIZE, gl.MAX_RENDERBUFFER_SIZE, gl.MAX_VERTEX_ATTRIBS,
        gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS, gl.MAX_VIEWPORT_DIMS];
      // Scalars are not iterable. Normalize them without leaking values to stdout.
      const normalized = parameters.map(id => {
        const value = gl.getParameter(id);
        return ArrayBuffer.isView(value) ? Array.from(value) : value;
      });
      const precision = [];
      for (const shader of [gl.VERTEX_SHADER, gl.FRAGMENT_SHADER]) {
        for (const level of [gl.LOW_FLOAT, gl.MEDIUM_FLOAT, gl.HIGH_FLOAT,
                              gl.LOW_INT, gl.MEDIUM_INT, gl.HIGH_INT]) {
          const item = gl.getShaderPrecisionFormat(shader, level);
          if (!item) throw Error('precision_unavailable');
          precision.push([item.rangeMin, item.rangeMax, item.precision]);
        }
      }
      gl.viewport(0, 0, 8, 8);
      gl.clearColor(0.25, 0.5, 0.75, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      const pixels = new Uint8Array(8 * 8 * 4);
      gl.readPixels(0, 0, 8, 8, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      if (gl.getError() !== gl.NO_ERROR || pixels.every(x => x === 0)) throw Error('readback_failed');
      const signature = [normalized, debug ? [gl.getParameter(debug.UNMASKED_VENDOR_WEBGL),
        gl.getParameter(debug.UNMASKED_RENDERER_WEBGL)] : null,
        (gl.getSupportedExtensions() || []).slice().sort(), precision, Array.from(pixels)];
      return {status: 'ok', sha256: await digest(signature),
              extensionCount: (gl.getSupportedExtensions() || []).length};
    } catch (_) { return {status: 'error'}; }
  };
  const result = {token, webgl: await probe('webgl'), webgl2: await probe('webgl2')};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})().catch(async () => {
  const result = {token: '__TOKEN__', error: 'probe_failed'};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=__TOKEN__', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
});
</script>'''


class ObservationUnavailable(ValueError):
    """Required observations were absent; this is not a product PASS/FAIL."""


def validate_observation(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"token", *CONTEXTS}:
        raise ObservationUnavailable("incomplete_report")
    if not isinstance(value["token"], str) or len(value["token"]) != 32:
        raise ObservationUnavailable("invalid_token")
    for context in CONTEXTS:
        item = value[context]
        if not isinstance(item, dict) or set(item) != {"status", "sha256", "extensionCount"}:
            raise ObservationUnavailable("incomplete_webgl_context")
        if item["status"] != "ok" or not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ObservationUnavailable("webgl_context_unavailable")
        if type(item["extensionCount"]) is not int or not 0 < item["extensionCount"] < 1000:
            raise ObservationUnavailable("invalid_extension_count")
    return value


def assess_observations(observations: dict[str, list[dict]]) -> dict:
    if set(observations) != set(MODES) or any(len(observations[mode]) != RUNS_PER_MODE for mode in MODES):
        raise ObservationUnavailable("six_runs_required")
    validated = {mode: [validate_observation(item) for item in observations[mode]] for mode in MODES}
    checks: dict[str, bool] = {}
    for context in CONTEXTS:
        for mode in MODES:
            checks[f"{mode}_{context}_repeat"] = (
                validated[mode][0][context]["sha256"] == validated[mode][1][context]["sha256"]
                and validated[mode][0][context]["extensionCount"] == validated[mode][1][context]["extensionCount"]
            )
        for mode in ("ordinary", "optin"):
            checks[f"{mode}_{context}_stock_parity"] = (
                validated[mode][0][context]["sha256"] == validated["stock"][0][context]["sha256"]
                and validated[mode][0][context]["extensionCount"] == validated["stock"][0][context]["extensionCount"]
            )
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str):
        super().__init__(("127.0.0.1", 0), Handler)
        self.token = token
        self.result: dict | None = None
        self.ready = threading.Event()
        self.rejected_external = 0


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *_args: object) -> None:
        pass

    def reply(self, code: int, body: bytes, mime: str = "text/plain") -> None:
        self.send_response(code)
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
            self.server.rejected_external += 1
            return None
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            return None
        if parse_qs(parsed.query).get("token") != [self.server.token]:
            return None
        return parsed.path

    def do_CONNECT(self) -> None:
        self.server.rejected_external += 1
        self.reply(403, b"No forwarding")

    def do_GET(self) -> None:
        route = self.route()
        if route == "/case":
            self.reply(200, PAGE.replace("__TOKEN__", self.server.token).encode(), "text/html; charset=utf-8")
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
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("report_size")
            result = json.loads(self.rfile.read(size))
            if not isinstance(result, dict) or result.get("token") != self.server.token:
                raise ValueError("report_token")
            self.server.result = result
            self.server.ready.set()
            self.reply(200, b"ok")
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def run_case(chrome: Path, mode: str, flags: tuple[str, ...]) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"neantik-webgl-{mode}-") as temporary:
        root = Path(temporary)
        token = uuid.uuid4().hex
        server = Server(token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        job = OwnedJob()
        process: subprocess.Popen[bytes] | None = None
        try:
            url = f"http://127.0.0.1:{server.server_port}/case?token={token}"
            args = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={root / 'Profile'}",
                    "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                    "--disable-component-update", "--disable-sync", "--disable-quic",
                    f"--proxy-server=http://127.0.0.1:{server.server_port}",
                    "--proxy-bypass-list=127.0.0.1;localhost",
                    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                    "--metrics-recording-only", *flags, url]
            process = spawn_owned_browser(args, root, job)
            try:
                stdout, _stderr = process.communicate(input=b"G", timeout=MAX_RUN_SECONDS)
            except subprocess.TimeoutExpired as error:
                raise ObservationUnavailable("browser_timeout") from error
            if process.returncode != 0 or not isinstance(server.result, dict):
                raise ObservationUnavailable("browser_or_probe_failed")
            match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
            if not match or json.loads(html.unescape(match.group(1))) != server.result:
                raise ObservationUnavailable("report_dom_mismatch")
            result = validate_observation(server.result)
            # Chrome may attempt background proxy traffic. The local fixture
            # rejects it; this graphics gate makes no network-silence claim.
            if result["token"] != token:
                raise ObservationUnavailable("token_mismatch")
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
            server.shutdown(); server.server_close(); thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-chrome", required=True, type=Path)
    parser.add_argument("--candidate-chrome", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Windows required")
    stock, candidate, output = args.stock_chrome.resolve(), args.candidate_chrome.resolve(), args.output.resolve()
    if output.is_relative_to(SOURCE_ROOT) or output.exists() or not output.parent.is_dir():
        parser.error("Output must be a new private file outside the repository")
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "six disposable loopback-only WebGL1/2 launches on one Windows host; no anonymity claim",
              "status": "INCONCLUSIVE", "checks": {}}
    try:
        result["binary_sha256"] = {label: {"chrome_exe": sha256(chrome),
                                           "chrome_dll": sha256(chrome.with_name("chrome.dll"))}
                                   for label, chrome in (("stock", stock), ("candidate", candidate))}
        receipt = receipt_checks(_read_receipt(stock), _read_receipt(candidate), sha256(PATCH))
        result["checks"].update(receipt)
        if not all(receipt.values()):
            result["status"] = "FAIL"
        else:
            with tempfile.TemporaryDirectory(prefix="neantik-webgl-core-") as temporary:
                root = Path(temporary)
                stock_copy = prepare_disposable_engine(stock, root / "stock")
                candidate_copy = prepare_disposable_engine(candidate, root / "candidate")
                flags = tuple(identity_arguments(native_preview_identity(1597331)))
                observations = {"stock": [run_case(stock_copy, "stock", ()) for _ in range(RUNS_PER_MODE)],
                                "ordinary": [run_case(candidate_copy, "ordinary", ()) for _ in range(RUNS_PER_MODE)],
                                "optin": [run_case(candidate_copy, "optin", flags) for _ in range(RUNS_PER_MODE)]}
                verdict = assess_observations(observations)
                result["status"] = verdict["status"]
                result["checks"].update(verdict["checks"])
    except ObservationUnavailable as error:
        result["reason_code"] = str(error)
    except Exception as error:
        result["reason_code"] = type(error).__name__
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks")}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2, "INCONCLUSIVE": 3}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
