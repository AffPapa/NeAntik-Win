"""Synthetic verdict tests for the bounded WebGL audit; no browser launch."""

from __future__ import annotations

import unittest

from webgl_surface_consistency_gate import (
    CONTEXTS, MODES, ObservationUnavailable, assess_observations,
    validate_observation,
)


def observation() -> dict:
    return {"token": "a" * 32, **{
        context: {"status": "ok", "sha256": "b" * 64, "extensionCount": 24}
        for context in CONTEXTS
    }}


def six_runs() -> dict[str, list[dict]]:
    return {mode: [observation(), observation()] for mode in MODES}


class WebGLVerdictTests(unittest.TestCase):
    def test_complete_parity_passes(self) -> None:
        result = assess_observations(six_runs())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["checks"]), 10)

    def test_missing_run_is_inconclusive(self) -> None:
        cases = six_runs()
        cases["optin"].pop()
        with self.assertRaises(ObservationUnavailable):
            assess_observations(cases)

    def test_missing_context_is_inconclusive(self) -> None:
        value = observation()
        del value["webgl2"]
        with self.assertRaises(ObservationUnavailable):
            validate_observation(value)

    def test_unsupported_and_error_are_inconclusive(self) -> None:
        for status in ("unsupported", "error", "timeout"):
            with self.subTest(status=status):
                value = observation()
                value["webgl"]["status"] = status
                with self.assertRaises(ObservationUnavailable):
                    validate_observation(value)

    def test_bad_hash_and_count_are_inconclusive(self) -> None:
        for digest, count in (("abc", 24), ("b" * 64, -1), ("b" * 64, "24")):
            with self.subTest(digest=digest, count=count):
                value = observation()
                value["webgl2"].update(sha256=digest, extensionCount=count)
                with self.assertRaises(ObservationUnavailable):
                    validate_observation(value)

    def test_mode_mismatch_is_fail(self) -> None:
        cases = six_runs()
        cases["optin"][0]["webgl"]["sha256"] = "c" * 64
        cases["optin"][1]["webgl"]["sha256"] = "c" * 64
        result = assess_observations(cases)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["optin_webgl_stock_parity"])
        self.assertTrue(result["checks"]["optin_webgl_repeat"])

    def test_restart_mismatch_is_fail(self) -> None:
        cases = six_runs()
        cases["stock"][1]["webgl2"]["extensionCount"] = 23
        result = assess_observations(cases)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["stock_webgl2_repeat"])


if __name__ == "__main__":
    unittest.main()
