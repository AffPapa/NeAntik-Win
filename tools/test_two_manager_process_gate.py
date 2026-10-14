"""Tests for the disposable two-manager recovery integration gate."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from two_manager_process_gate import (
    _command,
    _require_disposable_root,
    run_gate,
    run_restore_crash_gate,
)


class TwoManagerProcessGateTests(unittest.TestCase):
    def test_cleanup_guard_rejects_unmarked_root(self):
        with tempfile.TemporaryDirectory(prefix="neantik-two-manager-gate-") as temporary:
            with self.assertRaisesRegex(RuntimeError, "not_disposable_root"):
                _require_disposable_root(Path(temporary))

    def test_child_command_keeps_the_selected_disposable_root(self):
        root = Path("C:/synthetic-disposable-root")
        profile_id = "a" * 32
        command = _command("contend", root, profile_id)
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[2:], ["contend", "--root", str(root), "--profile-id", profile_id])

    @unittest.skipUnless(os.name == "nt", "Windows named mutex gate")
    def test_independent_managers_busy_then_recover_after_crash(self):
        report = run_gate()
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["reason"], "ok")
        self.assertTrue(all(report["checks"].values()), report)
        self.assertEqual(len(report["checks"]), 8)

    @unittest.skipUnless(os.name == "nt", "Windows process termination gate")
    def test_restore_process_crash_after_publish_recovers_profile_and_data(self):
        report = run_restore_crash_gate()
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["reason"], "ok")
        self.assertTrue(all(report["checks"].values()), report)
        self.assertEqual(len(report["checks"]), 10)


if __name__ == "__main__":
    unittest.main()
