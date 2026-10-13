"""Bounded Canvas API/latency gate for stock, ordinary and opt-in V5 Chromium.

Only disposable loopback profiles are used. Reports contain verdicts and timing
aggregates, never Canvas pixels or browser traits. This is not an anonymity test.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import math
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
CHECKS = ("dimensions", "repeat_pixels", "subregion_pixels", "opaque_alpha",
          "data_url_png", "blob_png", "encoded_bytes_equal", "decoded_dimensions")
SAMPLE_COUNT = 32
OPS_PER_SAMPLE = 16
MAX_RUN_SECONDS = 40

PAGE = r'''<!doctype html><html><meta charset="utf-8"><pre id="result">pending</pre>
<img src="/barrier?token=__TOKEN__" alt="load barrier"><script>
(async () => {
  const token = '__TOKEN__';
  const canvas = document.createElement('canvas');
  canvas.width = 64; canvas.height = 48;
  const context = canvas.getContext('2d', {willReadFrequently: true});
  if (!context) throw Error('2d unavailable');
  context.fillStyle = '#4368a9'; context.fillRect(0, 0, 64, 48);
  const full = context.getImageData(0, 0, 64, 48);
  const again = context.getImageData(0, 0, 64, 48);
  const part = context.getImageData(5, 7, 13, 11);
  const equal = (a, b) => a.length === b.length && a.every((value, index) => value === b[index]);
  let cropMatches = true;
  for (let y = 0; y < 11; y++) for (let x = 0; x < 13; x++) for (let c = 0; c < 4; c++) {
    if (part.data[(y * 13 + x) * 4 + c] !== full.data[((y + 7) * 64 + x + 5) * 4 + c]) cropMatches = false;
  }
  const url = canvas.toDataURL('image/png');
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  const fromUrl = new Uint8Array(await (await fetch(url)).arrayBuffer());
  const fromBlob = blob ? new Uint8Array(await blob.arrayBuffer()) : new Uint8Array();
  const bitmap = blob ? await createImageBitmap(blob) : null;
  const checks = {
    dimensions: full.width === 64 && full.height === 48 && part.width === 13 && part.height === 11,
    repeat_pixels: equal(full.data, again.data),
    subregion_pixels: cropMatches,
    opaque_alpha: Array.from(full.data).every((value, index) => index % 4 !== 3 || value === 255),
    data_url_png: url.startsWith('data:image/png;base64,') && fromUrl.length > 100,
    blob_png: !!blob && blob.type === 'image/png' && fromBlob.length > 100,
    encoded_bytes_equal: equal(fromUrl, fromBlob),
    decoded_dimensions: !!bitmap && bitmap.width === 64 && bitmap.height === 48,
  };
  if (bitmap) bitmap.close();
  const durations = [];
  for (let i = 0; i < __COUNT__; i++) {
    const start = performance.now();
    for (let j = 0; j < __OPS__; j++) {
      const sample = context.getImageData(0, 0, 64, 48);
      if (sample.data.length !== 64 * 48 * 4) throw Error('timed readback incomplete');
    }
    durations.push((performance.now() - start) / __OPS__);
  }
  durations.sort((a, b) => a - b);
  const result = {token, checks, p50_ms: durations[15], p95_ms: durations[30],
                  sample_count: durations.length};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})().catch(async () => {
  const result = {token: '__TOKEN__', error: 'probe_failed'};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=__TOKEN__', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
});
</script>'''.replace('__COUNT__', str(SAMPLE_COUNT)).replace('__OPS__', str(OPS_PER_SAMPLE))


class ObservationUnavailable(ValueError):
    """A required observation is absent; do not infer PASS or product FAIL."""


def validate_observation(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"token", "checks", "p50_ms", "p95_ms", "sample_count"}:
        raise ObservationUnavailable("incomplete_report")
    checks = value["checks"]
    if not isinstance(checks, dict) or set(checks) != set(CHECKS) or any(type(v) is not bool for v in checks.values()):
        raise ObservationUnavailable("incomplete_checks")
    if value["sample_count"] != SAMPLE_COUNT or type(value["sample_count"]) is not int:
        raise ObservationUnavailable("incomplete_timing")
    for key in ("p50_ms", "p95_ms"):
        number = value[key]
        if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 10000:
            raise ObservationUnavailable("invalid_timing")
    if value["p50_ms"] > value["p95_ms"]:
        raise ObservationUnavailable("timing_order_invalid")
    return value


def assess_observations(observations: list[dict]) -> dict:
    if len(observations) != 3:
        raise ObservationUnavailable("three_modes_required")
    stock, ordinary, optin = (validate_observation(item) for item in observations)
    checks = {f"{mode}_{name}": item["checks"][name]
              for mode, item in (("stock", stock), ("ordinary", ordinary), ("optin", optin))
              for name in CHECKS}
    # Deliberately generous screening budget: a noisy host can still yield an
    # inconclusive performance result. p50/p95 values are recorded for review.
    checks["ordinary_p95_budget"] = ordinary["p95_ms"] <= max(2.0, stock["p95_ms"] * 8)
    checks["optin_p95_budget"] = optin["p95_ms"] <= max(2.0, stock["p95_ms"] * 8)
    checks["optin_p95_absolute"] = optin["p95_ms"] <= 10.0
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "timing_ms": {mode: {"p50": round(item["p50_ms"], 3), "p95": round(item["p95_ms"], 3)}
                          for mode, item in (("stock", stock), ("ordinary", ordinary), ("optin", optin))}}


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
            if not 0 < size <= 2048:
                raise ValueError("report size")
            report = json.loads(self.rfile.read(size))
            if not isinstance(report, dict) or report.get("token") != self.server.token:
                raise ValueError("report token")
            self.server.result = report
            self.server.ready.set()
            self.reply(200, b"ok")
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def run_case(chrome: Path, mode: str, flags: tuple[str, ...]) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"neantik-v5-canvas-{mode}-") as temporary:
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
              "scope": "three disposable loopback-only launches on one Windows host; no anonymity claim",
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
            with tempfile.TemporaryDirectory(prefix="neantik-v5-canvas-core-") as temporary:
                root = Path(temporary)
                stock_copy = prepare_disposable_engine(stock, root / "stock")
                candidate_copy = prepare_disposable_engine(candidate, root / "candidate")
                flags = tuple(identity_arguments(native_preview_identity(1597331)))
                observations = [run_case(stock_copy, "stock", ()),
                                run_case(candidate_copy, "ordinary", ()),
                                run_case(candidate_copy, "optin", flags)]
                verdict = assess_observations(observations)
                result.update({"status": verdict["status"], "timing_ms": verdict["timing_ms"]})
                result["checks"].update(verdict["checks"])
    except Exception as error:
        # Error text can contain local paths or browser output; emit type only.
        result["reason_code"] = type(error).__name__
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks")}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2, "INCONCLUSIVE": 3}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
