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
  const rendering = async (view) => {
    const canvas = view.document.createElement('canvas');
    canvas.width = 320; canvas.height = 80;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Canvas2D unavailable');
    context.fillStyle = '#25335a'; context.fillRect(0, 0, 320, 80);
    context.fillStyle = '#e9f1ff'; context.font = '19px Arial';
    context.fillText('NeAntik audit 0123456789', 9, 36);
    const encoded = new view.TextEncoder().encode(canvas.toDataURL());
    const digest = await view.crypto.subtle.digest('SHA-256', encoded);
    const canvas2dSha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    const pixels = await view.crypto.subtle.digest('SHA-256', context.getImageData(0, 0, 320, 80).data);
    const canvasPixelSha256 = Array.from(new Uint8Array(pixels), byte => byte.toString(16).padStart(2, '0')).join('');
    const gl = view.document.createElement('canvas').getContext('webgl');
    const info = gl?.getExtension('WEBGL_debug_renderer_info');
    const webgl = gl ? {
      vendor: gl.getParameter(gl.VENDOR), renderer: gl.getParameter(gl.RENDERER),
      unmaskedVendor: info ? gl.getParameter(info.UNMASKED_VENDOR_WEBGL) : null,
      unmaskedRenderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : null,
    } : null;
    return {canvas2dSha256, canvasPixelSha256, webgl};
  };
  const audio = async (view) => {
    const context = new view.OfflineAudioContext(1, 4096, 44100);
    const oscillator = context.createOscillator();
    oscillator.type = 'triangle'; oscillator.frequency.value = 997;
    const gain = context.createGain(); gain.gain.value = 0.35;
    oscillator.connect(gain); gain.connect(context.destination);
    oscillator.start(0);
    const rendered = await context.startRendering();
    const samples = rendered.getChannelData(0).slice(256, 2304);
    const digest = await view.crypto.subtle.digest('SHA-256', samples);
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  };
  const surface = async (view) => ({
    userAgent: view.navigator.userAgent,
    platform: view.navigator.platform,
    language: view.navigator.language,
    languages: Array.from(view.navigator.languages || []),
    hardwareConcurrency: view.navigator.hardwareConcurrency,
    deviceMemory: view.navigator.deviceMemory ?? null,
    timezone: new view.Intl.DateTimeFormat().resolvedOptions().timeZone,
    timezoneOffsetMinutes: new view.Date().getTimezoneOffset(),
    screen: [view.screen.width, view.screen.height, view.screen.colorDepth],
    devicePixelRatio: view.devicePixelRatio,
    ...(await rendering(view)),
    audioSha256: await audio(view),
  });
  const main = await surface(window);
  const frame = document.createElement('iframe');
  frame.src = '/frame?token=' + token;
  const frameReady = new Promise((resolve, reject) => {
    frame.onload = resolve;
    frame.onerror = reject;
  });
  document.body.append(frame);
  await frameReady;
  const iframe = await surface(frame.contentWindow);
  const crossOrigin = '__CROSS_ORIGIN__';
  const crossOriginFrame = await new Promise((resolve, reject) => {
    const target = document.createElement('iframe');
    const timeout = setTimeout(() => { cleanup(); reject(new Error('cross-origin frame timeout')); }, 7000);
    function cleanup() { clearTimeout(timeout); window.removeEventListener('message', receive); target.remove(); }
    function receive(event) {
      if (event.origin !== crossOrigin || event.source !== target.contentWindow ||
          event.data?.token !== token) return;
      cleanup();
      if (event.data.error) reject(new Error('cross-origin rendering: ' + event.data.error));
      else resolve(event.data.surface);
    }
    window.addEventListener('message', receive);
    target.src = crossOrigin + '/cross-frame?token=' + token + '&parent=' + encodeURIComponent(location.origin);
    document.body.append(target);
  });
  const worker = await new Promise((resolve, reject) => {
    const target = new Worker('/worker.js?token=' + token);
    const timeout = setTimeout(() => { target.terminate(); reject(new Error('worker timeout')); }, 5000);
    target.onmessage = (event) => { clearTimeout(timeout); target.terminate(); resolve(event.data); };
    target.onerror = (error) => { clearTimeout(timeout); target.terminate(); reject(error); };
  });
  const sharedWorker = await new Promise((resolve, reject) => {
    const target = new SharedWorker('/shared-worker.js?token=' + token);
    const timeout = setTimeout(() => { target.port.close(); reject(new Error('shared worker timeout')); }, 7000);
    target.port.onmessage = (event) => { clearTimeout(timeout); target.port.close(); resolve(event.data); };
    target.port.onmessageerror = (error) => { clearTimeout(timeout); target.port.close(); reject(error); };
    target.port.start();
    target.port.postMessage('probe');
  });
  const registration = await navigator.serviceWorker.register('/service-worker.js?token=' + token, {scope: '/'});
  const serviceWorker = await new Promise(async (resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('service worker timeout')), 10000);
    try {
      await navigator.serviceWorker.ready;
      const channel = new MessageChannel();
      channel.port1.onmessage = (event) => { clearTimeout(timeout); channel.port1.close(); resolve(event.data); };
      channel.port1.onmessageerror = (error) => { clearTimeout(timeout); channel.port1.close(); reject(error); };
      registration.active.postMessage('probe', [channel.port2]);
    } catch (error) { clearTimeout(timeout); reject(error); }
  });
  await registration.unregister();
  const httpHints = await fetch('/hints?token=' + token, {cache: 'no-store'}).then(r => r.json());
  const uaHighEntropy = navigator.userAgentData
    ? await navigator.userAgentData.getHighEntropyValues(['fullVersionList', 'platformVersion'])
    : null;
  const result = {token, main, iframe, crossOriginFrame, worker, sharedWorker,
    serviceWorker, httpHints, uaHighEntropy};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})().catch(error => { document.getElementById('result').textContent = 'error:' + String(error); });
