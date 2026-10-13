"""Pure evaluation checks for the disposable extension-state audit."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from extension_isolation_audit import evaluate  # noqa: E402


def fixture() -> dict[str, dict]:
    def result(before, after):
        return {"before": before, "after": after, "extensionId": "a" * 32}
    return {"a_write": result(None, "A"), "b_read": result(None, None),
            "b_write": result(None, "B"), "b_again": result("B", "B"),
            "a_again": result("A", "A"),
            "restored": result("A", "A"), "clean_clone": result(None, None)}


class ExtensionIsolationEvaluationTests(unittest.TestCase):
    def test_expected_isolation(self):
        self.assertTrue(all(evaluate(fixture(), "A", "B").values()))

    def test_other_profile_storage_leak_fails(self):
        results = fixture()
        results["b_read"]["before"] = "A"
        self.assertFalse(evaluate(results, "A", "B")["b_cannot_read_a"])

    def test_restore_loss_and_clone_contamination_fail(self):
        results = fixture()
        results["restored"]["before"] = None
        results["clean_clone"]["before"] = "A"
        checks = evaluate(results, "A", "B")
        self.assertFalse(checks["restored_a_retains_extension_value"])
        self.assertFalse(checks["clean_clone_has_no_extension_value"])


if __name__ == "__main__":
    unittest.main()
