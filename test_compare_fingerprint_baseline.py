"""Synthetic controls for stock-versus-patched fingerprint comparison."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from compare_fingerprint_baseline import compare, compare_native_persona  # noqa: E402
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


class NativePersonaComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patch = "b" * 64
        self.stock_identity = {"chromium_version": "155.0.8059.40", "source_commit": "abc",
                               "privacy_patch_sha256": None, "native_persona_patch_sha256": None}
        self.candidate_identity = {"chromium_version": "155.0.8059.40", "source_commit": "abc",
                                   "privacy_patch_sha256": self.patch,
                                   "native_persona_patch_sha256": self.patch}
        self.stock = audit(8, 16)
        self.candidate = audit(8, 16)
        self.core = {"engine_id": "neantik-chromium", "schema": 2, "compiled_stage": 11,
                     "version": "155.0.8059.40", "source_commit": "abc",
                     "capabilities": {"canvas_site_scoped_experimental": True, "canvas": False}}

    def checks(self):
        return compare_native_persona(self.stock_identity, self.candidate_identity,
                                      self.stock, self.candidate, self.patch, self.core)

    def test_ordinary_mode_full_parity_passes(self):
        self.assertTrue(all(self.checks().values()))

    def test_cpu_and_memory_changes_are_not_discarded(self):
        self.candidate = audit(4, 8)
        self.assertFalse(self.checks()["ordinary_all_observed_surfaces_equal_including_cpu_ram"])

    def test_canvas_change_is_not_discarded(self):
        self.candidate["profiles"][0]["surfaces"]["main"]["canvasPixelSha256"] = "d" * 64
        self.assertFalse(self.checks()["ordinary_all_observed_surfaces_equal_including_cpu_ram"])

    def test_native_patch_receipt_must_match_public_source(self):
        self.candidate_identity["native_persona_patch_sha256"] = "a" * 64
        self.assertFalse(self.checks()["candidate_receipt_native_patch_matches_public_source"])

    def test_stock_must_be_unpatched(self):
        self.stock_identity["native_persona_patch_sha256"] = self.patch
        self.assertFalse(self.checks()["stock_without_patch"])

    def test_compiled_stage_must_be_evidenced(self):
        self.core["compiled_stage"] = 10
        self.assertFalse(self.checks()["candidate_compiled_core_stage_11"])

    def test_absent_handshake_is_failure(self):
        self.core = None
        self.assertFalse(self.checks()["candidate_compiled_core_stage_11"])

    def test_different_upstream_commit_fails(self):
        self.candidate_identity["source_commit"] = "other"
        self.assertFalse(self.checks()["same_upstream_commit"])


if __name__ == "__main__":
    unittest.main()
