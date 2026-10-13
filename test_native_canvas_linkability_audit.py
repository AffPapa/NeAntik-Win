"""Pure tests for local Canvas linkability summaries."""

from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import native_canvas_linkability_audit as audit  # noqa: E402
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

    def test_cli_measured_but_blocked_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_chrome = root / "baseline" / "chrome.exe"
            candidate_chrome = root / "candidate" / "chrome.exe"
            for chrome in (baseline_chrome, candidate_chrome):
                chrome.parent.mkdir()
                chrome.touch()
            output = root / "audit.json"
            baseline = {"profiles": 4, "unique_pixel_hashes": 1,
                        "unique_png_hashes": 1,
                        "first_seed_repeats_across_fresh_profiles": True}
            candidate = {"profiles": 4, "unique_pixel_hashes": 4,
                         "unique_png_hashes": 4,
                         "first_seed_repeats_across_fresh_profiles": True}
            args = ["audit", "--baseline-chrome", str(baseline_chrome),
                    "--candidate-chrome", str(candidate_chrome),
                    "--samples", "4", "--output", str(output)]
            with patch.object(sys, "argv", args), \
                    patch.object(audit, "measure_core", side_effect=[baseline, candidate]), \
                    redirect_stdout(StringIO()):
                exit_code = audit.main()
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(report["status"], "measured")
            self.assertEqual(report["release_gate"],
                             "blocked_by_stable_per_profile_canvas_identifier")

    def test_manual_review_is_not_release_approval(self):
        self.assertEqual(audit.report_exit_code({"status": "measured",
                                                 "release_gate": "requires_manual_review"}), 2)
        self.assertEqual(audit.report_exit_code({"status": "failed"}), 1)


if __name__ == "__main__":
    unittest.main()
