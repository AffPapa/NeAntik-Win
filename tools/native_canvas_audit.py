"""Disposable native-persona Canvas smoke test for an experimental Chromium core.

Only file:// test content is opened. No real profile or public site is used.
Different stable seeds are a functional test, not an anonymity guarantee.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from browser_integration import OwnedJob, spawn_owned_browser


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "native_canvas_probe.html"
REQUIRED = ("repeatMatches", "regionMatches", "pngRepeatMatches",
            "exportPreservesBacking", "clearIsTransparent")


def run_profile(chrome: Path, seed: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="neantik-native-canvas-qa-") as temporary:
        root = Path(temporary)
        job = OwnedJob()
        process: subprocess.Popen[bytes] | None = None
        try:
            arguments = [str(chrome), "--headless", "--dump-dom",
                         f"--user-data-dir={root / 'Profile'}", "--no-first-run",
                         "--no-default-browser-check", "--disable-background-networking",
                         "--disable-component-update", "--disable-sync", "--disable-quic",
                         "--host-resolver-rules=MAP * ~NOTFOUND", "--metrics-recording-only",
                         f"--neantik-fingerprint-seed={seed}", FIXTURE.as_uri()]
            process = spawn_owned_browser(arguments, root, job)
            stdout, stderr = process.communicate(input=b"G", timeout=30)
            if process.returncode != 0:
                raise RuntimeError(f"Browser exited {process.returncode}: {stderr.decode(errors='replace')[-400:]}")
            match = re.search(r'<pre id="result">(.*?)</pre>', stdout.decode("utf-8", errors="replace"), re.S)
            if not match:
                raise RuntimeError("Canvas probe did not return a result")
            result = json.loads(html.unescape(match.group(1)))
            if not isinstance(result, dict) or not all(result.get(key) is True for key in REQUIRED):
                raise RuntimeError("Canvas readback/export invariant failed")
            return result
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
            job.close()
            if process is not None:
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or not args.chrome.is_file() or args.chrome.name.lower() != "chrome.exe":
        parser.error("An existing Windows chrome.exe is required")
    if not FIXTURE.is_file() or args.output.exists() or not args.output.parent.is_dir():
        parser.error("Probe fixture missing or output path invalid")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "experimental native persona, local file only; no anonymity claim",
              "status": "started"}
    try:
        first = run_profile(args.chrome, 123456)
        same_seed = run_profile(args.chrome, 123456)
        other_seed = run_profile(args.chrome, 456789)
        report.update({"repeatable_across_profiles": first == same_seed,
                       "seed_changes_pixel_hash": first["pixelHash"] != other_seed["pixelHash"],
                       "seed_changes_png_hash": first["pngHash"] != other_seed["pngHash"],
                       "invariants": {key: first[key] and same_seed[key] and other_seed[key] for key in REQUIRED}})
        report["status"] = ("passed" if report["repeatable_across_profiles"] and
                            report["seed_changes_pixel_hash"] and report["seed_changes_png_hash"] and
                            all(report["invariants"].values()) else "failed")
    except Exception as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
