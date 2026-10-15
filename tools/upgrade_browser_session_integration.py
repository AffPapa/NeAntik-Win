"""Disposable same-account Chromium session migration gate for two exact portable ZIPs.

Tests synthetic state at one loopback origin across an explicitly versioned
public-old -> candidate engine pair. It never opens real profiles or copies
secrets. This is not a packaged GUI, in-place update, or cross-machine test.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import os
from pathlib import Path
import re
import shutil
import stat
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
const token = '__TOKEN__', phase = '__PHASE__';
(async () => {
  if (phase === 'write') {
    document.cookie = 'migration_fixture=' + token + '; Max-Age=86400; SameSite=Strict; Path=/';
    localStorage.setItem('migration_fixture', token);
  }
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('NeAntikMigrationFixture', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('state');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const indexedDBState = await new Promise((resolve, reject) => {
    const transaction = db.transaction('state', phase === 'write' ? 'readwrite' : 'readonly');
    const store = transaction.objectStore('state');
    if (phase === 'write') store.put(token, 'migration_fixture');
    const request = store.get('migration_fixture');
    let value;
    request.onsuccess = () => { value = request.result; };
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => { db.close(); resolve(value === token); };
    transaction.onerror = () => reject(transaction.error);
  });
  const cache = await caches.open('nevision_qa_cache');
  const cacheKey = '/nevision-qa-cache-entry';
  if (phase === 'write') await cache.put(cacheKey, new Response(token));
  const cached = await cache.match(cacheKey);
  const cacheState = Boolean(cached && (await cached.text()) === token);
  let registration;
  if (phase === 'write') {
    registration = await navigator.serviceWorker.register('/sw.js?token=' + token, {scope: '/'});
    await navigator.serviceWorker.ready;
    registration = await navigator.serviceWorker.getRegistration('/');
  } else {
    registration = await navigator.serviceWorker.getRegistration('/');
  }
  const workerState = Boolean(registration && registration.active &&
    registration.active.scriptURL === location.origin + '/sw.js?token=' + token);
  const result = {phase, cookie: document.cookie.includes('migration_fixture=' + token),
    localStorage: localStorage.getItem('migration_fixture') === token,
    indexedDB: indexedDBState, cacheStorage: cacheState, serviceWorker: workerState,
    notification: Notification.permission, origin: location.origin, token};
  document.getElementById('result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)});
})().catch(async error => {
  await fetch('/failure?token=' + token, {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({phase, token, message: String(error).slice(0, 400)})});
});
</script></body></html>"""

SERVICE_WORKER = ("self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));\n"
                  "self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));\n")
