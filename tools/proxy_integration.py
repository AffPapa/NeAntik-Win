"""Real headless Chrome against disposable, loopback-only proxy fixtures.

Run: python tools/proxy_integration.py
Tests direct positive control, HTTP and SOCKS5 without auth, then unavailable
proxies with no DIRECT fallback, including an IPv6 loopback target. Uses
NeVision Storage/proxy_endpoint, but does not exercise the packaged GUI or
BrowserLauncher.launch. Imports the gated
Windows Job launcher from browser_integration; no existing browser is controlled.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import platform
import re
import select
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit
import uuid

from browser_integration import (APP_VERSION, AppPaths, BrowserLauncher, HarnessError, OwnedJob,
                                 REPOSITORY, Storage, await_profile_closed, check, require, spawn_owned_browser)
from nevision_win import bundled_proxy_privacy_arguments, proxy_endpoint

TEST_HOST = "nevision-qa.invalid"


class Evidence:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tokens: set[str] = set()
        self.peer_routes: dict[int, str] = {}
        self.requests: list[dict[str, Any]] = []
        self.forwards: list[dict[str, Any]] = []
        self.rejected = {"http": 0, "socks5": 0}

    def register(self, connection: socket.socket, route: str) -> int:
        port = connection.getsockname()[1]
        with self.lock:
            self.peer_routes[port] = route
        return port

    def unregister(self, port: int) -> None:
        with self.lock:
            self.peer_routes.pop(port, None)

    def token_valid(self, token: str) -> bool:
        with self.lock:
            return token in self.tokens


class QuietHTTP(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args: Any) -> None:
        pass

    def reply(self, status: int, body: bytes, mime: str = "text/plain; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class LocalIPv6HTTPServer(LocalHTTPServer):
    address_family = socket.AF_INET6


class Target(QuietHTTP):
    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        token = parse_qs(parsed.query).get("token", [""])[0]
        evidence: Evidence = self.server.evidence
        if parsed.path != "/probe" or not evidence.token_valid(token):
            self.reply(404, b"Unknown disposable probe")
            return
        with evidence.lock:
            route = evidence.peer_routes.get(self.client_address[1], "direct")
            result = {"token": token, "route": route, "user_agent": self.headers.get("User-Agent", "")}
            evidence.requests.append(result)
        body = '<!doctype html><html><head><meta charset="utf-8"><title>Local proxy QA</title></head><body><pre id="proxy-result">'
        body += html.escape(json.dumps(result)) + "</pre></body></html>"
        self.reply(200, body.encode("utf-8"), "text/html; charset=utf-8")


class HTTPProxy(QuietHTTP):
    def reject(self) -> None:
        with self.server.evidence.lock:
            self.server.evidence.rejected["http"] += 1
        self.reply(403, b"This fixture forwards only its own loopback probe")

    def do_CONNECT(self) -> None:
        self.reject()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        token = parse_qs(parsed.query).get("token", [""])[0]
        evidence: Evidence = self.server.evidence
        try:
            ipv6_target = parsed.hostname == "::1" and parsed.port == self.server.ipv6_target_port
            ipv4_target = parsed.hostname in (TEST_HOST, "127.0.0.1") and parsed.port == self.server.target_port
            valid = parsed.scheme == "http" and (ipv4_target or ipv6_target)
        except ValueError:
            valid = False
        if not valid or parsed.path != "/probe" or not evidence.token_valid(token):
            self.reject()
            return
        upstream = None
        peer_port = None
        try:
            # The URL never selects the connection destination. No external DNS,
            # arbitrary forwarding, redirect handling, or CONNECT tunnelling.
            upstream_host = "::1" if ipv6_target else "127.0.0.1"
            target_port = self.server.ipv6_target_port if ipv6_target else self.server.target_port
            upstream = socket.create_connection((upstream_host, target_port), timeout=5)
            peer_port = evidence.register(upstream, "http")
            with evidence.lock:
                evidence.forwards.append({"scheme": "http", "token": token, "target_host": parsed.hostname, "target_port": target_port})
            connection = http.client.HTTPConnection(upstream_host, target_port, timeout=5)
            connection.sock = upstream
            connection.request("GET", f"/probe?token={token}", headers={"Host": parsed.netloc, "User-Agent": self.headers.get("User-Agent", "")})
            response = connection.getresponse()
            body = response.read(32768)
            self.reply(response.status, body, response.getheader("Content-Type", "text/plain"))
            connection.close()
        except (OSError, http.client.HTTPException):
            self.reply(502, b"Local fixture upstream failed")
        finally:
            if peer_port is not None:
                evidence.unregister(peer_port)
            if upstream:
                upstream.close()


def receive_exact(connection: socket.socket, length: int) -> bytes:
    output = b""
    while len(output) < length:
        chunk = connection.recv(length - len(output))
        if not chunk:
            raise ConnectionError("SOCKS fixture peer closed")
        output += chunk
    return output


class SocksServer(socketserver.ThreadingTCPServer):
    daemon_threads = True


class SocksProxy(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        client: socket.socket = self.request
        evidence: Evidence = self.server.evidence
        upstream = None
        peer_port = None
        client.settimeout(5)
        try:
            version, count = receive_exact(client, 2)
            methods = receive_exact(client, count)
            if version != 5 or 0 not in methods:
                client.sendall(b"\x05\xff")
                return
            client.sendall(b"\x05\x00")  # No authentication, intentionally.
            version, command, reserved, address_type = receive_exact(client, 4)
            if address_type == 3:
                host = receive_exact(client, receive_exact(client, 1)[0]).decode("ascii")
            elif address_type == 1:
                host = socket.inet_ntoa(receive_exact(client, 4))
            elif address_type == 4:
                host = socket.inet_ntop(socket.AF_INET6, receive_exact(client, 16))
            else:
                raise ValueError("Unsupported SOCKS address type")
            port = int.from_bytes(receive_exact(client, 2), "big")
            ipv6_target = host == "::1" and port == self.server.ipv6_target_port
            ipv4_target = host in (TEST_HOST, "127.0.0.1") and port == self.server.target_port
            if (version, command, reserved) != (5, 1, 0) or not (ipv4_target or ipv6_target):
                with evidence.lock:
                    evidence.rejected["socks5"] += 1
                client.sendall(b"\x05\x02\x00\x01" + b"\x00" * 6)
                return
            upstream_host = "::1" if ipv6_target else "127.0.0.1"
            upstream = socket.create_connection((upstream_host, port), timeout=5)
            peer_port = evidence.register(upstream, "socks5")
            with evidence.lock:
                evidence.forwards.append({"scheme": "socks5", "target_host": host, "target_port": port, "address_type": address_type})
            client.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("127.0.0.1") + peer_port.to_bytes(2, "big"))
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                readable, _, _ = select.select([client, upstream], [], [], 1)
                for connection in readable:
                    chunk = connection.recv(65536)
                    if not chunk:
                        return
                    (upstream if connection is client else client).sendall(chunk)
        except (OSError, ValueError, ConnectionError):
            return
        finally:
            if peer_port is not None:
                evidence.unregister(peer_port)
            if upstream:
                upstream.close()


def launch(chrome: Path, storage: Storage, profile_id: str, url: str, endpoint: str | None,
           report: dict[str, Any], label: str) -> str:
    folder = storage.profile_path(profile_id).resolve()
    require(folder.parent == storage.paths.profiles.resolve(), "Disposable profile path escaped")
    storage.ensure_profile_closed(profile_id)
    arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={folder}",
                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync", "--metrics-recording-only"]
    if endpoint:
        proxy_id = storage.get_profile(profile_id)["proxy_id"]
        proxy = storage.get_proxy(proxy_id)
        require(proxy is not None, "Synthetic proxy disappeared")
        arguments.append(f"--proxy-server={endpoint}")
        arguments.extend(bundled_proxy_privacy_arguments(proxy))
    else:
        arguments.extend(["--no-proxy-server", "--disable-quic",
                          f"--host-resolver-rules=MAP {TEST_HOST} 127.0.0.1, MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE ::1"])
    arguments.append(url)
    step: dict[str, Any] = {"name": label, "profile_id": profile_id, "status": "started",
                            "arguments": [value.replace(str(storage.paths.root), "<disposable-root>") for value in arguments]}
    report["launches"].append(step)
    job = OwnedJob()
    process = None
    try:
        started = time.monotonic()
        process = spawn_owned_browser(arguments, folder, job)
        step["owned_gated_launcher_process_id"] = process.pid
        stdout, stderr = process.communicate(input=b"G", timeout=45)
        step["return_code"] = process.returncode
        step["elapsed_seconds"] = round(time.monotonic() - started, 3)
        step["stderr_excerpt"] = stderr.decode("utf-8", errors="replace").replace(str(storage.paths.root), "<disposable-root>")[-3000:]
        require(process.returncode == 0, f"{label}: Chrome exited {process.returncode}")
        deadline = time.monotonic() + 5
        while job.active_count() and time.monotonic() < deadline:
            time.sleep(0.1)
        require(job.active_count() == 0, f"{label}: own descendants failed to exit naturally")
        step["owned_job_processes_after_natural_exit"] = 0
        await_profile_closed(storage, profile_id)
        step["chromium_profile_lock_released"] = True
        step["status"] = "completed"
        return stdout.decode("utf-8", errors="replace")
    except BaseException as error:
        step["status"] = "failed"
        step["error"] = f"{type(error).__name__}: {error}"
        if process is not None and process.poll() is None:
            process.terminate()
        raise
    finally:
        job.close()
        if process:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream:
                    stream.close()


def run(report: dict[str, Any], args: argparse.Namespace) -> None:
    root = Path(tempfile.mkdtemp(prefix="nevision-proxy-integration-"))
    report["disposable_root"] = str(root)
    storage = Storage(AppPaths(root))
    chrome = Path(args.chrome).resolve() if args.chrome else BrowserLauncher(storage).resolve_browser().resolve()
    require(chrome.is_file() and chrome.name.lower() == "chrome.exe", "Installed Chrome chrome.exe is required")
    report["browser_executable"] = str(chrome)
    evidence = Evidence()
    target = LocalHTTPServer(("127.0.0.1", 0), Target)
    ipv6_target = LocalIPv6HTTPServer(("::1", 0), Target)
    proxy = LocalHTTPServer(("127.0.0.1", 0), HTTPProxy)
    socks = SocksServer(("127.0.0.1", 0), SocksProxy)
    for server in (target, ipv6_target, proxy, socks):
        server.evidence = evidence
        server.target_port = target.server_port
        server.ipv6_target_port = ipv6_target.server_port
    servers = (target, ipv6_target, proxy, socks)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    unavailable = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    unavailable.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    unavailable.bind(("127.0.0.1", 0))  # Reserved for the entire test; intentionally never listen().
    dead_port = unavailable.getsockname()[1]
    completed = False
    try:
        legs = [("direct", None, None), ("http", "http", proxy.server_port),
                ("http_loopback", "http", proxy.server_port),
                ("http_unavailable", "http", dead_port), ("socks5", "socks5", socks.server_address[1]),
                ("socks5_loopback", "socks5", socks.server_address[1]),
                ("socks5_unavailable", "socks5", dead_port),
                ("direct_v6", None, None),
                ("http_v6", "http", proxy.server_port),
                ("socks5_v6", "socks5", socks.server_address[1]),
                ("http_v6_unavailable", "http", dead_port),
                ("socks5_v6_unavailable", "socks5", dead_port),
                ("direct_after", None, None)]
        for name, scheme, port in legs:
            token = uuid.uuid4().hex
            with evidence.lock:
                evidence.tokens.add(token)
                forward_start = len(evidence.forwards)
            endpoint = None
            profile = {"name": f"Disposable proxy QA {name}"}
            if scheme:
                proxy_id = storage.save_proxy({"name": name, "scheme": scheme, "host": "127.0.0.1", "port": port})
                profile["proxy_id"] = proxy_id
                endpoint = proxy_endpoint(storage.get_proxy(proxy_id))
            profile_id = storage.save_profile(profile)
            is_ipv6 = "_v6" in name
            target_host = "::1" if is_ipv6 else "127.0.0.1" if name.endswith("_loopback") else TEST_HOST
            target_port = ipv6_target.server_port if is_ipv6 else target.server_port
            url_host = f"[{target_host}]" if is_ipv6 else target_host
            url = f"http://{url_host}:{target_port}/probe?token={token}"
            dom = launch(chrome, storage, profile_id, url, endpoint, report, name)
            with evidence.lock:
                requests = [item for item in evidence.requests if item["token"] == token]
                forwards = evidence.forwards[forward_start:]
            step = report["launches"][-1]
            step["target_requests"] = requests
            step["proxy_forwards"] = forwards
            if name.endswith("_unavailable"):
                marker = "ERR_PROXY_CONNECTION_FAILED"
                # Current headless Chrome reports failed navigations on stderr
                # and may dump an empty DOM instead of a visual error page.
                marker_in_dom = marker in dom
                marker_in_stderr = f"Page load failed: net::{marker}" in step["stderr_excerpt"]
                step["expected_error_marker_present"] = marker_in_dom or marker_in_stderr
                step["error_evidence_source"] = "dump-dom" if marker_in_dom else "headless navigation stderr" if marker_in_stderr else None
                check(report, f"{name}: Chrome reports {marker}", marker_in_dom or marker_in_stderr)
                check(report, f"{name}: target receives zero requests (no direct fallback)", len(requests) == 0)
                check(report, f"{name}: no successful target page in DOM", '<pre id="proxy-result">' not in dom)
            else:
                match = re.search(r'<pre id="proxy-result">(.*?)</pre>', dom, re.S)
                check(report, f"{name}: target DOM loaded", match is not None)
                result = json.loads(html.unescape(match.group(1)))
                expected_route = scheme or "direct"
                check(report, f"{name}: correct token and observed peer route",
                      result["token"] == token and result["route"] == expected_route and len(requests) > 0
                      and all(item["route"] == expected_route for item in requests))
                if scheme:
                    check(report, f"{name}: controlled proxy actually opened loopback upstream",
                          any(item["scheme"] == scheme and item["target_host"] == target_host for item in forwards))
                if scheme == "socks5" and target_host == TEST_HOST:
                    check(report, "SOCKS5 sends hostname to controlled proxy (remote resolution mode)",
                          any(item.get("address_type") == 3 for item in forwards))
                report["browser_user_agent"] = result["user_agent"]
        report["rejected_background_proxy_requests"] = evidence.rejected
        completed = True
    finally:
        unavailable.close()
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
        if completed:
            resolved = root.resolve()
            require(resolved.parent == Path(tempfile.gettempdir()).resolve()
                    and resolved.name.startswith("nevision-proxy-integration-") and not root.is_symlink(), "Unsafe cleanup target")
            shutil.rmtree(resolved)
            report["cleanup"] = "Removed only this run's disposable root; own browser jobs ended naturally."
        else:
            report["cleanup"] = "Disposable root retained after failure for diagnosis."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome")
    parser.add_argument("--output", type=Path, default=REPOSITORY / "docs" / "qa" / f"proxy-integration-{APP_VERSION.removesuffix('-preview')}.json")
    parser.add_argument("--overwrite-report", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.parent.is_dir() or (output.exists() and not args.overwrite_report):
        parser.error("Output parent must exist; replacing an existing report requires --overwrite-report")
    report: dict[str, Any] = {
        "format": "nevision-loopback-proxy-integration-v1", "status": "running",
        "application_version": APP_VERSION, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(), "os": platform.platform(),
        "source_sha256": hashlib.sha256((REPOSITORY / "nevision_win.py").read_bytes()).hexdigest(),
            "method": "Specified Chrome headless --dump-dom; real Storage/proxy_endpoint; new profiles; gated Windows Jobs; loopback-only target and proxy fixtures",
        "assertions": [], "launches": [],
        "limitations": [
            "Source integration, not packaged EXE or GUI/BrowserLauncher.launch wiring.",
            "Only unauthenticated HTTP and SOCKS5 to an HTTP loopback test target; HTTPS proxy/TLS CONNECT, proxy auth prompts and commercial proxies are not tested.",
            "No fingerprint, WebRTC/UDP leak, packet-capture or all-traffic anonymity claim.",
            "The source-built strict proxy flags are exercised with synthetic hostname and 127.0.0.1 URL cases; successful loopback cases must be observed via the controlled proxy.",
            "IPv6 coverage uses ::1 direct and working HTTP/SOCKS5 proxy positive controls plus unavailable IPv4 loopback proxies; it does not observe external IPv6 egress or DNS.",
            "Direct positive controls before and after negative cases verify the local target and hostname mapping work.",
            "Browser exit code zero alone is not a success signal: positive cases require target/proxy evidence; unavailable cases require the specific proxy error and zero target requests.",
            "All fixture forwarding is hardcoded to our own loopback target; external destinations/HTTP CONNECT are rejected.",
            "Arguments contain no proxy credentials; only generated profile directories and local fixture addresses.",
        ],
        "reference": "https://chromium.googlesource.com/chromium/src/+/HEAD/net/docs/proxy.md",
    }
    exit_code = 0
    try:
        run(report, args)
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "passed_assertions": sum(item["passed"] for item in report["assertions"]),
                      "launches": len(report["launches"]), "report": str(output), "error": report.get("error")}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
