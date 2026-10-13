"""Measure seed-stable Canvas identifiers on one disposable Windows host.

This compares a public baseline Chromium core with the unreleased V3 core.
Only loopback content is opened; no real profile or remote checker is used.
The report contains counts, not raw Canvas hashes or local device traits.
This is a local linkability warning, not an anonymity or population study.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from native_canvas_audit import run_profile


def summarize_runs(runs: list[dict], repeat: dict) -> dict:
    if not runs or any(type(run.get("pixelHash")) is not int
                       or type(run.get("pngHash")) is not int for run in [*runs, repeat]):
        raise ValueError("Canvas probe did not produce both hashes")
    return {
        "profiles": len(runs),
        "unique_pixel_hashes": len({run["pixelHash"] for run in runs}),
        "unique_png_hashes": len({run["pngHash"] for run in runs}),
        "first_seed_repeats_across_fresh_profiles":
            runs[0]["pixelHash"] == repeat["pixelHash"]
            and runs[0]["pngHash"] == repeat["pngHash"],
    }


def measure_core(chrome: Path, seeds: list[int]) -> dict:
    runs = [run_profile(chrome, seed) for seed in seeds]
    repeat = run_profile(chrome, seeds[0])
    summary = summarize_runs(runs, repeat)
    summary["chrome_exe_sha256"] = hashlib.sha256(chrome.read_bytes()).hexdigest()
    return summary


def assess_local_linkability(baseline: dict, candidate: dict) -> dict:
    sample_count = baseline["profiles"]
    if candidate["profiles"] != sample_count:
        raise ValueError("Baseline and candidate sample sizes differ")
    return {
        "baseline_seed_does_not_change_canvas":
            baseline["unique_pixel_hashes"] == baseline["unique_png_hashes"] == 1,
        "candidate_has_one_pixel_identifier_per_seed":
            candidate["unique_pixel_hashes"] == sample_count,
        "candidate_has_one_png_identifier_per_seed":
            candidate["unique_png_hashes"] == sample_count,
        "candidate_identifier_survives_fresh_profile":
            candidate["first_seed_repeats_across_fresh_profiles"],
    }


def release_gate(observations: dict) -> str:
    if all(observations.values()):
        return "blocked_by_stable_per_profile_canvas_identifier"
    return "requires_manual_review"


def report_exit_code(report: dict) -> int:
    """Keep successful measurement distinct from permission to release."""
    if report.get("status") != "measured":
        return 1
    return 0 if report.get("release_gate") == "approved" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-chrome", type=Path, required=True)
    parser.add_argument("--candidate-chrome", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or not 4 <= args.samples <= 32:
        parser.error("Windows and 4–32 samples are required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output path must be new and its parent must exist")
    for path in (args.baseline_chrome, args.candidate_chrome):
        if not path.is_file() or path.name.lower() != "chrome.exe":
            parser.error("Both inputs must be existing Windows chrome.exe files")
    seeds = [110001 + index * 9719 for index in range(args.samples)]
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "single Windows host, fixed Canvas probe, fresh profiles; not a population anonymity score",
              "samples": args.samples, "status": "started"}
    try:
        report["baseline"] = measure_core(args.baseline_chrome, seeds)
        report["candidate"] = measure_core(args.candidate_chrome, seeds)
        report["observations"] = assess_local_linkability(report["baseline"], report["candidate"])
        report["status"] = "measured"
        report["release_gate"] = release_gate(report["observations"])
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "samples": args.samples,
                      "observations": report.get("observations"),
                      "release_gate": report.get("release_gate"),
                      "report": str(args.output), "error": report.get("error")}, ensure_ascii=False))
    return report_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
