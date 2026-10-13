"""Local V5 candidate gate: Canvas context scope and renderer argv transport.

Three tokenized loopback pages run in one owned browser: two in its default
BrowserContext and one in a new CDP BrowserContext. They measure main-frame,
iframe, and worker Canvas readback. Win32_Process queries only descendants of
the owned launcher; raw command lines and Canvas values stay in memory.

Run only after building the candidate Chromium core:
  python tools/canvas_mojo_gate.py --chrome C:\\path\\chrome.exe --output C:\\private\\new-report.json

This is one-host functional evidence, not a network anonymity guarantee.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid

from browser_integration import OwnedJob, spawn_owned_browser
from native_canvas_v4_context_gate import (CONTEXTS, TOP_LEVEL_SITE_CONTEXTS,
                                            SURFACES, ContextServer, validate_session)
from start_page_network_audit import RejectingProxy
from websocket_route_integration import cdp_frame, cdp_receive


class Inconclusive(RuntimeError):
    """A measurement or trusted process observation was unavailable."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def harness_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"],
                            cwd=Path(__file__).resolve().parent.parent,
                            capture_output=True, text=True, timeout=5, check=False)
    value = result.stdout.strip()
    if result.returncode != 0 or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise Inconclusive("harness_source_commit_unavailable")
    return value


