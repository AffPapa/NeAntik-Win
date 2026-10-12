"""Loopback-only Chromium/NeAntik storage integration, not packaged GUI QA.

Run from the repository: python tools/browser_integration.py
Uses new temporary AppPaths, real Storage, and a new headless browser process for
each visit. No existing windows, CDP, WebDriver, or personal profiles are used.
The local test page commits IndexedDB, Cache Storage and a service-worker
registration before releasing a load barrier; dump-dom and the server's
received result must agree. Background HTTP(S) is directed to a
loopback rejecting proxy, never forwarded. Chromium's sandbox remains enabled.

The report is generated evidence, not a claim about fingerprints, extensions,
proxy authentication, another Windows account, or the portable EXE's GUI.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit
import uuid
from unittest.mock import patch
import zipfile

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
from nevision_win import APP_VERSION, AppPaths, BrowserLauncher, NeVisionApp, Storage  # noqa: E402

EMPTY = {"cookie": None, "local_storage": None, "indexed_db": None,
         "indexed_db_namespace": False,
         "cache_storage": None, "cache_namespace": False, "service_worker": None}
PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=")
PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>NeVision isolated QA</title></head>
<body><pre id="nevision-result">pending</pre><img alt="load barrier" src="/barrier?token=__TOKEN__">
<script nonce="__TOKEN__">
(async () => {
  const config = __CONFIG__;
  const key = 'nevision_qa_value';
  function openDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('nevision_qa_isolation', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('values');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error('IndexedDB open blocked'));
    });
  }
  async function idb(writeValue) {
    const db = await openDB();
    try {
      return await new Promise((resolve, reject) => {
        const writing = writeValue !== undefined;
        const tx = db.transaction('values', writing ? 'readwrite' : 'readonly', {durability: 'strict'});
        const store = tx.objectStore('values');
        const request = writing ? store.put(writeValue, key) : store.get(key);
        let value = null;
        request.onsuccess = () => { if (!writing) value = request.result ?? null; };
        tx.oncomplete = () => resolve(value); // A request success alone is not a commit.
        tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction error'));
        tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
      });
    } finally { db.close(); }
  }
  async function snapshot() {
    const item = document.cookie.split('; ').find(part => part.startsWith(key + '='));
    const dbExists = (await indexedDB.databases()).some(item => item.name === 'nevision_qa_isolation');
    const cacheExists = await caches.has('nevision_qa_cache');
    const cache = cacheExists ? await caches.open('nevision_qa_cache') : null;
    const cached = cache ? await cache.match('/nevision-qa-cache-entry') : null;
    const registration = await navigator.serviceWorker.getRegistration('/');
    return {
      cookie: item ? decodeURIComponent(item.slice(key.length + 1)) : null,
      local_storage: localStorage.getItem(key),
      indexed_db: dbExists ? await idb() : null,
      indexed_db_namespace: dbExists,
      cache_storage: cached ? await cached.text() : null,
      cache_namespace: cacheExists,
      service_worker: registration ? 'registered' : null,
    };
  }
  let result;
  try {
    let versionDetails = null;
    if (navigator.userAgentData) {
      try { versionDetails = await navigator.userAgentData.getHighEntropyValues(['fullVersionList', 'platformVersion']); }
      catch (_) { /* Optional version metadata must not alter storage coverage. */ }
    }
    const before = await snapshot();
    if (config.operation === 'write') {
      document.cookie = key + '=' + encodeURIComponent(config.value) + '; Max-Age=86400; Path=/; SameSite=Lax';
      localStorage.setItem(key, config.value);
      await idb(config.value);
      const cache = await caches.open('nevision_qa_cache');
      await cache.put('/nevision-qa-cache-entry', new Response(config.value));
      await navigator.serviceWorker.register('/nevision-qa-service-worker.js?token=' + config.token, {scope: '/'});
      await navigator.serviceWorker.ready;
    }
    result = {token: config.token, operation: config.operation, before, after: await snapshot(),
      user_agent: navigator.userAgent, version_details: versionDetails, origin: location.origin, error: null};
  } catch (error) {
    result = {token: config.token, error: String(error), user_agent: navigator.userAgent, origin: location.origin};
  }
  document.getElementById('nevision-result').textContent = JSON.stringify(result);
  await fetch('/report?token=' + config.token, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(result)
  });
})();
</script></body></html>"""


