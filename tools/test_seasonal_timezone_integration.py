"""Synthetic checks for the fixed-date V5 timezone gate; no browser needed."""

from __future__ import annotations

import unittest

from seasonal_timezone_gate import CONTEXTS, SEASONS, ObservationUnavailable, assess, expected_epoch


def sample() -> dict:
    report = {}
    for context in CONTEXTS:
        report[context] = {}
        for season, date in (("winter", "Thu Jan 15 2026"), ("summer", "Wed Jul 15 2026")):
            report[context][season] = {
                "epochMilliseconds": expected_epoch(season),
                "timezone": "UTC", "offsetMinutes": 0,
                "localHours": 12, "localMinutes": 0, "utcHours": 12, "utcMinutes": 0,
                "dateString": f"{date} 12:00:00 GMT+0000 (Coordinated Universal Time)",
                "intlDefault": f"{date}, 12:00 UTC", "intlUTC": f"{date}, 12:00 UTC",
            }
    return report


class SeasonalTimezoneGateTests(unittest.TestCase):
    def test_expected_epoch_distinguishes_seasons(self) -> None:
        self.assertEqual(expected_epoch("winter"), 1768478400000)
        self.assertEqual(expected_epoch("summer"), 1784116800000)

    def test_consistent_utc_passes(self) -> None:
        checks = assess(sample())
        self.assertEqual(len(checks), len(SEASONS) * 5)
        self.assertTrue(all(checks.values()))

    def test_dst_offset_in_one_worker_fails(self) -> None:
        report = sample()
        report["worker"]["summer"]["offsetMinutes"] = -60
        checks = assess(report)
        self.assertFalse(checks["summer_all_contexts_equal"])
        self.assertFalse(checks["summer_utc_date_offset_and_clock"])
        self.assertTrue(checks["winter_all_contexts_equal"])

    def test_default_intl_mismatch_fails(self) -> None:
        report = sample()
        report["crossOriginFrame"]["winter"]["intlDefault"] = "Jan 15, 07:00 EST"
        checks = assess(report)
        self.assertFalse(checks["winter_intl_utc_matches_date"])
        self.assertFalse(checks["winter_all_contexts_equal"])

    def test_date_string_offset_mismatch_fails(self) -> None:
        report = sample()
        report["sharedWorker"]["summer"]["dateString"] = "Wed Jul 15 2026 12:00:00 GMT+0100"
        self.assertFalse(assess(report)["summer_date_string_utc_offset"])

    def test_wrong_instant_fails(self) -> None:
        report = sample()
        report["main"]["summer"]["epochMilliseconds"] += 3600000
        self.assertFalse(assess(report)["summer_fixed_instant"])

    def test_missing_context_is_inconclusive(self) -> None:
        report = sample()
        del report["serviceWorker"]
        with self.assertRaises(ObservationUnavailable):
            assess(report)

    def test_missing_season_is_inconclusive(self) -> None:
        report = sample()
        del report["iframe"]["summer"]
        with self.assertRaises(ObservationUnavailable):
            assess(report)

    def test_missing_field_is_inconclusive(self) -> None:
        report = sample()
        del report["main"]["winter"]["intlUTC"]
        with self.assertRaises(ObservationUnavailable):
            assess(report)

    def test_boolean_offset_is_inconclusive(self) -> None:
        report = sample()
        report["worker"]["summer"]["offsetMinutes"] = False
        with self.assertRaises(ObservationUnavailable):
            assess(report)


if __name__ == "__main__":
    unittest.main()
