"""Pure regression checks for the private loopback fingerprint audit."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from fingerprint_surface_audit import (compare_fresh_profiles, compare_repeat_launches,
                                       evaluate, observation_statuses)  # noqa: E402


def report():
    common = {"userAgent": "Chromium test", "platform": "Win32", "language": "en-US",
              "languages": ["en-US"], "intlLocale": "en-US",
              "hardwareConcurrency": 4, "deviceMemory": 8,
              "timezone": "Etc/UTC", "timezoneOffsetMinutes": 0}
    window = {**common, "screen": [1000, 800, 24], "devicePixelRatio": 1,
              "canvas2dSha256": "a" * 64, "canvasPixelSha256": "c" * 64,
              "audioSha256": "e" * 64,
              "webglPixel": {"status": "ok", "sha256": "1" * 64},
              "textMetrics": {"status": "ok", "sha256": "2" * 64},
              "audioSampleRate": {"status": "ok", "hz": 44100},
              "webgl": {"vendor": "test", "renderer": "test", "unmaskedVendor": None,
                        "unmaskedRenderer": None}}
    ua_data = {"uaBrands": [{"brand": "Chromium", "version": "155"}],
               "uaPlatform": "Windows",
               "uaHighEntropy": {"fullVersionList": [{"brand": "Chromium", "version": "155.0.8059.40"}],
                                 "platformVersion": "19.0.0"}}
    worker = {**common, **deepcopy(ua_data), "canvasPixelSha256": "c" * 64}
    return {"measurement_version": 3,
            "surfaces": {"main": deepcopy(window), "iframe": deepcopy(window),
                         "crossOriginFrame": deepcopy(window), "worker": worker,
                         "sharedWorker": {**common, **deepcopy(ua_data)},
                         "serviceWorker": {**common, **deepcopy(ua_data)}},
            "http": {"userAgent": "Chromium test", "acceptLanguage": "en-US,en;q=0.9",
                     "secChUa": '"Chromium";v="155"', "secChUaPlatform": '"Windows"'},
            "client_hints": {"deviceMemory": "8", "secChUa": '"Chromium";v="155"',
                             "secChUaPlatform": '"Windows"',
                             "uaFullVersionList": '"Chromium";v="155.0.8059.40"',
                             "uaPlatformVersion": '"19.0.0"'},
            "ua_high_entropy": {"fullVersionList": [{"brand": "Chromium", "version": "155.0.8059.40"}],
                                "platformVersion": "19.0.0"},
            "ua_brands": [{"brand": "Chromium", "version": "155"}],
            "ua_platform": "Windows",
            "blocked_external_requests": 0}


class FingerprintAuditEvaluationTests(unittest.TestCase):
    def test_consistent_contexts_and_client_hint(self):
        self.assertTrue(all(evaluate([report()])[0].values()))

    def test_mismatched_worker_value_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["worker"]["hardwareConcurrency"] = 16
        self.assertFalse(evaluate([value])[0]["main_worker_common"])

    def test_mismatched_cross_origin_frame_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["crossOriginFrame"]["deviceMemory"] = 16
        self.assertFalse(evaluate([value])[0]["main_cross_origin_frame"])

    def test_canvas_and_webgl_context_mismatch_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["iframe"]["canvas2dSha256"] = "b" * 64
        value["surfaces"]["crossOriginFrame"]["webgl"]["renderer"] = "different"
        checks = evaluate([value])[0]
        self.assertFalse(checks["canvas2d_iframe_parity"])
        self.assertFalse(checks["webgl_cross_origin_parity"])

    def test_worker_canvas_pixel_mismatch_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["worker"]["canvasPixelSha256"] = "d" * 64
        self.assertFalse(evaluate([value])[0]["canvas_pixels_dedicated_worker_parity"])

    def test_audio_context_mismatch_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["crossOriginFrame"]["audioSha256"] = "f" * 64
        self.assertFalse(evaluate([value])[0]["audio_cross_origin_parity"])

    def test_missing_audio_observation_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["main"]["audioSha256"] = None
        self.assertFalse(evaluate([value])[0]["audio_observed"])

    def test_missing_rendering_observation_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["main"]["canvas2dSha256"] = None
        value["surfaces"]["main"]["webgl"] = None
        checks = evaluate([value])[0]
        self.assertFalse(checks["canvas2d_observed"])
        self.assertFalse(checks["webgl_observed"])

    def test_webgl_pixel_digest_mismatch_is_rejected(self):
        value = report()
        value["surfaces"]["crossOriginFrame"]["webglPixel"]["sha256"] = "3" * 64
        self.assertFalse(evaluate([value])[0]["webgl_pixel_cross_origin_parity"])

    def test_text_metrics_missing_or_malformed_is_rejected(self):
        value = report()
        value["surfaces"]["main"]["textMetrics"] = {"status": "ok", "sha256": "not-a-digest"}
        self.assertFalse(evaluate([value])[0]["text_metrics_observed"])

    def test_unsupported_webgl_and_timed_out_audio_are_not_pass(self):
        value = report()
        value["surfaces"]["main"]["webglPixel"] = {"status": "unsupported"}
        value["surfaces"]["main"]["audioSampleRate"] = {"status": "timeout"}
        checks = evaluate([value])[0]
        self.assertFalse(checks["webgl_pixel_observed"])
        self.assertFalse(checks["audio_sample_rate_observed"])
        self.assertIn("unsupported", observation_statuses([value]))
        self.assertIn("timeout", observation_statuses([value]))

    def test_audio_sample_rate_mismatch_is_rejected(self):
        value = report()
        value["surfaces"]["iframe"]["audioSampleRate"]["hz"] = 48000
        self.assertFalse(evaluate([value])[0]["audio_sample_rate_iframe_parity"])

    def test_legacy_report_without_new_fields_remains_evaluable(self):
        value = report()
        del value["measurement_version"]
        for context in ("main", "iframe", "crossOriginFrame"):
            for field in ("webglPixel", "textMetrics", "audioSampleRate"):
                del value["surfaces"][context][field]
        checks = evaluate([value])[0]
        self.assertTrue(all(checks.values()))
        self.assertNotIn("webgl_pixel_observed", checks)

    def test_mismatched_shared_worker_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["sharedWorker"]["hardwareConcurrency"] = 16
        self.assertFalse(evaluate([value])[0]["main_shared_worker_common"])

    def test_mismatched_service_worker_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["serviceWorker"]["deviceMemory"] = 16
        self.assertFalse(evaluate([value])[0]["main_service_worker_common"])

    def test_mismatched_date_timezone_offset_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["serviceWorker"]["timezoneOffsetMinutes"] = -420
        self.assertFalse(evaluate([value])[0]["main_service_worker_common"])

    def test_mismatched_client_hint_is_rejected(self):
        value = report()
        value["client_hints"]["deviceMemory"] = "16"
        self.assertFalse(evaluate([value])[0]["device_memory_hint_parity"])

    def test_malformed_client_hint_is_rejected(self):
        value = report()
        value["client_hints"]["deviceMemory"] = "unparseable"
        self.assertFalse(evaluate([value])[0]["device_memory_hint_parity"])

    def test_unobserved_hint_fails_the_audit(self):
        value = report()
        value["client_hints"]["deviceMemory"] = None
        self.assertFalse(evaluate([value])[0]["device_memory_hint_parity"])

    def test_mismatched_high_entropy_ua_hint_is_rejected(self):
        value = report()
        value["client_hints"]["uaFullVersionList"] = '"Chromium";v="154.0.0.0"'
        self.assertFalse(evaluate([value])[0]["ua_full_version_hint_parity"])

    def test_mismatched_low_entropy_ua_hint_is_rejected(self):
        value = report()
        value["http"]["secChUa"] = '"Chromium";v="154"'
        self.assertFalse(evaluate([value])[0]["ua_brand_hint_parity"])

    def test_missing_high_entropy_ua_hint_is_rejected(self):
        value = report()
        value["client_hints"]["uaPlatformVersion"] = None
        self.assertFalse(evaluate([value])[0]["ua_platform_version_hint_parity"])

    def test_worker_ua_data_mismatch_is_rejected_in_each_context(self):
        names = (("worker", "dedicated_worker"),
                 ("sharedWorker", "shared_worker"),
                 ("serviceWorker", "service_worker"))
        for context, name in names:
            with self.subTest(context=context):
                value = report()
                value["surfaces"][context]["uaHighEntropy"]["platformVersion"] = "20.0.0"
                self.assertFalse(evaluate([value])[0][f"ua_data_{name}_parity"])

    def test_missing_worker_ua_data_is_rejected_in_each_context(self):
        names = (("worker", "dedicated_worker"),
                 ("sharedWorker", "shared_worker"),
                 ("serviceWorker", "service_worker"))
        for context, name in names:
            with self.subTest(context=context):
                value = report()
                del value["surfaces"][context]["uaHighEntropy"]
                self.assertFalse(evaluate([value])[0][f"ua_data_{name}_parity"])

    def test_version_two_report_without_worker_ua_data_remains_evaluable(self):
        value = report()
        value["measurement_version"] = 2
        for context in ("worker", "sharedWorker", "serviceWorker"):
            for field in ("uaBrands", "uaPlatform", "uaHighEntropy"):
                del value["surfaces"][context][field]
        checks = evaluate([value])[0]
        self.assertTrue(all(checks.values()))
        self.assertNotIn("ua_data_dedicated_worker_parity", checks)

    def test_mismatched_primary_http_language_is_rejected(self):
        value = report()
        value["http"]["acceptLanguage"] = "fr-FR,fr;q=0.9"
        self.assertFalse(evaluate([value])[0]["js_http_primary_language"])

    def test_missing_primary_http_language_is_rejected(self):
        value = report()
        value["http"]["acceptLanguage"] = None
        self.assertFalse(evaluate([value])[0]["js_http_primary_language"])

    def test_mismatched_platform_hint_is_rejected(self):
        value = report()
        value["http"]["secChUaPlatform"] = '"Linux"'
        self.assertFalse(evaluate([value])[0]["ua_platform_hint_parity"])

    def test_missing_platform_hint_is_rejected(self):
        value = report()
        value["http"]["secChUaPlatform"] = None
        self.assertFalse(evaluate([value])[0]["ua_platform_hint_parity"])

    def test_fresh_profile_http_difference_is_rejected(self):
        first, second = report(), report()
        second["http"]["acceptLanguage"] = "fr-FR,fr;q=0.9"
        checks = compare_fresh_profiles([first, second])
        self.assertTrue(checks["profile_surfaces_equal"])
        self.assertFalse(checks["profile_http_equal"])

    def test_fresh_profile_hint_difference_is_rejected(self):
        first, second = report(), report()
        second["client_hints"]["uaPlatformVersion"] = '"20.0.0"'
        self.assertFalse(compare_fresh_profiles([first, second])["profile_client_hints_equal"])

    def test_fresh_profile_count_is_required(self):
        with self.assertRaises(ValueError):
            compare_fresh_profiles([report()])

    def test_repeat_launch_mismatch_is_rejected(self):
        first, second = report(), report()
        second["surfaces"]["main"]["canvasPixelSha256"] = "d" * 64
        self.assertFalse(compare_repeat_launches([first, second])["repeat_surfaces_equal"])

    def test_repeat_launch_count_is_required(self):
        with self.assertRaises(ValueError):
            compare_repeat_launches([report()])

if __name__ == "__main__":
    unittest.main()
