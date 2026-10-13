"""Synthetic integration-gate tests; no Chromium process or user profile is opened."""

from __future__ import annotations

from copy import deepcopy
import unittest

from v5_optin_cross_surface_gate import (CONTEXTS, FRAMES, ObservationUnavailable,
                                         V5_PATCH_SHA256, assess_reports, receipt_checks)


def report(*, optin: bool = False, canvas: str = "a") -> dict:
    digest = canvas * 64
    surfaces = {}
    for context in CONTEXTS:
        surfaces[context] = {
            "userAgent": "Synthetic Chromium",
            "platform": "Win32",
            "language": "en-US", "languages": ["en-US", "en"],
            "intlLocale": "en-US", "hardwareConcurrency": 4 if optin else 16,
            "deviceMemory": 8 if optin else 16,
            "timezone": "UTC" if optin else "Asia/Bangkok",
            "timezoneOffsetMinutes": 0 if optin else -420,
        }
    for context in FRAMES:
        surfaces[context].update({
            "screen": [1920, 1080, 24], "devicePixelRatio": 1,
            "canvas2dSha256": digest, "canvasPixelSha256": digest,
            "webgl": {"vendor": "Synthetic"},
            "webglPixel": {"status": "ok", "sha256": "c" * 64},
            "textMetrics": {"status": "ok", "sha256": "d" * 64},
            "audioSha256": "e" * 64,
            "audioSampleRate": {"status": "ok", "hz": 48000},
        })
    surfaces["worker"]["canvasPixelSha256"] = digest
    return {
        "measurement_version": 2, "blocked_external_requests": 0,
        "surfaces": surfaces, "http": {"userAgent": "Synthetic Chromium"},
        "client_hints": {"deviceMemory": "8" if optin else "16", "secChUa": "synthetic"},
        "ua_high_entropy": {"platformVersion": "synthetic"},
        "ua_brands": [{"brand": "Synthetic", "version": "155"}],
        "ua_platform": "Windows",
    }


def four_reports() -> list[dict]:
    return [report(), report(), report(optin=True, canvas="a"),
            report(optin=True, canvas="b")]


class AssessmentTests(unittest.TestCase):
    def assess(self, reports: list[dict]) -> dict:
        return assess_reports(reports, [{"synthetic_context": True} for _ in reports])

    def test_complete_synthetic_control_passes(self) -> None:
        result = self.assess(four_reports())
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))

    def test_rejected_background_requests_do_not_fail_privacy_gate(self) -> None:
        reports = four_reports()
        for item in reports:
            item["blocked_external_requests"] = 4
        self.assertEqual(self.assess(reports)["status"], "PASS")

    def test_canvas_rotation_is_required(self) -> None:
        reports = four_reports()
        reports[3] = deepcopy(reports[2])
        result = self.assess(reports)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["optin_canvas_rotates_between_fresh_sessions"])

    def test_missing_rendering_field_is_inconclusive(self) -> None:
        reports = four_reports()
        del reports[2]["surfaces"]["main"]["webglPixel"]
        with self.assertRaises(ObservationUnavailable):
            self.assess(reports)

    def test_unsupported_rendering_field_is_inconclusive(self) -> None:
        reports = four_reports()
        reports[2]["surfaces"]["iframe"]["textMetrics"] = {"status": "unsupported"}
        with self.assertRaises(ObservationUnavailable):
            self.assess(reports)

    def test_missing_canvas_digest_is_inconclusive(self) -> None:
        reports = four_reports()
        reports[3]["surfaces"]["worker"].pop("canvasPixelSha256")
        with self.assertRaises(ObservationUnavailable):
            self.assess(reports)

    def test_discordant_noncanvas_optin_is_fail(self) -> None:
        reports = four_reports()
        reports[2]["surfaces"]["main"]["audioSampleRate"]["hz"] = 44100
        result = self.assess(reports)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["optin_noncanvas_rendering_matches_default"])

    def test_wrong_cpu_or_client_hint_is_fail(self) -> None:
        reports = four_reports()
        reports[2]["surfaces"]["worker"]["hardwareConcurrency"] = 8
        reports[3]["client_hints"]["deviceMemory"] = "4"
        result = self.assess(reports)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["optin_cpu_ram_bounded_by_stock"])
        self.assertFalse(result["checks"]["optin_device_memory_hint_matches_js"])

    def test_missing_context_result_is_inconclusive(self) -> None:
        with self.assertRaises(ObservationUnavailable):
            assess_reports(four_reports(), [{"ok": True} for _ in range(3)])

    def test_failed_context_result_is_fail(self) -> None:
        checks = [{"ok": True} for _ in range(4)]
        checks[1]["ok"] = False
        result = assess_reports(four_reports(), checks)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["all_contexts_consistent"])


class ProvenanceTests(unittest.TestCase):
    def receipts(self) -> tuple[dict, dict]:
        stock = {"format": "neantik-chromium-source-build-v1",
                 "source_commit": "a" * 40, "chromium_version": "155.0.8059.40",
                 "privacy_patch_sha256": "", "native_persona_patch_sha256": ""}
        candidate = dict(stock)
        candidate["privacy_patch_sha256"] = V5_PATCH_SHA256
        candidate["native_persona_patch_sha256"] = V5_PATCH_SHA256
        candidate["native_persona_core_info"] = {
            "engine_id": "neantik-chromium", "schema": 2, "compiled_stage": 11,
            "source_commit": stock["source_commit"], "version": stock["chromium_version"],
            "capabilities": {"stable_seed": True, "hardware_concurrency": True,
                             "device_memory": True, "canvas_site_scoped_experimental": True,
                             "timezone": True, "canvas": False,
                             "canvas_opaque_srgb_uint8": False}}
        return stock, candidate

    def test_exact_v5_receipts_pass(self) -> None:
        stock, candidate = self.receipts()
        self.assertTrue(all(receipt_checks(stock, candidate, V5_PATCH_SHA256).values()))

    def test_v4_or_cross_commit_receipt_fails(self) -> None:
        stock, candidate = self.receipts()
        candidate["native_persona_patch_sha256"] = "0" * 64
        candidate["source_commit"] = "b" * 40
        checks = receipt_checks(stock, candidate, V5_PATCH_SHA256)
        self.assertFalse(checks["candidate_exact_v5_patch"])
        self.assertFalse(checks["same_upstream_commit_and_version"])

    def test_missing_capability_fails(self) -> None:
        stock, candidate = self.receipts()
        candidate["native_persona_core_info"]["capabilities"].pop("timezone")
        self.assertFalse(receipt_checks(stock, candidate, V5_PATCH_SHA256)[
            "candidate_compiled_schema_and_capabilities"])


if __name__ == "__main__":
    unittest.main()
