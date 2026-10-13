"""Compare disposable stock and patched Chromium audits from one source commit.

Runs the loopback-only audit for both engines. Full device-trait reports stay in
the caller's private output directory; stdout contains only check names and
booleans. This is not a linkability or external-network anonymity test.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from launcher_integration import check_engine_tree


def read_engine_identity(chrome: Path) -> dict[str, str | None]:
    if chrome.name.lower() != "chrome.exe" or not chrome.is_file():
        raise ValueError("An existing chrome.exe is required")
    check_engine_tree(chrome.parent)
    receipt = json.loads((chrome.parent / "ENGINE_PROVENANCE.json").read_text(encoding="utf-8"))
    return {key: receipt.get(key) for key in
            ("chromium_version", "source_commit", "privacy_patch_sha256")}


def _samples(report: dict) -> list[dict]:
    primary = report.get("profiles")
    repeats = report.get("repeat_profiles")
    if not isinstance(primary, list) or not isinstance(repeats, list) or len(primary) != 2 or len(repeats) != 2:
        raise ValueError("Both two-profile/two-launch report groups are required")
    return [item for pair in zip(primary, repeats) for item in pair]


def _local_gate_passed(report: dict) -> bool:
    groups = [report.get("context_consistency"), report.get("repeat_consistency"),
              report.get("repeat_context_consistency")]
    profile = {key: report.get(key) for key in (
        "profile_surfaces_equal", "profile_http_equal", "profile_client_hints_equal",
        "profile_high_entropy_equal", "profile_platform_equal")}
    return all(value is True for value in profile.values()) and all(
        isinstance(group, list) and len(group) == 2
        and all(isinstance(item, dict) and item and all(value is True for value in item.values())
                for item in group)
        for group in groups
    )


def _ordinary_surfaces(report: dict) -> dict:
    result = json.loads(json.dumps(report))
    for surface in result["surfaces"].values():
        if isinstance(surface, dict):
            surface.pop("hardwareConcurrency", None)
            surface.pop("deviceMemory", None)
    hints = result.get("client_hints")
    if isinstance(hints, dict):
        hints.pop("deviceMemory", None)
    result.pop("blocked_external_requests", None)
    return result


def compare(stock_identity: dict, candidate_identity: dict,
            stock_report: dict, candidate_report: dict,
            expected_patch_sha256: str) -> tuple[dict[str, bool], dict[str, bool]]:
    stock_samples = _samples(stock_report)
    candidate_samples = _samples(candidate_report)
    checks = {
        "same_upstream_commit": bool(stock_identity.get("source_commit"))
        and stock_identity.get("source_commit") == candidate_identity.get("source_commit"),
        "same_chromium_version": bool(stock_identity.get("chromium_version"))
        and stock_identity.get("chromium_version") == candidate_identity.get("chromium_version"),
        "stock_without_privacy_patch": not bool(stock_identity.get("privacy_patch_sha256")),
        "candidate_with_privacy_patch": bool(candidate_identity.get("privacy_patch_sha256")),
        "candidate_patch_matches_public_source": (
            candidate_identity.get("privacy_patch_sha256") == expected_patch_sha256),
        "stock_local_gate": _local_gate_passed(stock_report),
        "candidate_local_gate": _local_gate_passed(candidate_report),
        "other_observed_surfaces_equal": all(
            _ordinary_surfaces(stock) == _ordinary_surfaces(candidate)
            for stock, candidate in zip(stock_samples, candidate_samples)
        ),
    }
    observations: dict[str, bool] = {}
    for key, label in (("hardwareConcurrency", "cpu"), ("deviceMemory", "memory")):
        pairs = [(stock["surfaces"]["main"].get(key), candidate["surfaces"]["main"].get(key))
                 for stock, candidate in zip(stock_samples, candidate_samples)]
        numeric = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                      for pair in pairs for value in pair)
        checks[f"{label}_observed_and_not_above_stock"] = numeric and all(
            candidate <= stock for stock, candidate in pairs)
        observations[f"{label}_strictly_lower_on_this_host"] = numeric and all(
            candidate < stock for stock, candidate in pairs)
    return checks, observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-chrome", required=True, type=Path)
    parser.add_argument("--candidate-chrome", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    stock_chrome = args.stock_chrome.resolve()
    candidate_chrome = args.candidate_chrome.resolve()
    output_dir = args.output_dir.resolve()
    source_root = Path(__file__).resolve().parent.parent
    if output_dir.is_relative_to(source_root):
        parser.error("Private reports must be written outside the source repository")
    if output_dir.exists():
        parser.error("Refusing to overwrite an existing output directory")
    try:
        identities = [read_engine_identity(chrome) for chrome in (stock_chrome, candidate_chrome)]
    except (OSError, ValueError) as error:
        parser.error(str(error))
    output_dir.mkdir(parents=True)
    reports = []
    audit_script = Path(__file__).with_name("fingerprint_surface_audit.py")
    for label, chrome in (("stock", stock_chrome), ("candidate", candidate_chrome)):
        output = output_dir / f"{label}.json"
        result = subprocess.run([sys.executable, str(audit_script), "--chrome", str(chrome),
                                 "--output", str(output)], capture_output=True, text=True,
                                timeout=180, check=False)
        if result.returncode != 0 or not output.is_file():
            print(json.dumps({"status": "failed", "phase": f"{label}_audit",
                              "exit_code": result.returncode}))
            return 1
        reports.append(json.loads(output.read_text(encoding="utf-8")))
    public_patch = source_root / "docs" / "chromium-privacy-baseline.patch"
    expected_patch_sha256 = hashlib.sha256(public_patch.read_bytes()).hexdigest()
    checks, observations = compare(identities[0], identities[1], reports[0], reports[1],
                                   expected_patch_sha256)
    passed = all(checks.values())
    summary = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
               "scope": "one host; loopback; exact upstream commit; no anonymity conclusion",
               "status": "passed" if passed else "failed", "checks": checks,
               "observations": observations}
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "checks": checks,
                      "observations": observations, "output_dir": str(output_dir)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
