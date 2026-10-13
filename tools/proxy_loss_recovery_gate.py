"""Loopback-only HTTP proxy loss/recovery in one owned Chromium session.

The synthetic target never accepts an external connection. The proxy forwards
only one tokenized local URL. This tests a local fail-closed route, not public
network leakage, DNS, WebRTC, or anonymity.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote, urlsplit
from urllib.request import Request, ProxyHandler, build_opener
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from nevision_win import bundled_proxy_privacy_arguments, proxy_endpoint
from proxy_integration import Evidence, HTTPProxy, LocalHTTPServer, Target, TEST_HOST
from start_page_network_audit import summarize_netlog
from websocket_route_integration import cdp_frame, cdp_receive


class Inconclusive(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def start(server: LocalHTTPServer) -> threading.Thread:
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return worker


def stop(server: LocalHTTPServer, worker: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)
    if worker.is_alive():
        raise Inconclusive("local_fixture_did_not_stop")


def proxy_server(port: int, target_port: int, evidence: Evidence) -> LocalHTTPServer:
    server = LocalHTTPServer(("127.0.0.1", port), HTTPProxy)
    server.target_port = target_port
    server.ipv6_target_port = -1
    server.evidence = evidence
    return server


def debug_port(profile: Path, process: subprocess.Popen[bytes]) -> int:
    marker = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise Inconclusive("browser_exited_before_navigation")
        try:
            port = int(marker.read_text(encoding="ascii").splitlines()[0])
            if 0 < port < 65536:
                return port
        except (OSError, ValueError, IndexError):
            pass
        time.sleep(0.1)
    raise Inconclusive("local_devtools_port_missing")


def new_tab(port: int, url: str) -> None:
    request = Request(f"http://127.0.0.1:{port}/json/new?{quote(url, safe='')}", method="PUT")
    # Ignore the machine's ambient proxy settings for the local CDP channel.
    with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
        if response.status != 200:
            raise Inconclusive("local_devtools_navigation_failed")


def close_browser(port: int) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/json/version")
        response = connection.getresponse()
        if response.status != 200:
            raise Inconclusive("local_devtools_version_failed")
        address = urlsplit(json.loads(response.read(65536))["webSocketDebuggerUrl"])
    finally:
        connection.close()
    if address.hostname not in ("127.0.0.1", "localhost") or address.port != port:
        raise Inconclusive("browser_debug_endpoint_not_local")
    with socket.create_connection(("127.0.0.1", port), timeout=5) as peer:
        peer.settimeout(5)
        nonce = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (f"GET {address.path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                     "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                     "Sec-WebSocket-Version: 13\r\n"
                     f"Sec-WebSocket-Key: {nonce}\r\nOrigin: http://127.0.0.1\r\n\r\n")
        peer.sendall(handshake.encode("ascii"))
        header = b""
        while b"\r\n\r\n" not in header and len(header) < 8192:
            header += peer.recv(8192)
        if not header.startswith(b"HTTP/1.1 101 "):
            raise Inconclusive("browser_debug_websocket_rejected")
        peer.sendall(cdp_frame(json.dumps({"id": 1, "method": "Browser.close"})))
        try:
            cdp_receive(peer)
        except (OSError, ValueError):
            pass  # The browser may close the socket before acknowledging.


def wait_for_token(evidence: Evidence, token: str, timeout: float) -> str | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with evidence.lock:
            routes = [item["route"] for item in evidence.requests if item["token"] == token]
        if routes:
            return routes[-1]
        time.sleep(0.1)
    return None


def measure(chrome: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="neantik-proxy-loss-qa-") as temporary:
        root = Path(temporary)
        profile = root / "Profile"
        profile.mkdir()
        netlog = root / "netlog.json"
        evidence = Evidence()
        target = LocalHTTPServer(("127.0.0.1", 0), Target)
        target.evidence = evidence
        target_worker = start(target)
        proxy = proxy_server(0, target.server_port, evidence)
        proxy_port = proxy.server_port
        proxy_worker = start(proxy)
        job = OwnedJob()
        process = None
        port = None
        checks: dict[str, bool] = {}
        try:
            endpoint = {"scheme": "http", "host": "127.0.0.1", "port": proxy_port}
            args = [str(chrome), "--headless=new", "--remote-debugging-address=127.0.0.1",
                    "--remote-debugging-port=0", "--remote-allow-origins=http://127.0.0.1",
                    "--no-first-run", "--no-default-browser-check",
                    "--disable-background-networking", "--disable-component-update",
                    "--disable-sync", "--disable-quic", "--metrics-recording-only",
                    f"--user-data-dir={profile}", f"--log-net-log={netlog}",
                    f"--proxy-server={proxy_endpoint(endpoint)}",
                    *bundled_proxy_privacy_arguments(endpoint), "about:blank"]
            process = spawn_owned_browser(args, root, job)
            assert process.stdin is not None
            process.stdin.write(b"G")
            process.stdin.flush()
            process.stdin.close()
            process.stdin = None
            port = debug_port(profile, process)

            def visit(token: str) -> None:
                with evidence.lock:
                    evidence.tokens.add(token)
                new_tab(port, f"http://{TEST_HOST}:{target.server_port}/probe?token={token}")

            first = uuid.uuid4().hex
            visit(first)
            checks["before_loss_through_proxy"] = wait_for_token(evidence, first, 12) == "http"
            if not checks["before_loss_through_proxy"]:
                raise Inconclusive("positive_proxy_control_missing")

            stop(proxy, proxy_worker)
            proxy = None
            proxy_worker = None
            with evidence.lock:
                prior_requests = len(evidence.requests)
            during = uuid.uuid4().hex
            visit(during)
            # A new target should fail while the proxy listener is closed.
            checks["browser_alive_during_loss"] = process.poll() is None
            checks["no_target_hit_during_loss"] = wait_for_token(evidence, during, 4) is None
            with evidence.lock:
                checks["no_other_target_hit_during_loss"] = len(evidence.requests) == prior_requests

            proxy = proxy_server(proxy_port, target.server_port, evidence)
            proxy_worker = start(proxy)
            after = uuid.uuid4().hex
            visit(after)
            checks["after_recovery_through_proxy"] = wait_for_token(evidence, after, 12) == "http"
            checks["same_browser_process"] = process.poll() is None
            with evidence.lock:
                checks["exactly_two_target_hits"] = len(evidence.requests) == 2
                checks["proxy_forwarded_two_probes"] = sum(
                    item.get("token") in {first, after} for item in evidence.forwards) == 2
        finally:
            if process is not None:
                if port is not None and process.poll() is None:
                    try:
                        close_browser(port)
                    except (OSError, ValueError, Inconclusive):
                        pass
                try:
                    process.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    job.close()
                    process.kill()
                    process.communicate(timeout=8)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream:
                        stream.close()
            job.close()
            if proxy is not None and proxy_worker is not None:
                stop(proxy, proxy_worker)
            stop(target, target_worker)
        if not netlog.is_file():
            raise Inconclusive("browser_netlog_missing")
        summary = summarize_netlog(json.loads(netlog.read_text(encoding="utf-8")))
        remote_hosts = summary["tcp_remote_hosts"]
        checks["netlog_tcp_loopback_only"] = bool(remote_hosts) and set(remote_hosts) == {"127.0.0.1"}
        checks["netlog_udp_sends_zero"] = summary["udp_send_count"] == 0
        return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
                "scope": "one Windows host, one owned browser process and synthetic profile, HTTP proxy/target on loopback only",
                "netlog_tcp_remote_hosts": sorted(remote_hosts),
                "netlog_udp_send_count": summary["udp_send_count"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or args.chrome.name.lower() != "chrome.exe" or not args.chrome.is_file():
        parser.error("Existing Windows chrome.exe is required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be a new file in an existing directory")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                       cwd=Path(__file__).resolve().parent.parent,
                                                       text=True).strip(),
              "chrome_exe_sha256": sha256(args.chrome),
              "chrome_dll_sha256": sha256(args.chrome.with_name("chrome.dll")),
              "status": "INCONCLUSIVE"}
    try:
        report.update(measure(args.chrome.resolve()))
    except Exception as error:
        report["reason_code"] = str(error) if isinstance(error, Inconclusive) else type(error).__name__
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks", {}),
                      "reason_code": report.get("reason_code")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