STATE_FIELDS = ("cookie", "localStorage", "indexedDB", "cacheStorage", "serviceWorker")
PHASES = ("write", "old-read", "candidate-read")


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str):
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.token = token
        self.phase = "write"
        self.results: dict[str, dict] = {}
        self.failures: dict[str, str] = {}
        self.ready = threading.Event()
        self.page_hits: dict[str, int] = {phase: 0 for phase in PHASES}
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
            self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{self.server.token}'; worker-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'")
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
        if route and route[0] == "/sw.js":
            self.reply(200, SERVICE_WORKER.encode("utf-8"), "application/javascript; charset=utf-8")
        elif route and route[0] == "/case" and route[1].get("phase") == [self.server.phase]:
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
        if route and route[0] == "/failure":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError("Invalid failure size")
                failure = json.loads(self.rfile.read(length))
                if (not isinstance(failure, dict) or failure.get("token") != self.server.token
                        or failure.get("phase") != self.server.phase
                        or not isinstance(failure.get("message"), str)):
                    raise ValueError("Invalid failure identity")
                self.server.failures[self.server.phase] = failure["message"][:400]
                self.reply(200, b"ok")
                self.server.ready.set()
            except (ValueError, UnicodeError):
                self.reply(400, b"Invalid failure")
            return
        if not route or route[0] != "/report":
            self.reply(404, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid report size")
            result = json.loads(self.rfile.read(length))
            if (not isinstance(result, dict) or result.get("token") != self.server.token
                    or result.get("phase") != self.server.phase or self.server.phase in self.server.results
                    or any(type(result.get(field)) is not bool for field in STATE_FIELDS)
                    or result.get("notification") not in {"denied", "granted", "default"}
                    or result.get("origin") != f"http://127.0.0.1:{self.server.server_port}"):
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
from privacy_defaults import ensure_managed_download_directory, initialize_privacy_defaults
root = Path(sys.argv[2])
storage = Storage(AppPaths(root))
profiles = storage.list_profiles()
assert len(profiles) == 1
path = storage.profile_path(profiles[0]["id"])
assert path.parent == root / "Data" / "Profiles"
default = path / "Default"
fixture_state = default / "synthetic-state.txt"
if fixture_state.is_file() and not (default / "Preferences").exists():
    moved_state = path.parent.parent / ".migration-state-fixture"
    if moved_state.exists():
        raise RuntimeError("Synthetic migration-state staging path already exists")
    fixture_state.replace(moved_state)
    if any(default.iterdir()):
        moved_state.replace(fixture_state)
        raise RuntimeError("Unexpected synthetic Default contents")
    default.rmdir()
    if not initialize_privacy_defaults(path):
        moved_state.replace(fixture_state)
        raise RuntimeError("Could not prepare synthetic managed download preferences")
else:
    initialize_privacy_defaults(path)
if not ensure_managed_download_directory(path):
    raise RuntimeError("Managed download path was not recognized")
preferences = json.loads((default / "Preferences").read_text(encoding="utf-8"))
download_path = preferences.get("download", {}).get("default_directory")
expected_download_path = str((path / "Downloads").resolve())
assert download_path == expected_download_path
print(json.dumps({"profile_id": profiles[0]["id"], "path": str(path),
    "downloads_path": download_path}))
'''


def profile_path(source: Path, portable: Path) -> tuple[str, Path]:
    process = subprocess.run([sys.executable, "-c", PROFILE_PATH_WORKER, str(source), str(portable)],
                             cwd=source, capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise RuntimeError("Synthetic profile path worker failed")
    value = json.loads(process.stdout)
    path = Path(value["path"])
    if path.parent != portable / "Data" / "Profiles":
        raise RuntimeError("Synthetic profile escaped disposable Data")
    validate_profile_root(path)
    return value["profile_id"], path


def validate_profile_root(profile: Path) -> None:
    """Reject redirected portable/profile roots before any Chromium Popen."""
    profile = Path(profile)
    portable = profile.parent.parent.parent
    if (profile.parent != portable / "Data" / "Profiles"
            or not re.fullmatch(r"[0-9a-f]{32}", profile.name)):
        raise RuntimeError("unsafe_profile_path_boundary")
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for label, path in (("portable", portable), ("data", portable / "Data"),
                        ("profiles", portable / "Data" / "Profiles"),
                        ("profile", profile)):
        try:
            details = path.lstat()
        except OSError as exc:
            raise RuntimeError(f"unsafe_profile_path_missing:{label}") from exc
        attributes = getattr(details, "st_file_attributes", 0)
        if stat.S_ISLNK(details.st_mode) or (reparse_flag and attributes & reparse_flag):
            raise RuntimeError(f"unsafe_profile_path_reparse_point:{label}")
        if not stat.S_ISDIR(details.st_mode):
            raise RuntimeError(f"unsafe_profile_path_not_directory:{label}")


def grant_disposable_engine_read_access(engine: Path, disposable_root: Path) -> None:
    if engine.resolve().parent != disposable_root.resolve():
        raise RuntimeError("Engine ACL target is not inside disposable extraction")
    process = subprocess.run(["icacls.exe", str(engine), "/grant:r", "*S-1-15-2-1:(OI)(CI)RX", "/T"],
                             capture_output=True, timeout=90)
    if process.returncode:
        raise RuntimeError("AppContainer could not read disposable Engine/Chromium")


def visit(chrome: Path, profile: Path, server: FixtureServer, phase: str,
          expected_notification: str) -> dict:
    server.phase = phase
    server.ready.clear()
    url = f"http://127.0.0.1:{server.server_port}/case?token={server.token}&phase={phase}"
    arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={profile}",
                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                 "--enable-logging=stderr", "--v=1",
                 "--disable-component-update", "--disable-sync", "--disable-quic",
                 "--metrics-recording-only", "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                 f"--proxy-server=http://127.0.0.1:{server.server_port}",
                 "--proxy-bypass-list=127.0.0.1;localhost",
                 "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", url]
    job = OwnedJob()
    process = None
    try:
        validate_profile_root(profile)
        process = spawn_owned_browser(arguments, profile, job)
        started = time.monotonic()
        stdout, stderr = process.communicate(input=b"G", timeout=55)
        if process.returncode != 0:
            diagnostic = stderr.decode("utf-8", errors="replace")
            diagnostic = diagnostic.replace(server.token, "<synthetic-token>")
            diagnostic = diagnostic.replace(str(profile), "<synthetic-profile>")
            diagnostic = diagnostic.replace(str(chrome), "<synthetic-chromium>")
            error_lines = [line[-240:] for line in diagnostic.splitlines()
                           if re.search(r"(?:ERROR|FATAL|CRASH|Check failed|failed|error)", line, re.I)]
            excerpt = "\n".join(error_lines[-12:]) or diagnostic[-1600:]
            stdout_excerpt = stdout.decode("utf-8", errors="replace")[-800:]
            stdout_excerpt = stdout_excerpt.replace(server.token, "<synthetic-token>")
            stdout_excerpt = stdout_excerpt.replace(str(profile), "<synthetic-profile>")
            stdout_excerpt = stdout_excerpt.replace(str(chrome), "<synthetic-chromium>")
            result = server.results.get(phase)
            safe_result = ({field: result.get(field) for field in (*STATE_FIELDS, "notification")}
                           if isinstance(result, dict) else None)
            safe_failure = server.failures.get(phase, "").replace(server.token, "<synthetic-token>")
            raise RuntimeError(
                f"{phase}: Chromium exit {process.returncode} after {time.monotonic() - started:.3f}s; "
                f"page_hits={server.page_hits[phase]}; safe_result={safe_result}; "
                f"page_failure={safe_failure or None}; "
                f"stdout: {stdout_excerpt.strip()}; "
                f"stderr: {excerpt.strip()}")
        deadline = time.monotonic() + 5
        while job.active_count() and time.monotonic() < deadline:
            time.sleep(0.1)
        if job.active_count():
            raise RuntimeError(f"{phase}: owned Chromium descendants remained alive")
        result = server.results.get(phase)
        if not isinstance(result, dict):
            stdout_excerpt = stdout.decode("utf-8", errors="replace")[-1200:]
            stdout_excerpt = stdout_excerpt.replace(server.token, "<synthetic-token>")
            stdout_excerpt = stdout_excerpt.replace(str(profile), "<synthetic-profile>")
            stdout_excerpt = stdout_excerpt.replace(str(chrome), "<synthetic-chromium>")
            safe_failure = server.failures.get(phase, "").replace(server.token, "<synthetic-token>")
            raise RuntimeError(f"{phase}: no loopback page result after {time.monotonic() - started:.3f}s; "
                               f"page_hits={server.page_hits[phase]}; page_failure={safe_failure or None}; "
                               f"stdout: {stdout_excerpt.strip()}")
        match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
        if not match or json.loads(html.unescape(match.group(1))) != result:
            raise RuntimeError(f"{phase}: DOM and server result differ")
        if result.get("origin") != f"http://127.0.0.1:{server.server_port}":
            raise RuntimeError(f"{phase}: wrong origin")
        if any(result.get(field) is not True for field in STATE_FIELDS):
            raise RuntimeError(f"{phase}: synthetic browser state was unavailable")
        if result.get("notification") != expected_notification:
            raise RuntimeError(f"{phase}: synthetic notification permission changed")
        if server.page_hits[phase] != 1:
            raise RuntimeError(f"{phase}: expected exactly one controlled page hit")
        return {"phase": phase, "status": "passed", **{field: True for field in STATE_FIELDS},
                "notification": result["notification"],
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


def allow_notification_permission(profile: Path, origin: str) -> None:
    """Set one synthetic origin permission in a closed disposable profile."""
    preferences = profile / "Default" / "Preferences"
    details = preferences.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (not stat.S_ISREG(details.st_mode)
            or (reparse and getattr(details, "st_file_attributes", 0) & reparse)):
        raise RuntimeError("Synthetic Preferences is not a regular file")
    payload = json.loads(preferences.read_text(encoding="utf-8"))
    exceptions = (payload.setdefault("profile", {}).setdefault("content_settings", {})
                  .setdefault("exceptions", {}).setdefault("notifications", {}))
    exceptions[f"{origin},*"] = {"last_modified": "0", "setting": 1}
    preferences.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def extract_compact_archive_root(archive_path: Path, qa_root: Path, archive_root: str,
                                compact_name: str) -> Path:
    """Extract a validated single-root portable ZIP, then shorten its QA path before Chromium starts."""
    if compact_name not in {"o", "n"} or not re.fullmatch(r"[A-Za-z0-9._-]+", archive_root):
        raise RuntimeError("Invalid compact archive extraction target")
    extraction = qa_root / f"{compact_name}-extract"
    compact = qa_root / compact_name
    extraction.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extraction)
    source = extraction / archive_root
    if (source.parent.resolve() != extraction.resolve() or not source.is_dir()
            or compact.exists() or compact.is_symlink()):
        raise RuntimeError("Archive root did not match the validated portable layout")
    source.replace(compact)
    extraction.rmdir()
    return compact


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
              "coverage": "same Windows account; one synthetic loopback origin; cookies, localStorage, IndexedDB, Cache Storage, service-worker registration, site notification choice and managed Downloads path/file across two exact portable releases",
              "limitations": ["Not a packaged GUI or in-place update test", "No cross-account or cross-machine DPAPI guarantee",
                              "No extension, password, history, arbitrary-site, or actual browser-download-flow migration claim; Downloads check uses a synthetic file and production path-rebase helper",
                              "Local strict proxy/DNS setup does not prove absence of external network leakage"],
              "visits": []}
    with tempfile.TemporaryDirectory(prefix="na-") as temporary:
        qa = Path(temporary)
        old_source, new_source = qa / "source-old", qa / "source-new"
        git_source(repo, old_commit, old_source)
        git_source(repo, new_commit, new_source)
        old_portable = extract_compact_archive_root(old_zip, qa, old_root, "o")
        new_portable = extract_compact_archive_root(candidate_zip, qa, new_root, "n")
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
                                          old_profile, server, "write", "denied"))
            download_file_name = "migration-fixture-download.txt"
            download_bytes = b"synthetic browser download fixture\n"
            download_file = old_profile / "Downloads" / download_file_name
            download_file.write_bytes(download_bytes)
            download_sha256 = hashlib.sha256(download_bytes).hexdigest()
            allow_notification_permission(old_profile, f"http://127.0.0.1:{server.server_port}")
            report["visits"].append(visit(old_portable / "Engine" / "Chromium" / "chrome.exe",
                                          old_profile, server, "old-read", "granted"))
            staged_state = old_profile.parent.parent / ".migration-state-fixture"
            fixture_state = old_profile / "Default" / "synthetic-state.txt"
            if not staged_state.is_file() or fixture_state.exists():
                raise RuntimeError("Synthetic migration marker was not safely staged")
            staged_state.replace(fixture_state)
            old_digest = data_digest(old_portable)
            shutil.copytree(old_portable / "Data", new_portable / "Data", dirs_exist_ok=False)
            if data_digest(new_portable) != old_digest:
                raise RuntimeError("Copied Data differs from preserved old snapshot")
            run_worker(new_source, "upgrade", new_portable, candidate_version)
            new_id, new_profile = profile_path(new_source, new_portable)
            if new_id != old_id:
                raise RuntimeError("Upgrade changed synthetic profile identity")
            migrated_download = new_profile / "Downloads" / download_file_name
            if (not migrated_download.is_file()
                    or hashlib.sha256(migrated_download.read_bytes()).hexdigest() != download_sha256):
                raise RuntimeError("Managed Downloads fixture was lost or changed during upgrade")
            report["managed_downloads"] = {"path_rebased": True, "synthetic_file_sha256": download_sha256,
                                           "file_preserved": True}
            report["visits"].append(visit(new_portable / "Engine" / "Chromium" / "chrome.exe",
                                          new_profile, server, "candidate-read", "granted"))
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
