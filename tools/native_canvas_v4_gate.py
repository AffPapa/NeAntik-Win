"""Local V4 Canvas linkability gate; never a claim of general anonymity.

Each of two disposable, saved user-data directories is visited in three browser
sessions (initial launch plus two restarts). In every session the same browser
opens two distinct loopback *sites*: 127.0.0.1 and localhost. Raw probe values
stay in memory; the JSON report contains only aggregate booleans and counts.

Exit 0 means this local matrix passed, NOT that the browser is release-ready.
Exit 2 means complete measurements contradicted the proposed session/site
scoping. Exit 3 means incomplete or inconclusive measurement.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
from urllib.parse import quote
from urllib.request import build_opener, ProxyHandler, Request

from browser_integration import OwnedJob, spawn_owned_browser
from native_canvas_audit import ProbeServer, REQUIRED


PROFILE_COUNT = 2
SESSION_COUNT = 3  # Initial launch and two restarts of the SAME profile.
SITES = ("127.0.0.1", "localhost")
SURFACES = ("pixelHash", "pngHash")
EXPECTED_CASES = PROFILE_COUNT * SESSION_COUNT * len(SITES)


class Inconclusive(RuntimeError):
    """A missing result is not evidence of a browser privacy defect."""


class ObservedFailure(RuntimeError):
    """A probe completed but a required Canvas compatibility invariant failed."""


def validate_result(result: object) -> dict:
    if not isinstance(result, dict):
        raise Inconclusive("invalid_probe_result")
    if result.get("error") is not None:
        raise Inconclusive("probe_script_error")
    for key in SURFACES:
        value = result.get(key)
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise Inconclusive("missing_canvas_measurement")
    if any(key not in result or type(result[key]) is not bool for key in REQUIRED):
        raise Inconclusive("canvas_invariant_unmeasured")
    if any(result[key] is False for key in REQUIRED):
        raise ObservedFailure("canvas_invariant_failed")
    return result


def summarize_matrix(matrix: dict[tuple[int, int, str], dict]) -> dict:
    """Fail closed on any missing case; never put raw values in the summary."""
    expected = {(profile, session, site)
                for profile in range(PROFILE_COUNT)
                for session in range(SESSION_COUNT)
                for site in SITES}
    if set(matrix) != expected:
        raise Inconclusive("incomplete_profile_session_site_matrix")
    for result in matrix.values():
        validate_result(result)
    checks = {
        "all_12_cases_measured": True,
        "same_session_sites_differ_on_both_surfaces": all(
            matrix[(profile, session, SITES[0])][surface]
            != matrix[(profile, session, SITES[1])][surface]
            for profile in range(PROFILE_COUNT)
            for session in range(SESSION_COUNT)
            for surface in SURFACES
        ),
        "saved_profile_changes_on_each_restart_on_both_surfaces": all(
            len({matrix[(profile, session, site)][surface]
                 for session in range(SESSION_COUNT)}) == SESSION_COUNT
            for profile in range(PROFILE_COUNT)
            for site in SITES
            for surface in SURFACES
        ),
    }
    return {"cases_measured": len(matrix), "profiles": PROFILE_COUNT,
            "sessions_per_profile": SESSION_COUNT, "restarts_per_profile": SESSION_COUNT - 1,
            "sites_per_session": len(SITES), "checks": checks,
            "local_gate": "PASS" if all(checks.values()) else "FAIL"}


def _launch(chrome: Path, profile: Path, root: Path, job: OwnedJob,
            url: str, proxy_port: int, seed: int) -> subprocess.Popen[bytes]:
    arguments = [str(chrome), "--headless=new", f"--user-data-dir={profile}",
                 "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                 "--no-first-run", "--no-default-browser-check",
                 "--disable-background-networking", "--disable-component-update",
                 "--disable-sync", "--disable-quic", "--metrics-recording-only",
                 f"--proxy-server=http://127.0.0.1:{proxy_port}",
                 "--proxy-bypass-list=127.0.0.1;localhost",
                 "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
                 f"--neantik-fingerprint-seed={seed}", url]
    process = spawn_owned_browser(arguments, root, job)
    assert process.stdin is not None
    process.stdin.write(b"G")
    process.stdin.flush()
    process.stdin.close()
    process.stdin = None
    return process


def _open_second_site_in_same_browser(profile: Path, url: str) -> None:
    """Create a second top-level tab through the first browser's local CDP HTTP endpoint."""
    marker = profile / "DevToolsActivePort"
    if not marker.is_file():
        raise Inconclusive("local_debug_endpoint_missing")
    try:
        port = int(marker.read_text(encoding="ascii").splitlines()[0])
        if not 0 < port < 65536:
            raise ValueError("port out of range")
        endpoint = f"http://127.0.0.1:{port}/json/new?{quote(url, safe='')}"
        request = Request(endpoint, method="PUT")
        # Do not permit an environment proxy to see the local target URL/token.
        with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
            if response.status != 200:
                raise ValueError("CDP did not create a target")
    except Exception as error:
        raise Inconclusive(f"local_debug_navigation_{type(error).__name__}") from None


