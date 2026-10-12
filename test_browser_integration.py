"""Pure contract checks for the disposable browser-storage integration harness."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from browser_integration import EMPTY, state  # noqa: E402


class BrowserStorageContractTests(unittest.TestCase):
    def test_empty_profile_has_no_test_values_or_namespaces(self):
        self.assertEqual(EMPTY["indexed_db_namespace"], False)
        self.assertEqual(EMPTY["cache_namespace"], False)
        self.assertIsNone(EMPTY["service_worker"])

    def test_written_profile_has_all_expected_states(self):
        result = state("synthetic")
        self.assertEqual(result["cookie"], "synthetic")
        self.assertEqual(result["local_storage"], "synthetic")
        self.assertEqual(result["indexed_db"], "synthetic")
        self.assertEqual(result["cache_storage"], "synthetic")
        self.assertIs(result["indexed_db_namespace"], True)
        self.assertIs(result["cache_namespace"], True)
        self.assertEqual(result["service_worker"], "registered")


if __name__ == "__main__":
    unittest.main()
