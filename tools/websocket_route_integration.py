"""Disposable loopback-only WS/WSS routing test for a specified Chromium build.

Run with --chrome and --output (a new file outside Git). This is a browser
transport integration check, not an external DNS/UDP/IPv6 or anonymity audit.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import select
import shutil
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote, urlsplit
import uuid

from browser_integration import (AppPaths, BrowserLauncher, OwnedJob, Storage,
                                 await_profile_closed, spawn_owned_browser)
from nevision_win import bundled_proxy_privacy_arguments
from native_persona_context_audit import prepare_disposable_engine
from privacy_defaults import initialize_privacy_defaults

HOST = "nevision-qa.invalid"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def endpoint_host_port(value: str) -> tuple[str, int]:
    parsed = urlsplit("//" + value)
    if (parsed.hostname != HOST or not parsed.port or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("Proxy fixture rejects non-local target")
    return parsed.hostname, parsed.port


def recv_exact(sock: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("Peer closed")
        data += chunk
    return data


def websocket_text_frame(text: str) -> bytes:
    payload = text.encode("ascii")
    if len(payload) > 125:
        raise ValueError("Fixture frame too large")
    return bytes([0x81, len(payload)]) + payload


def certificate_spki_pin(openssl: str, cert: Path) -> str:
    """Hash only the disposable public key, never the PEM or private key."""
    public = subprocess.run([openssl, "x509", "-in", str(cert), "-pubkey", "-noout"],
                            check=True, capture_output=True, timeout=15).stdout
    der = subprocess.run([openssl, "pkey", "-pubin", "-outform", "DER"], input=public,
                         check=True, capture_output=True, timeout=15).stdout
    return base64.b64encode(hashlib.sha256(der).digest()).decode("ascii")


def read_client_text_frame(sock: socket.socket) -> str:
    first, second = recv_exact(sock, 2)
    if first != 0x81 or not second & 0x80:
        raise ValueError("Expected masked single-frame text")
    length = second & 0x7f
    if length > 125:
        raise ValueError("Fixture rejects extended payload")
    mask = recv_exact(sock, 4)
    payload = recv_exact(sock, length)
    return bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)).decode("ascii")


class Evidence:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.routes: dict[int, str] = {}
        self.observations: list[dict[str, str]] = []
        self.proxy_connections: list[str] = []

    def register(self, upstream: socket.socket, route: str) -> int:
        peer_port = upstream.getsockname()[1]
        with self.lock:
            self.routes[peer_port] = route
            self.proxy_connections.append(route)
        return peer_port

    def unregister(self, peer_port: int) -> None:
        with self.lock:
            self.routes.pop(peer_port, None)


class TargetServer(ThreadingHTTPServer):
    daemon_threads = True


class Target(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        server: TargetServer = self.server  # type: ignore[assignment]
        if self.path == f"/page/{server.token}":
            content = page_html("ws" if not server.tls else "wss", server.server_port,
                                server.token, "127.0.0.1").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if self.path != f"/socket/{server.token}" or self.headers.get("Upgrade", "").lower() != "websocket":
            self.send_error(404)
            return
        key = self.headers.get("Sec-WebSocket-Key", "")
        try:
            if len(base64.b64decode(key, validate=True)) != 16:
                raise ValueError("Invalid WebSocket key")
            accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.end_headers()
            self.connection.settimeout(8)
            message = read_client_text_frame(self.connection)
            if message != server.token:
                raise ValueError("Unexpected synthetic payload")
            with server.evidence.lock:
                route = server.evidence.routes.get(self.client_address[1], "direct")
                server.evidence.observations.append({"token": server.token, "route": route})
            self.connection.sendall(websocket_text_frame("ack:" + server.token))
        except (OSError, ValueError, UnicodeError):
            return


def tunnel(client: socket.socket, upstream: socket.socket) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        readable, _, _ = select.select([client, upstream], [], [], 0.5)
        for source in readable:
            data = source.recv(65536)
            if not data:
                return
            (upstream if source is client else client).sendall(data)


class HTTPProxyServer(ThreadingHTTPServer):
    daemon_threads = True


class HTTPProxy(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_CONNECT(self) -> None:
        server: HTTPProxyServer = self.server  # type: ignore[assignment]
        try:
            host, port = endpoint_host_port(self.path)
            if host != HOST or port != server.target_port:
                raise ValueError("Target outside fixture")
            upstream = socket.create_connection(("127.0.0.1", port), timeout=5)
            peer_port = server.evidence.register(upstream, server.route)
        except (ValueError, OSError):
            # Chromium may abandon a rejected CONNECT before reading its body.
            # A header-only denial keeps the loopback fixture quiet and strict.
            try:
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
            except OSError:
                pass
            return
        try:
            self.send_response(200, "Connection Established")
            self.end_headers()
            self.connection.settimeout(8)
            upstream.settimeout(8)
            tunnel(self.connection, upstream)
        except OSError:
            pass
        finally:
            server.evidence.unregister(peer_port)
            upstream.close()

    def do_GET(self) -> None:
        self.send_error(403)


class SocksServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False


class SocksProxy(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server: SocksServer = self.server  # type: ignore[assignment]
        client: socket.socket = self.request
        client.settimeout(8)
        upstream = None
        peer_port = None
        try:
            version, count = recv_exact(client, 2)
            methods = recv_exact(client, count)
            if version != 5 or 0 not in methods:
                client.sendall(b"\x05\xff")
                return
            client.sendall(b"\x05\x00")
            version, command, reserved, address_type = recv_exact(client, 4)
            if address_type != 3:
                raise ValueError("Only remote DNS hostname is accepted")
            host = recv_exact(client, recv_exact(client, 1)[0]).decode("ascii")
            port = int.from_bytes(recv_exact(client, 2), "big")
            if (version, command, reserved, host, port) != (5, 1, 0, HOST, server.target_port):
                raise ValueError("Target outside fixture")
            upstream = socket.create_connection(("127.0.0.1", port), timeout=5)
            peer_port = server.evidence.register(upstream, "socks5")
            client.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("127.0.0.1") + peer_port.to_bytes(2, "big"))
            tunnel(client, upstream)
        except (OSError, ValueError, UnicodeError, ConnectionError):
            return
        finally:
            if peer_port is not None:
                server.evidence.unregister(peer_port)
            if upstream is not None:
                upstream.close()


def page_html(protocol: str, port: int, token: str, host: str = HOST) -> str:
    if host not in (HOST, "127.0.0.1"):
        raise ValueError("Page fixture host escaped loopback test")
    socket_url = f"{protocol}://{host}:{port}/socket/{token}"
    page = f'''<!doctype html><meta charset="utf-8"><pre id="result">waiting</pre>
<script>
const ws = new WebSocket({json.dumps(socket_url)});
ws.onopen = () => ws.send({json.dumps(token)});
ws.onmessage = event => {{ document.getElementById('result').textContent =
  event.data === {json.dumps('ack:' + token)} ? 'ack' : 'wrong'; ws.close(); }};
ws.onerror = () => {{ document.getElementById('result').textContent = 'failed'; }};
</script>'''
    return page


def page_url(protocol: str, port: int, token: str, host: str = HOST) -> str:
    # Proxy cases use a data: document, so loading the top page never requires
    # an exception from the application's strict no-bypass proxy flags.
    return "data:text/html," + quote(page_html(protocol, port, token, host))


def cdp_frame(message: str) -> bytes:
    payload = message.encode("utf-8")
    length = len(payload)
    header = b"\x81"
    if length < 126:
        header += bytes([0x80 | length])
    elif length <= 65535:
        header += b"\xfe" + length.to_bytes(2, "big")
    else:
        header += b"\xff" + length.to_bytes(8, "big")
    mask = os.urandom(4)
    return header + mask + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))


def cdp_receive(sock: socket.socket) -> dict[str, object]:
    while True:
        first, second = recv_exact(sock, 2)
        length = second & 0x7f
        if length == 126:
            length = int.from_bytes(recv_exact(sock, 2), "big")
        elif length == 127:
            length = int.from_bytes(recv_exact(sock, 8), "big")
        if length > 1024 * 1024 or second & 0x80:
            raise ValueError("Unexpected DevTools frame")
        payload = recv_exact(sock, length)
        if first & 0xf == 9:
            sock.sendall(b"\x8a" + bytes([len(payload)]) + payload)
            continue
        if first & 0xf != 1:
            raise ValueError("Unexpected DevTools opcode")
        return json.loads(payload)


def observe_page(profile: Path, process: subprocess.Popen[bytes]) -> str:
    active = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 20
    while not active.is_file():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("Owned Chromium did not expose its local DevTools port")
        time.sleep(0.1)
    while True:
        try:
            port = int(active.read_text(encoding="ascii").splitlines()[0])
            break
        except (OSError, ValueError, IndexError):
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Local DevTools port was not readable")
            time.sleep(0.1)
    if not 0 < port < 65536:
        raise RuntimeError("Invalid local DevTools port")
    page = None
    while page is None and time.monotonic() < deadline:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request("GET", "/json/list")
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError("DevTools target listing failed")
            targets = json.loads(response.read(65536))
            page = next((item for item in targets if item.get("type") == "page"), None)
        finally:
            connection.close()
        if page is None:
            time.sleep(0.1)
    if page is None:
        raise RuntimeError("Owned Chromium page was not created")
    websocket_url = urlsplit(page["webSocketDebuggerUrl"])
    if websocket_url.hostname not in ("127.0.0.1", "localhost") or websocket_url.port != port:
        raise RuntimeError("DevTools target escaped local port")
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    sock.settimeout(5)
    try:
        nonce = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (f"GET {websocket_url.path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                   f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                   f"Sec-WebSocket-Key: {nonce}\r\nOrigin: http://127.0.0.1\r\n\r\n")
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response and len(response) < 8192:
            response += sock.recv(8192)
        if not response.startswith(b"HTTP/1.1 101 "):
            raise RuntimeError("Local DevTools WebSocket handshake failed")
        state = "waiting"
        sequence = 0
        while time.monotonic() < deadline:
            sequence += 1
            command = {"id": sequence, "method": "Runtime.evaluate", "params": {
                "expression": "document.getElementById('result')?.textContent || 'waiting'", "returnByValue": True}}
            sock.sendall(cdp_frame(json.dumps(command)))
            while True:
                message = cdp_receive(sock)
                if message.get("id") == sequence:
                    state = str(message.get("result", {}).get("result", {}).get("value", "waiting"))
                    break
            if state in ("ack", "wrong", "failed"):
                return state
            time.sleep(0.1)
        return state
    finally:
        sock.close()


def browser_arguments(chrome: Path, profile: Path, protocol: str, route: str,
                      port: int, proxy_port: int | None, token: str, spki_pin: str) -> list[str]:
    arguments = [str(chrome), "--headless", "--remote-debugging-port=0",
                 "--remote-debugging-address=127.0.0.1",
                 "--remote-allow-origins=http://127.0.0.1",
                 f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                 "--disable-background-networking", "--disable-component-update",
                 "--disable-sync", "--disable-quic", "--metrics-recording-only"]
    if spki_pin:
        arguments.append(f"--ignore-certificate-errors-spki-list={spki_pin}")
    if route == "direct":
        arguments += ["--no-proxy-server", f"--host-resolver-rules=MAP {HOST} 127.0.0.1, MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"]
    else:
        scheme = "https" if route.startswith("https") else "http" if route.startswith("http") else "socks5"
        arguments += [f"--proxy-server={scheme}://127.0.0.1:{proxy_port}"]
        arguments += bundled_proxy_privacy_arguments({"scheme": scheme, "host": "127.0.0.1", "port": proxy_port})
    # Direct is a loopback transport control. Proxy legs deliberately use a
    # synthetic hostname so DNS cannot silently connect around the proxy.
    page_scheme = "https" if protocol == "wss" else "http"
    arguments.append(f"{page_scheme}://127.0.0.1:{port}/page/{token}" if route == "direct" else
                     page_url(protocol, port, token))
    return arguments


def run_browser(chrome: Path, root: Path, protocol: str, route: str, port: int,
                proxy_port: int | None, token: str, spki_pin: str) -> tuple[str, bool]:
    storage = Storage(AppPaths(root))
    profile_id = storage.save_profile({"name": f"Disposable WebSocket QA {protocol} {route}"})
    profile = storage.profile_path(profile_id)
    storage.ensure_profile_closed(profile_id)
    if not initialize_privacy_defaults(profile):
        raise RuntimeError("Could not initialize disposable WebSocket profile defaults")
    arguments = browser_arguments(chrome, profile, protocol, route, port, proxy_port, token, spki_pin)
    job = OwnedJob()
    process = None
    try:
        BrowserLauncher(storage).ensure_profile_path_is_isolated(profile_id)
        process = spawn_owned_browser(arguments, root, job)
        if process.stdin:
            process.stdin.write(b"G")
            process.stdin.flush()
        state = observe_page(profile, process)
        return state, process.poll() is None
    finally:
        job.close()
        if process:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream:
                    stream.close()
        await_profile_closed(storage, profile_id)


def run_case(chrome: Path, root: Path, cert: Path, key: Path, spki_pin: str,
             proxy_cert: Path, proxy_key: Path, proxy_pin: str,
             protocol: str, route: str) -> dict[str, object]:
    evidence = Evidence()
    token = uuid.uuid4().hex
    target = TargetServer(("127.0.0.1", 0), Target)
    target.token, target.evidence = token, evidence
    target.tls = protocol == "wss"
    if protocol == "wss":
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        target.socket = context.wrap_socket(target.socket, server_side=True)
    proxy = HTTPProxyServer(("127.0.0.1", 0), HTTPProxy)
    proxy.target_port, proxy.evidence, proxy.route = target.server_port, evidence, "http"
    tls_proxy = HTTPProxyServer(("127.0.0.1", 0), HTTPProxy)
    tls_proxy.target_port, tls_proxy.evidence, tls_proxy.route = target.server_port, evidence, "https"
    proxy_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    proxy_context.minimum_version = ssl.TLSVersion.TLSv1_2
    proxy_context.load_cert_chain(proxy_cert, proxy_key)
    tls_proxy.socket = proxy_context.wrap_socket(tls_proxy.socket, server_side=True)
    socks = SocksServer(("127.0.0.1", 0), SocksProxy)
    socks.target_port, socks.evidence = target.server_port, evidence
    servers = (target, proxy, tls_proxy, socks)
    threads = [threading.Thread(target=item.serve_forever, daemon=True) for item in servers]
    for thread in threads:
        thread.start()
    unavailable = socket.socket()
    unavailable.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    unavailable.bind(("127.0.0.1", 0))
    try:
        proxy_port = (unavailable.getsockname()[1] if route.endswith("unavailable") else
                      proxy.server_port if route == "http" else
                      tls_proxy.server_port if route.startswith("https") else
                      socks.server_address[1] if route == "socks5" else None)
        # The target and proxy use different disposable keys. A WSS target can
        # remain pinned while the untrusted HTTPS-proxy certificate is rejected.
        pins = [spki_pin] if protocol == "wss" else []
        if route.startswith("https") and route != "https_untrusted":
            pins.append(proxy_pin)
        state, browser_alive = run_browser(chrome, root, protocol, route, target.server_port,
                                           proxy_port, token, ",".join(pins))
        with evidence.lock:
            observations = list(evidence.observations)
            connections = list(evidence.proxy_connections)
        if route.endswith(("unavailable", "untrusted")):
            passed = browser_alive and state == "failed" and not observations and not connections
        else:
            passed = (browser_alive and state == "ack" and len(observations) == 1 and
                      observations[0] == {"token": token, "route": route} and
                      (connections == [route] if route != "direct" else not connections))
        return {"transport": protocol, "route": route, "status": "PASS" if passed else "FAIL",
                "dom_state": state, "target_observations": len(observations),
                "observed_route": observations[0]["route"] if observations else None,
                "proxy_connections": len(connections), "browser_alive_during_observation": browser_alive}
    finally:
        unavailable.close()
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source_chrome = args.chrome.resolve()
    chrome = source_chrome
    output = args.output.resolve()
    if not chrome.is_file() or chrome.name.lower() != "chrome.exe":
        parser.error("--chrome must be an existing chrome.exe")
    if output.exists() or not output.parent.is_dir():
        parser.error("--output must be a new file in an existing directory")
    openssl = shutil.which("openssl") or r"C:\Program Files\Git\mingw64\bin\openssl.exe"
    if not Path(openssl).is_file():
        parser.error("OpenSSL is needed for disposable WSS certificate generation")
    report: dict[str, object] = {"scope": "loopback-only synthetic WS/WSS proxy routes",
                                 "browser_sha256": hashlib.sha256(chrome.read_bytes()).hexdigest(),
                                 "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                 "started_at_utc": datetime.now(timezone.utc).isoformat(), "cases": [],
                                 "limitations": ["Headless source integration, not GUI or packaged launcher",
                                                 "No external DNS, UDP, IPv6 or network-anonymity claim",
                                                 "Self-signed WSS certificate accepted only by its SPKI hash in owned test process",
                                                 "Unauthenticated loopback proxies only"]}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-ws-route-qa-") as temporary:
            root = Path(temporary)
            if not (source_chrome.parent / "ENGINE_PROVENANCE.json").is_file():
                raise RuntimeError("Portable engine provenance is required; installed Chrome is not equivalent")
            source_hash = hashlib.sha256(source_chrome.read_bytes()).hexdigest()
            chrome = prepare_disposable_engine(source_chrome, root / "engine")
            prepared_hash = hashlib.sha256(chrome.read_bytes()).hexdigest()
            if prepared_hash != source_hash:
                raise RuntimeError("Disposable ACL-prepared engine executable hash changed")
            report["source_chrome_sha256"] = source_hash
            report["prepared_chrome_sha256"] = prepared_hash
            report["disposable_engine_acl_prepared"] = True
            cert, key = root / "fixture.crt", root / "fixture.key"
            subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-keyout", str(key), "-out", str(cert), "-subj", f"/CN={HOST}",
                            "-addext", f"subjectAltName=DNS:{HOST}"],
                           check=True, capture_output=True, timeout=20)
            spki_pin = certificate_spki_pin(openssl, cert)
            proxy_cert, proxy_key = root / "proxy.crt", root / "proxy.key"
            subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-keyout", str(proxy_key), "-out", str(proxy_cert),
                            "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                           check=True, capture_output=True, timeout=20)
            proxy_pin = certificate_spki_pin(openssl, proxy_cert)
            for protocol in ("ws", "wss"):
                for route in ("direct", "http", "socks5", "https", "http_unavailable",
                              "socks5_unavailable", "https_unavailable", "https_untrusted"):
                    report["cases"].append(run_case(chrome, root, cert, key, spki_pin,
                                                    proxy_cert, proxy_key, proxy_pin, protocol, route))
        report["status"] = "PASS" if all(item["status"] == "PASS" for item in report["cases"]) else "FAIL"
    except Exception as exc:
        report["status"] = "INCONCLUSIVE"
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "passed": sum(item["status"] == "PASS" for item in report["cases"]),
                      "cases": len(report["cases"]), "report": str(output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