def _one_session(chrome: Path, profile: Path, root: Path, seed: int) -> tuple[dict[str, dict], int]:
    servers = [ProbeServer(uuid.uuid4().hex) for _ in SITES]
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    job: OwnedJob | None = None
    processes: list[subprocess.Popen[bytes]] = []
    try:
        job = OwnedJob()
        first = servers[0]
        url = f"http://{SITES[0]}:{first.server_port}/case?token={first.token}"
        processes.append(_launch(chrome, profile, root, job, url, first.server_port, seed))
        if not first.ready.wait(45):
            raise Inconclusive("first_loopback_site_timeout")
        validate_result(first.result)
        if processes[0].poll() is not None:
            raise Inconclusive("browser_exited_before_second_site")
        second = servers[1]
        url = f"http://{SITES[1]}:{second.server_port}/case?token={second.token}"
        _open_second_site_in_same_browser(profile, url)
        if not second.ready.wait(45):
            raise Inconclusive("second_loopback_site_timeout")
        validate_result(second.result)
        if processes[0].poll() is not None:
            raise Inconclusive("browser_exited_during_session")
        return ({site: validate_result(server.result)
                 for site, server in zip(SITES, servers)},
                sum(server.rejected_external_requests for server in servers))
    finally:
        if job is not None:
            job.close()  # Kills only the disposable owned Chromium process tree.
        for process in processes:
            try:
                process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=8)
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)


def measure(chrome: Path) -> dict:
    matrix: dict[tuple[int, int, str], dict] = {}
    blocked_requests = 0
    with tempfile.TemporaryDirectory(prefix="neantik-v4-canvas-local-") as temporary:
        root = Path(temporary)
        for profile in range(PROFILE_COUNT):
            user_data = root / f"synthetic-profile-{profile}"
            seed = 110001 + profile * 9719  # Deliberately expose a V3 stable-seed regression.
            for session in range(SESSION_COUNT):
                results, blocked = _one_session(chrome, user_data, root, seed)
                blocked_requests += blocked
                for site, result in results.items():
                    matrix[(profile, session, site)] = result
                # A closed Job is necessary but not sufficient; ensure the
                # profile singleton has stopped before reopening this folder.
                deadline = time.monotonic() + 8
                while (user_data / "SingletonLock").exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                if (user_data / "SingletonLock").exists():
                    raise Inconclusive("saved_profile_still_locked_after_restart")
    summary = summarize_matrix(matrix)
    summary["rejected_non_loopback_requests"] = blocked_requests
    return summary


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core_dll = args.chrome.with_name("chrome.dll")
    if (os.name != "nt" or not args.chrome.is_file() or
            args.chrome.name.lower() != "chrome.exe" or not core_dll.is_file()):
        parser.error("An existing Windows chrome.exe and adjacent chrome.dll are required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be a new path in an existing directory")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "single Windows host, two synthetic saved profiles, three sessions and two loopback sites; not release or anonymity approval",
              "chrome_exe_sha256": _sha256(args.chrome),
              "chrome_dll_sha256": _sha256(core_dll), "status": "INCONCLUSIVE"}
    try:
        report.update(measure(args.chrome))
        report["status"] = report["local_gate"]
    except ObservedFailure as error:
        report["status"] = "FAIL"
        report["reason_code"] = str(error)
    except Exception as error:
        report["reason_code"] = (str(error) if isinstance(error, Inconclusive)
                                 else f"harness_{type(error).__name__}")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases_measured": report.get("cases_measured", 0),
                      "report": str(args.output), "reason_code": report.get("reason_code")}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2}.get(report["status"], 3)


if __name__ == "__main__":
    raise SystemExit(main())