class ProbeGroup:
    def __init__(self) -> None:
        token = uuid.uuid4().hex
        self.token = token
        config: dict = {"token": token}
        self.servers = [ContextServer("127.0.0.1", token, "main", config),
                        ContextServer("127.0.0.1", token, "frame", config),
                        ContextServer("localhost", token, "frame", config)]
        main, same, cross = self.servers
        origin = f"http://127.0.0.1:{main.server_port}"
        config.update({"parentOrigin": origin,
                       "sameSiteOrigin": f"http://127.0.0.1:{same.server_port}",
                       "crossSiteOrigin": f"http://localhost:{cross.server_port}",
                       "sameSiteUrl": f"http://127.0.0.1:{same.server_port}/frame?token={token}",
                       "crossSiteUrl": f"http://localhost:{cross.server_port}/frame?token={token}",
                       "workerUrl": f"/canvas-worker.js?token={token}"})
        self.url = f"{origin}/main?token={token}"
        self.workers: list[threading.Thread] = []

    def start(self) -> None:
        self.workers = [threading.Thread(target=server.serve_forever, daemon=True)
                        for server in self.servers]
        for worker in self.workers:
            worker.start()

    def result(self, process: subprocess.Popen[bytes]) -> dict:
        if not self.servers[0].ready.wait(75):
            raise Inconclusive("loopback_canvas_report_timeout")
        if process.poll() is not None:
            raise Inconclusive("browser_exited_during_canvas_probe")
        report = self.servers[0].result
        return validate_session(report)

    def stop(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for worker in self.workers:
            worker.join(timeout=5)


def debug_port(profile: Path, process: subprocess.Popen[bytes]) -> int:
    marker = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise Inconclusive("browser_exited_before_devtools")
        try:
            port = int(marker.read_text(encoding="ascii").splitlines()[0])
            if 0 < port < 65536:
                return port
        except (OSError, ValueError, IndexError):
            pass
        time.sleep(0.1)
    raise Inconclusive("local_devtools_port_missing")


class BrowserCDP:
    def __init__(self, port: int) -> None:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", "/json/version")
            response = connection.getresponse()
            if response.status != 200:
                raise Inconclusive("local_devtools_version_failed")
            address = urlsplit(json.loads(response.read(65536))["webSocketDebuggerUrl"])
        finally:
            connection.close()
        if address.hostname not in ("127.0.0.1", "localhost") or address.port != port:
            raise Inconclusive("devtools_endpoint_not_loopback")
        self.peer = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.peer.settimeout(10)
        self.sequence = 0
        nonce = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (f"GET {address.path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                     "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                     "Sec-WebSocket-Version: 13\r\n"
                     f"Sec-WebSocket-Key: {nonce}\r\nOrigin: http://127.0.0.1\r\n\r\n")
        self.peer.sendall(handshake.encode("ascii"))
        header = b""
        while b"\r\n\r\n" not in header and len(header) < 8192:
            block = self.peer.recv(8192)
            if not block:
                break
            header += block
        if not header.startswith(b"HTTP/1.1 101 "):
            self.close()
            raise Inconclusive("browser_devtools_websocket_rejected")

    def command(self, method: str, params: dict | None = None,
                session_id: str | None = None) -> dict:
        self.sequence += 1
        sequence = self.sequence
        request = {"id": sequence, "method": method, "params": params or {}}
        if session_id is not None:
            request["sessionId"] = session_id
        self.peer.sendall(cdp_frame(json.dumps(request)))
        while True:
            message = cdp_receive(self.peer)
            if message.get("id") == sequence:
                if "error" in message or not isinstance(message.get("result"), dict):
                    raise Inconclusive("browser_devtools_command_failed")
                return message["result"]

    def close(self) -> None:
        self.peer.close()


def keep_workers_alive(cdp: BrowserCDP, target_id: str, group: ProbeGroup) -> None:
    attached = cdp.command("Target.attachToTarget", {"targetId": target_id,
                                                      "flatten": True})
    session = attached.get("sessionId")
    if not isinstance(session, str) or not session:
        raise Inconclusive("worker_page_cdp_session_missing")
    worker_url = f"/canvas-worker.js?token={group.token}"
    # The existing fixture replies with a Canvas measurement, then keeps the
    # worker alive until its owner releases it or the owned browser closes.
    expression = f"""(async () => {{
      const url = {json.dumps(worker_url)};
      globalThis.__qaDedicated = new Worker(url);
      globalThis.__qaShared = new SharedWorker(url, {{name: 'mojo-argv-' + {json.dumps(group.token)}}});
      globalThis.__qaShared.port.start();
      const dedicated = new Promise((resolve, reject) => {{
        const timer = setTimeout(() => reject(Error('worker timeout')), 10000);
        __qaDedicated.onmessage = event => {{ clearTimeout(timer); resolve(event.data); }};
        __qaDedicated.onerror = () => {{ clearTimeout(timer); reject(Error('worker error')); }};
        __qaDedicated.postMessage(null);
      }});
      const shared = new Promise((resolve, reject) => {{
        const timer = setTimeout(() => reject(Error('shared worker timeout')), 10000);
        __qaShared.port.onmessage = event => {{ clearTimeout(timer); resolve(event.data); }};
        __qaShared.port.postMessage(null);
      }});
      const values = await Promise.all([dedicated, shared]);
      return values.every(item => item && Number.isInteger(item.pixelHash) &&
        Number.isInteger(item.pngHash)) ? 'ready' : 'invalid';
    }})()"""
    response = cdp.command("Runtime.evaluate", {"expression": expression,
                                                "awaitPromise": True,
                                                "returnByValue": True}, session)
    if response.get("exceptionDetails") or response.get("result", {}).get("value") != "ready":
        raise Inconclusive("active_workers_not_confirmed")


def owned_chromium_command_lines(parent_pid: int, chrome: Path) -> dict[str, int | bool]:
    """Inspect only descendants of our helper; never print or persist argv."""
    script = r'''
$ErrorActionPreference = 'Stop'
$pending = [System.Collections.Generic.Queue[int]]::new()
$pending.Enqueue(__PARENT_PID__)
$seen = [System.Collections.Generic.HashSet[int]]::new()
$records = [System.Collections.Generic.List[object]]::new()
while ($pending.Count -gt 0) {
    $parentPid = $pending.Dequeue()
    foreach ($item in @(Get-CimInstance -ClassName Win32_Process -Filter "ParentProcessId = $parentPid" -Property ProcessId,Name,ExecutablePath,CommandLine)) {
        $childPid = [int]$item.ProcessId
        if ($childPid -gt 0 -and $seen.Add($childPid)) {
            $records.Add([pscustomobject]@{Name=$item.Name; Path=$item.ExecutablePath; CommandLine=$item.CommandLine})
            if ($records.Count -gt 100) { throw 'Unexpected owned process count' }
            $pending.Enqueue($childPid)
        }
    }
}
ConvertTo-Json -InputObject @($records.ToArray()) -Compress -Depth 3
'''
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                             script.replace("__PARENT_PID__", str(int(parent_pid)))],
                            capture_output=True, timeout=25, check=False)
    if result.returncode != 0:
        raise Inconclusive("owned_process_query_failed")
    try:
        records = json.loads(result.stdout.decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        raise Inconclusive("owned_process_query_invalid") from None
    if not isinstance(records, list):
        raise Inconclusive("owned_process_query_incomplete")
    expected = os.path.normcase(os.path.abspath(chrome))
    chromium = [item for item in records if isinstance(item, dict)
                and isinstance(item.get("Path"), str)
                and os.path.normcase(os.path.abspath(item["Path"])) == expected]
    if not chromium or any(not isinstance(item.get("CommandLine"), str) for item in chromium):
        raise Inconclusive("owned_chromium_argv_unavailable")
    renderers = [item for item in chromium if "--type=renderer" in item["CommandLine"]]
    if not renderers:
        raise Inconclusive("owned_renderer_argv_unavailable")
    forbidden = "neantik-canvas-session-key"
    return {"chromium_processes_inspected": len(chromium),
            "renderer_processes_inspected": len(renderers),
            "canvas_session_key_absent_from_owned_chromium_argv": all(
                forbidden not in item["CommandLine"] for item in chromium)}


def _same(left: dict, right: dict, contexts: tuple[str, ...]) -> bool:
    return all(left[name][surface] == right[name][surface]
               for name in contexts for surface in SURFACES)


def _different(left: dict, right: dict, contexts: tuple[str, ...]) -> bool:
    return all(left[name][surface] != right[name][surface]
               for name in contexts for surface in SURFACES)


def close_owned_session(cdp: BrowserCDP | None, job: OwnedJob | None,
                        process: subprocess.Popen[bytes] | None) -> None:
    if cdp is not None:
        try:
            cdp.command("Browser.close")
        except (OSError, ValueError, Inconclusive):
            pass
        cdp.close()
    if job is not None:
        job.close()
    if process is not None:
        try:
            process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=8)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                stream.close()


