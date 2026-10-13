"""Synthetic orchestration check; never starts Chromium or opens user profiles."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import proxy_loss_recovery_gate as gate


class ProxyLossRecoveryGateTests(unittest.TestCase):
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
