"""Isolated HTTPS-proxy TLS/CONNECT and fail-closed browser integration.

All listeners and forwarding stay on 127.0.0.1. A new disposable certificate,
key, profile and token are made for each run; no user profile or trust store is
modified. This is a local route test, not an external leak or anonymity test.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import select
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from nevision_win import bundled_proxy_privacy_arguments, proxy_endpoint

TARGET_NAME = "neantik-https-proxy-qa.invalid"
TIMEOUT_SECONDS = 45


def certificate_spki_pin(openssl: str, cert: Path) -> str:
    """Return only the public-key hash; never output PEM or a private key."""
    public = subprocess.run([openssl, "x509", "-in", str(cert), "-pubkey", "-noout"],
                            check=True, capture_output=True, timeout=15).stdout
    der = subprocess.run([openssl, "pkey", "-pubin", "-outform", "DER"], input=public,
                         check=True, capture_output=True, timeout=15).stdout
    return base64.b64encode(hashlib.sha256(der).digest()).decode("ascii")


def generate_disposable_certificate(openssl: str, folder: Path) -> tuple[Path, Path, str]:
    cert, key = folder / "fixture.crt", folder / "fixture.key"
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-keyout", str(key), "-out", str(cert), "-subj", "/CN=NeAntik local QA",
                    "-addext", f"subjectAltName=IP:127.0.0.1,DNS:{TARGET_NAME}"],
                   check=True, capture_output=True, timeout=25)
    return cert, key, certificate_spki_pin(openssl, cert)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True


class TLSServer(LocalServer):
    def __init__(self, handler: type[BaseHTTPRequestHandler], cert: Path, key: Path):
        super().__init__(("127.0.0.1", 0), handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        self.socket = context.wrap_socket(self.socket, server_side=True)


class TargetHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        if self.path != f"/probe/{self.server.expected_token}":
            self.send_error(404)
            return
        with self.server.observation_lock:
            self.server.token_hits += 1
        body = b'<html><body><div id="route-ok">HTTPS target reached</div></body></html>'
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_CONNECT(self) -> None:
        expected = f"{TARGET_NAME}:{self.server.target_port}"
        if self.path != expected:
            self.send_error(403, "Local fixture allows only its own target")
            return
        with self.server.observation_lock:
            self.server.connect_count += 1
        try:
            upstream = socket.create_connection(("127.0.0.1", self.server.target_port), timeout=5)
        except OSError:
            self.send_error(502, "Local target unavailable")
            return
        try:
            self.send_response(200, "Connection Established")
            self.end_headers()
            self.wfile.flush()
            self.connection.settimeout(8)
            upstream.settimeout(8)
            peers = (self.connection, upstream)
            while True:
                readable, _, _ = select.select(peers, (), (), 8)
                if not readable:
                    break
                for source in readable:
                    chunk = source.recv(65536)
                    if not chunk:
                        return
                    (upstream if source is self.connection else self.connection).sendall(chunk)
        except (OSError, ValueError):
            pass
        finally:
            upstream.close()
            self.close_connection = True

    def do_GET(self) -> None:
        self.send_error(403, "CONNECT to the local target only")


def start_server(server: LocalServer) -> threading.Thread:
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return worker


def stop_server(server: LocalServer, worker: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)


def case_arguments(chrome: Path, profile: Path, url: str, scheme: str | None,
                   proxy_port: int | None, spki_pin: str | None) -> list[str]:
    arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync", "--metrics-recording-only",
                 "--disable-quic"]
    if spki_pin:
        arguments.append(f"--ignore-certificate-errors-spki-list={spki_pin}")
    if scheme:
        assert proxy_port is not None
        proxy = {"scheme": scheme, "host": "127.0.0.1", "port": proxy_port}
        arguments.append(f"--proxy-server={proxy_endpoint(proxy)}")
        arguments.extend(bundled_proxy_privacy_arguments(proxy))
    else:
        arguments.extend(["--no-proxy-server",
                          f"--host-resolver-rules=MAP {TARGET_NAME} 127.0.0.1, "
                          "MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"])
    arguments.append(url)
    return arguments


def run_browser_case(chrome: Path, root: Path, label: str, url: str,
                     scheme: str | None, proxy_port: int | None, spki_pin: str | None) -> dict:
    profile = root / label
    profile.mkdir()
    args = case_arguments(chrome, profile, url, scheme, proxy_port, spki_pin)
    job = OwnedJob()
    process = None
    try:
        process = spawn_owned_browser(args, profile, job)
        stdout, stderr = process.communicate(input=b"G", timeout=TIMEOUT_SECONDS)
        output = stdout.decode("utf-8", "replace")
        diagnostics = stderr.decode("utf-8", "replace")
        deadline = time.monotonic() + 5
        while job.active_count() and time.monotonic() < deadline:
            time.sleep(0.1)
        return {"case": label, "exit_code": process.returncode,
                "page_loaded": '<div id="route-ok">HTTPS target reached</div>' in output,
                "net_errors": sorted(set(re.findall(r"ERR_[A-Z_]+", diagnostics + output))),
                "owned_processes_after_exit": job.active_count()}
    finally:
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream:
                    stream.close()


def evaluate_case(label: str, result: dict, hits: int, connects: int) -> dict:
    positive = label in {"direct_before", "tls_proxy_connect", "direct_after"}
    expected_connect = label == "tls_proxy_connect"
    checks = {
        "browser_exited": result["exit_code"] == 0,
        "owned_processes_exited": result["owned_processes_after_exit"] == 0,
        "page_state": result["page_loaded"] == positive,
        "target_requests": hits >= 1 if positive else hits == 0,
        "proxy_connect": connects >= 1 if expected_connect else connects == 0,
    }
    if label == "cert_untrusted":
        checks["proxy_certificate_error"] = any(error in result["net_errors"] for error in
                                                ("ERR_PROXY_CERTIFICATE_INVALID", "ERR_CERT_AUTHORITY_INVALID"))
    if label == "dead_proxy_port":
        checks["proxy_connection_error"] = "ERR_PROXY_CONNECTION_FAILED" in result["net_errors"]
    return {"case": label, "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "target_request_count": hits, "proxy_connect_count": connects,
            "browser_exit_code": result["exit_code"], "net_errors": result["net_errors"]}


def run(chrome: Path, openssl: str, root: Path) -> dict:
    cert, key, spki_pin = generate_disposable_certificate(openssl, root)
    token = uuid.uuid4().hex
    target = TLSServer(TargetHandler, cert, key)
    target.expected_token = token
    target.observation_lock = threading.Lock()
    target.token_hits = 0
    proxy = TLSServer(ProxyHandler, cert, key)
    proxy.target_port = target.server_port
    proxy.observation_lock = threading.Lock()
    proxy.connect_count = 0
    target_thread = start_server(target)
    proxy_thread = start_server(proxy)
    unavailable = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    unavailable.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    unavailable.bind(("127.0.0.1", 0))  # Reserve a port but never listen.
    dead_port = unavailable.getsockname()[1]
    url = f"https://{TARGET_NAME}:{target.server_port}/probe/{token}"
    cases: list[dict] = []
    try:
        for label, scheme, port, pin in (
            ("direct_before", None, None, spki_pin),
            ("tls_proxy_connect", "https", proxy.server_port, spki_pin),
            ("cert_untrusted", "https", proxy.server_port, None),
            ("dead_proxy_port", "https", dead_port, spki_pin),
            ("direct_after", None, None, spki_pin),
        ):
            with target.observation_lock:
                previous_hits = target.token_hits
            with proxy.observation_lock:
                previous_connects = proxy.connect_count
            result = run_browser_case(chrome, root, label, url, scheme, port, pin)
            with target.observation_lock:
                hits = target.token_hits - previous_hits
            with proxy.observation_lock:
                connects = proxy.connect_count - previous_connects
            cases.append(evaluate_case(label, result, hits, connects))
    finally:
        unavailable.close()
        stop_server(proxy, proxy_thread)
        stop_server(target, target_thread)
    return {"status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
            "scope": "disposable loopback-only HTTPS proxy TLS + CONNECT; no external route claim",
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "chrome_sha256": hashlib.sha256(chrome.read_bytes()).hexdigest(), "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chrome = args.chrome.resolve()
    output = args.output.resolve()
    if not chrome.is_file() or chrome.name.lower() != "chrome.exe":
        parser.error("--chrome must name an existing chrome.exe")
    if output.exists() or not output.parent.is_dir():
        parser.error("--output must be a new file in an existing directory")
    openssl = shutil.which("openssl") or r"C:\Program Files\Git\mingw64\bin\openssl.exe"
    if not Path(openssl).is_file():
        parser.error("OpenSSL is required to generate a one-day disposable local certificate")
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-https-proxy-qa-") as folder:
            report = run(chrome, openssl, Path(folder))
    except Exception as error:
        report = {"status": "FAIL", "scope": "disposable loopback-only HTTPS proxy TLS + CONNECT",
                  "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                  "error_type": type(error).__name__, "error": str(error)[:250]}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_statuses": [
        {"case": case["case"], "status": case["status"]} for case in report.get("cases", [])],
        "report": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
