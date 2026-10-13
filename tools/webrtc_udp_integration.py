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
import select
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from proxy_integration import receive_exact


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
  __PROXY_ROUTE_PROBE__
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

    def snapshot(self) -> dict[str, int]:
        return {"stun_binding_requests": self.count,
                "all_udp_datagrams": self.all_datagrams}


def netlog_udp_summary(path: Path, stun_host: str, stun_port: int) -> dict[str, int]:
    """Count attempted UDP sends without copying sensitive NetLog URLs to a report."""
    document = json.loads(path.read_text(encoding="utf-8"))
    constants = document.get("constants", {})
    event_type = constants.get("logEventTypes", {}).get("UDP_BYTES_SENT")
    if not isinstance(event_type, int) or not isinstance(document.get("events"), list):
        raise RuntimeError("Chromium NetLog lacks UDP event metadata")
    destination = f"{stun_host}:{stun_port}"
    attempts = [event for event in document["events"] if event.get("type") == event_type]
    return {"all_udp_sends": len(attempts),
            "stun_destination_sends": sum(event.get("params", {}).get("address") == destination
                                          for event in attempts),
            "other_udp_sends": sum(event.get("params", {}).get("address") != destination
                                   for event in attempts)}


def evaluate_cases(direct: dict, proxy: dict, diagnostic_disable_network_sandbox: bool) -> str:
    """Never treat a weakened-sandbox control as a product privacy pass."""
    checks_pass = (direct["stun_binding_requests"] > 0 and
                   direct["netlog"]["stun_destination_sends"] > 0 and
                   proxy["stun_binding_requests"] == 0 and
                   proxy["netlog"]["all_udp_sends"] == 0)
    if not checks_pass:
        return "inconclusive"
    return "diagnostic_control_only" if diagnostic_disable_network_sandbox else "passed"


def evaluate_socks_case(direct: dict, proxy: dict) -> str:
    """A private STUN negative control is valid only with an observed SOCKS route."""
    checks_pass = (direct["stun_binding_requests"] > 0 and
                   direct["netlog"]["stun_destination_sends"] > 0 and
                   proxy.get("proxy_bound") is True and
                   proxy.get("proxy_scheme") == "socks5" and
                   proxy["stun_binding_requests"] == 0 and
                   proxy["all_udp_datagrams"] == 0 and
                   proxy["netlog"]["all_udp_sends"] == 0 and
                   proxy["route_control_requests"] > 0 and
                   proxy["proxied_page_requests"] > 0)
    return "passed" if checks_pass else "inconclusive"


