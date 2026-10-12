"""Measure self-hosted STUN UDP under direct and proxy-bound Chromium modes.

The website/proxy fixture is loopback; STUN binds an address owned by this host.
This is not an external WebRTC, TURN, IPv6, DNS or anonymity test. A positive
direct control must send a STUN Binding request before the proxy case can pass.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit
import uuid

from browser_integration import OwnedJob, spawn_owned_browser


PAGE = r'''<!doctype html><html><head><meta charset="utf-8"></head><body>
<pre id="result">pending</pre><img alt="load barrier" src="/barrier?token=__TOKEN__">
<script>
(async () => {
  const token = '__TOKEN__';
  const peer = new RTCPeerConnection({iceServers: [{urls: 'stun:__STUN_HOST__:__STUN_PORT__'}],
                                     iceTransportPolicy: 'all'});
  const candidates = [];
  peer.onicecandidate = event => { if (event.candidate) candidates.push(event.candidate.type || 'unknown'); };
  peer.createDataChannel('local-stun-qa');
  let error = null;
  try {
    await peer.setLocalDescription(await peer.createOffer());
    await new Promise(resolve => setTimeout(resolve, 4000));
  } catch (caught) { error = String(caught); }
  const result = {token, error, candidateTypes: candidates};
  peer.close();
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})().catch(error => { document.getElementById('result').textContent = 'error:' + String(error); });
</script></body></html>'''


def is_stun_binding_request(packet: bytes) -> bool:
    return (len(packet) >= 20 and packet[:2] == b"\x00\x01" and
            packet[4:8] == b"\x21\x12\xa4\x42")


class StunSink:
    def __init__(self, host: str) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, 0))
        self.socket.settimeout(0.2)
        self.port = self.socket.getsockname()[1]
        self.count = 0
        self.all_datagrams = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.receive, daemon=True)
        self.thread.start()

    def receive(self) -> None:
        while not self.stop.is_set():
            try:
                packet, _peer = self.socket.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            self.all_datagrams += 1
            if is_stun_binding_request(packet):
                self.count += 1

    def close(self) -> None:
        self.stop.set()
        self.socket.close()
        self.thread.join(timeout=2)


class ProbeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str, stun_host: str, stun_port: int):
        super().__init__(("127.0.0.1", 0), ProbeHandler)
        self.token = token
        self.stun_host = stun_host
        self.stun_port = stun_port
        self.ready = threading.Event()
        self.result: dict | None = None
        self.rejected_external_requests = 0


class ProbeHandler(BaseHTTPRequestHandler):
    server: ProbeServer

    def log_message(self, *_args: object) -> None:
        pass

    def reply(self, status: int, data: bytes, mime: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def route(self) -> str | None:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port != self.server.server_port:
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
            page = (PAGE.replace("__TOKEN__", self.server.token)
                    .replace("__STUN_HOST__", self.server.stun_host)
                    .replace("__STUN_PORT__", str(self.server.stun_port)))
            self.reply(200, page.encode(), "text/html; charset=utf-8")
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
            if not 0 < length <= 4096:
                raise ValueError("Invalid report length")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict) or value.get("token") != self.server.token:
                raise ValueError("Invalid report identity")
            self.server.result = value
            self.reply(200, b"ok")
            self.server.ready.set()
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


def run_case(chrome: Path, root: Path, proxy_bound: bool, stun_host: str) -> dict:
    token = uuid.uuid4().hex
    stun = StunSink(stun_host)
    server = ProbeServer(token, stun_host, stun.port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        profile = root / ("proxy" if proxy_bound else "direct")
        url = f"http://127.0.0.1:{server.server_port}/case?token={token}"
        arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                     "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                     "--disable-component-update", "--disable-sync", "--disable-quic",
                     "--metrics-recording-only"]
        if proxy_bound:
            arguments += [f"--proxy-server=http://127.0.0.1:{server.server_port}",
                          "--proxy-bypass-list=<-loopback>",
                          "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                          "--webrtc-ip-handling-policy=disable_non_proxied_udp"]
        else:
            arguments += ["--no-proxy-server"]
        process = spawn_owned_browser([*arguments, url], root, job)
        stdout, stderr = process.communicate(input=b"G", timeout=45)
        if process.returncode != 0 or not isinstance(server.result, dict):
            raise RuntimeError(f"Browser did not complete WebRTC case: exit={process.returncode}; stderr={stderr.decode(errors='replace')[-400:]}")
        match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
        if not match or json.loads(html.unescape(match.group(1))) != server.result:
            raise RuntimeError("Browser DOM and loopback report differ")
        if server.result.get("error"):
            raise RuntimeError(f"WebRTC page error: {server.result['error']}")
        return {"proxy_bound": proxy_bound, "stun_binding_requests": stun.count,
                "all_udp_datagrams": stun.all_datagrams,
                "candidate_types": server.result.get("candidateTypes", []),
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
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        stun.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stun-host", default="127.0.0.1",
                        help="IPv4 address owned by this computer; use a private LAN address if Chromium blocks loopback STUN")
    args = parser.parse_args()
    if os.name != "nt" or not args.chrome.is_file() or args.chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output path must be new and its parent must exist")
    try:
        stun_ip = ipaddress.ip_address(args.stun_host)
        if stun_ip.version != 4 or not stun_ip.is_private:
            raise ValueError("STUN host must be a private or loopback IPv4 address")
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.bind((args.stun_host, 0))
        finally:
            probe.close()
    except (ValueError, OSError) as error:
        parser.error(f"STUN host must be assigned to this computer: {error}")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "direct positive control and proxy-policy comparison; self-hosted STUN; no public network claim",
              "cases": [], "status": "started"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-webrtc-udp-qa-") as temporary:
            root = Path(temporary)
            report["cases"].append(run_case(args.chrome, root, False, args.stun_host))
            report["cases"].append(run_case(args.chrome, root, True, args.stun_host))
        direct, proxy = report["cases"]
        report["status"] = "passed" if direct["stun_binding_requests"] > 0 and proxy["stun_binding_requests"] == 0 else "inconclusive"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": report["cases"],
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
