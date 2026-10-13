"""Two loopback-site HTTP/JS language and Client Hint consistency gate.

Uses one disposable saved profile at 127.0.0.1 and localhost. The test proxy
rejects external destinations; the report contains booleans and binary hashes,
not the observed device traits or request headers. This is not an anonymity gate.
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


LANGUAGE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
HINT_FIELDS = ("deviceMemory", "secChUa", "secChUaPlatform",
               "uaFullVersionList", "uaPlatformVersion")
CONTEXTS = ("main", "iframe", "crossOriginFrame", "worker", "sharedWorker", "serviceWorker")


def parse_accept_language(header: object) -> list[str] | None:
    if not isinstance(header, str) or not header:
        return None
    result: list[str] = []
    previous_quality = 1.01
    for token in header.split(","):
        parts = token.strip().split(";")
        if len(parts) not in (1, 2) or not LANGUAGE.fullmatch(parts[0]):
            return None
        quality = 1.0
        if len(parts) == 2:
            match = re.fullmatch(r"q=(0(?:\.\d{1,3})?|1(?:\.0{1,3})?)", parts[1].strip())
            if not match:
                return None
            quality = float(match.group(1))
        if quality <= 0 or quality > previous_quality:
            return None
        previous_quality = quality
        normalized = parts[0].lower()
        if normalized in result:
            return None
        result.append(normalized)
    return result


def language_issue(report: dict) -> str | None:
    observed = parse_accept_language(report.get("http", {}).get("acceptLanguage"))
    if not observed:
        return "http_language_missing_or_malformed"
    for context in CONTEXTS:
        surface = report.get("surfaces", {}).get(context, {})
        languages = surface.get("languages")
        if not isinstance(languages, list) or not languages or not all(
                isinstance(item, str) and LANGUAGE.fullmatch(item) for item in languages):
            return "js_languages_missing_or_malformed"
        normalized = [item.lower() for item in languages]
        primary = surface.get("language")
        locale = surface.get("intlLocale")
        if not isinstance(primary, str) or primary.lower() != normalized[0]:
            return "js_primary_language_disagrees"
        fallback = normalized[0].split("-", 1)[0]
        if not isinstance(locale, str) or locale.lower() not in (*normalized, fallback):
            return "intl_locale_disagrees"
        # Chromium may append the base language to the HTTP header if JS
        # exposes only the regional preference. No unrelated extra is allowed.
        allowed = (normalized, normalized + [fallback]) if fallback not in normalized else (normalized,)
        if observed not in allowed:
            return "http_js_language_lists_disagree"
    return None


def language_consistent(report: dict) -> bool:
    return language_issue(report) is None


def summarize(reports: list[dict]) -> dict:
    if len(reports) != 2:
        raise ValueError("Exactly two loopback-site reports are required")
    first, second = reports
    def common_surfaces(report: dict) -> dict:
        return {name: {key: value for key, value in surface.items()
                       if key not in ("canvas2dSha256", "canvasPixelSha256")}
                for name, surface in report["surfaces"].items()}
    checks = {
        "all_contexts_and_existing_hints_agree": all(all(evaluate([item])[0].values()) for item in reports),
        "full_languages_and_intl_agree": all(language_consistent(item) for item in reports),
        "all_requested_hints_present": all(
            all(isinstance(item.get("client_hints", {}).get(field), str)
                and bool(item["client_hints"][field]) for field in HINT_FIELDS)
            for item in reports),
        "http_headers_equal_between_sites": first.get("http") == second.get("http"),
        "client_hints_equal_between_sites": first.get("client_hints") == second.get("client_hints"),
        "ua_js_hints_equal_between_sites": (
            first.get("ua_brands") == second.get("ua_brands")
            and first.get("ua_high_entropy") == second.get("ua_high_entropy")
            and first.get("ua_platform") == second.get("ua_platform")),
        "js_common_surfaces_equal_between_sites": common_surfaces(first) == common_surfaces(second),
    }
    return {"sites": ["127.0.0.1", "localhost"], "checks": checks,
            "language_issue_codes": [language_issue(item) for item in reports],
            "blocked_external_attempts": [item.get("blocked_external_requests") for item in reports],
            "status": "PASS" if all(checks.values()) else "FAIL"}


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
    if (os.name != "nt" or chrome.name.lower() != "chrome.exe" or not chrome.is_file()
            or not chrome.with_name("chrome.dll").is_file()):
        parser.error("An existing Windows chrome.exe and adjacent chrome.dll are required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be a new path in an existing directory")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "one disposable profile, two loopback top-level sites; not anonymity approval",
              "chrome_exe_sha256": sha256(chrome),
              "chrome_dll_sha256": sha256(chrome.with_name("chrome.dll")),
              "status": "INCONCLUSIVE"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-two-site-engine-") as engine_dir:
            disposable_chrome = prepare_disposable_engine(chrome, Path(engine_dir))
            with tempfile.TemporaryDirectory(prefix="neantik-two-site-profile-") as profile_dir:
                root = Path(profile_dir)
                flags = tuple(identity_arguments(native_preview_identity(319771)))
                reports = [audit_profile(disposable_chrome, root, flags,
                                         reuse_existing=index > 0, primary_hostname=host)
                           for index, host in enumerate(("127.0.0.1", "localhost"))]
        report.update(summarize(reports))
    except Exception as error:
        report["reason_code"] = type(error).__name__
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks"),
                      "reason_code": report.get("reason_code"), "report": str(args.output)},
                     ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2}.get(report["status"], 3)


if __name__ == "__main__":
    raise SystemExit(main())
