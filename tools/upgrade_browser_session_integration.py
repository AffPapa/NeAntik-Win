"""Disposable same-account Chromium session migration gate for two exact portable ZIPs.

Tests one synthetic loopback origin's cookie and localStorage across the bundled
an explicitly versioned public-old -> candidate engine pair. It never opens real profiles, copies secrets, or claims
cross-machine portability, extension state, service workers, or full GUI update.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid
import zipfile

from browser_integration import OwnedJob, spawn_owned_browser
from upgrade_rollback_integration import (
    data_digest, git_source, inspect_archive, run_worker, validate_release_pair,
)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Migration QA</title></head>
<body><pre id="result">pending</pre><img src="/barrier?token=__TOKEN__" alt="barrier">
<script nonce="__TOKEN__">
(async () => {
  const token = '__TOKEN__', phase = '__PHASE__';
  if (phase === 'write') {
    document.cookie = 'migration_fixture=' + token + '; Max-Age=86400; SameSite=Strict; Path=/';
    localStorage.setItem('migration_fixture', token);
  }
  const result = {phase, cookie: document.cookie.includes('migration_fixture=' + token),
    localStorage: localStorage.getItem('migration_fixture') === token,
    origin: location.origin, token};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})();
</script></body></html>"""


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str):
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.token = token
        self.phase = "write"
        self.results: dict[str, dict] = {}
        self.ready = threading.Event()
        self.page_hits: dict[str, int] = {"write": 0, "read": 0}
        self.rejected_proxy_requests = 0


