"""Compare Chromium startup HTTP(S) requests for a blank page and its NTP.

This is a disposable, direct-network diagnostic, not a leak or anonymity test.
It records hostnames only; raw NetLogs and profiles are deleted at teardown.
The caller must supply a private output path outside the source tree.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit

from browser_integration import OwnedJob, spawn_owned_browser
from privacy_defaults import initialize_privacy_defaults


def summarize_netlog(document: dict) -> dict:
    event_type = document.get("constants", {}).get("logEventTypes", {}).get("URL_REQUEST_START_JOB")
    events = document.get("events")
    if not isinstance(event_type, int) or not isinstance(events, list):
        raise ValueError("Chromium NetLog lacks URL request events")
    host_counts: Counter[str] = Counter()
    for event in events:
        if not isinstance(event, dict) or event.get("type") != event_type:
            continue
        url = event.get("params", {}).get("url", "")
        if not isinstance(url, str):
            continue
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            host_counts[parsed.hostname.lower()] += 1
    return {"http_request_count": sum(host_counts.values()),
            "host_counts": dict(sorted(host_counts.items()))}


def run_case(chrome: Path, root: Path, name: str, url: str) -> dict:
    profile = root / name / "Profile"
    profile.parent.mkdir(parents=True)
    if not initialize_privacy_defaults(profile):
        raise RuntimeError("Could not initialize a disposable profile")
    log = root / name / "netlog.json"
    arguments = [str(chrome), "--headless", "--dump-dom", "--virtual-time-budget=5000",
                 f"--user-data-dir={profile}", "--no-first-run",
                 "--no-default-browser-check", f"--log-net-log={log}", url]
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
    args = parser.parse_args()
    chrome = args.chrome.resolve()
    if os.name != "nt" or not chrome.is_file() or chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output path must be new and its parent must exist")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "one Windows host, direct network, fresh profiles, headless startup only",
              "cases": {}, "status": "started"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-start-page-qa-") as temporary:
            root = Path(temporary)
            report["cases"]["blank"] = run_case(chrome, root, "blank", "about:blank")
            report["cases"]["new_tab"] = run_case(chrome, root, "new-tab", "chrome://newtab")
        report["status"] = "measured"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": report["cases"],
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
