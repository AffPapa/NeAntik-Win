"""Meaningful release selection and tag-integrity checks; no network or install."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("verify-pins.py")
module_spec = importlib.util.spec_from_file_location("native_pin_verifier", MODULE_PATH)
pins = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(pins)


class PinTests(unittest.TestCase):
    def test_small_higher_rollout_does_not_replace_broad_stable(self):
        stable = {"version": "155.0.8059.40", "fraction": 1, "pinnable": True}
        experimental = {"version": "156.0.8078.12", "fraction": .005, "pinnable": False}
        self.assertEqual(pins.select_stable_release([experimental, stable]), stable)

    def test_numeric_version_order_and_zero_fraction(self):
        older = {"version": "99.0.1.1", "fraction": 1, "pinnable": True}
        newer = {"version": "100.0.1.1", "fraction": 1, "pinnable": True}
        zero = {"version": "200.0.1.1", "fraction": 0, "pinnable": True}
        self.assertEqual(pins.select_stable_release([older, zero, newer]), newer)

    def test_no_eligible_release_fails(self):
        with self.assertRaises(ValueError):
            pins.select_stable_release([{"version": "156.0.1.1", "fraction": .5, "pinnable": False}])

    def test_tag_commit_mismatch_is_a_separate_failure(self):
        spec = {"chromium": {"version_history_url": "https://example.test/versions", "tag": "refs/tags/155.0.1.1", "version": "155.0.1.1", "commit": "a" * 40}, "depot_tools": {"commit": "b" * 40}}
        responses = [{"releases": [{"version": "155.0.1.1", "fraction": 1, "pinnable": True}]},
                     {"refs/tags/155.0.1.1": {"value": "c" * 40}}, {"commit": "b" * 40}]
        with patch.object(pins, "request_json", side_effect=responses):
            result = pins.verify(spec)
        self.assertFalse(result["tag_matches"])
        self.assertTrue(result["current_stable_matches"])
        self.assertTrue(result["depot_commit_matches"])

    def test_pagination_until_pinnable_release(self):
        spec = {"chromium": {"version_history_url": "https://example.test/versions?page_size=100", "tag": "refs/tags/155.0.1.1", "version": "155.0.1.1", "commit": "a" * 40}, "depot_tools": {"commit": "b" * 40}}
        responses = [{"releases": [], "nextPageToken": "next/+"}, {"releases": [{"version": "155.0.1.1", "fraction": 1, "pinnable": True}]},
                     {"refs/tags/155.0.1.1": {"value": "a" * 40}}, {"commit": "b" * 40}]
        with patch.object(pins, "request_json", side_effect=responses) as request:
            result = pins.verify(spec)
        self.assertTrue(result["tag_matches"])
        self.assertIn("pageToken=next%2F%2B", request.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