class FixtureHandler(BaseHTTPRequestHandler):
    server: FixtureServer

    def log_message(self, _format: str, *args: object) -> None:
        pass

    def reply(self, status: int, content: bytes, mime: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        if mime.startswith("text/html"):
            self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{self.server.token}'; img-src 'self'; connect-src 'self'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def route(self) -> tuple[str, dict[str, list[str]]] | None:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            self.server.rejected_proxy_requests += 1
            return None
        query = parse_qs(parsed.query)
        if query.get("token") != [self.server.token]:
            return None
        return parsed.path, query

    def do_CONNECT(self) -> None:
        self.server.rejected_proxy_requests += 1
        self.reply(403, b"No external forwarding")

    def do_GET(self) -> None:
        route = self.route()
        if route and route[0] == "/case" and route[1].get("phase") == [self.server.phase]:
            self.server.page_hits[self.server.phase] += 1
            content = PAGE.replace("__TOKEN__", self.server.token).replace("__PHASE__", self.server.phase)
            self.reply(200, content.encode("utf-8"), "text/html; charset=utf-8")
        elif route and route[0] == "/barrier":
            self.server.ready.wait(25)
            self.reply(200, b"", "image/png")
        else:
            self.reply(404, b"Not found")

    def do_POST(self) -> None:
        route = self.route()
        if not route or route[0] != "/report":
            self.reply(404, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid report size")
            result = json.loads(self.rfile.read(length))
            if (not isinstance(result, dict) or result.get("token") != self.server.token
                    or result.get("phase") != self.server.phase or self.server.phase in self.server.results):
                raise ValueError("Invalid or duplicate result")
            self.server.results[self.server.phase] = result
            self.reply(200, b"ok")
            self.server.ready.set()
        except (ValueError, UnicodeError):
            self.reply(400, b"Invalid report")


PROFILE_PATH_WORKER = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from nevision_win import AppPaths, Storage
root = Path(sys.argv[2])
storage = Storage(AppPaths(root))
profiles = storage.list_profiles()
assert len(profiles) == 1
path = storage.profile_path(profiles[0]["id"]).resolve()
assert path.parent == (root / "Data" / "Profiles").resolve()
print(json.dumps({"profile_id": profiles[0]["id"], "path": str(path)}))
'''


def profile_path(source: Path, portable: Path) -> tuple[str, Path]:
    process = subprocess.run([sys.executable, "-c", PROFILE_PATH_WORKER, str(source), str(portable)],
                             cwd=source, capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise RuntimeError("Synthetic profile path worker failed")
    value = json.loads(process.stdout)
    path = Path(value["path"])
    if path.parent != (portable / "Data" / "Profiles").resolve():
        raise RuntimeError("Synthetic profile escaped disposable Data")
    return value["profile_id"], path


def grant_disposable_engine_read_access(engine: Path, disposable_root: Path) -> None:
    if engine.resolve().parent != disposable_root.resolve():
        raise RuntimeError("Engine ACL target is not inside disposable extraction")
    process = subprocess.run(["icacls.exe", str(engine), "/grant:r", "*S-1-15-2-1:(OI)(CI)RX", "/T"],
                             capture_output=True, timeout=90)
    if process.returncode:
        raise RuntimeError("AppContainer could not read disposable Engine/Chromium")


def visit(chrome: Path, profile: Path, server: FixtureServer, phase: str) -> dict:
    server.phase = phase
    server.ready.clear()
    url = f"http://127.0.0.1:{server.server_port}/case?token={server.token}&phase={phase}"
    arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync", "--disable-quic",
                 "--metrics-recording-only", "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                 f"--proxy-server=http://127.0.0.1:{server.server_port}",
                 "--proxy-bypass-list=127.0.0.1;localhost",
                 "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", url]
    job = OwnedJob()
    process = None
    try:
        process = spawn_owned_browser(arguments, profile, job)
        stdout, _stderr = process.communicate(input=b"G", timeout=55)
        if process.returncode != 0:
            raise RuntimeError(f"{phase}: Chromium exit {process.returncode}")
        deadline = time.monotonic() + 5
        while job.active_count() and time.monotonic() < deadline:
            time.sleep(0.1)
        if job.active_count():
            raise RuntimeError(f"{phase}: owned Chromium descendants remained alive")
        result = server.results.get(phase)
        if not isinstance(result, dict):
            raise RuntimeError(f"{phase}: no loopback page result")
        match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
        if not match or json.loads(html.unescape(match.group(1))) != result:
            raise RuntimeError(f"{phase}: DOM and server result differ")
        if result.get("origin") != f"http://127.0.0.1:{server.server_port}":
            raise RuntimeError(f"{phase}: wrong origin")
        if result.get("cookie") is not True or result.get("localStorage") is not True:
            raise RuntimeError(f"{phase}: synthetic browser state was unavailable")
        if server.page_hits[phase] != 1:
            raise RuntimeError(f"{phase}: expected exactly one controlled page hit")
        return {"phase": phase, "status": "passed", "cookie": True, "localStorage": True,
                "page_hits": server.page_hits[phase], "server_and_dom_agree": True}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def run(old_zip: Path, old_version: str, old_sha256: str,
        candidate_zip: Path, candidate_version: str, candidate_sha256: str) -> dict:
    if os.name != "nt":
        raise RuntimeError("This browser-session gate requires Windows")
    validate_release_pair(old_version, old_sha256, candidate_version, candidate_sha256)
    old_root, old_commit = inspect_archive(old_zip, old_sha256, old_version)
    new_root, new_commit = inspect_archive(candidate_zip, candidate_sha256, candidate_version)
    repo = Path(__file__).resolve().parents[1]
    tag = subprocess.check_output(["git", "rev-parse", f"v{old_version}^{{commit}}"], cwd=repo, text=True).strip()
    subprocess.run(["git", "merge-base", "--is-ancestor", old_commit, tag], cwd=repo, check=True)
    report = {"format": "neantik-upgrade-browser-session-v1", "status": "started",
              "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "old_version": old_version, "candidate_version": candidate_version,
              "old_zip_sha256": old_sha256.lower(), "candidate_zip_sha256": candidate_sha256.lower(),
              "old_source_commit": old_commit, "candidate_source_commit": new_commit,
              "coverage": "same Windows account; one synthetic loopback origin; cookie and localStorage in one ordinary Chromium profile",
              "limitations": ["Not a packaged GUI or in-place update test", "No cross-account or cross-machine DPAPI guarantee",
                              "No extension, service-worker, IndexedDB, cache, password, history, or real-site migration claim",
                              "Local strict proxy/DNS setup does not prove absence of external network leakage"],
              "visits": []}
    with tempfile.TemporaryDirectory(prefix="neantik-upgrade-browser-session-") as temporary:
        qa = Path(temporary)
        old_source, new_source = qa / "source-old", qa / "source-new"
        git_source(repo, old_commit, old_source)
        git_source(repo, new_commit, new_source)
        with zipfile.ZipFile(old_zip) as archive:
            archive.extractall(qa / "old")
        with zipfile.ZipFile(candidate_zip) as archive:
            archive.extractall(qa / "new")
        old_portable, new_portable = qa / "old" / old_root, qa / "new" / new_root
        for portable in (old_portable, new_portable):
            engine = portable / "Engine" / "Chromium"
            if not (engine / "chrome.exe").is_file():
                raise RuntimeError("Archive missing bundled Chromium")
            grant_disposable_engine_read_access(engine, portable / "Engine")
        run_worker(old_source, "seed", old_portable, old_version)
        old_id, old_profile = profile_path(old_source, old_portable)
        token = uuid.uuid4().hex
        server = FixtureServer(token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            report["visits"].append(visit(old_portable / "Engine" / "Chromium" / "chrome.exe",
                                          old_profile, server, "write"))
            old_digest = data_digest(old_portable)
            shutil.copytree(old_portable / "Data", new_portable / "Data", dirs_exist_ok=False)
            if data_digest(new_portable) != old_digest:
                raise RuntimeError("Copied Data differs from preserved old snapshot")
            run_worker(new_source, "upgrade", new_portable, candidate_version)
            new_id, new_profile = profile_path(new_source, new_portable)
            if new_id != old_id:
                raise RuntimeError("Upgrade changed synthetic profile identity")
            report["visits"].append(visit(new_portable / "Engine" / "Chromium" / "chrome.exe",
                                          new_profile, server, "read"))
            if data_digest(old_portable) != old_digest:
                raise RuntimeError("Candidate changed preserved old Data snapshot")
            report["preserved_old_snapshot"] = True
            report["rejected_proxy_requests"] = server.rejected_proxy_requests
            report["status"] = "passed"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-zip", type=Path, required=True)
    parser.add_argument("--old-version", required=True)
    parser.add_argument("--old-sha256", required=True)
    parser.add_argument("--candidate-zip", type=Path, required=True)
    parser.add_argument("--candidate-version", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.old_zip.resolve(strict=True), args.old_version, args.old_sha256,
                     args.candidate_zip.resolve(strict=True), args.candidate_version, args.candidate_sha256)
    except Exception as error:
        report = {"format": "neantik-upgrade-browser-session-v1", "status": "failed",
                  "error": f"{type(error).__name__}: {error}"}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
