"""Synthetic summary tests; no browser or personal fingerprint data required."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from native_persona_surface_audit import summarize  # noqa: E402


def sample(index: int, *, device: str = "same") -> dict:
    digest = f"{index + 1:064x}"
    return {"surfaces": {"main": {"canvas2dSha256": digest,
                                   "canvasPixelSha256": digest,
                                   "device": device}},
            "http": {"language": "ru"}, "blocked_external_requests": index}


class SummaryTests(unittest.TestCase):
    def test_unique_canvas_and_stable_other_surfaces_pass(self) -> None:
        result = summarize([sample(index) for index in range(4)], [{"ok": True}] * 4)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["checks"]), 4)
        self.assertNotIn("surfaces", result)

    def test_stable_canvas_fails(self) -> None:
        result = summarize([sample(0) for _ in range(4)], [{"ok": True}] * 4)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["canvas_png_changes_each_session"])

    def test_other_surface_or_context_drift_fails(self) -> None:
        reports = [sample(index) for index in range(4)]
        reports[2]["surfaces"]["main"]["device"] = "different"
        contexts = [{"ok": True}] * 3 + [{"ok": False}]
        result = summarize(reports, contexts)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["non_canvas_surfaces_stable"])
        self.assertFalse(result["checks"]["all_context_checks_pass"])

    def test_incomplete_or_missing_data_rejected(self) -> None:
        with self.assertRaises(ValueError):
            summarize([sample(0)], [{"ok": True}])
        reports = [sample(index) for index in range(4)]
        del reports[1]["surfaces"]["main"]["canvasPixelSha256"]
        with self.assertRaises(ValueError):
            summarize(reports, [{"ok": True}] * 4)
        reports[1]["surfaces"]["main"]["canvasPixelSha256"] = "z" * 64
        with self.assertRaises(ValueError):
            summarize(reports, [{"ok": True}] * 4)


if __name__ == "__main__":
    unittest.main()
