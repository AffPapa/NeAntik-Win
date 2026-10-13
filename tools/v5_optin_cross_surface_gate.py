"""Bounded, loopback-only stock/default/V5 opt-in fingerprint consistency gate.

Four disposable, owned Chromium launches are measured. The output contains only
boolean checks and binary hashes, never raw browser traits or request headers.
This is not a linkability, real-site compatibility, or anonymity assessment.
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
from launcher_integration import check_engine_tree
from native_persona_context_audit import prepare_disposable_engine
from profile_identity import identity_arguments, native_preview_identity


SOURCE_ROOT = Path(__file__).resolve().parents[1]
PATCH = SOURCE_ROOT / "docs" / "chromium-native-persona-prototype-v5.patch"
V5_PATCH_SHA256 = "0c592ca18304823faf8f0e2534619c5f7b458072e451ede81eb528a2b8c76d22"
CONTEXTS = ("main", "iframe", "crossOriginFrame", "worker", "sharedWorker", "serviceWorker")
FRAMES = ("main", "iframe", "crossOriginFrame")
CANVAS = ("canvas2dSha256", "canvasPixelSha256")
OBSERVATIONS = ("webglPixel", "textMetrics", "audioSampleRate")
UNCHANGED = ("webgl", "webglPixel", "textMetrics", "audioSha256", "audioSampleRate",
             "userAgent", "platform", "language", "languages", "intlLocale",
             "screen", "devicePixelRatio")
REQUIRED_CAPABILITIES = ("stable_seed", "hardware_concurrency", "device_memory",
                         "canvas_site_scoped_experimental", "timezone")
HEX64 = re.compile(r"[a-f0-9]{64}\Z")


class ObservationUnavailable(ValueError):
    """A required result is missing or unsupported, so no PASS/FAIL inference is safe."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def receipt_checks(stock: dict, candidate: dict, patch_digest: str) -> dict[str, bool]:
    """Exact public V5 receipt and same-upstream stock control."""
    info = candidate.get("native_persona_core_info")
    info = info if isinstance(info, dict) else {}
    caps = info.get("capabilities")
    caps = caps if isinstance(caps, dict) else {}
    return {
        "public_patch_exact_v5": patch_digest == V5_PATCH_SHA256,
        "both_source_built_receipts": stock.get("format") == candidate.get("format") == "neantik-chromium-source-build-v1",
        "same_upstream_commit_and_version": bool(stock.get("source_commit"))
        and stock.get("source_commit") == candidate.get("source_commit")
        and bool(stock.get("chromium_version"))
        and stock.get("chromium_version") == candidate.get("chromium_version"),
        "stock_unpatched": not stock.get("privacy_patch_sha256")
        and not stock.get("native_persona_patch_sha256"),
        "candidate_exact_v5_patch": candidate.get("privacy_patch_sha256") == V5_PATCH_SHA256
        and candidate.get("native_persona_patch_sha256") == V5_PATCH_SHA256,
        "candidate_compiled_schema_and_capabilities": info.get("engine_id") == "neantik-chromium"
        and info.get("schema") == 2 and info.get("compiled_stage") == 11
        and info.get("version") == candidate.get("chromium_version")
        and info.get("source_commit") == candidate.get("source_commit")
        and caps.get("canvas") is False and caps.get("canvas_opaque_srgb_uint8") is False
        and all(caps.get(name) is True for name in REQUIRED_CAPABILITIES),
    }


def _surface(report: dict, context: str) -> dict:
    surfaces = report.get("surfaces")
    value = surfaces.get(context) if isinstance(surfaces, dict) else None
    if not isinstance(value, dict):
        raise ObservationUnavailable("missing_context")
    return value


def _field(report: dict, context: str, name: str):
    surface = _surface(report, context)
    if name not in surface or surface[name] is None:
        raise ObservationUnavailable("missing_surface_field")
    return surface[name]


def _observed(report: dict) -> None:
    if report.get("measurement_version") != 2 or type(report.get("blocked_external_requests")) is not int or report["blocked_external_requests"] < 0:
        raise ObservationUnavailable("incomplete_measurement")
    for context in CONTEXTS:
        for name in ("hardwareConcurrency", "deviceMemory", "timezone", "timezoneOffsetMinutes"):
            _field(report, context, name)
    for context in FRAMES:
        for name in CANVAS:
            value = _field(report, context, name)
            if not isinstance(value, str) or not HEX64.fullmatch(value):
                raise ObservationUnavailable("canvas_digest_unavailable")
        for name in ("webglPixel", "textMetrics"):
            value = _field(report, context, name)
            if not isinstance(value, dict) or value.get("status") != "ok" or not isinstance(value.get("sha256"), str) or not HEX64.fullmatch(value["sha256"]):
                raise ObservationUnavailable("rendering_observation_unavailable")
        rate = _field(report, context, "audioSampleRate")
        if not isinstance(rate, dict) or rate.get("status") != "ok" or type(rate.get("hz")) not in (int, float) or not 8000 <= rate["hz"] <= 192000:
            raise ObservationUnavailable("audio_observation_unavailable")
        for name in UNCHANGED:
            _field(report, context, name)
    worker_pixels = _field(report, "worker", "canvasPixelSha256")
    if not isinstance(worker_pixels, str) or not HEX64.fullmatch(worker_pixels):
        raise ObservationUnavailable("worker_canvas_digest_unavailable")
    for field in ("http", "client_hints", "ua_high_entropy", "ua_brands", "ua_platform"):
        if report.get(field) is None:
            raise ObservationUnavailable("missing_http_or_ua_observation")


