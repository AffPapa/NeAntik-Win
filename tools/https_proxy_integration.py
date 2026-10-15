"""Isolated HTTPS-proxy TLS/CONNECT and fail-closed browser integration.

All listeners and forwarding stay on IPv4/IPv6 loopback. A new disposable
certificate, key, profile and token are made for each run; no user profile
or trust store is modified. This is a local route test, not an external leak
or anonymity test.
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
import stat
import ssl
import subprocess
import tempfile
import threading
import time
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from native_persona_context_audit import prepare_disposable_engine
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
                    "-addext", f"subjectAltName=IP:127.0.0.1,IP:::1,DNS:{TARGET_NAME}"],
                   check=True, capture_output=True, timeout=25)
    return cert, key, certificate_spki_pin(openssl, cert)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True


class TLSServer(LocalServer):
    def __init__(self, handler: type[BaseHTTPRequestHandler], cert: Path, key: Path,
                 bind_host: str = "127.0.0.1"):
        super().__init__((bind_host, 0), handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        self.socket = context.wrap_socket(self.socket, server_side=True)


class IPv6TLSServer(TLSServer):
    address_family = socket.AF_INET6


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
        # The auth case uses an IP-literal URL: if Chromium silently falls
        # back to DIRECT, this same local target is reachable and records it.
        expected_host = "127.0.0.1" if getattr(self.server, "require_auth", False) else TARGET_NAME
        expected = f"{expected_host}:{self.server.target_port}"
        if self.path != expected:
            self.send_error(403, "Local fixture allows only its own target")
            return
        if getattr(self.server, "require_auth", False):
            with self.server.observation_lock:
                self.server.auth_challenge_count += 1
            self.send_response(407, "Proxy Authentication Required")
            self.send_header("Proxy-Authenticate", 'Basic realm="NeAntik synthetic QA"')
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
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


def require_plain_profile_directory(root: Path, profile: Path) -> None:
    """Reject redirected temporary user-data roots before a browser process starts."""
    root, profile = Path(root), Path(profile)
    if profile.parent != root:
        raise RuntimeError("profile_path_boundary")
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for label, path in (("root", root), ("profile", profile)):
        try:
            details = path.lstat()
        except OSError as exc:
            raise RuntimeError(f"profile_path_missing:{label}") from exc
        attributes = getattr(details, "st_file_attributes", 0)
        if stat.S_ISLNK(details.st_mode) or (reparse_flag and attributes & reparse_flag):
            raise RuntimeError(f"profile_path_reparse_point:{label}")
        if not stat.S_ISDIR(details.st_mode):
            raise RuntimeError(f"profile_path_not_directory:{label}")


def case_arguments(chrome: Path, profile: Path, url: str, scheme: str | None,
                   proxy_port: int | None, spki_pin: str | None,
                   proxy_host: str = "127.0.0.1") -> list[str]:
    arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync", "--metrics-recording-only",
                 "--disable-quic"]
    if spki_pin:
        arguments.append(f"--ignore-certificate-errors-spki-list={spki_pin}")
    if scheme:
        assert proxy_port is not None
        proxy = {"scheme": scheme, "host": proxy_host, "port": proxy_port}
        arguments.append(f"--proxy-server={proxy_endpoint(proxy)}")
        arguments.extend(bundled_proxy_privacy_arguments(proxy))
    else:
        arguments.extend(["--no-proxy-server",
                          f"--host-resolver-rules=MAP {TARGET_NAME} 127.0.0.1, "
                          "MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"])
    arguments.append(url)
    return arguments


def run_browser_case(chrome: Path, root: Path, label: str, url: str,
                     scheme: str | None, proxy_port: int | None, spki_pin: str | None,
                     proxy_host: str = "127.0.0.1") -> dict:
    profile = root / label
    profile.mkdir()
    args = case_arguments(chrome, profile, url, scheme, proxy_port, spki_pin, proxy_host)
    job = OwnedJob()
    process = None
    try:
        require_plain_profile_directory(root, profile)
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


def evaluate_case(label: str, result: dict, hits: int, connects: int,
                  other_connects: int = 0, auth_challenges: int = 0) -> dict:
    known_cases = {"direct_before", "tls_proxy_connect", "cert_untrusted",
                   "dead_proxy_port", "tls_proxy_connect_v6", "cert_untrusted_v6",
                   "dead_proxy_port_v6", "auth_direct_control", "auth_required", "direct_after"}
    if label not in known_cases:
        raise ValueError(f"Unknown HTTPS proxy case: {label}")
    positive = label in {"direct_before", "tls_proxy_connect", "tls_proxy_connect_v6",
                         "auth_direct_control", "direct_after"}
    expected_connect = label in {"tls_proxy_connect", "tls_proxy_connect_v6"}
    checks = {
        "browser_exited": result["exit_code"] == 0,
        "owned_processes_exited": result["owned_processes_after_exit"] == 0,
        "page_state": result["page_loaded"] == positive,
        "target_requests": hits >= 1 if positive else hits == 0,
        "proxy_connect": connects >= 1 if expected_connect else connects == 0,
        "other_proxy_not_used": other_connects == 0,
        "auth_challenge": auth_challenges >= 1 if label == "auth_required" else auth_challenges == 0,
    }
    if label == "auth_required":
        checks["proxy_auth_error"] = any(
            error in result["net_errors"] for error in
            ("ERR_PROXY_AUTH_REQUESTED", "ERR_INVALID_AUTH_CREDENTIALS"))
    if label in {"cert_untrusted", "cert_untrusted_v6"}:
        checks["proxy_certificate_error"] = any(error in result["net_errors"] for error in
                                                ("ERR_PROXY_CERTIFICATE_INVALID", "ERR_CERT_AUTHORITY_INVALID"))
    if label in {"dead_proxy_port", "dead_proxy_port_v6"}:
        checks["proxy_connection_error"] = "ERR_PROXY_CONNECTION_FAILED" in result["net_errors"]
    return {"case": label, "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "target_request_count": hits, "proxy_connect_count": connects,
            "other_proxy_connect_count": other_connects,
            "auth_challenge_count": auth_challenges,
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
    auth_proxy = TLSServer(ProxyHandler, cert, key)
    auth_proxy.target_port = target.server_port
    auth_proxy.observation_lock = threading.Lock()
    auth_proxy.connect_count = 0
    auth_proxy.auth_challenge_count = 0
    auth_proxy.require_auth = True
    ipv6_proxy = IPv6TLSServer(ProxyHandler, cert, key, "::1")
    ipv6_proxy.target_port = target.server_port
    ipv6_proxy.observation_lock = threading.Lock()
    ipv6_proxy.connect_count = 0
    target_thread = start_server(target)
    proxy_thread = start_server(proxy)
    auth_proxy_thread = start_server(auth_proxy)
    ipv6_proxy_thread = start_server(ipv6_proxy)
    unavailable = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    unavailable.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    unavailable.bind(("127.0.0.1", 0))  # Reserve a port but never listen.
    dead_port = unavailable.getsockname()[1]
    unavailable_v6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    unavailable_v6.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    unavailable_v6.bind(("::1", 0))  # Reserve an IPv6 proxy endpoint without listening.
    dead_v6_port = unavailable_v6.getsockname()[1]
    url = f"https://{TARGET_NAME}:{target.server_port}/probe/{token}"
    direct_trap_url = f"https://127.0.0.1:{target.server_port}/probe/{token}"
    cases: list[dict] = []
    try:
        for label, scheme, host, port, pin in (
            ("direct_before", None, "127.0.0.1", None, spki_pin),
            ("tls_proxy_connect", "https", "127.0.0.1", proxy.server_port, spki_pin),
            ("cert_untrusted", "https", "127.0.0.1", proxy.server_port, None),
            ("dead_proxy_port", "https", "127.0.0.1", dead_port, spki_pin),
            ("tls_proxy_connect_v6", "https", "::1", ipv6_proxy.server_port, spki_pin),
            ("cert_untrusted_v6", "https", "::1", ipv6_proxy.server_port, None),
            ("dead_proxy_port_v6", "https", "::1", dead_v6_port, spki_pin),
            ("auth_direct_control", None, "127.0.0.1", None, spki_pin),
            ("auth_required", "https", "127.0.0.1", auth_proxy.server_port, spki_pin),
            ("direct_after", None, "127.0.0.1", None, spki_pin),
        ):
            with target.observation_lock:
                previous_hits = target.token_hits
            with proxy.observation_lock:
                previous_v4_connects = proxy.connect_count
            with ipv6_proxy.observation_lock:
                previous_v6_connects = ipv6_proxy.connect_count
            with auth_proxy.observation_lock:
                previous_auth_connects = auth_proxy.connect_count
                previous_auth_challenges = auth_proxy.auth_challenge_count
            case_url = direct_trap_url if label in {"auth_direct_control", "auth_required"} else url
            result = run_browser_case(chrome, root, label, case_url, scheme, port, pin, host)
            with target.observation_lock:
                hits = target.token_hits - previous_hits
            with proxy.observation_lock:
                v4_connects = proxy.connect_count - previous_v4_connects
            with ipv6_proxy.observation_lock:
                v6_connects = ipv6_proxy.connect_count - previous_v6_connects
            with auth_proxy.observation_lock:
                auth_connects = auth_proxy.connect_count - previous_auth_connects
                auth_challenges = auth_proxy.auth_challenge_count - previous_auth_challenges
            if label == "auth_required":
                selected_connects, other_connects = auth_connects, v4_connects + v6_connects
            elif host == "::1":
                selected_connects, other_connects = v6_connects, v4_connects + auth_connects
            else:
                selected_connects, other_connects = v4_connects, v6_connects + auth_connects
            cases.append(evaluate_case(label, result, hits, selected_connects,
                                       other_connects, auth_challenges))
    finally:
        unavailable.close()
        unavailable_v6.close()
        stop_server(auth_proxy, auth_proxy_thread)
        stop_server(ipv6_proxy, ipv6_proxy_thread)
        stop_server(proxy, proxy_thread)
        stop_server(target, target_thread)
    return {"status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
            "scope": "disposable IPv4/IPv6 loopback-only HTTPS proxy TLS + CONNECT; no external route claim",
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
            root = Path(folder)
            disposable_chrome = prepare_disposable_engine(chrome, root / "engine")
            if hashlib.sha256(disposable_chrome.read_bytes()).digest() != hashlib.sha256(chrome.read_bytes()).digest():
                raise RuntimeError("Disposable Chromium copy differs from the supplied portable executable")
            report = run(disposable_chrome, openssl, root)
    except Exception as error:
        report = {"status": "INCONCLUSIVE", "scope": "disposable IPv4/IPv6 loopback-only HTTPS proxy TLS + CONNECT",
                  "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                  "error_type": type(error).__name__, "error": str(error)[:250]}
    report["harness_source_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True).strip()
    report["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_statuses": [
        {"case": case["case"], "status": case["status"]} for case in report.get("cases", [])],
        "report": str(output)}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
