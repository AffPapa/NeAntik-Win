"""Synthetic V5 Canvas compatibility verdict tests; no browser is launched."""

from __future__ import annotations

from copy import deepcopy
import unittest

from v5_canvas_compat_perf_gate import (CHECKS, SAMPLE_COUNT, ObservationUnavailable,
                                        assess_observations, validate_observation)


def observation(token: str = "synthetic") -> dict:
    return {"token": token, "checks": {name: True for name in CHECKS},
            "p50_ms": 0.4, "p95_ms": 1.2, "sample_count": SAMPLE_COUNT}


class CanvasVerdictTests(unittest.TestCase):
    def test_complete_three_mode_report_passes(self) -> None:
        result = assess_observations([observation() for _ in range(3)])
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))

    def test_missing_mode_is_inconclusive(self) -> None:
        with self.assertRaises(ObservationUnavailable):
            assess_observations([observation(), observation()])

    def test_missing_api_check_is_inconclusive(self) -> None:
        cases = [observation() for _ in range(3)]
        del cases[2]["checks"]["blob_png"]
        with self.assertRaises(ObservationUnavailable):
            assess_observations(cases)

    def test_wrong_check_type_is_inconclusive(self) -> None:
        value = observation()
        value["checks"]["repeat_pixels"] = "true"
        with self.assertRaises(ObservationUnavailable):
            validate_observation(value)

    def test_failed_semantics_is_fail(self) -> None:
        cases = [observation() for _ in range(3)]
        cases[2]["checks"]["repeat_pixels"] = False
        result = assess_observations(cases)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["optin_repeat_pixels"])

    def test_missing_and_nonfinite_timing_is_inconclusive(self) -> None:
        for bad in (float("nan"), float("inf"), -1, "1.2", None):
            with self.subTest(value=bad):
                value = observation()
                value["p95_ms"] = bad
                with self.assertRaises(ObservationUnavailable):
                    validate_observation(value)

    def test_sample_count_and_order_required(self) -> None:
        value = observation()
        value["sample_count"] = SAMPLE_COUNT - 1
        with self.assertRaises(ObservationUnavailable):
            validate_observation(value)
        value = observation()
        value["p50_ms"] = 2
        with self.assertRaises(ObservationUnavailable):
            validate_observation(value)

    def test_slow_optin_fails_budget(self) -> None:
        cases = [observation() for _ in range(3)]
        cases[2]["p95_ms"] = 150
        result = assess_observations(cases)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["optin_p95_absolute"])


if __name__ == "__main__":
    unittest.main()
