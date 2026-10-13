"""Pure tests for local Canvas linkability summaries."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from native_canvas_linkability_audit import assess_local_linkability, release_gate, summarize_runs  # noqa: E402


class CanvasLinkabilitySummaryTests(unittest.TestCase):
    def test_unique_stable_per_seed_is_release_warning(self):
        baseline = summarize_runs([{"pixelHash": 1, "pngHash": 1}] * 4,
                                  {"pixelHash": 1, "pngHash": 1})
        candidate = summarize_runs(
            [{"pixelHash": i, "pngHash": i} for i in range(4)],
            {"pixelHash": 0, "pngHash": 0})
        observations = assess_local_linkability(baseline, candidate)
        self.assertTrue(all(observations.values()))
        self.assertEqual(release_gate(observations), "blocked_by_stable_per_profile_canvas_identifier")

    def test_repeat_failure_is_detected(self):
        candidate = summarize_runs(
            [{"pixelHash": 1, "pngHash": 1}, {"pixelHash": 2, "pngHash": 2}],
            {"pixelHash": 3, "pngHash": 3})
        self.assertFalse(candidate["first_seed_repeats_across_fresh_profiles"])

    def test_incomplete_evidence_never_passes_release_gate(self):
        self.assertEqual(release_gate({"control": True, "cohort": False}), "requires_manual_review")

    def test_missing_hash_rejected(self):
        with self.assertRaises(ValueError):
            summarize_runs([{"pixelHash": 1}], {"pixelHash": 1, "pngHash": 2})


if __name__ == "__main__":
    unittest.main()
