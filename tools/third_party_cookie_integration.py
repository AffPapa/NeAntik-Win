"""Loopback-only exact-engine check for the fresh-profile cookie default.

Uses a synthetic Secure cookie, one first-party positive control, one cross-site
iframe request, and an allow-third-party control. It records booleans only.
"""

from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(ROOT))
from browser_integration import OwnedJob, spawn_owned_browser  # noqa: E402
from nevision_win import AppPaths, BrowserLauncher, Storage  # noqa: E402
from privacy_defaults import initialize_privacy_defaults  # noqa: E402

COOKIE = "__Host-neantik-control=synthetic"
EXPECTED_CHROME_SHA256 = "7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa"


class Fixture(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.lock = threading.Lock()
        self.seed_cookie_seen = False
        self.iframe_requested = False
        self.iframe_cookie_seen = False
        self.hosts: set[str] = set()


class Handler(BaseHTTPRequestHandler):
    server: Fixture

    def log_message(self, _format: str, *args: object) -> None:
        pass

    def respond(self, body: str, set_cookie: bool = False) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        if set_cookie:
            # Persist across the seed and assertion browser processes; this
            # value exists only in disposable profiles and expires in 1 hour.
            self.send_header("Set-Cookie", COOKIE + "; Path=/; Max-Age=3600; Secure; SameSite=None")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        host = self.headers.get("Host", "").split(":", 1)[0].lower()
        if host not in {"localhost", "127.0.0.1"}:
            self.send_error(403)
            return
        route = urlsplit(self.path).path
        has_cookie = COOKIE in self.headers.get("Cookie", "")
        with self.server.lock:
            self.server.hosts.add(host)
            if route == "/seed-check":
                self.server.seed_cookie_seen = has_cookie
            elif route == "/probe":
                self.server.iframe_requested = True
                self.server.iframe_cookie_seen = has_cookie
        if route == "/seed":
            self.respond("<!doctype html><title>seeded</title>", set_cookie=True)
        elif route == "/seed-check":
            self.respond("<!doctype html><title>verified</title>")
        elif route == "/probe":
            self.respond("<!doctype html><title>third-party probe</title>")
        elif route == "/page":
            self.respond(f"<!doctype html><iframe src='http://localhost:{self.server.server_port}/probe'></iframe>")
        else:
            self.send_error(404)


def launch(chrome: Path, storage: Storage, profile_id: str, url: str) -> None:
    BrowserLauncher(storage).ensure_profile_path_is_isolated(profile_id)
    port = urlsplit(url).port
    args = [str(chrome), "--headless", "--dump-dom", f"--user-data-dir={storage.profile_path(profile_id)}",
            "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
            "--disable-component-update", "--disable-sync", "--disable-quic", "--metrics-recording-only",
            "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
            f"--unsafely-treat-insecure-origin-as-secure=http://localhost:{port}", url]
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = spawn_owned_browser(args, storage.profile_path(profile_id), job)
        _stdout, _stderr = process.communicate(input=b"G", timeout=30)
        if process.returncode != 0:
            raise RuntimeError(f"Chromium process failed (exit={process.returncode})")
    except subprocess.TimeoutExpired as error:
        if process is not None and process.poll() is None:
            process.terminate()
        raise RuntimeError("Chromium timeout") from error
    finally:
        job.close()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()


def run_case(chrome: Path, storage: Storage, server: Fixture, profile_id: str,
             block_third_party: bool) -> dict[str, bool]:
    initialize_privacy_defaults(storage.profile_path(profile_id))
    preferences = storage.profile_path(profile_id) / "Default" / "Preferences"
    payload = json.loads(preferences.read_text(encoding="utf-8"))
    if not block_third_party:
        payload["profile"]["cookie_controls_mode"] = 0
        preferences.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    expected_mode = 1 if block_third_party else 0
    configured_mode_matches = payload["profile"].get("cookie_controls_mode") == expected_mode
    base = f"http://localhost:{server.server_port}"
    launch(chrome, storage, profile_id, base + "/seed")
    launch(chrome, storage, profile_id, base + "/seed-check")
    with server.lock:
        first_party_ok = server.seed_cookie_seen
        server.seed_cookie_seen = False
        server.iframe_requested = False
        server.iframe_cookie_seen = False
    launch(chrome, storage, profile_id, f"http://127.0.0.1:{server.server_port}/page")
    with server.lock:
        return {"cookie_control_mode_matches_case": configured_mode_matches,
                "first_party_positive_control": first_party_ok,
                "cross_site_iframe_requested": server.iframe_requested,
                "cross_site_cookie_sent": server.iframe_cookie_seen}


def main() -> int:
    if os.name != "nt":
        raise SystemExit("Windows is required for the production launch guard and owned Jobs")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    args = parser.parse_args()
    chrome = args.chrome.resolve(strict=True)
    if chrome.name.lower() != "chrome.exe" or hashlib.sha256(chrome.read_bytes()).hexdigest() != EXPECTED_CHROME_SHA256:
        parser.error("Expected the exact Chromium binary from NeAntik Win 0.8.19-preview")

    server = Fixture()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from native_persona_context_audit import prepare_disposable_engine

        with tempfile.TemporaryDirectory(prefix="neantik-cookie-engine-") as engine_tmp:
            prepared = prepare_disposable_engine(chrome, Path(engine_tmp))
            if hashlib.sha256(prepared.read_bytes()).hexdigest() != EXPECTED_CHROME_SHA256:
                raise RuntimeError("Sandbox-prepared Chromium bytes do not match the release binary")
            with tempfile.TemporaryDirectory(prefix="neantik-cookie-audit-") as data_tmp:
                storage = Storage(AppPaths(Path(data_tmp)))
                blocked_id = storage.save_profile({"name": "Synthetic blocked-cookie profile"})
                allowed_id = storage.save_profile({"name": "Synthetic allow-cookie control"})
                blocked = run_case(prepared, storage, server, blocked_id, True)
                allowed = run_case(prepared, storage, server, allowed_id, False)
        checks = {
            "fresh_profile_cookie_mode_is_block": blocked["cookie_control_mode_matches_case"],
            "allow_profile_control_cookie_mode_is_allow": allowed["cookie_control_mode_matches_case"],
            "first_party_cookie_stored_in_both_profiles": blocked["first_party_positive_control"] and allowed["first_party_positive_control"],
            "cross_site_probe_reached_in_both_profiles": blocked["cross_site_iframe_requested"] and allowed["cross_site_iframe_requested"],
            "third_party_cookie_blocked_by_fresh_profile_default": not blocked["cross_site_cookie_sent"],
            "third_party_cookie_allow_control_works": allowed["cross_site_cookie_sent"],
            "all_requests_loopback_only": server.hosts <= {"localhost", "127.0.0.1"},
        }
        print(json.dumps({"status": "PASS" if all(checks.values()) else "FAIL",
                          "checks": checks,
                          "scope": "exact 0.8.19 Chromium; two disposable profiles; two loopback hostnames",
                          "cookie_values_and_device_data_recorded": False,
                          "limitations": ["HTTP localhost is marked secure only in the test invocation.",
                                          "Does not cover Storage Access API, CHIPS, site exceptions, or real-site compatibility."]},
                         sort_keys=True))
        return 0 if all(checks.values()) else 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
