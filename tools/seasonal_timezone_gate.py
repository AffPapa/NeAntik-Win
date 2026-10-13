"""Bounded local V5 opt-in test for Date/Intl winter/summer consistency.

This tests two fixed UTC instants in six browser contexts using one disposable
profile. It is not a network privacy, anonymity, or full timezone API test.
Only verdicts and binary hashes are written; raw observed strings stay in RAM.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from fingerprint_surface_audit import AuditHandler, AuditTimeoutError
from native_persona_context_audit import prepare_disposable_engine
from privacy_defaults import initialize_privacy_defaults
from profile_identity import identity_arguments, native_preview_identity
from v5_optin_cross_surface_gate import _read_receipt, PATCH, V5_PATCH_SHA256, sha256


SOURCE_ROOT = Path(__file__).resolve().parents[1]
CONTEXTS = ("main", "iframe", "crossOriginFrame", "worker", "sharedWorker", "serviceWorker")
SEASONS = ("winter", "summer")
INSTANTS = {"winter": "2026-01-15T12:00:00.000Z", "summer": "2026-07-15T12:00:00.000Z"}

PROBE_JS = r'''
function seasonalProbe() {
  const instants = {winter: '2026-01-15T12:00:00.000Z',
                    summer: '2026-07-15T12:00:00.000Z'};
  const options = {hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
                   hour: '2-digit', minute: '2-digit', timeZoneName: 'short'};
  const formatDefault = new Intl.DateTimeFormat('en-US', options);
  const formatUTC = new Intl.DateTimeFormat('en-US', {...options, timeZone: 'UTC'});
  const output = {};
  for (const [season, instant] of Object.entries(instants)) {
    const date = new Date(instant);
    output[season] = {
      epochMilliseconds: date.getTime(),
      timezone: formatDefault.resolvedOptions().timeZone,
      offsetMinutes: date.getTimezoneOffset(),
      localHours: date.getHours(), localMinutes: date.getMinutes(),
      utcHours: date.getUTCHours(), utcMinutes: date.getUTCMinutes(),
      dateString: date.toString(),
      intlDefault: formatDefault.format(date), intlUTC: formatUTC.format(date),
    };
  }
  return output;
}
'''

PAGE = r'''<!doctype html><html><head><meta charset="utf-8"></head><body>
<pre id="result">pending</pre><img src="/barrier?token=__TOKEN__" alt="barrier">
<script>
__PROBE_JS__
(async () => {
  const token = '__TOKEN__';
  const main = seasonalProbe();
  const frame = document.createElement('iframe');
  frame.src = '/frame?token=' + token;
  const ready = new Promise((resolve, reject) => { frame.onload = resolve; frame.onerror = reject; });
  document.body.append(frame); await ready;
  const iframe = frame.contentWindow.seasonalProbe();
  const crossOriginFrame = await new Promise((resolve, reject) => {
    const target = document.createElement('iframe');
    const timer = setTimeout(() => { cleanup(); reject(new Error('cross frame timeout')); }, 7000);
    function cleanup() { clearTimeout(timer); window.removeEventListener('message', receive); target.remove(); }
    function receive(event) {
      if (event.origin !== '__CROSS_ORIGIN__' || event.source !== target.contentWindow ||
          event.data?.token !== token) return;
      cleanup(); event.data.error ? reject(new Error('cross frame error')) : resolve(event.data.value);
    }
    window.addEventListener('message', receive);
    target.src = '__CROSS_ORIGIN__/cross-frame?token=' + token +
      '&parent=' + encodeURIComponent(location.origin);
    document.body.append(target);
  });
  const worker = await new Promise((resolve, reject) => {
    const target = new Worker('/worker.js?token=' + token);
    const timer = setTimeout(() => { target.terminate(); reject(new Error('worker timeout')); }, 7000);
    target.onmessage = event => { clearTimeout(timer); target.terminate(); resolve(event.data); };
    target.onerror = error => { clearTimeout(timer); target.terminate(); reject(error); };
  });
  const sharedWorker = await new Promise((resolve, reject) => {
    const target = new SharedWorker('/shared-worker.js?token=' + token);
    const timer = setTimeout(() => { target.port.close(); reject(new Error('shared worker timeout')); }, 7000);
    target.port.onmessage = event => { clearTimeout(timer); target.port.close(); resolve(event.data); };
    target.port.start(); target.port.postMessage('probe');
  });
  const registration = await navigator.serviceWorker.register('/service-worker.js?token=' + token,
    {scope: '/'});
  const serviceWorker = await new Promise(async (resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('service worker timeout')), 10000);
    try {
      await navigator.serviceWorker.ready;
      const channel = new MessageChannel();
      channel.port1.onmessage = event => { clearTimeout(timer); channel.port1.close(); resolve(event.data); };
      registration.active.postMessage('probe', [channel.port2]);
    } catch (_) { clearTimeout(timer); reject(new Error('service worker error')); }
  });
  await registration.unregister();
  const result = {token, main, iframe, crossOriginFrame, worker, sharedWorker, serviceWorker};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(result)});
})().catch(_ => { document.getElementById('result').textContent = 'error:seasonal_probe_failed'; });
</script></body></html>'''

FRAME = r'''<!doctype html><html><head><meta charset="utf-8"></head><body><script>
__PROBE_JS__
</script></body></html>'''

CROSS_FRAME = r'''<!doctype html><html><head><meta charset="utf-8"></head><body><script>
__PROBE_JS__
const params = new URLSearchParams(location.search);
try { parent.postMessage({token: params.get('token'), value: seasonalProbe()}, params.get('parent')); }
catch (_) { parent.postMessage({token: params.get('token'), error: true}, params.get('parent')); }
</script></body></html>'''

WORKER = PROBE_JS + "\npostMessage(seasonalProbe());"
SHARED_WORKER = PROBE_JS + "\nonconnect = event => { const port = event.ports[0]; port.onmessage = () => port.postMessage(seasonalProbe()); };"
SERVICE_WORKER = PROBE_JS + "\nself.addEventListener('message', event => event.ports[0].postMessage(seasonalProbe()));"


class SeasonalHandler(AuditHandler):
    def do_GET(self) -> None:
        route = self.route()
        if route == "/case":
            body = PAGE.replace("__PROBE_JS__", PROBE_JS).replace("__TOKEN__", self.server.token)
            body = body.replace("__CROSS_ORIGIN__", self.server.cross_origin)
            self.reply(200, body.encode(), "text/html; charset=utf-8")
        elif route == "/frame":
            self.reply(200, FRAME.replace("__PROBE_JS__", PROBE_JS).encode(), "text/html; charset=utf-8")
        elif route == "/cross-frame":
            self.reply(200, CROSS_FRAME.replace("__PROBE_JS__", PROBE_JS).encode(), "text/html; charset=utf-8")
        elif route in ("/worker.js", "/shared-worker.js", "/service-worker.js"):
            body = {"/worker.js": WORKER, "/shared-worker.js": SHARED_WORKER,
                    "/service-worker.js": SERVICE_WORKER}[route]
            self.reply(200, body.encode(), "application/javascript; charset=utf-8")
        elif route == "/barrier":
            self.server.ready.wait(20)
            self.reply(200, b"", "image/png")
        else:
            self.reply(404, b"Not found")


class SeasonalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str, cross_origin: str = "") -> None:
        super().__init__(("127.0.0.1", 0), SeasonalHandler)
        self.token = token
        self.cross_origin = cross_origin
        self.result: dict | None = None
        self.ready = threading.Event()
        self.external_attempts = 0


class ObservationUnavailable(ValueError):
    """The page did not produce the complete six-context, two-date observation."""


def _complete(report: dict) -> None:
    if not isinstance(report, dict) or set(report) != set(CONTEXTS):
        raise ObservationUnavailable("missing_context")
    expected = {"epochMilliseconds", "timezone", "offsetMinutes", "localHours",
                "localMinutes", "utcHours", "utcMinutes", "dateString", "intlDefault", "intlUTC"}
    for context in CONTEXTS:
        seasons = report[context]
        if not isinstance(seasons, dict) or set(seasons) != set(SEASONS):
            raise ObservationUnavailable("missing_season")
        for season in SEASONS:
            value = seasons[season]
            if not isinstance(value, dict) or set(value) != expected:
                raise ObservationUnavailable("missing_field")
            for field in ("epochMilliseconds", "offsetMinutes", "localHours", "localMinutes",
                          "utcHours", "utcMinutes"):
                if type(value[field]) is not int:
                    raise ObservationUnavailable("invalid_integer")
            for field in ("timezone", "dateString", "intlDefault", "intlUTC"):
                if not isinstance(value[field], str) or not value[field]:
                    raise ObservationUnavailable("invalid_string")


def assess(report: dict) -> dict[str, bool]:
    """Pure checks; missing data is INCONCLUSIVE, contradictory data is FAIL."""
    _complete(report)
    checks = {}
    for season in SEASONS:
        reference = report["main"][season]
        checks[f"{season}_all_contexts_equal"] = all(
            report[context][season] == reference for context in CONTEXTS)
        checks[f"{season}_utc_date_offset_and_clock"] = all(
            (item["offsetMinutes"] == 0 and item["localHours"] == item["utcHours"] == 12
             and item["localMinutes"] == item["utcMinutes"] == 0)
            for item in (report[context][season] for context in CONTEXTS))
        checks[f"{season}_intl_utc_matches_date"] = all(
            item["timezone"] == "UTC" and item["intlDefault"] == item["intlUTC"]
            for item in (report[context][season] for context in CONTEXTS))
        checks[f"{season}_date_string_utc_offset"] = all(
            "GMT+0000" in report[context][season]["dateString"] for context in CONTEXTS)
        checks[f"{season}_fixed_instant"] = all(
            report[context][season]["epochMilliseconds"] == expected_epoch(season)
            for context in CONTEXTS)
    return checks


def expected_epoch(season: str) -> int:
    return int(datetime.fromisoformat(INSTANTS[season].replace("Z", "+00:00")).timestamp() * 1000)


def audit(chrome: Path, root: Path, flags: tuple[str, ...]) -> tuple[dict, int]:
    profile = root / "Profile"
    if not initialize_privacy_defaults(profile):
        raise RuntimeError("Could not initialize a fresh disposable profile")
    token = uuid.uuid4().hex
    cross = SeasonalServer(token)
    primary = SeasonalServer(token, f"http://localhost:{cross.server_port}")
    threads = [threading.Thread(target=server.serve_forever, daemon=True)
               for server in (primary, cross)]
    for thread in threads:
        thread.start()
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        url = f"http://127.0.0.1:{primary.server_port}/case?token={token}"
        arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                     "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                     "--disable-component-update", "--disable-sync", "--disable-quic",
                     "--metrics-recording-only", f"--proxy-server=http://127.0.0.1:{primary.server_port}",
                     "--proxy-bypass-list=127.0.0.1;localhost",
                     "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
                     *flags, url]
        process = spawn_owned_browser(arguments, root, job)
        try:
            stdout, _ = process.communicate(input=b"G", timeout=45)
        except subprocess.TimeoutExpired as error:
            raise AuditTimeoutError("browser_timeout") from error
        if process.returncode != 0:
            raise RuntimeError("Chromium failed")
        result = primary.result
        if not isinstance(result, dict):
            raise ObservationUnavailable("missing_report")
        match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
        if not match or json.loads(html.unescape(match.group(1))) != result or result.get("token") != token:
            raise ObservationUnavailable("dom_report_mismatch")
        return {context: result[context] for context in CONTEXTS}, primary.external_attempts + cross.external_attempts
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for server in (primary, cross):
            server.shutdown(); server.server_close()
        for thread in threads:
            thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chrome = args.candidate_chrome.resolve()
    output = args.output.resolve()
    if os.name != "nt":
        parser.error("Windows is required")
    if output.is_relative_to(SOURCE_ROOT) or output.exists() or not output.parent.is_dir():
        parser.error("Output must be a new private file outside the source repository")
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "one owned loopback-only opt-in session, fixed 2026 winter/summer dates; no anonymity claim",
              "status": "INCONCLUSIVE", "checks": {}}
    try:
        receipt = _read_receipt(chrome)
        info = receipt.get("native_persona_core_info") or {}
        capabilities = info.get("capabilities") or {}
        result["binary_sha256"] = {"chrome_exe": sha256(chrome),
                                   "chrome_dll": sha256(chrome.with_name("chrome.dll"))}
        result["checks"]["exact_v5_timezone_capability"] = (
            sha256(PATCH) == V5_PATCH_SHA256
            and receipt.get("privacy_patch_sha256") == V5_PATCH_SHA256
            and receipt.get("native_persona_patch_sha256") == V5_PATCH_SHA256
            and capabilities.get("timezone") is True)
        if not result["checks"]["exact_v5_timezone_capability"]:
            result["status"] = "FAIL"
        else:
            with tempfile.TemporaryDirectory(prefix="neantik-seasonal-timezone-") as temporary:
                root = Path(temporary)
                engine = prepare_disposable_engine(chrome, root / "engine")
                flags = tuple(identity_arguments(native_preview_identity(1597331)))
                report, _blocked_external_attempts = audit(engine, root / "session", flags)
                result["checks"].update(assess(report))
                result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except Exception as error:
        result["reason_code"] = type(error).__name__
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result["checks"],
                      "reason_code": result.get("reason_code")}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2, "INCONCLUSIVE": 3}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