def measure(chrome: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="neantik-canvas-mojo-qa-") as temporary:
        root = Path(temporary)
        profile = root / "synthetic-profile"
        groups = [ProbeGroup() for _ in range(3)]
        reject = RejectingProxy()
        reject_thread = threading.Thread(target=reject.serve_forever, daemon=True)
        for group in groups:
            group.start()
        reject_thread.start()
        job = None
        process = None
        cdp = None
        try:
            job = OwnedJob()
            args = [str(chrome), "--headless=new", f"--user-data-dir={profile}",
                    "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                    "--remote-allow-origins=http://127.0.0.1", "--no-first-run",
                    "--no-default-browser-check", "--disable-background-networking",
                    "--disable-component-update", "--disable-sync", "--disable-quic",
                    "--metrics-recording-only",
                    f"--proxy-server=http://127.0.0.1:{reject.server_port}",
                    "--proxy-bypass-list=127.0.0.1;localhost",
                    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
                    "--neantik-fingerprint-seed=1597331", groups[0].url]
            process = spawn_owned_browser(args, root, job)
            assert process.stdin is not None
            process.stdin.write(b"G")
            process.stdin.flush()
            process.stdin.close()
            process.stdin = None
            first = groups[0].result(process)
            cdp = BrowserCDP(debug_port(profile, process))
            normal_target = cdp.command("Target.createTarget", {"url": groups[1].url})
            if not isinstance(normal_target.get("targetId"), str):
                raise Inconclusive("second_default_context_target_missing")
            second = groups[1].result(process)
            context = cdp.command("Target.createBrowserContext").get("browserContextId")
            if not isinstance(context, str) or not context:
                raise Inconclusive("new_browser_context_missing")
            isolated_target = cdp.command("Target.createTarget",
                                          {"url": groups[2].url, "browserContextId": context})
            if not isinstance(isolated_target.get("targetId"), str):
                raise Inconclusive("isolated_context_target_missing")
            isolated = groups[2].result(process)
            if any(entry.get("unavailable") is True
                   for result in (first, second, isolated) for entry in result.values()):
                raise Inconclusive("canvas_context_unavailable")
            keep_workers_alive(cdp, normal_target["targetId"], groups[1])
            argv = owned_chromium_command_lines(process.pid, chrome)
            if process.poll() is not None:
                raise Inconclusive("browser_exited_before_process_inspection")
            checks = {
                "all_three_context_reports_complete": True,
                "all_iframe_and_worker_readbacks_match_own_main": all(
                    _same(result, {name: result["main"] for name in CONTEXTS},
                          TOP_LEVEL_SITE_CONTEXTS)
                    for result in (first, second, isolated)),
                "same_browser_context_stable_on_same_site": _same(first, second, CONTEXTS),
                "different_browser_context_distinct_on_same_site": _different(
                    first, isolated, CONTEXTS),
                "canvas_session_key_absent_from_owned_chromium_argv": argv[
                    "canvas_session_key_absent_from_owned_chromium_argv"],
                "dedicated_and_shared_workers_active_at_argv_snapshot": True,
            }
            # Close the first browser before resetting the one-shot probe. The
            # second launch uses the exact same URL/site and a fresh user-data
            # directory; a process restart alone is not the isolation claim.
            close_owned_session(cdp, job, process)
            cdp = job = process = None
            main_server = groups[0].servers[0]
            main_server.result = None
            main_server.ready.clear()
            rotated_profile = root / "synthetic-profile-new-session"
            rotated_args = [f"--user-data-dir={rotated_profile}"
                            if value.startswith("--user-data-dir=") else value
                            for value in args]
            job = OwnedJob()
            process = spawn_owned_browser(rotated_args, root, job)
            assert process.stdin is not None
            process.stdin.write(b"G")
            process.stdin.flush()
            process.stdin.close()
            process.stdin = None
            rotated = groups[0].result(process)
            if any(entry.get("unavailable") is True for entry in rotated.values()):
                raise Inconclusive("new_session_canvas_context_unavailable")
            checks["new_user_data_dir_rotates_same_origin_readback"] = _different(
                first, rotated, CONTEXTS)
            return {"status": "PASS" if all(checks.values()) else "FAIL",
                    "checks": checks,
                    "chromium_processes_inspected": argv["chromium_processes_inspected"],
                    "renderer_processes_inspected": argv["renderer_processes_inspected"],
                    "scope": "one Windows host, two owned Chromium launches and fresh synthetic profiles; same loopback origin across sessions; three pages in two BrowserContexts in first session"}
        finally:
            close_owned_session(cdp, job, process)
            reject.shutdown()
            reject.server_close()
            reject_thread.join(timeout=5)
            for group in groups:
                group.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = args.chrome.with_name("chrome.dll")
    if (os.name != "nt" or args.chrome.name.lower() != "chrome.exe" or
            not args.chrome.is_file() or not core.is_file()):
        parser.error("Existing Windows chrome.exe and adjacent chrome.dll required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be a new file in an existing private directory")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "INCONCLUSIVE", "chrome_exe_sha256": sha256(args.chrome),
              "chrome_dll_sha256": sha256(core),
              "harness_source_commit": harness_commit()}
    try:
        report.update(measure(args.chrome.resolve()))
    except Inconclusive as error:
        report["reason_code"] = str(error)
    except Exception as error:
        report["reason_code"] = f"harness_{type(error).__name__}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks", {}),
                      "reason_code": report.get("reason_code")}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2}.get(report["status"], 3)


if __name__ == "__main__":
    raise SystemExit(main())