</script></body></html>'''

WORKER = r'''(async () => {
const canvas = new OffscreenCanvas(320, 80);
const context = canvas.getContext('2d');
if (!context) throw new Error('OffscreenCanvas2D unavailable');
context.fillStyle = '#25335a'; context.fillRect(0, 0, 320, 80);
context.fillStyle = '#e9f1ff'; context.font = '19px Arial';
context.fillText('NeAntik audit 0123456789', 9, 36);
const pixels = await crypto.subtle.digest('SHA-256', context.getImageData(0, 0, 320, 80).data);
const canvasPixelSha256 = Array.from(new Uint8Array(pixels), byte => byte.toString(16).padStart(2, '0')).join('');
postMessage({
  userAgent: navigator.userAgent,
  platform: navigator.platform,
  language: navigator.language,
  languages: Array.from(navigator.languages || []),
  hardwareConcurrency: navigator.hardwareConcurrency,
  deviceMemory: navigator.deviceMemory ?? null,
  timezone: new Intl.DateTimeFormat().resolvedOptions().timeZone,
  timezoneOffsetMinutes: new Date().getTimezoneOffset(),
  canvasPixelSha256,
});
})().catch(error => postMessage({auditError: String(error)}));'''

SHARED_WORKER = r'''onconnect = (event) => {
  const port = event.ports[0];
  port.onmessage = () => port.postMessage({
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    language: navigator.language,
    languages: Array.from(navigator.languages || []),
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory ?? null,
    timezone: new Intl.DateTimeFormat().resolvedOptions().timeZone,
    timezoneOffsetMinutes: new Date().getTimezoneOffset(),
  });
};'''

SERVICE_WORKER = r'''self.addEventListener('message', (event) => {
  event.ports[0].postMessage({
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    language: navigator.language,
    languages: Array.from(navigator.languages || []),
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory ?? null,
    timezone: new Intl.DateTimeFormat().resolvedOptions().timeZone,
    timezoneOffsetMinutes: new Date().getTimezoneOffset(),
  });
});'''

CROSS_ORIGIN_FRAME = r'''<!doctype html><html><head><meta charset="utf-8"></head><body>
<script>
const params = new URLSearchParams(location.search);
const parentOrigin = params.get('parent');
async function measure() {
const canvas = document.createElement('canvas');
canvas.width = 320; canvas.height = 80;
const context = canvas.getContext('2d');
if (!context) throw new Error('Canvas2D unavailable');
context.fillStyle = '#25335a'; context.fillRect(0, 0, 320, 80);
context.fillStyle = '#e9f1ff'; context.font = '19px Arial';
context.fillText('NeAntik audit 0123456789', 9, 36);
const encoded = new TextEncoder().encode(canvas.toDataURL());
const digest = await crypto.subtle.digest('SHA-256', encoded);
const canvas2dSha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
const pixels = await crypto.subtle.digest('SHA-256', context.getImageData(0, 0, 320, 80).data);
const canvasPixelSha256 = Array.from(new Uint8Array(pixels), byte => byte.toString(16).padStart(2, '0')).join('');
const gl = document.createElement('canvas').getContext('webgl');
const info = gl?.getExtension('WEBGL_debug_renderer_info');
const webgl = gl ? {
  vendor: gl.getParameter(gl.VENDOR), renderer: gl.getParameter(gl.RENDERER),
  unmaskedVendor: info ? gl.getParameter(info.UNMASKED_VENDOR_WEBGL) : null,
  unmaskedRenderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : null,
} : null;
const audio = new OfflineAudioContext(1, 4096, 44100);
const oscillator = audio.createOscillator();
oscillator.type = 'triangle'; oscillator.frequency.value = 997;
const gain = audio.createGain(); gain.gain.value = 0.35;
oscillator.connect(gain); gain.connect(audio.destination);
oscillator.start(0);
const rendered = await audio.startRendering();
const samples = rendered.getChannelData(0).slice(256, 2304);
const audioDigest = await crypto.subtle.digest('SHA-256', samples);
const audioSha256 = Array.from(new Uint8Array(audioDigest), byte => byte.toString(16).padStart(2, '0')).join('');
const surface = {
  userAgent: navigator.userAgent,
  platform: navigator.platform,
  language: navigator.language,
  languages: Array.from(navigator.languages || []),
  hardwareConcurrency: navigator.hardwareConcurrency,
  deviceMemory: navigator.deviceMemory ?? null,
  timezone: new Intl.DateTimeFormat().resolvedOptions().timeZone,
  timezoneOffsetMinutes: new Date().getTimezoneOffset(),
  screen: [screen.width, screen.height, screen.colorDepth],
  devicePixelRatio,
  canvas2dSha256, canvasPixelSha256, webgl, audioSha256,
};
parent.postMessage({token: params.get('token'), surface}, parentOrigin);
}
measure().catch(error => parent.postMessage({token: params.get('token'), error: String(error)}, parentOrigin));
</script></body></html>'''


class AuditServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str, cross_origin: str = ""):
        super().__init__(("127.0.0.1", 0), AuditHandler)
        self.token = token
        self.cross_origin = cross_origin
        self.result: dict | None = None
        self.ready = threading.Event()
        self.external_attempts = 0
        self.headers_seen: dict[str, str | None] = {}
        self.hints_seen: dict[str, str | None] = {}


class AuditHandler(BaseHTTPRequestHandler):
    server: AuditServer

    def log_message(self, _format: str, *args: object) -> None:
        pass

    def reply(self, status: int, content: bytes, mime: str = "text/plain",
              extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
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
            self.reply(200, PAGE.replace("__TOKEN__", self.server.token)
                       .replace("__CROSS_ORIGIN__", self.server.cross_origin).encode(), "text/html; charset=utf-8",
                       {"Accept-CH": "Sec-CH-Device-Memory, Sec-CH-UA-Full-Version-List, Sec-CH-UA-Platform-Version"})
        elif route == "/hints":
            self.server.hints_seen = {
                "deviceMemory": self.headers.get("Sec-CH-Device-Memory"),
                "uaFullVersionList": self.headers.get("Sec-CH-UA-Full-Version-List"),
                "uaPlatformVersion": self.headers.get("Sec-CH-UA-Platform-Version"),
            }
            self.reply(200, json.dumps(self.server.hints_seen).encode(), "application/json; charset=utf-8")
        elif route == "/frame":
            self.reply(200, b"<!doctype html><html><body>frame</body></html>", "text/html; charset=utf-8")
        elif route == "/cross-frame":
            self.reply(200, CROSS_ORIGIN_FRAME.encode(), "text/html; charset=utf-8")
        elif route == "/worker.js":
            self.reply(200, WORKER.encode(), "application/javascript; charset=utf-8")
        elif route == "/shared-worker.js":
            self.reply(200, SHARED_WORKER.encode(), "application/javascript; charset=utf-8")
        elif route == "/service-worker.js":
            self.reply(200, SERVICE_WORKER.encode(), "application/javascript; charset=utf-8")
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


def audit_profile(chrome: Path, root: Path, native_flags: tuple[str, ...] = ()) -> dict:
    profile = root / "Profile"
    if not initialize_privacy_defaults(profile):
        raise RuntimeError("Could not initialize a fresh profile")
    token = uuid.uuid4().hex
    cross_server = AuditServer(token)
    server = AuditServer(token, f"http://127.0.0.1:{cross_server.server_port}")
    threads = [threading.Thread(target=item.serve_forever, daemon=True)
               for item in (server, cross_server)]
    for thread in threads:
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
                     "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                     *native_flags, url]
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
        surfaces = {key: result[key] for key in ("main", "iframe", "crossOriginFrame",
                                                   "worker", "sharedWorker", "serviceWorker")}
        return {"surfaces": surfaces, "http": server.headers_seen,
                "client_hints": server.hints_seen,
                "ua_high_entropy": result.get("uaHighEntropy"),
                "blocked_external_requests": server.external_attempts + cross_server.external_attempts}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for item in (server, cross_server):
            item.shutdown()
            item.server_close()
        for thread in threads:
            thread.join(timeout=5)


def evaluate(reports: list[dict]) -> list[dict[str, bool]]:
    keys = ("userAgent", "platform", "language", "languages", "hardwareConcurrency",
            "deviceMemory", "timezone", "timezoneOffsetMinutes")
    consistency = []
    for report in reports:
        surfaces = report["surfaces"]
        hint = report.get("client_hints", {}).get("deviceMemory")
        memory = surfaces["main"]["deviceMemory"]
        try:
            hint_matches = hint is not None and memory is not None and float(hint) == memory
        except (TypeError, ValueError):
            hint_matches = False
        ua_data = report.get("ua_high_entropy") or {}
        full_version_hint = report.get("client_hints", {}).get("uaFullVersionList")
        observed_brands = ua_data.get("fullVersionList")
        header_brands = re.findall(r'"([^"]+)";v="([^"]+)"', full_version_hint or "")
        js_brands = [
            (item["brand"], item["version"])
            for item in observed_brands or []
            if isinstance(item, dict)
            and isinstance(item.get("brand"), str)
            and isinstance(item.get("version"), str)
        ] if isinstance(observed_brands, list) else []
        ua_full_version_matches = (
            bool(header_brands)
            and isinstance(observed_brands, list)
            and len(header_brands) == len(observed_brands) == len(js_brands)
            and sorted(header_brands) == sorted(js_brands)
        )
        platform_hint = report.get("client_hints", {}).get("uaPlatformVersion")
        ua_platform_version_matches = (
            isinstance(platform_hint, str)
            and platform_hint.startswith('"') and platform_hint.endswith('"')
            and platform_hint[1:-1] == ua_data.get("platformVersion")
        )
        consistency.append({
            "main_iframe": surfaces["main"] == surfaces["iframe"],
            "main_cross_origin_frame": surfaces["main"] == surfaces["crossOriginFrame"],
            "canvas2d_observed": isinstance(surfaces["main"].get("canvas2dSha256"), str)
            and bool(re.fullmatch(r"[a-f0-9]{64}", surfaces["main"]["canvas2dSha256"])),
            "canvas2d_iframe_parity": surfaces["main"].get("canvas2dSha256") == surfaces["iframe"].get("canvas2dSha256"),
            "canvas2d_cross_origin_parity": surfaces["main"].get("canvas2dSha256") == surfaces["crossOriginFrame"].get("canvas2dSha256"),
            "canvas_pixels_observed": isinstance(surfaces["main"].get("canvasPixelSha256"), str)
            and bool(re.fullmatch(r"[a-f0-9]{64}", surfaces["main"]["canvasPixelSha256"])),
            "canvas_pixels_dedicated_worker_parity": (
                surfaces["main"].get("canvasPixelSha256") == surfaces["worker"].get("canvasPixelSha256")
                and isinstance(surfaces["worker"].get("canvasPixelSha256"), str)
            ),
            "webgl_observed": isinstance(surfaces["main"].get("webgl"), dict),
            "webgl_iframe_parity": surfaces["main"].get("webgl") == surfaces["iframe"].get("webgl"),
            "webgl_cross_origin_parity": surfaces["main"].get("webgl") == surfaces["crossOriginFrame"].get("webgl"),
            "audio_observed": isinstance(surfaces["main"].get("audioSha256"), str)
            and bool(re.fullmatch(r"[a-f0-9]{64}", surfaces["main"]["audioSha256"])),
            "audio_iframe_parity": surfaces["main"].get("audioSha256") == surfaces["iframe"].get("audioSha256"),
            "audio_cross_origin_parity": surfaces["main"].get("audioSha256") == surfaces["crossOriginFrame"].get("audioSha256"),
            "main_worker_common": all(surfaces["main"].get(key) == surfaces["worker"].get(key) for key in keys),
            "main_shared_worker_common": all(surfaces["main"].get(key) == surfaces["sharedWorker"].get(key) for key in keys),
            "main_service_worker_common": all(surfaces["main"].get(key) == surfaces["serviceWorker"].get(key) for key in keys),
            "js_http_user_agent": surfaces["main"]["userAgent"] == report["http"]["userAgent"],
            "device_memory_hint_parity": hint_matches,
            "ua_full_version_hint_parity": ua_full_version_matches,
            "ua_platform_version_hint_parity": ua_platform_version_matches,
        })
    return consistency


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
    consistency = evaluate(reports)
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
