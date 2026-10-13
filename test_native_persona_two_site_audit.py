"""Synthetic regression checks for the loopback two-site persona gate."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from native_persona_two_site_audit import language_consistent, parse_accept_language, summarize  # noqa: E402
from test_fingerprint_surface_audit import report  # noqa: E402


def measured() -> dict:
    item = report()
    item["client_hints"].update({"secChUa": '"Chromium";v="155"',
                                 "secChUaPlatform": '"Windows"'})
    return item


class TwoSiteGateTests(unittest.TestCase):
    def test_full_header_parser_rejects_malformed_or_reordered_quality(self) -> None:
        self.assertEqual(parse_accept_language("en-US,en;q=0.9"), ["en-us", "en"])
        for header in (None, "", "en-US,fr;q=1.1", "en-US,fr;q=0.8,en;q=0.9",
                       "en-US,en-US;q=0.9", "en-US,*;q=0.8"):
            self.assertIsNone(parse_accept_language(header))

    def test_two_sites_agree(self) -> None:
        self.assertEqual(summarize([measured(), measured()])["status"], "PASS")

    def test_unrelated_header_fallback_fails(self) -> None:
        value = measured()
        value["http"]["acceptLanguage"] = "en-US,fr;q=0.9"
        self.assertFalse(language_consistent(value))

    def test_worker_intl_mismatch_fails(self) -> None:
        value = measured()
        value["surfaces"]["serviceWorker"]["intlLocale"] = "fr-FR"
        self.assertFalse(summarize([measured(), value])["checks"]["full_languages_and_intl_agree"])

    def test_cross_site_hint_mismatch_fails(self) -> None:
        other = deepcopy(measured())
        other["client_hints"]["uaPlatformVersion"] = '"20.0.0"'
        self.assertFalse(summarize([measured(), other])["checks"]["client_hints_equal_between_sites"])

    def test_missing_hint_fails(self) -> None:
        other = measured()
        other["client_hints"]["secChUa"] = None
        self.assertFalse(summarize([measured(), other])["checks"]["all_requested_hints_present"])

    def test_low_entropy_js_brand_mismatch_fails(self) -> None:
        other = measured()
        other["ua_brands"] = [{"brand": "Chromium", "version": "154"}]
        self.assertFalse(summarize([measured(), other])["checks"]["ua_js_hints_equal_between_sites"])
        self.assertFalse(summarize([measured(), other])["checks"]["all_contexts_and_existing_hints_agree"])

    def test_cross_site_js_mismatch_fails(self) -> None:
        other = measured()
        other["surfaces"]["crossOriginFrame"]["deviceMemory"] = 16
        self.assertFalse(summarize([measured(), other])["checks"]["js_common_surfaces_equal_between_sites"])

    def test_canvas_values_are_outside_this_gate(self) -> None:
        other = measured()
        other["surfaces"]["main"]["canvasPixelSha256"] = "d" * 64
        self.assertTrue(summarize([measured(), other])["checks"]["js_common_surfaces_equal_between_sites"])

    def test_external_attempt_is_reported_but_not_a_p1_failure(self) -> None:
        other = measured()
        other["blocked_external_requests"] = 1
        summary = summarize([measured(), other])
        self.assertEqual(summary["blocked_external_attempts"], [0, 1])
        self.assertEqual(summary["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
