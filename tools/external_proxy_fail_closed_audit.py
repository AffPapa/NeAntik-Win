"""Check a disposable browser's external HTTPS and rejecting-proxy paths.

The endpoint must be a consented HTTPS JSON page that returns a `userAgent`
field, such as NeAntik's no-store /api/headers. Both local proxy fixtures
reject every request and never forward. This proves only the observed route on this host;
it is not a DNS, IPv6, WebRTC, packet-capture or anonymity certificate.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit

from browser_integration import OwnedJob, spawn_owned_browser
from nevision_win import bundled_proxy_privacy_arguments, proxy_endpoint
from privacy_defaults import initialize_privacy_defaults
from start_page_network_audit import RejectingProxy, summarize_netlog


class RejectingSocks5(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), RejectingSocks5Handler)
        self.host_counts: Counter[str] = Counter()
        self.address_types: Counter[int] = Counter()
        self.lock = threading.Lock()


def receive_exact(connection: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = connection.recv(length - len(data))
        if not chunk:
            raise ConnectionError("SOCKS5 peer closed")
        data.extend(chunk)
    return bytes(data)


class RejectingSocks5Handler(socketserver.BaseRequestHandler):
    server: RejectingSocks5

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
            receive_exact(client, 2)
            with self.server.lock:
                self.server.host_counts[host] += 1
                self.server.address_types[address_type] += 1
            client.sendall(b"\x05\x05\x00\x01" + b"\x00" * 6)
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
              "scope": "one Windows host; consented HTTPS endpoint; rejecting loopback HTTP and SOCKS5 proxies; no external leak certificate",
              "endpoint_host": endpoint.hostname.lower(), "cases": {}, "status": "started"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-external-route-qa-") as temporary:
            root = Path(temporary)
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
        report["checks"] = evaluate_external_route(
            endpoint.hostname.lower(), report["cases"]["direct"], report["cases"]["proxy_bound"])
        report["socks5_checks"] = evaluate_socks5_route(
            endpoint.hostname.lower(), report["cases"]["direct"], report["cases"]["socks5_proxy_bound"])
        report["status"] = "passed" if all([*report["checks"].values(),
                                              *report["socks5_checks"].values()]) else "inconclusive"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks"),
                      "socks5_checks": report.get("socks5_checks"),
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
