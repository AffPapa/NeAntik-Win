"""Compare direct/proxied WebRTC UDP using a receiver in a WSL network namespace.

The HTTP page is loopback on Windows; the STUN UDP sink is a private WSL host.
This can establish a stronger local positive control than host-loopback alone,
but does not certify public egress, IPv6, TURN, DNS, or anonymity.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from native_persona_context_audit import prepare_disposable_engine
from webrtc_udp_integration import evaluate_cases, evaluate_socks_case, run_case


class RemoteSink:
    def __init__(self, ready: dict):
        self.host = str(ready["host"])
        self.port = int(ready["udp_port"])
        self.control_port = int(ready["control_port"])
        self.token = str(ready["token"])
        if not (1 <= self.port <= 65535 and 1 <= self.control_port <= 65535
                and len(self.token) >= 24):
            raise RuntimeError("Invalid WSL receiver handshake")

    def request(self, route: str, method: str = "GET") -> dict:
        url = f"http://{self.host}:{self.control_port}{route}?{urlencode({'token': self.token})}"
        with urlopen(Request(url, method=method), timeout=5) as response:
            value = json.load(response)
        if not isinstance(value, dict):
            raise RuntimeError("Invalid WSL receiver response")
        return value

    def reset(self) -> None:
        if self.request("/reset", "POST").get("reset") is not True:
            raise RuntimeError("WSL receiver reset failed")

    def snapshot(self) -> dict[str, int]:
        value = self.request("/state")
        if not all(type(value.get(key)) is int and value[key] >= 0
                   for key in ("stun_binding_requests", "all_udp_datagrams")):
            raise RuntimeError("Invalid WSL receiver counters")
        return value

    def stop(self) -> None:
        self.request("/stop", "POST")


def read_handshake(process: subprocess.Popen[str]) -> dict:
    lines: queue.Queue[str] = queue.Queue()
    thread = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
    thread.start()
    try:
        line = lines.get(timeout=20)
    except queue.Empty as error:
        raise RuntimeError("WSL receiver did not become ready") from error
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"WSL receiver startup failed: {line[:180]!r}") from error
    if not isinstance(value, dict):
        raise RuntimeError("Invalid WSL receiver handshake")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--wsl-host", required=True, help="Private IPv4 address assigned to the chosen WSL distro")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or not args.chrome.is_file() or args.chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be a new file in an existing directory")
    try:
        host = ipaddress.ip_address(args.wsl_host)
        if host.version != 4 or not host.is_private or host.is_loopback:
            raise ValueError("WSL host must be a non-loopback private IPv4 address")
    except ValueError as error:
        parser.error(str(error))
    script = Path(__file__).resolve().with_name("remote_stun_sink.py")
    path_result = subprocess.run(["wsl.exe", "-d", args.distro, "--", "wslpath", "-a",
                                  script.as_posix()],
                                 capture_output=True, text=True, timeout=10, check=False)
    if path_result.returncode != 0:
        parser.error("Could not translate receiver path into WSL")
    wsl_script = path_result.stdout.strip()
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Windows Chromium to private WSL network namespace; no public-network or anonymity claim",
              "wsl_distro": args.distro, "wsl_host": args.wsl_host,
              "cases": [], "status": "started"}
    process: subprocess.Popen[str] | None = None
    sink: RemoteSink | None = None
    try:
        process = subprocess.Popen(["wsl.exe", "-d", args.distro, "--", "python3", wsl_script,
                                    "--bind", args.wsl_host],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        ready = read_handshake(process)
        if ready.get("host") != args.wsl_host:
            raise RuntimeError("WSL receiver bound a different address")
        sink = RemoteSink(ready)
        sink.snapshot()  # Positive control for host-to-WSL TCP reachability.
        root = Path(tempfile.mkdtemp(prefix="neantik-wsl-stun-qa-"))
        try:
            chrome = prepare_disposable_engine(args.chrome, root)
            report["cases"].append(run_case(chrome, root, False, args.wsl_host,
                                            remote_sink=sink))
            report["cases"].append(run_case(chrome, root, True, args.wsl_host,
                                            remote_sink=sink))
            report["cases"].append(run_case(chrome, root, True, args.wsl_host,
                                            remote_sink=sink, verify_proxy_route=True,
                                            proxy_scheme="socks5"))
        finally:
            temp_parent = Path(tempfile.gettempdir()).resolve()
            if root.resolve().parent != temp_parent or not root.name.startswith("neantik-wsl-stun-qa-") or root.is_symlink():
                raise RuntimeError("Unsafe WSL STUN QA cleanup target")
            cleanup_error = None
            for _ in range(20):
                try:
                    shutil.rmtree(root)
                    cleanup_error = None
                    break
                except PermissionError as error:
                    cleanup_error = error
                    time.sleep(0.25)
            if cleanup_error is not None:
                raise RuntimeError(f"WSL STUN QA files remain locked: {cleanup_error}")
        http_result = evaluate_cases(report["cases"][0], report["cases"][1], False)
        socks_result = evaluate_socks_case(report["cases"][0], report["cases"][2])
        report["route_checks"] = {"http": http_result, "socks5": socks_result}
        report["status"] = ("cross_namespace_passed" if http_result == "passed" and
                            socks_result == "passed" else "inconclusive")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "cross_namespace_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