class RouteSocksServer(socketserver.ThreadingTCPServer):
    """Only a disposable loopback probe page may be forwarded."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, page_port: int):
        super().__init__(("127.0.0.1", 0), RouteSocksHandler)
        self.page_port = page_port
        self.lock = threading.Lock()
        self.route_control_requests = 0
        self.proxied_page_requests = 0
        self.rejected_requests = 0

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return {"route_control_requests": self.route_control_requests,
                    "proxied_page_requests": self.proxied_page_requests,
                    "rejected_external_requests": self.rejected_requests}


class RouteSocksHandler(socketserver.BaseRequestHandler):
    server: RouteSocksServer

    def handle(self) -> None:
        client: socket.socket = self.request
        client.settimeout(5)
        try:
            version, count = receive_exact(client, 2)
            methods = receive_exact(client, count)
            if version != 5 or 0 not in methods:
                client.sendall(b"\x05\xff")
                return
            client.sendall(b"\x05\x00")
            version, command, reserved, kind = receive_exact(client, 4)
            if kind == 1:
                host = socket.inet_ntoa(receive_exact(client, 4))
            elif kind == 3:
                host = receive_exact(client, receive_exact(client, 1)[0]).decode("ascii")
            elif kind == 4:
                host = socket.inet_ntop(socket.AF_INET6, receive_exact(client, 16))
            else:
                raise ValueError("Unsupported SOCKS address type")
            port = int.from_bytes(receive_exact(client, 2), "big")
            valid_command = (version, command, reserved) == (5, 1, 0)
            page = valid_command and host == "127.0.0.1" and port == self.server.page_port
            with self.server.lock:
                if page:
                    self.server.proxied_page_requests += 1
                elif valid_command and host == "neantik-route-control.invalid" and port == 80:
                    self.server.route_control_requests += 1
                else:
                    self.server.rejected_requests += 1
            if not page:
                client.sendall(b"\x05\x02\x00\x01" + b"\x00" * 6)
                return
            with socket.create_connection(("127.0.0.1", self.server.page_port), timeout=5) as upstream:
                client.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("127.0.0.1") + b"\x00\x00")
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    readable, _, _ = select.select([client, upstream], [], [], 1)
                    for source in readable:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        (upstream if source is client else client).sendall(chunk)
        except (OSError, ValueError, ConnectionError):
            return


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
        self.route_control_requests = 0
        self.verify_proxy_route = False


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
                if parsed.hostname == "neantik-route-control.invalid":
                    self.server.route_control_requests += 1
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
                    .replace("__STUN_PORT__", str(self.server.stun_port))
                    .replace("__PROXY_ROUTE_PROBE__",
                             "await fetch('http://neantik-route-control.invalid/', {mode: 'no-cors'}).catch(() => {});"
                             if self.server.verify_proxy_route else ""))
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


def run_case(chrome: Path, root: Path, proxy_bound: bool, stun_host: str,
             force_default_policy: bool = False, net_log_dir: Path | None = None,
             diagnostic_disable_network_sandbox: bool = False,
             remote_sink: object | None = None,
             verify_proxy_route: bool = False,
             proxy_scheme: str = "http") -> dict:
    if verify_proxy_route and not proxy_bound:
        raise ValueError("Proxy route control requires a proxy-bound case")
    if proxy_scheme not in ("http", "socks5"):
        raise ValueError("Only the synthetic HTTP and SOCKS5 proxies are supported")
    token = uuid.uuid4().hex
    stun = remote_sink if remote_sink is not None else StunSink(stun_host)
    if remote_sink is not None:
        stun.reset()
    server = ProbeServer(token, stun_host, stun.port)
    server.verify_proxy_route = verify_proxy_route
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    socks = RouteSocksServer(server.server_port) if proxy_bound and proxy_scheme == "socks5" else None
    socks_thread = threading.Thread(target=socks.serve_forever, daemon=True) if socks is not None else None
    if socks_thread is not None:
        socks_thread.start()
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        profile_name = ("proxy-socks5" if proxy_scheme == "socks5" else "proxy") if proxy_bound else "direct"
        profile = root / profile_name
        log_dir = net_log_dir or root
        net_log_path = log_dir / f"{profile_name}.json"
        url = f"http://127.0.0.1:{server.server_port}/case?token={token}"
        arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                     "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                     "--disable-component-update", "--disable-sync", "--disable-quic",
                     "--metrics-recording-only", f"--log-net-log={net_log_path}"]
        if diagnostic_disable_network_sandbox:
            arguments.append("--disable-features=NetworkServiceSandbox")
        if proxy_bound:
            proxy_port = socks.server_address[1] if socks is not None else server.server_port
            arguments += [f"--proxy-server={proxy_scheme}://127.0.0.1:{proxy_port}",
                          "--proxy-bypass-list=<-loopback>",
                          "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                          "--webrtc-ip-handling-policy=disable_non_proxied_udp"]
        else:
            arguments += ["--no-proxy-server"]
            if force_default_policy:
                arguments += ["--force-webrtc-ip-handling-policy=default"]
        process = spawn_owned_browser([*arguments, url], root, job)
        stdout, stderr = process.communicate(input=b"G", timeout=45)
        if process.returncode != 0 or not isinstance(server.result, dict):
            raise RuntimeError(f"Browser did not complete WebRTC case: exit={process.returncode}")
        match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
        if not match or json.loads(html.unescape(match.group(1))) != server.result:
            raise RuntimeError("Browser DOM and loopback report differ")
        if server.result.get("error"):
            raise RuntimeError(f"WebRTC page error: {server.result['error']}")
        receiver = stun.snapshot()
        route = socks.snapshot() if socks is not None else {
            "route_control_requests": server.route_control_requests,
            "proxied_page_requests": 0,
            "rejected_external_requests": server.rejected_external_requests}
        return {"proxy_bound": proxy_bound, "stun_destination_port": stun.port,
                "proxy_scheme": proxy_scheme if proxy_bound else "direct",
                "stun_binding_requests": receiver["stun_binding_requests"],
                "all_udp_datagrams": receiver["all_udp_datagrams"],
                "netlog": netlog_udp_summary(net_log_path, stun_host, stun.port),
                "candidate_types": server.result.get("candidateTypes", []),
                "rejected_external_requests": route["rejected_external_requests"],
                "route_control_requests": route["route_control_requests"],
                "proxied_page_requests": route["proxied_page_requests"]}
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
        if socks is not None:
            socks.shutdown()
            socks.server_close()
            socks_thread.join(timeout=5)
        if remote_sink is None:
            stun.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stun-host", default="127.0.0.1",
                        help="IPv4 address owned by this computer; use a private LAN address if Chromium blocks loopback STUN")
    parser.add_argument("--force-default-policy", action="store_true",
                        help="Diagnostic only: force Chromium's default WebRTC IP handling on the direct control")
    parser.add_argument("--net-log-dir", type=Path,
                        help="Existing private directory for Chromium NetLogs; logs may contain sensitive request details")
    parser.add_argument("--diagnostic-disable-network-sandbox", action="store_true",
                        help="Diagnostic control only: temporarily disable network-service sandbox in disposable test processes; never a product setting or privacy pass")
    args = parser.parse_args()
    if os.name != "nt" or not args.chrome.is_file() or args.chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output path must be new and its parent must exist")
    if args.net_log_dir is not None and (not args.net_log_dir.is_dir() or
                                         any((args.net_log_dir / name).exists() for name in ("direct.json", "proxy.json"))):
        parser.error("NetLog directory must exist and not already contain direct.json or proxy.json")
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
              "diagnostic_disable_network_sandbox": args.diagnostic_disable_network_sandbox,
              "cases": [], "status": "started"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-webrtc-udp-qa-") as temporary:
            root = Path(temporary)
            report["cases"].append(run_case(args.chrome, root, False, args.stun_host,
                                            args.force_default_policy, args.net_log_dir,
                                            args.diagnostic_disable_network_sandbox))
            report["cases"].append(run_case(args.chrome, root, True, args.stun_host,
                                            net_log_dir=args.net_log_dir,
                                            diagnostic_disable_network_sandbox=args.diagnostic_disable_network_sandbox))
        direct, proxy = report["cases"]
        report["status"] = evaluate_cases(direct, proxy, args.diagnostic_disable_network_sandbox)
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": report["cases"],
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    # Only a normally sandboxed pass may satisfy an automated release gate.
    return 0 if report["status"] == "passed" else 2 if report["status"] == "diagnostic_control_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
