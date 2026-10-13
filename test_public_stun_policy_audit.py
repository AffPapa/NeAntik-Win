"""Synthetic policy classification tests; no live network required."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from public_stun_policy_audit import classify  # noqa: E402


def case(types: list[str], sends: int, rejected: int = 0) -> dict:
    return {"candidate_types": types, "netlog": {"all_udp_sends": sends},
            "route_control_requests": rejected}


class ClassificationTests(unittest.TestCase):
    def test_positive_direct_and_quiet_proxy_pass(self) -> None:
        result = classify(case(["host", "srflx"], 5), case([], 0, 1))
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn("address", result)

    def test_proxy_candidate_or_udp_send_fails(self) -> None:
        self.assertEqual(classify(case(["srflx"], 5), case(["host"], 0, 1))["status"], "FAIL")
        self.assertEqual(classify(case(["srflx"], 5), case([], 1, 1))["status"], "FAIL")

    def test_missing_direct_positive_is_inconclusive(self) -> None:
        result = classify(case(["host"], 0), case([], 0, 1))
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(classify(case(["srflx"], 5), case([], 0))["status"], "INCONCLUSIVE")

    def test_missing_measurement_rejected(self) -> None:
        with self.assertRaises(ValueError):
            classify({"candidate_types": ["srflx"]}, case([], 0))
        with self.assertRaises(ValueError):
            classify(case(["srflx"], 1), case([12], 0))


if __name__ == "__main__":
    unittest.main()
