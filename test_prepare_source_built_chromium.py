"""Policy tests for staging a source-built Chromium runtime."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import prepare_source_built_chromium as staging


class SourceBuildStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="neantik-source-stage-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "src"
        self.build = self.root / "out"
        self.source.mkdir()
        self.build.mkdir()
        (self.source / "chrome").mkdir()
        (self.source / "chrome" / "VERSION").write_text("MAJOR=155\nMINOR=0\nBUILD=8059\nPATCH=40\n", encoding="utf-8")
        (self.source / "LICENSE").write_text("Chromium license fixture", encoding="utf-8")
        (self.source / "DEPS").write_text("original dependencies\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        self.commit = staging.git(self.source, "rev-parse", "HEAD")
        (self.build / "args.gn").write_text("is_debug = false\nis_component_build = false\nis_chrome_branded = false\n", encoding="utf-8")
        for name in ("chrome.exe", "chrome.dll", "chrome_elf.dll", "icudtl.dat", "resources.pak", "155.0.8059.40.manifest",
                     "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
            (self.build / name).write_bytes(name.encode("ascii"))
        (self.build / "locales").mkdir()
        (self.build / "locales" / "en-US.pak").write_bytes(b"locale fixture")
        (self.build / "locales" / "ru.pak").write_bytes(b"russian fixture")
        (self.build / "locales" / "th.pak").write_bytes(b"thai fixture")
        (self.build / "locales" / "de.pak").write_bytes(b"unused fixture")
        (self.build / "locales" / "en-US.pak.info").write_bytes(b"build metadata, not runtime")

    def args(self, approved: str | None = None) -> argparse.Namespace:
        return argparse.Namespace(source_root=str(self.source), build_root=str(self.build),
                                  output=str(self.root / "staged"), commit=self.commit,
                                  version="155.0.8059.40", approved_build_patch_sha256=approved)

    @patch.object(staging, "extract_credits", return_value=b"<!DOCTYPE html>" + b"C" * 110_000)
    def test_clean_source_stages_runtime_and_credits(self, _extract) -> None:
        receipt = staging.stage(self.args())
        self.assertEqual(receipt["channel"], "stable")
        self.assertEqual(receipt["build_patch_sha256"], "")
        self.assertEqual(receipt["source_commit"], self.commit)
        self.assertTrue((self.root / "staged" / "chrome.exe").is_file())
        self.assertTrue((self.root / "staged" / "155.0.8059.40.manifest").is_file())
        self.assertTrue((self.root / "staged" / "locales" / "en-US.pak").is_file())
        self.assertEqual(receipt["locales"], ["en-US.pak", "ru.pak", "th.pak"])
        self.assertFalse((self.root / "staged" / "locales" / "de.pak").exists())
        self.assertFalse((self.root / "staged" / "locales" / "en-US.pak.info").exists())
        self.assertFalse((self.root / "staged" / "Data").exists())

    @patch.object(staging, "extract_credits", return_value=b"<!DOCTYPE html>" + b"C" * 110_000)
    def test_only_approved_build_patch_is_accepted(self, _extract) -> None:
        (self.source / "DEPS").write_text("approved build dependency change\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "approved SHA-256"):
            staging.stage(self.args())
        patch_bytes = subprocess.check_output(["git", "-C", str(self.source), "diff", "HEAD", "--binary", "--", "DEPS", "build/toolchain/win/midl.py"])
        receipt = staging.stage(self.args(hashlib.sha256(patch_bytes).hexdigest()))
        self.assertEqual(receipt["build_patch_sha256"], hashlib.sha256(patch_bytes).hexdigest())

    def test_runtime_source_change_is_rejected(self) -> None:
        (self.source / "chrome" / "VERSION").write_text("MAJOR=156\nMINOR=0\nBUILD=1\nPATCH=0\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unapproved Chromium source changes"):
            staging.stage(self.args())


if __name__ == "__main__":
    unittest.main()
