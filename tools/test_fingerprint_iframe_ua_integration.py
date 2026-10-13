"""Synthetic iframe UA-CH measurement tests; never start Chromium or read user Data."""

from __future__ import annotations

from copy import deepcopy
import unittest

from fingerprint_surface_audit import evaluate, observation_statuses


def complete_report(version: int = 4) -> dict:
    brands = [{"brand": "Synthetic", "version": "155"}]
    high = {"fullVersionList": [{"brand": "Synthetic", "version": "155.0.0.0"}],
            "platformVersion": "15.0"}
    frame = {"userAgent": "Synthetic Chromium", "deviceMemory": 8,
             "uaBrands": brands, "uaPlatform": "Windows", "uaHighEntropy": high}
    return {
        "measurement_version": version,
        "surfaces": {
            "main": deepcopy(frame), "iframe": deepcopy(frame),
            "crossOriginFrame": deepcopy(frame),
            "worker": deepcopy(frame), "sharedWorker": deepcopy(frame),
            "serviceWorker": deepcopy(frame),
        },
        "http": {"userAgent": "Synthetic Chromium", "acceptLanguage": "en-US,en;q=0.9",
                 "secChUa": '"Synthetic";v="155"', "secChUaPlatform": '"Windows"'},
        "client_hints": {"deviceMemory": "8", "uaFullVersionList": '"Synthetic";v="155.0.0.0"',
                         "uaPlatformVersion": '"15.0"'},
        "ua_high_entropy": high, "ua_brands": brands, "ua_platform": "Windows",
    }


class IframeUaTests(unittest.TestCase):
    def test_version_four_healthy_frame_observations_pass(self) -> None:
        checks = evaluate([complete_report()])[0]
        for name in ("ua_data_main_parity", "ua_data_iframe_parity",
                     "ua_data_cross_origin_iframe_parity"):
            self.assertTrue(checks[name], name)
        self.assertNotIn("missing_ua_frame", observation_statuses([complete_report()]))

    def test_version_four_cross_origin_mismatch_fails(self) -> None:
        report = complete_report()
        report["surfaces"]["crossOriginFrame"]["uaHighEntropy"]["platformVersion"] = "14.0"
        checks = evaluate([report])[0]
        self.assertFalse(checks["ua_data_cross_origin_iframe_parity"])
        self.assertTrue(checks["ua_data_iframe_parity"])

    def test_version_four_missing_field_is_inconclusive_not_pass(self) -> None:
        report = complete_report()
        report["surfaces"]["iframe"].pop("uaHighEntropy")
        checks = evaluate([report])[0]
        self.assertFalse(checks["ua_data_iframe_parity"])
        self.assertIn("missing_ua_frame", observation_statuses([report]))

    def test_version_four_empty_high_entropy_list_is_inconclusive(self) -> None:
        report = complete_report()
        report["surfaces"]["crossOriginFrame"]["uaHighEntropy"]["fullVersionList"] = []
        self.assertFalse(evaluate([report])[0]["ua_data_cross_origin_iframe_parity"])
        self.assertIn("missing_ua_frame", observation_statuses([report]))

    def test_version_three_retains_prior_worker_only_schema(self) -> None:
        report = complete_report(version=3)
        for context in ("main", "iframe", "crossOriginFrame"):
            for field in ("uaBrands", "uaPlatform", "uaHighEntropy"):
                report["surfaces"][context].pop(field)
        checks = evaluate([report])[0]
        self.assertNotIn("ua_data_iframe_parity", checks)
        self.assertTrue(checks["ua_data_dedicated_worker_parity"])
        self.assertNotIn("missing_ua_frame", observation_statuses([report]))


if __name__ == "__main__":
    unittest.main()
