"""Synthetic orchestration check; never starts Chromium or opens user profiles."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import proxy_loss_recovery_gate as gate


class ProxyLossRecoveryGateTests(unittest.TestCase):
    def test_plain_temp_profile_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="neantik-loss-profile-test-") as temporary:
            root = Path(temporary)
            profile = root / "Profile"
            profile.mkdir()
            gate.require_plain_profile_directory(root, profile)

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_profile_junction_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="neantik-loss-junction-test-") as temporary:
            root = Path(temporary)
            target = root / "outside"
            target.mkdir()
            profile = root / "Profile"
            result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(profile), str(target)],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode:
                self.skipTest("Windows junction creation is unavailable in this environment")
            try:
                self.assertTrue(profile.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                with self.assertRaisesRegex(RuntimeError, "profile_path_reparse_point:profile"):
                    gate.require_plain_profile_directory(root, profile)
            finally:
                profile.rmdir()

    def test_public_core_is_prepared_in_disposable_copy_before_measurement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="neantik-loss-gate-test-") as temporary:
            root = Path(temporary)
            engine = root / "extracted-release" / "Engine" / "Chromium"
            engine.mkdir(parents=True)
            chrome = engine / "chrome.exe"
            chrome.write_bytes(b"synthetic-browser")
            (engine / "chrome.dll").write_bytes(b"synthetic-library")
            output = root / "result.json"
            prepared_roots: list[Path] = []

            def prepare(source: Path, destination: Path) -> Path:
                self.assertEqual(source, chrome.resolve())
                self.assertTrue(destination.is_dir())
                self.assertNotEqual(destination, engine)
                prepared_roots.append(destination)
                return destination / "qa-portable" / "Engine" / "Chromium" / "chrome.exe"

            def measure(prepared_chrome: Path) -> dict:
                self.assertEqual(prepared_chrome, prepared_roots[0] / "qa-portable" / "Engine" / "Chromium" / "chrome.exe")
                self.assertTrue(prepared_roots[0].is_dir())
                return {"status": "PASS", "checks": {"synthetic": True}}

            with patch.object(sys, "argv", ["proxy_loss_recovery_gate.py", "--chrome", str(chrome),
                                            "--output", str(output)]), \
                 patch.object(gate, "prepare_disposable_engine", side_effect=prepare), \
                 patch.object(gate, "measure", side_effect=measure):
                self.assertEqual(gate.main(), 0)

            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "PASS")
            self.assertFalse(prepared_roots[0].exists())


if __name__ == "__main__":
    unittest.main()