def assess_reports(reports: list[dict], context_checks: list[dict[str, bool]]) -> dict:
    """Pure verdict; unit tests use synthetic reports without launching Chromium."""
    if len(reports) != 4 or len(context_checks) != 4:
        raise ObservationUnavailable("four_launches_required")
    for report in reports:
        _observed(report)
    if any(not isinstance(checks, dict) or not checks for checks in context_checks):
        raise ObservationUnavailable("context_checks_missing")
    stock, ordinary, opt_first, opt_second = reports
    checks = {
        "all_contexts_consistent": all(all(value is True for value in item.values())
                                        for item in context_checks),
        "external_attempts_counted_by_rejector": all(
            item["blocked_external_requests"] >= 0 for item in reports),
        "ordinary_http_and_hints_match_stock": all(
            stock[name] == ordinary[name]
            for name in ("http", "client_hints", "ua_high_entropy", "ua_brands", "ua_platform")),
        "optin_http_and_hints_match_default": all(
            ordinary[name] == run[name]
            for run in (opt_first, opt_second)
            for name in ("http", "client_hints", "ua_high_entropy", "ua_brands", "ua_platform")
            if name != "client_hints")
        and all({key: value for key, value in ordinary["client_hints"].items() if key != "deviceMemory"}
                == {key: value for key, value in run["client_hints"].items() if key != "deviceMemory"}
                for run in (opt_first, opt_second)),
        "ordinary_measured_surfaces_match_stock": all(
            _field(stock, context, name) == _field(ordinary, context, name)
            for context in FRAMES for name in (*UNCHANGED, *CANVAS, "hardwareConcurrency",
                                                "deviceMemory", "timezone", "timezoneOffsetMinutes")),
        "optin_noncanvas_rendering_matches_default": all(
            _field(ordinary, context, name) == _field(run, context, name)
            for run in (opt_first, opt_second) for context in FRAMES for name in UNCHANGED),
        "optin_cpu_ram_bounded_by_stock": all(
            _field(run, context, "hardwareConcurrency") == min(_field(stock, context, "hardwareConcurrency"), 4)
            and _field(run, context, "deviceMemory") == min(_field(stock, context, "deviceMemory"), 8)
            for run in (opt_first, opt_second) for context in CONTEXTS),
        "optin_utc_in_all_contexts": all(
            _field(run, context, "timezone") == "UTC"
            and _field(run, context, "timezoneOffsetMinutes") == 0
            for run in (opt_first, opt_second) for context in CONTEXTS),
        "optin_device_memory_hint_matches_js": all(
            str(run["client_hints"].get("deviceMemory")) == str(_field(run, "main", "deviceMemory"))
            for run in (opt_first, opt_second)),
        "optin_canvas_rotates_between_fresh_sessions": all(
            _field(opt_first, "main", name) != _field(opt_second, "main", name)
            for name in CANVAS),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _read_receipt(chrome: Path) -> dict:
    if chrome.name.lower() != "chrome.exe" or not chrome.is_file() or not chrome.with_name("chrome.dll").is_file():
        raise ObservationUnavailable("chromium_binary_missing")
    check_engine_tree(chrome.parent)
    value = json.loads((chrome.parent / "ENGINE_PROVENANCE.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ObservationUnavailable("invalid_receipt")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-chrome", type=Path, required=True)
    parser.add_argument("--candidate-chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stock = args.stock_chrome.resolve()
    candidate = args.candidate_chrome.resolve()
    output = args.output.resolve()
    if os.name != "nt":
        parser.error("Windows is required")
    if output.is_relative_to(SOURCE_ROOT) or output.exists() or not output.parent.is_dir():
        parser.error("Output must be a new private file outside the source repository")
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "four owned loopback-only disposable sessions on one Windows host; no anonymity claim",
              "status": "INCONCLUSIVE", "checks": {}}
    try:
        result["binary_sha256"] = {
            label: {"chrome_exe": sha256(chrome), "chrome_dll": sha256(chrome.with_name("chrome.dll"))}
            for label, chrome in (("stock", stock), ("candidate", candidate))
        }
        stock_receipt = _read_receipt(stock)
        candidate_receipt = _read_receipt(candidate)
        provenance = receipt_checks(stock_receipt, candidate_receipt, sha256(PATCH))
        result["checks"].update(provenance)
        if not all(provenance.values()):
            result["status"] = "FAIL"
        else:
            with tempfile.TemporaryDirectory(prefix="neantik-v5-cross-surface-") as temporary:
                root = Path(temporary)
                stock_copy = prepare_disposable_engine(stock, root / "stock-engine")
                candidate_copy = prepare_disposable_engine(candidate, root / "candidate-engine")
                flags = tuple(identity_arguments(native_preview_identity(1597331)))
                sessions = (
                    (stock_copy, root / "stock", ()),
                    (candidate_copy, root / "ordinary", ()),
                    (candidate_copy, root / "optin-first", flags),
                    (candidate_copy, root / "optin-second", flags),
                )
                reports = [audit_profile(chrome, profile, launch_flags)
                           for chrome, profile, launch_flags in sessions]
                verdict = assess_reports(reports, [evaluate([item])[0] for item in reports])
                result["checks"].update(verdict["checks"])
                result["status"] = verdict["status"]
    except Exception as error:
        # Exception text may contain local paths, URLs or browser output.
        result["reason_code"] = type(error).__name__
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result["checks"],
                      "reason_code": result.get("reason_code")}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2, "INCONCLUSIVE": 3}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
