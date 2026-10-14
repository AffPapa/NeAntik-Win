"""Check a disposable browser's external HTTPS and proxy paths.

The endpoint must be a consented HTTPS JSON page that returns a `userAgent`
field, such as NeAntik's no-store /api/headers. Rejecting fixtures never
forward; working HTTP CONNECT and SOCKS5 fixtures allow only the named HTTPS origin.
This proves only the observed route on this host;
it is not a DNS, IPv6, WebRTC, packet-capture or anonymity certificate.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
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
from urllib.parse import urlsplit

from browser_integration import OwnedJob, spawn_owned_browser
from native_persona_context_audit import prepare_disposable_engine
from nevision_win import bundled_proxy_privacy_arguments, proxy_endpoint
from privacy_defaults import initialize_privacy_defaults
from start_page_network_audit import RejectingProxy, summarize_netlog


class WorkingConnectProxy(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, allowed_host: str) -> None:
        super().__init__(("127.0.0.1", 0), WorkingConnectProxyHandler)
        self.allowed_host = allowed_host.lower()
        self.host_counts: Counter[str] = Counter()
        self.connected_tunnels = 0
        self.lock = threading.Lock()


class WorkingConnectProxyHandler(BaseHTTPRequestHandler):
    server: WorkingConnectProxy
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        pass

    def do_CONNECT(self) -> None:
        try:
            target = urlsplit("//" + self.path)
            host = target.hostname.lower() if target.hostname else ""
            port = target.port
            valid = (host == self.server.allowed_host and port == 443
                     and target.username is None and target.password is None
                     and not target.path and not target.query and not target.fragment)
        except ValueError:
            host, valid = "", False
        if host:
            with self.server.lock:
                self.server.host_counts[host] += 1
        if not valid:
            self.send_error(403, "Only the named HTTPS test endpoint is allowed")
            return
        try:
            upstream = socket.create_connection((host, 443), timeout=10)
        except OSError:
            self.send_error(502, "Test endpoint unavailable")
            return
        with upstream:
            with self.server.lock:
                self.server.connected_tunnels += 1
            self.send_response(200, "Connection Established")
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.close_connection = True
            self.connection.settimeout(10)
            upstream.settimeout(10)
            sockets = (self.connection, upstream)
            try:
                while True:
                    ready, _, _ = select.select(sockets, (), (), 10)
                    if not ready:
                        return
                    for source in ready:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        destination = upstream if source is self.connection else self.connection
                        destination.sendall(chunk)
            except OSError:
                return

    def do_GET(self) -> None:
        self.send_error(403, "CONNECT to the named HTTPS endpoint only")

    do_POST = do_GET


class Socks5Proxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, allowed_host: str | None = None) -> None:
        super().__init__(("127.0.0.1", 0), RejectingSocks5Handler)
        self.allowed_host = allowed_host.lower() if allowed_host else None
        self.host_counts: Counter[str] = Counter()
        self.address_types: Counter[int] = Counter()
        self.connected_tunnels = 0
        self.lock = threading.Lock()


class WorkingSocks5(Socks5Proxy):
    def __init__(self, allowed_host: str) -> None:
        super().__init__(allowed_host)


class RejectingSocks5(Socks5Proxy):
    def __init__(self) -> None:
        super().__init__()


def receive_exact(connection: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = connection.recv(length - len(data))
        if not chunk:
            raise ConnectionError("SOCKS5 peer closed")
        data.extend(chunk)
    return bytes(data)


class RejectingSocks5Handler(socketserver.BaseRequestHandler):
    server: Socks5Proxy

    def handle(self) -> None:
        client: socket.socket = self.request
        client.settimeout(5)
        try:
            version, count = receive_exact(client, 2)
            if version != 5 or not 1 <= count <= 16:
                return
            methods = receive_exact(client, count)
            if 0 not in methods:
                client.sendall(b"\x05\xff")
                return
            client.sendall(b"\x05\x00")
            version, command, reserved, address_type = receive_exact(client, 4)
            if (version, command, reserved) != (5, 1, 0):
                return
            if address_type == 3:
                length = receive_exact(client, 1)[0]
                host = receive_exact(client, length).decode("ascii").lower()
            elif address_type == 1:
                host = socket.inet_ntop(socket.AF_INET, receive_exact(client, 4))
            elif address_type == 4:
                host = socket.inet_ntop(socket.AF_INET6, receive_exact(client, 16))
            else:
                return
            port = int.from_bytes(receive_exact(client, 2), "big")
            with self.server.lock:
                self.server.host_counts[host] += 1
                self.server.address_types[address_type] += 1
            if host != self.server.allowed_host or port != 443 or address_type != 3:
                client.sendall(b"\x05\x05\x00\x01" + b"\x00" * 6)
                return
            try:
                upstream = socket.create_connection((host, port), timeout=10)
            except OSError:
                client.sendall(b"\x05\x04\x00\x01" + b"\x00" * 6)
                return
            with upstream:
                with self.server.lock:
                    self.server.connected_tunnels += 1
                client.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
                client.settimeout(10)
                upstream.settimeout(10)
                sockets = (client, upstream)
                while True:
                    ready, _, _ = select.select(sockets, (), (), 10)
                    if not ready:
                        return
                    for source in ready:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        destination = upstream if source is client else client
                        destination.sendall(chunk)
        except (OSError, ValueError, ConnectionError, UnicodeError):
            return


def response_has_expected_json(dom: bytes) -> bool:
    match = re.search(r"<pre[^>]*>(.*?)</pre>", dom.decode("utf-8", errors="replace"), re.S)
    if not match:
        return False
    try:
        value = json.loads(html.unescape(match.group(1)))
    except (ValueError, TypeError):
        return False
    return isinstance(value, dict) and isinstance(value.get("userAgent"), str)


def run_case(chrome: Path, root: Path, name: str, endpoint: str,
             proxy_port: int | None = None, proxy_scheme: str = "http") -> dict:
    profile = root / name / "Profile"
    profile.parent.mkdir(parents=True)
    if not initialize_privacy_defaults(profile):
        raise RuntimeError("Could not initialize a disposable browser profile")
    log = root / name / "netlog.json"
    arguments = [str(chrome), "--headless", "--dump-dom", "--virtual-time-budget=5000",
                 f"--user-data-dir={profile}", "--no-first-run",
                 "--no-default-browser-check", f"--log-net-log={log}"]
    if proxy_port is not None:
        proxy = {"scheme": proxy_scheme, "host": "127.0.0.1", "port": proxy_port}
        arguments.extend([f"--proxy-server={proxy_endpoint(proxy)}",
                          *bundled_proxy_privacy_arguments(proxy)])
    arguments.append(endpoint)
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = spawn_owned_browser(arguments, profile.parent, job)
        stdout, _stderr = process.communicate(input=b"G", timeout=45)
        if process.returncode != 0:
            raise RuntimeError(f"Chromium {name} exited {process.returncode}")
    finally:
        job.close()
        if process is not None and process.poll() is None:
            process.kill()
    if not log.is_file():
        raise RuntimeError(f"Chromium did not write the {name} NetLog")
    summary = summarize_netlog(json.loads(log.read_text(encoding="utf-8")))
    summary["expected_json_rendered"] = response_has_expected_json(stdout)
    return summary


def evaluate_external_route(endpoint_host: str, direct: dict,
                            proxied: dict) -> dict[str, bool]:
    return {
        "direct_endpoint_rendered": direct.get("expected_json_rendered") is True,
        "direct_endpoint_requested": direct.get("host_counts", {}).get(endpoint_host, 0) > 0,
        "proxy_endpoint_requested": proxied.get("host_counts", {}).get(endpoint_host, 0) > 0,
        "proxy_received_endpoint": proxied.get("proxy_observed_hosts", {}).get(endpoint_host, 0) > 0,
        "proxy_did_not_render_endpoint": proxied.get("expected_json_rendered") is False,
        "proxied_tcp_only_loopback": bool(proxied.get("tcp_remote_hosts"))
        and set(proxied["tcp_remote_hosts"]) == {"127.0.0.1"},
        "proxied_netlog_has_no_udp_sends": proxied.get("udp_send_count") == 0,
    }


def evaluate_socks5_route(endpoint_host: str, direct: dict,
                          proxied: dict) -> dict[str, bool]:
    checks = evaluate_external_route(endpoint_host, direct, proxied)
    checks["socks5_proxy_received_domain_name"] = (
        proxied.get("proxy_observed_hosts", {}).get(endpoint_host, 0) > 0
        and proxied.get("proxy_observed_address_types", {}).get("3", 0) > 0
    )
    return checks


def evaluate_working_connect_route(endpoint_host: str, direct: dict,
                                   proxied: dict) -> dict[str, bool]:
    remote_hosts = proxied.get("tcp_remote_hosts", {})
    return {
        "direct_endpoint_rendered": direct.get("expected_json_rendered") is True,
        "proxied_endpoint_rendered": proxied.get("expected_json_rendered") is True,
        "proxy_received_endpoint": proxied.get("proxy_observed_hosts", {}).get(endpoint_host, 0) > 0,
        "proxy_opened_tunnel": proxied.get("proxy_connected_tunnels", 0) > 0,
        "proxied_tcp_only_loopback": bool(remote_hosts) and set(remote_hosts) == {"127.0.0.1"},
        "proxied_netlog_has_no_udp_sends": proxied.get("udp_send_count") == 0,
    }


def evaluate_working_socks5_route(endpoint_host: str, direct: dict,
                                  proxied: dict) -> dict[str, bool]:
    checks = evaluate_working_connect_route(endpoint_host, direct, proxied)
    checks["socks5_proxy_received_domain_name"] = (
        proxied.get("proxy_observed_address_types", {}).get("3", 0) > 0
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chrome = args.chrome.resolve()
    endpoint = urlsplit(args.endpoint)
    if os.name != "nt" or not chrome.is_file() or chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.fragment:
        parser.error("Endpoint must be an HTTPS URL without credentials or fragment")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output path must be new and its parent must exist")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "one Windows host; consented HTTPS endpoint; allowlisted working HTTP CONNECT/SOCKS5 plus rejecting HTTP/SOCKS5 loopback proxies; no external leak certificate",
              "endpoint_host": endpoint.hostname.lower(), "cases": {}, "status": "started"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-external-route-qa-") as temporary:
            qa_root = Path(temporary)
            # A ZIP extraction drops the AppContainer read/execute ACL needed
            # by Chromium's sandbox. Prepare that ACL only on a disposable
            # engine copy, never on the verified release tree.
            chrome = prepare_disposable_engine(chrome, qa_root / "engine")
            root = qa_root / "cases"
            root.mkdir()
            report["cases"]["direct"] = run_case(chrome, root, "direct", args.endpoint)
            proxy = RejectingProxy()
            thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            thread.start()
            try:
                report["cases"]["proxy_bound"] = run_case(
                    chrome, root, "proxy-bound", args.endpoint, proxy.server_port)
                report["cases"]["proxy_bound"]["proxy_observed_hosts"] = dict(
                    sorted(proxy.host_counts.items()))
            finally:
                proxy.shutdown()
                proxy.server_close()
                thread.join(timeout=5)
            working = WorkingConnectProxy(endpoint.hostname.lower())
            working_thread = threading.Thread(target=working.serve_forever, daemon=True)
            working_thread.start()
            try:
                report["cases"]["working_connect"] = run_case(
                    chrome, root, "working-connect", args.endpoint, working.server_port)
                report["cases"]["working_connect"]["proxy_observed_hosts"] = dict(
                    sorted(working.host_counts.items()))
                report["cases"]["working_connect"]["proxy_connected_tunnels"] = working.connected_tunnels
            finally:
                working.shutdown()
                working.server_close()
                working_thread.join(timeout=5)
            socks = RejectingSocks5()
            socks_thread = threading.Thread(target=socks.serve_forever, daemon=True)
            socks_thread.start()
            try:
                report["cases"]["socks5_proxy_bound"] = run_case(
                    chrome, root, "socks5-proxy-bound", args.endpoint,
                    socks.server_address[1], "socks5")
                report["cases"]["socks5_proxy_bound"]["proxy_observed_hosts"] = dict(
                    sorted(socks.host_counts.items()))
                report["cases"]["socks5_proxy_bound"]["proxy_observed_address_types"] = {
                    str(key): value for key, value in sorted(socks.address_types.items())}
            finally:
                socks.shutdown()
                socks.server_close()
                socks_thread.join(timeout=5)
            working_socks = WorkingSocks5(endpoint.hostname.lower())
            working_socks_thread = threading.Thread(target=working_socks.serve_forever, daemon=True)
            working_socks_thread.start()
            try:
                report["cases"]["working_socks5"] = run_case(
                    chrome, root, "working-socks5", args.endpoint,
                    working_socks.server_address[1], "socks5")
                report["cases"]["working_socks5"]["proxy_observed_hosts"] = dict(
                    sorted(working_socks.host_counts.items()))
                report["cases"]["working_socks5"]["proxy_observed_address_types"] = {
                    str(key): value for key, value in sorted(working_socks.address_types.items())}
                report["cases"]["working_socks5"]["proxy_connected_tunnels"] = working_socks.connected_tunnels
            finally:
                working_socks.shutdown()
                working_socks.server_close()
                working_socks_thread.join(timeout=5)
        report["checks"] = evaluate_external_route(
            endpoint.hostname.lower(), report["cases"]["direct"], report["cases"]["proxy_bound"])
        report["socks5_checks"] = evaluate_socks5_route(
            endpoint.hostname.lower(), report["cases"]["direct"], report["cases"]["socks5_proxy_bound"])
        report["working_connect_checks"] = evaluate_working_connect_route(
            endpoint.hostname.lower(), report["cases"]["direct"], report["cases"]["working_connect"])
        report["working_socks5_checks"] = evaluate_working_socks5_route(
            endpoint.hostname.lower(), report["cases"]["direct"], report["cases"]["working_socks5"])
        report["status"] = "passed" if all([*report["checks"].values(),
                                              *report["socks5_checks"].values(),
                                              *report["working_connect_checks"].values(),
                                              *report["working_socks5_checks"].values()]) else "inconclusive"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks"),
                      "socks5_checks": report.get("socks5_checks"),
                      "working_connect_checks": report.get("working_connect_checks"),
                      "working_socks5_checks": report.get("working_socks5_checks"),
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
