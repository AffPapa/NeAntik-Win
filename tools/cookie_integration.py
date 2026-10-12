"""Verify third-party-cookie blocking in real Chromium with disposable HTTPS sites.

The two *.test names resolve only to a loopback TLS server. A rejecting proxy
handles all other URLs. The certificate is generated for this test and Chromium
accepts it only in this owned headless process. The control profile explicitly
allows third-party cookies, so a blocked result has a positive comparison.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from privacy_defaults import initialize_privacy_defaults


class CookieServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str, cert: Path, key: Path):
        super().__init__(("127.0.0.1", 0), CookieHandler)
        self.token = token
        self.observations: list[dict] = []
        self.checked = threading.Event()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        self.socket = context.wrap_socket(self.socket, server_side=True)


class CookieHandler(BaseHTTPRequestHandler):
    server: CookieServer

    def log_message(self, *_args: object) -> None:
        pass

    def reply(self, body: str, *, cookie: bool = False) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", f"probe={self.server.token}; SameSite=None; Secure; Path=/")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        host = self.headers.get("Host", "").split(":", 1)[0]
        token = self.server.token
        port = self.server.server_port
        if self.path == "/top" and host == "site-a.test":
            self.reply(f"""<!doctype html><meta charset=utf-8><title>Cookie QA</title>
<pre id=result>waiting</pre><iframe id=third src='https://site-b.test:{port}/set'></iframe>
<img src='/barrier' alt='barrier'>
<script>
addEventListener('message', event => {{
  if (event.origin !== 'https://site-b.test:{port}') return;
  if (event.data === 'set') document.getElementById('third').src = 'https://site-b.test:{port}/check';
  else if (event.data === 'checked') document.getElementById('result').textContent = 'complete';
}});
</script>""")
        elif self.path == "/set" and host == "site-b.test":
            self.reply("<script>parent.postMessage('set','*')</script>", cookie=True)
        elif self.path == "/check" and host == "site-b.test":
            present = f"probe={token}" in self.headers.get("Cookie", "")
            self.server.observations.append({"host": host, "third_party_cookie_present": present})
            self.server.checked.set()
            self.reply("<script>parent.postMessage('checked','*')</script>")
        elif self.path == "/barrier" and host == "site-a.test":
            self.server.checked.wait(25)
            self.reply("done")
        else:
            self.send_error(404)


class RejectProxy(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        self.send_error(403)

    def do_CONNECT(self) -> None:
        self.send_error(403)


def run_case(chrome: Path, root: Path, cert: Path, key: Path, blocked: bool) -> dict:
    token = uuid.uuid4().hex
    server = CookieServer(token, cert, key)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    reject = ThreadingHTTPServer(("127.0.0.1", 0), RejectProxy)
    reject_thread = threading.Thread(target=reject.serve_forever, daemon=True)
    reject_thread.start()
    profile = root / ("blocked" if blocked else "allowed")
    if blocked:
        if not initialize_privacy_defaults(profile):
            raise RuntimeError("New profile privacy defaults were not created")
    else:
        default = profile / "Default"
        default.mkdir(parents=True)
        (default / "Preferences").write_text('{"profile":{"cookie_controls_mode":0}}', encoding="utf-8")
    job = OwnedJob()
    process = None
    try:
        arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                     "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                     "--disable-component-update", "--disable-sync", "--disable-quic",
                     "--ignore-certificate-errors", "--metrics-recording-only",
                     f"--host-resolver-rules=MAP site-a.test 127.0.0.1, MAP site-b.test 127.0.0.1, MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                     f"--proxy-server=http://127.0.0.1:{reject.server_port}",
                     "--proxy-bypass-list=site-a.test;site-b.test",
                     f"https://site-a.test:{server.server_port}/top"]
        process = spawn_owned_browser(arguments, root, job)
        stdout, stderr = process.communicate(input=b"G", timeout=45)
        if process.returncode != 0 or len(server.observations) != 1:
            raise RuntimeError(f"Chromium case failed: blocked={blocked}, exit={process.returncode}, observations={server.observations}, stderr={stderr.decode('utf-8', 'replace')[-450:]}")
        if b'<pre id="result">complete</pre>' not in stdout and b'<pre id=result>complete</pre>' not in stdout:
            raise RuntimeError("Top page did not complete the iframe sequence")
        return {"blocked_setting": blocked, "cookie_present": server.observations[0]["third_party_cookie_present"],
                "observations": len(server.observations), "browser_exit": process.returncode}
    finally:
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for service, worker in ((server, thread), (reject, reject_thread)):
            service.shutdown()
            service.server_close()
            worker.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output path must be new and its parent must exist")
    openssl = shutil.which("openssl") or r"C:\Program Files\Git\mingw64\bin\openssl.exe"
    if not Path(openssl).is_file():
        parser.error("OpenSSL is needed only to generate a disposable test certificate")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "scope": "two loopback HTTPS sites, self-signed test certificate, owned headless Chromium", "cases": [], "status": "started"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-cookie-qa-") as temporary:
            root = Path(temporary)
            cert, key = root / "site.crt", root / "site.key"
            subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-keyout", str(key), "-out", str(cert), "-subj", "/CN=site-a.test",
                            "-addext", "subjectAltName=DNS:site-a.test,DNS:site-b.test"],
                           check=True, capture_output=True, timeout=20)
            report["cases"].append(run_case(args.chrome, root, cert, key, False))
            report["cases"].append(run_case(args.chrome, root, cert, key, True))
        control, protected = report["cases"]
        report["status"] = "passed" if control["cookie_present"] and not protected["cookie_present"] else "inconclusive"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": report["cases"], "report": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
