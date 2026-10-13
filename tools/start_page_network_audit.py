"""Compare Chromium startup requests for a blank page, NTP and local proxy.

This is a disposable local diagnostic, not an external leak or anonymity test.
The summary records hostnames and connection IPs without URL paths; raw
NetLogs and profiles are deleted at teardown. Console output omits IPs.
The caller must supply a private output path outside the source tree.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit

from browser_integration import OwnedJob, spawn_owned_browser
from nevision_win import bundled_proxy_privacy_arguments, proxy_endpoint
from privacy_defaults import initialize_privacy_defaults


def summarize_netlog(document: dict) -> dict:
    types = document.get("constants", {}).get("logEventTypes", {})
    event_type = types.get("URL_REQUEST_START_JOB")
    events = document.get("events")
    if not isinstance(event_type, int) or not isinstance(events, list):
        raise ValueError("Chromium NetLog lacks URL request events")
    host_counts: Counter[str] = Counter()
    tcp_remote_hosts: Counter[str] = Counter()
    udp_sends = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") == types.get("UDP_BYTES_SENT") and isinstance(types.get("UDP_BYTES_SENT"), int):
            udp_sends += 1
        if event.get("type") == types.get("TCP_CONNECT") and event.get("phase") == 2:
            remote = event.get("params", {}).get("remote_address")
            if isinstance(remote, str):
                try:
                    host = urlsplit("//" + remote).hostname
                except ValueError:
                    host = None
                if host:
                    tcp_remote_hosts[host.lower()] += 1
        if event.get("type") != event_type:
            continue
        url = event.get("params", {}).get("url", "")
        if not isinstance(url, str):
            continue
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            host_counts[parsed.hostname.lower()] += 1
    return {"http_request_count": sum(host_counts.values()),
            "host_counts": dict(sorted(host_counts.items())),
            "tcp_remote_hosts": dict(sorted(tcp_remote_hosts.items())),
            "udp_send_count": udp_sends}


class RejectingProxy(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), RejectingProxyHandler)
        self.host_counts: Counter[str] = Counter()
        self.lock = threading.Lock()


class RejectingProxyHandler(BaseHTTPRequestHandler):
    server: RejectingProxy

    def log_message(self, _format: str, *_args: object) -> None:
        pass

    def reject(self) -> None:
        target = self.path if self.command == "CONNECT" else self.headers.get("Host", "")
        if self.command != "CONNECT" and self.path.startswith(("http://", "https://")):
            target = self.path
        try:
            host = urlsplit(target if "://" in target else "//" + target).hostname
        except ValueError:
            host = None
        if host:
            with self.server.lock:
                self.server.host_counts[host.lower()] += 1
        self.send_response(502)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    do_CONNECT = reject
    do_GET = reject
    do_POST = reject


def evaluate_proxy_route(case: dict) -> dict[str, bool]:
    """Narrow NetLog/fixture invariants, not an OS packet-capture guarantee."""
    remote_hosts = case.get("tcp_remote_hosts", {})
    return {
        "proxy_observed_requests": bool(case.get("proxy_observed_hosts")),
        "tcp_only_to_loopback_proxy": bool(remote_hosts)
        and set(remote_hosts) == {"127.0.0.1"},
        "no_udp_sends_in_netlog": case.get("udp_send_count") == 0,
    }


def run_case(chrome: Path, root: Path, name: str, url: str,
             proxy_port: int | None = None) -> dict:
    profile = root / name / "Profile"
    profile.parent.mkdir(parents=True)
    if not initialize_privacy_defaults(profile):
        raise RuntimeError("Could not initialize a disposable profile")
    log = root / name / "netlog.json"
    arguments = [str(chrome), "--headless", "--dump-dom", "--virtual-time-budget=5000",
                 f"--user-data-dir={profile}", "--no-first-run",
                 "--no-default-browser-check", f"--log-net-log={log}"]
    if proxy_port is not None:
        proxy = {"scheme": "http", "host": "127.0.0.1", "port": proxy_port}
        arguments.extend([f"--proxy-server={proxy_endpoint(proxy)}",
                          *bundled_proxy_privacy_arguments(proxy)])
    arguments.append(url)
    job = OwnedJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = spawn_owned_browser(arguments, profile.parent, job)
        _stdout, stderr = process.communicate(input=b"G", timeout=40)
        if process.returncode != 0:
            raise RuntimeError(f"Chromium {name} exited {process.returncode}: {stderr.decode(errors='replace')[-300:]}")
    finally:
        job.close()
        if process is not None and process.poll() is None:
            process.kill()
    if not log.is_file():
        raise RuntimeError(f"Chromium did not write the {name} NetLog")
    return summarize_netlog(json.loads(log.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proxy-startup", action="store_true",
                        help="Also run a blank-page startup against a rejecting loopback HTTP proxy")
    args = parser.parse_args()
    chrome = args.chrome.resolve()
    if os.name != "nt" or not chrome.is_file() or chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output path must be new and its parent must exist")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "one Windows host, fresh profiles, headless startup only; proxy case is local NetLog evidence, not external leak proof",
              "cases": {}, "status": "started"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-start-page-qa-") as temporary:
            root = Path(temporary)
            report["cases"]["blank"] = run_case(chrome, root, "blank", "about:blank")
            report["cases"]["new_tab"] = run_case(chrome, root, "new-tab", "chrome://newtab")
            if args.proxy_startup:
                proxy = RejectingProxy()
                thread = threading.Thread(target=proxy.serve_forever, daemon=True)
                thread.start()
                try:
                    report["cases"]["proxy_blank"] = run_case(
                        chrome, root, "proxy-blank", "about:blank", proxy.server_port)
                    report["cases"]["proxy_blank"]["proxy_observed_hosts"] = dict(
                        sorted(proxy.host_counts.items()))
                finally:
                    proxy.shutdown()
                    proxy.server_close()
                    thread.join(timeout=5)
                proxy_case = report["cases"]["proxy_blank"]
                report["proxy_route_checks"] = evaluate_proxy_route(proxy_case)
        report["status"] = "measured"
        if args.proxy_startup and not all(report["proxy_route_checks"].values()):
            report["status"] = "inconclusive"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "cases": {name: {"http_request_count": case["http_request_count"],
                                        "tcp_connection_count": sum(case["tcp_remote_hosts"].values()),
                                        "udp_send_count": case["udp_send_count"]}
                                for name, case in report["cases"].items()},
                      "proxy_route_checks": report.get("proxy_route_checks"),
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