class HarnessError(RuntimeError):
    pass


class LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.cases: dict[str, dict[str, Any]] = {}
        self.case_lock = threading.Lock()
        self.blocked_proxy_requests = 0

    def add_case(self, operation: str, value: str | None) -> tuple[str, str]:
        token = uuid.uuid4().hex
        with self.case_lock:
            self.cases[token] = {
                "config": {"token": token, "operation": operation, "value": value},
                "ready": threading.Event(), "result": None,
            }
        return token, f"http://127.0.0.1:{self.server_port}/case?token={token}"


class Handler(BaseHTTPRequestHandler):
    server: LoopbackServer

    def log_message(self, _format: str, *args: Any) -> None:
        pass

    def _reply(self, status: int, content: bytes, mime: str = "text/plain", nonce: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        if nonce:
            self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{nonce}'; worker-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_CONNECT(self) -> None:
        with self.server.case_lock:
            self.server.blocked_proxy_requests += 1
        self._reply(403, b"This loopback QA server never forwards requests.")

    def _case(self) -> tuple[str, dict[str, Any] | None, str]:
        url = urlsplit(self.path)
        if url.scheme or url.netloc:  # Reject background proxy traffic, do not forward it.
            with self.server.case_lock:
                self.server.blocked_proxy_requests += 1
            return "", None, ""
        token = parse_qs(url.query).get("token", [""])[0]
        with self.server.case_lock:
            return token, self.server.cases.get(token), url.path

    def do_GET(self) -> None:
        token, case, route = self._case()
        if case is None:
            self._reply(404, b"Not found")
        elif route == "/case":
            page = PAGE.replace("__TOKEN__", token).replace("__CONFIG__", json.dumps(case["config"]))
            self._reply(200, page.encode("utf-8"), "text/html; charset=utf-8", nonce=token)
        elif route == "/nevision-qa-service-worker.js":
            self._reply(200, b"self.addEventListener('install', () => self.skipWaiting());", "application/javascript; charset=utf-8")
        elif route == "/barrier":
            case["ready"].wait(25)
            self._reply(200, PIXEL, "image/png")
        else:
            self._reply(404, b"Not found")

    def do_POST(self) -> None:
        token, case, route = self._case()
        if case is None or route != "/report":
            self._reply(404, b"Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32768:
                raise ValueError("Invalid body length")
            result = json.loads(self.rfile.read(length))
            if not isinstance(result, dict) or result.get("token") != token:
                raise ValueError("Invalid result identity")
            with self.server.case_lock:
                if case["result"] is not None:
                    raise ValueError("Duplicate result")
                case["result"] = result
            self._reply(200, b"ok")
            case["ready"].set()
        except (ValueError, UnicodeError):
            self._reply(400, b"Invalid report")


class OwnedJob:
    """Windows job containing only our newly launched process and its children."""

    def __init__(self) -> None:
        self.handle = None
        if os.name != "nt":
            raise HarnessError("This Windows release integration tool requires Windows.")

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                        ("max_ws", ctypes.c_size_t), ("active_limit", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(key, ctypes.c_uint64) for key in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

        class Accounting(ctypes.Structure):
            _fields_ = [(key, ctypes.c_int64) for key in ("user", "kernel", "period_user", "period_kernel")] + [
                (key, wintypes.DWORD) for key in ("page_faults", "total_processes", "active_processes", "terminated_processes")]

        self.accounting_type = Accounting
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, arguments, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ("SetInformationJobObject", [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ("QueryInformationJobObject", [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def active_count(self) -> int:
        counters = self.accounting_type()
        if not self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(counters), ctypes.sizeof(counters), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.active_processes)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessError(message)


def state(value: str) -> dict[str, Any]:
    return {**dict.fromkeys(EMPTY, value), "indexed_db_namespace": True,
            "cache_namespace": True,
            "service_worker": "registered"}


GATED_CHROME_CODE = """import sys
if sys.stdin.buffer.read(1) != b'G':
    raise SystemExit(97)
import subprocess
result = subprocess.run(sys.argv[1:], stdin=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW)
raise SystemExit(result.returncode)
"""


def spawn_owned_browser(arguments: list[str], folder: Path, job: OwnedJob) -> subprocess.Popen[bytes]:
    """Gate Chrome creation until its isolated Python parent belongs to our Job.

    -I -S prevents user startup/site code; before the gate the helper only reads
    stdin. Chrome and every descendant therefore inherit the job from creation,
    eliminating the race of assigning an already-running Chrome to a job.
    The caller releases the gate with communicate(input=b'G').
    """
    process = subprocess.Popen([sys.executable, "-I", "-S", "-c", GATED_CHROME_CODE, *arguments],
                               cwd=str(folder), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        job.assign(process)
    except BaseException:
        process.terminate()
        process.communicate(timeout=5)
        raise
    return process


def await_profile_closed(storage: Storage, profile_id: str) -> None:
    deadline = time.monotonic() + 5
    while True:
        try:
            storage.ensure_profile_closed(profile_id)
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def visit(chrome: Path, storage: Storage, profile_id: str, server: LoopbackServer,
          operation: str, value: str | None, label: str, report: dict[str, Any]) -> dict[str, Any]:
    folder = storage.profile_path(profile_id).resolve()
    require(folder.parent == storage.paths.profiles.resolve(), "Profile escaped disposable Storage root")
    storage.ensure_profile_closed(profile_id)
    token, url = server.add_case(operation, value)
    arguments = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={folder}",
                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                 "--disable-component-update", "--disable-sync", "--disable-quic", "--metrics-recording-only",
                 f"--proxy-server=http://127.0.0.1:{server.server_port}",
                 "--proxy-bypass-list=127.0.0.1;localhost",
                 "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", url]
    process: subprocess.Popen[bytes] | None = None
    job = OwnedJob()
    started = time.monotonic()
    step: dict[str, Any] = {"name": label, "profile_id": profile_id, "operation": operation, "status": "started"}
    report["visits"].append(step)
    try:
        process = spawn_owned_browser(arguments, folder, job)
        step["owned_gated_launcher_process_id"] = process.pid
        stdout, stderr = process.communicate(input=b"G", timeout=45)
        step["return_code"] = process.returncode
        step["elapsed_seconds"] = round(time.monotonic() - started, 3)
        step["stderr_bytes"] = len(stderr)
        step["stderr_excerpt"] = stderr.decode("utf-8", errors="replace").replace(str(storage.paths.root), "<disposable-root>")[-3000:]
        require(process.returncode == 0, f"{label}: Chrome returned {process.returncode}")
        deadline = time.monotonic() + 5
        while job.active_count() and time.monotonic() < deadline:
            time.sleep(0.1)
        require(job.active_count() == 0, f"{label}: owned Chrome descendants did not exit naturally")
        step["owned_job_processes_after_natural_exit"] = 0
        await_profile_closed(storage, profile_id)
        step["chromium_profile_lock_released"] = True
        with server.case_lock:
            result = server.cases[token]["result"]
        require(isinstance(result, dict), f"{label}: no completed loopback result")
        require(result.get("error") is None, f"{label}: page error: {result.get('error')}")
        match = re.search(r'<pre id="nevision-result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
        require(match is not None, f"{label}: dump-dom has no result element")
        dom_result = json.loads(html.unescape(match.group(1)))
        require(dom_result == result, f"{label}: dump-dom disagrees with completed server result")
        require(result.get("origin") == f"http://127.0.0.1:{server.server_port}", f"{label}: wrong origin")
        require(result.get("operation") == operation, f"{label}: wrong operation")
        step["before"], step["after"] = result["before"], result["after"]
        step["dom_matches_server_result"] = True
        step["status"] = "completed"
        report["browser_user_agent"] = result["user_agent"]
        report["browser_version_details"] = result.get("version_details")
        return result
    except BaseException as error:
        step["status"] = "failed"
        step["error"] = f"{type(error).__name__}: {error}"
        if process is not None and process.poll() is None:
            # A live Popen handle refers to our exact process, not a recycled PID.
            process.terminate()
        raise
    finally:
        # The unnamed job can contain only this invocation's process descendants.
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream:
                    stream.close()


def check(report: dict[str, Any], name: str, condition: bool) -> None:
    report["assertions"].append({"name": name, "passed": bool(condition)})
    require(condition, name)


def configuration_clone(storage: Storage, source_id: str) -> tuple[str, str]:
    """Call the real clone handler with a view double, no Tk window or clicks."""
    class View:
        def __init__(self) -> None:
            self.storage = storage
            self.created_id = ""
            self.status = ""

        def selected_profile(self) -> dict[str, Any]:
            return storage.get_profile(source_id)

        def set_status(self, text: str) -> None:
            self.status = text

        def refresh_profiles(self, select_id: str) -> None:
            self.created_id = select_id

    view = View()
    with patch("nevision_win.messagebox.showerror", side_effect=HarnessError("Clone handler reported an error")):
        NeVisionApp.clone_selected(view)
    require(bool(view.created_id), "Real clone handler did not create a profile")
    return view.created_id, view.status


def run(args: argparse.Namespace, report: dict[str, Any]) -> None:
    root = Path(tempfile.mkdtemp(prefix="nevision-browser-integration-"))
    report["disposable_root"] = str(root)
    storage = Storage(AppPaths(root))
    chrome = Path(args.chrome).resolve() if args.chrome else BrowserLauncher(storage).resolve_browser().resolve()
    require(chrome.is_file() and chrome.name.lower() == "chrome.exe", "A valid Chromium/Chrome chrome.exe is required")
    report["browser_executable"] = str(chrome)
    server = LoopbackServer()
    server_thread = threading.Thread(target=server.serve_forever, name="nevision-qa-loopback", daemon=True)
    server_thread.start()
    report["loopback_origin"] = f"http://127.0.0.1:{server.server_port}"
    completed = False
    try:
        profile_a = storage.save_profile({"name": "Integration A", "group_name": "Disposable QA", "tags": "isolation", "notes": "Generated test data only"})
        profile_b = storage.save_profile({"name": "Integration B", "group_name": "Disposable QA"})
        run_token = uuid.uuid4().hex[:12]
        value_a, value_b = "A-" + run_token, "B-" + run_token
        a = visit(chrome, storage, profile_a, server, "write", value_a, "A writes all storage APIs", report)
        check(report, "A initially has no test cookie/localStorage/IndexedDB/Cache Storage/service worker", a["before"] == EMPTY)
        check(report, "A writes and reads five independent browser storage states", a["after"] == state(value_a))
        b = visit(chrome, storage, profile_b, server, "write", value_b, "B isolated write", report)
        check(report, "B cannot see A's test storage values", b["before"] == EMPTY)
        check(report, "B stores its own distinct values", b["after"] == state(value_b))
        a_again = visit(chrome, storage, profile_a, server, "read", None, "A restart persistence", report)
        check(report, "A restart retains all five states without a rewrite", a_again["before"] == a_again["after"] == state(value_a))
        b_again = visit(chrome, storage, profile_b, server, "read", None, "B restart persistence", report)
        check(report, "B restart retains its five distinct states without a rewrite", b_again["before"] == b_again["after"] == state(value_b))
        # A real non-null binding makes the restore reset assertion non-vacuous.
        # This fixture is not used by visits, which use the rejecting QA proxy.
        fixture_proxy = storage.save_proxy({"name": "Synthetic local proxy fixture", "scheme": "http",
                                            "host": "127.0.0.1", "port": server.server_port})
        source_profile = storage.get_profile(profile_a)
        storage.save_profile({**source_profile, "proxy_id": fixture_proxy}, profile_a)
        check(report, "Source A has a real proxy binding before backup", storage.get_profile(profile_a)["proxy_id"] == fixture_proxy)
        await_profile_closed(storage, profile_a)
        archive = storage.backup_profile(profile_a)
        with zipfile.ZipFile(archive) as zipped:
            manifest = json.loads(zipped.read("nevision-manifest.json"))
            names = zipped.namelist()
        report["backup"] = {"bytes": archive.stat().st_size, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                            "members": len(names), "manifest": manifest}
        check(report, "Backup accurately declares sensitive browser data without proxy credentials",
              manifest.get("browser_session_data_included") is True and manifest.get("proxy_credentials_included") is False and manifest.get("encrypted") is False)
        restored_id = storage.restore_profile(archive, "Restored integration A")
        restored_profile = storage.get_profile(restored_id)
        check(report, "Restore has a new profile ID and no proxy assignment", restored_id not in (profile_a, profile_b) and restored_profile["proxy_id"] is None)
        restored = visit(chrome, storage, restored_id, server, "read", None, "Restored A reads copied storage", report)
        check(report, "Same-machine restored profile retains five browser storage states", restored["before"] == restored["after"] == state(value_a))
        clone_id, clone_status = configuration_clone(storage, profile_a)
        clone = storage.get_profile(clone_id)
        check(report, "Configuration clone copies metadata into a new profile", clone_id not in (profile_a, profile_b, restored_id)
              and clone["group_name"] == "Disposable QA" and clone["tags"] == "isolation" and clone["proxy_id"] == fixture_proxy)
        check(report, "Configuration clone folder starts empty", not any(storage.profile_path(clone_id).iterdir()))
        clone_result = visit(chrome, storage, clone_id, server, "read", None, "Configuration-only clone is clean", report)
        check(report, "Configuration clone has no inherited browser storage state", clone_result["before"] == clone_result["after"] == EMPTY)
        report["configuration_clone"] = {"actual_handler": "NeVisionApp.clone_selected", "view": "test double, no GUI", "status_text": clone_status}
        a_final = visit(chrome, storage, profile_a, server, "read", None, "Original A remains intact", report)
        check(report, "Backup/restore/clone leave original A's values intact", a_final["before"] == a_final["after"] == state(value_a))
        for profile in storage.list_profiles():
            await_profile_closed(storage, profile["id"])
        completed = True
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        report["rejected_background_proxy_requests"] = server.blocked_proxy_requests
        if completed:
            # Exact mkdtemp root only; never accept a caller-provided deletion path.
            resolved = root.resolve()
            require(resolved.parent == Path(tempfile.gettempdir()).resolve()
                    and resolved.name.startswith("nevision-browser-integration-")
                    and not root.is_symlink(), "Disposable cleanup target failed safety validation")
            shutil.rmtree(resolved)
            report["cleanup"] = "Removed only this completed run's disposable root; all owned browser jobs exited naturally."
        else:
            report["cleanup"] = "Disposable root retained after failure for diagnosis; no personal profiles touched."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", help="Browser chrome.exe, including a staged portable Chromium; default uses normal NeAntik discovery")
    parser.add_argument("--output", type=Path, default=REPOSITORY / "docs" / "qa" / f"browser-integration-{APP_VERSION.removesuffix('-preview')}.json")
    parser.add_argument("--overwrite-report", action="store_true", help="Explicitly replace a prior generated report")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.parent.is_dir():
        parser.error("Output directory must already exist")
    if output.exists() and not args.overwrite_report:
        parser.error("Output already exists; choose another output or explicitly use --overwrite-report")
    report: dict[str, Any] = {
        "format": "nevision-browser-storage-integration-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running", "application_version": APP_VERSION,
        "source_sha256": hashlib.sha256((REPOSITORY / "nevision_win.py").read_bytes()).hexdigest(),
        "python_version": platform.python_version(), "os": platform.platform(),
        "method": "Specified Chromium/Chrome executable" if args.chrome else "Discovered browser executable",
        "browser_test_mode": "headless --dump-dom, local HTTP test page, real NeAntik Storage",
        "assertions": [], "visits": [],
        "limitations": [
            "This is source-level headless browser/storage integration, not packaged EXE, GUI, accessibility, or performance QA.",
            "Does not test fingerprint spoofing, proxy authentication, extension behavior, downloads, or real third-party accounts.",
            "Restore is tested on the same machine, OS account, Chrome binary and local origin; this does not guarantee cross-machine DPAPI/App-Bound encrypted data portability.",
            "Test values are synthetic; persistent cookies are explicitly given Max-Age, not session-only cookies.",
            "Only our loopback URL is navigated; background HTTP(S) is sent to a rejecting loopback proxy, no forwarding; no packet capture was performed.",
            "The actual configuration-clone handler uses a test view double, so visual button wiring is not covered.",
            "All browser invocations are new processes with newly created or restored disposable NeVision profiles; no existing browser is controlled.",
            "Chrome creation is gated until its isolated Python launcher has joined a dedicated Windows Job; only that job is cleaned up.",
        ],
        "reference": "https://developer.chrome.com/docs/automation-and-testing/headless",
    }
    exit_code = 0
    try:
        run(args, report)
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "passed_assertions": sum(item["passed"] for item in report["assertions"]),
                      "visits": len(report["visits"]), "report": str(output), "error": report.get("error")}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
