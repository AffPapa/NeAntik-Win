"""Synthetic controls for stock-versus-patched fingerprint comparison."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from compare_fingerprint_baseline import compare  # noqa: E402
from fingerprint_surface_audit import compare_fresh_profiles, compare_repeat_launches, evaluate  # noqa: E402
from test_fingerprint_surface_audit import report  # noqa: E402


def audit(cpu: int, memory: int) -> dict:
    launches = []
    for _ in range(2):
        first, second = report(), report()
        for sample in (first, second):
            for surface in sample["surfaces"].values():
                surface["hardwareConcurrency"] = cpu
                surface["deviceMemory"] = memory
            sample["client_hints"]["deviceMemory"] = str(memory)
        launches.append([first, second])
    primary = [pair[0] for pair in launches]
    return {**compare_fresh_profiles(primary),
            "profiles": primary, "repeat_profiles": [pair[1] for pair in launches],
            "context_consistency": evaluate(primary),
            "repeat_consistency": [compare_repeat_launches(pair) for pair in launches],
            "repeat_context_consistency": [evaluate([pair[1]])[0] for pair in launches]}


class BaselineComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stock_identity = {"chromium_version": "155.0.8059.40", "source_commit": "abc", "privacy_patch_sha256": None}
        self.candidate_identity = {"chromium_version": "155.0.8059.40", "source_commit": "abc", "privacy_patch_sha256": "f" * 64}
        self.stock = audit(8, 16)
        self.candidate = audit(4, 8)

    def test_matching_commit_and_bounded_values_pass(self):
        checks, observations = compare(self.stock_identity, self.candidate_identity,
                                       self.stock, self.candidate, "f" * 64)
        self.assertTrue(all(checks.values()))
        self.assertTrue(all(observations.values()))

    def test_different_source_commit_is_rejected(self):
        self.candidate_identity["source_commit"] = "different"
        checks, _ = compare(self.stock_identity, self.candidate_identity,
                            self.stock, self.candidate, "f" * 64)
        self.assertFalse(checks["same_upstream_commit"])

    def test_candidate_above_stock_is_rejected(self):
        self.candidate = audit(16, 32)
        checks, _ = compare(self.stock_identity, self.candidate_identity,
                            self.stock, self.candidate, "f" * 64)
        self.assertFalse(checks["cpu_observed_and_not_above_stock"])
        self.assertFalse(checks["memory_observed_and_not_above_stock"])

    def test_other_surface_change_is_rejected(self):
        self.candidate["profiles"][0]["surfaces"]["main"]["canvasPixelSha256"] = "d" * 64
        checks, _ = compare(self.stock_identity, self.candidate_identity,
                            self.stock, self.candidate, "f" * 64)
        self.assertFalse(checks["other_observed_surfaces_equal"])

    def test_missing_repeat_is_rejected(self):
        self.candidate["repeat_profiles"].pop()
        with self.assertRaises(ValueError):
            compare(self.stock_identity, self.candidate_identity,
                    self.stock, self.candidate, "f" * 64)

    def test_failed_local_gate_is_rejected(self):
        self.candidate["context_consistency"][0]["main_iframe"] = False
        checks, _ = compare(self.stock_identity, self.candidate_identity,
                            self.stock, self.candidate, "f" * 64)
        self.assertFalse(checks["candidate_local_gate"])

    def test_incomplete_true_only_check_group_is_rejected(self):
        self.candidate["context_consistency"] = [{"invented": True}, {"invented": True}]
        checks, _ = compare(self.stock_identity, self.candidate_identity,
                            self.stock, self.candidate, "f" * 64)
        self.assertFalse(checks["candidate_local_gate"])

    def test_candidate_patch_must_match_public_source(self):
        checks, _ = compare(self.stock_identity, self.candidate_identity,
                            self.stock, self.candidate, "a" * 64)
        self.assertFalse(checks["candidate_patch_matches_public_source"])


if __name__ == "__main__":
    unittest.main()
