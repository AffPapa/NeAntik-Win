"""Pure-data regression checks for the disposable native-persona audit."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from native_persona_context_audit import REQUIRED_CAPABILITIES, check_reports  # noqa: E402


def report(cpu: int, memory: float, timezone: str = "UTC") -> dict:
    main = {
        "userAgent": "test-UA", "platform": "test-platform", "language": "en-US",
        "languages": ["en-US"], "hardwareConcurrency": cpu,
        "deviceMemory": memory, "timezone": timezone,
        "timezoneOffsetMinutes": 0 if timezone == "UTC" else -420,
        "screen": [1280, 800, 24], "devicePixelRatio": 1,
        "canvas2dSha256": "a" * 64,
        "webgl": {"vendor": "test", "renderer": "test", "unmaskedVendor": None,
                  "unmaskedRenderer": None},
    }
    worker = {key: main[key] for key in (
        "userAgent", "platform", "language", "languages",
        "hardwareConcurrency", "deviceMemory", "timezone", "timezoneOffsetMinutes",
    )}
    return {
        "surfaces": {
            "main": main, "iframe": dict(main), "crossOriginFrame": dict(main),
            "worker": worker, "sharedWorker": dict(worker), "serviceWorker": dict(worker),
        },
        "http": {"userAgent": "test-UA"},
        "client_hints": {"deviceMemory": str(memory),
                         "uaFullVersionList": '"Chromium";v="155.0.8059.40"',
                         "uaPlatformVersion": '"19.0.0"'},
        "ua_high_entropy": {"fullVersionList": [{"brand": "Chromium", "version": "155.0.8059.40"}],
                            "platformVersion": "19.0.0"},
    }


class NativePersonaContextAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = {"engine_id": "neantik-chromium", "schema": 2,
                     "capabilities": {name: True for name in REQUIRED_CAPABILITIES}}
        self.baseline = report(8, 16, "Asia/Bangkok")
        self.runs = [report(4, 8) for _ in range(3)]

    def test_valid_coherent_persona(self) -> None:
        self.assertTrue(all(check_reports(self.core, self.baseline, self.runs).values()))

    def test_rejects_old_core_and_worker_mismatch(self) -> None:
        self.core["schema"] = 1
        self.runs[1]["surfaces"]["worker"]["timezone"] = "Asia/Bangkok"
        checks = check_reports(self.core, self.baseline, self.runs)
        self.assertFalse(checks["compiled_core_schema_2"])
        self.assertFalse(checks["all_contexts_and_http_hints_agree"])
        self.assertFalse(checks["same_seed_repeats"])
        self.assertFalse(checks["timezone_is_utc_in_all_contexts"])

    def test_rejects_values_above_stock_host(self) -> None:
        self.baseline = report(2, 4, "Asia/Bangkok")
        checks = check_reports(self.core, self.baseline, self.runs)
        self.assertFalse(checks["cpu_bounded_by_stock"])
        self.assertFalse(checks["memory_bounded_by_stock"])

    def test_rejects_date_timezone_disagreement(self) -> None:
        self.runs[0]["surfaces"]["serviceWorker"]["timezoneOffsetMinutes"] = -420
        checks = check_reports(self.core, self.baseline, self.runs)
        self.assertFalse(checks["date_timezone_offset_is_zero_in_all_contexts"])
        self.assertFalse(checks["all_contexts_and_http_hints_agree"])

    def test_canvas_linkability_is_separate_from_common_surfaces(self) -> None:
        for surface in self.runs[2]["surfaces"].values():
            if "canvas2dSha256" in surface:
                surface["canvas2dSha256"] = "b" * 64
        checks = check_reports(self.core, self.baseline, self.runs)
        self.assertTrue(checks["different_seed_keeps_common_surfaces"])
        self.assertFalse(checks["different_seed_canvas_identical"])


if __name__ == "__main__":
    unittest.main()
