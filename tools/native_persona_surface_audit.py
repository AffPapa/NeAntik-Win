"""Measure V4b Canvas session changes and selected cross-surface coherence.

Runs four disposable loopback-only browser sessions: two profiles, each opened
twice. The report contains booleans and binary hashes, not device traits or
Canvas values. A pass is not a population-entropy or anonymity claim.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from fingerprint_surface_audit import audit_profile, evaluate
from native_persona_context_audit import prepare_disposable_engine
from profile_identity import identity_arguments, native_preview_identity


CANVAS_FIELDS = ("canvas2dSha256", "canvasPixelSha256")


def summarize(reports: list[dict], contexts: list[dict[str, bool]]) -> dict:
    """Fail closed; keep raw fingerprint values out of the returned summary."""
    if len(reports) != 4 or len(contexts) != 4:
        raise ValueError("Two profiles and two launches per profile are required")
    stripped = []
    canvas = {field: [] for field in CANVAS_FIELDS}
    for report in reports:
        value = json.loads(json.dumps(report))
        surfaces = value.get("surfaces")
        if not isinstance(surfaces, dict) or not isinstance(surfaces.get("main"), dict):
            raise ValueError("Missing measured browser surfaces")
        for field in CANVAS_FIELDS:
            observed = surfaces["main"].get(field)
            if not isinstance(observed, str) or re.fullmatch(r"[a-f0-9]{64}", observed) is None:
                raise ValueError("Missing Canvas digest")
            canvas[field].append(observed)
        for surface in surfaces.values():
            if isinstance(surface, dict):
                for field in CANVAS_FIELDS:
                    surface.pop(field, None)
        value.pop("blocked_external_requests", None)
        stripped.append(value)
    checks = {
        "all_context_checks_pass": all(
            isinstance(item, dict) and item and all(value is True for value in item.values())
            for item in contexts
        ),
        "non_canvas_surfaces_stable": all(item == stripped[0] for item in stripped[1:]),
        "canvas_png_changes_each_session": len(set(canvas["canvas2dSha256"])) == 4,
        "canvas_pixels_change_each_session": len(set(canvas["canvasPixelSha256"])) == 4,
    }
    return {"profiles": 2, "sessions_per_profile": 2, "measured_sessions": 4,
            "checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"}


def sha256(path: Path) -> str:
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
    chrome = args.chrome.resolve()
    if (os.name != "nt" or chrome.name.lower() != "chrome.exe" or
            not chrome.is_file() or not chrome.with_name("chrome.dll").is_file()):
        parser.error("An existing Windows chrome.exe and adjacent chrome.dll are required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be a new path in an existing directory")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "two disposable profiles, two V4b sessions each, one Windows host and loopback sites; not anonymity approval",
              "chrome_exe_sha256": sha256(chrome),
              "chrome_dll_sha256": sha256(chrome.with_name("chrome.dll")),
              "status": "INCONCLUSIVE"}
    try:
        measurements: list[dict] = []
        contexts: list[dict[str, bool]] = []
        with tempfile.TemporaryDirectory(prefix="neantik-v4b-surface-engine-") as engine_dir:
            disposable_chrome = prepare_disposable_engine(chrome, Path(engine_dir))
            for index in range(2):
                with tempfile.TemporaryDirectory(prefix="neantik-v4b-surface-profile-") as profile_dir:
                    identity = native_preview_identity(113777 + index * 9311)
                    flags = tuple(identity_arguments(identity))
                    root = Path(profile_dir)
                    for launch in range(2):
                        measured = audit_profile(disposable_chrome, root, flags,
                                                 reuse_existing=launch > 0)
                        measurements.append(measured)
                        contexts.append(evaluate([measured])[0])
        report.update(summarize(measurements, contexts))
    except Exception as error:
        # Browser diagnostics can include local paths or URLs; publish only a
        # bounded class name, not the exception body or raw device traits.
        report["reason_code"] = type(error).__name__
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks"),
                      "report": str(args.output), "reason_code": report.get("reason_code")},
                     ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2}.get(report["status"], 3)


if __name__ == "__main__":
    raise SystemExit(main())
