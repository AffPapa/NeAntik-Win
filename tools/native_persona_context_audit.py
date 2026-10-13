"""Disposable cross-context audit for the unreleased native persona prototype.

The page and both origins are loopback-only. Full reports may expose local
device traits; write them outside the source tree and never publish them.
Different seeds are a functional control, not an anonymity measurement.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from fingerprint_surface_audit import audit_profile, evaluate
from launcher_integration import check_engine_tree
from nevision_win import AppPaths, BrowserLauncher, Storage
from profile_identity import identity_arguments, native_preview_identity


REQUIRED_CAPABILITIES = (
    "stable_seed", "hardware_concurrency", "device_memory",
    "canvas_opaque_srgb_uint8", "timezone",
)


def check_reports(core_info: dict, baseline: dict, runs: list[dict]) -> dict[str, bool]:
    """Check narrow functional invariants without assigning a privacy score."""
    capabilities = core_info.get("capabilities", {})
    baseline_main = baseline["surfaces"]["main"]
    same_a, same_b, other = runs
    expected_cpu = min(4, baseline_main["hardwareConcurrency"])
    expected_memory = min(8, baseline_main["deviceMemory"])
    contexts = evaluate([baseline, *runs])
    def without_canvas(report: dict) -> dict:
        return {
            name: {key: value for key, value in surface.items()
                   if key not in ("canvas2dSha256", "canvasPixelSha256")}
            for name, surface in report["surfaces"].items()
        }
    return {
        "compiled_core_schema_2": core_info.get("engine_id") == "neantik-chromium"
        and core_info.get("schema") == 2
        and all(capabilities.get(name) is True for name in REQUIRED_CAPABILITIES),
        "all_contexts_and_http_hints_agree": all(all(items.values()) for items in contexts),
        "same_seed_repeats": same_a["surfaces"] == same_b["surfaces"],
        "different_seed_keeps_common_surfaces": without_canvas(same_a) == without_canvas(other),
        "different_seed_canvas_identical": all(
            same_a["surfaces"][name].get(key) == other["surfaces"][name].get(key)
            for name in same_a["surfaces"]
            for key in ("canvas2dSha256", "canvasPixelSha256")
            if key in same_a["surfaces"][name] or key in other["surfaces"][name]
        ),
        "cpu_bounded_by_stock": all(
            run["surfaces"]["main"]["hardwareConcurrency"] == expected_cpu for run in runs
        ),
        "memory_bounded_by_stock": all(
            run["surfaces"]["main"]["deviceMemory"] == expected_memory for run in runs
        ),
        "timezone_is_utc_in_all_contexts": all(
            all(surface["timezone"] == "UTC" for surface in run["surfaces"].values())
            for run in runs
        ),
        "date_timezone_offset_is_zero_in_all_contexts": all(
            all(surface["timezoneOffsetMinutes"] == 0 for surface in run["surfaces"].values())
            for run in runs
        ),
    }


def read_core_info(chrome: Path, root: Path) -> dict:
    path = root / "core-info.json"
    process = subprocess.run(
        [str(chrome), f"--neantik-core-info={path}"],
        cwd=root, capture_output=True, timeout=20, check=False,
    )
    if process.returncode != 0 or not path.is_file():
        raise RuntimeError("Native compiled-core handshake failed")
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_disposable_engine(chrome: Path, root: Path) -> Path:
    """Give an extracted portable core sandbox access only in a QA copy."""
    if not (chrome.parent / "ENGINE_PROVENANCE.json").is_file():
        return chrome
    check_engine_tree(chrome.parent)
    portable_root = root / "qa-portable"
    engine = portable_root / "Engine" / "Chromium"
    engine.parent.mkdir(parents=True)
    shutil.copytree(chrome.parent, engine)
    BrowserLauncher(Storage(AppPaths(portable_root))).ensure_bundled_sandbox_access(engine)
    return engine / "chrome.exe"


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
    with tempfile.TemporaryDirectory(prefix="neantik-native-context-qa-") as temporary:
        root = Path(temporary)
        chrome = prepare_disposable_engine(chrome, root)
        core_info = read_core_info(chrome, root)
        baseline = audit_profile(chrome, root / "ordinary")
        seeds = (1, 1, 2)
        runs = [
            audit_profile(
                chrome, root / f"persona-{index}",
                tuple(identity_arguments(native_preview_identity(seed))),
            )
            for index, seed in enumerate(seeds)
        ]
        checks = check_reports(core_info, baseline, runs)
        report = {
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "local Chromium prototype on one host; no anonymity or external-network claim",
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "compiled_core": core_info,
            "ordinary": baseline,
            "persona_runs": runs,
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "checks": checks,
                          "report": str(args.output)}, ensure_ascii=False))
        return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
