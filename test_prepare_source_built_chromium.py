"""Policy tests for staging a source-built Chromium runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import prepare_source_built_chromium as staging


class SourceBuildStageTests(unittest.TestCase):
    def test_dynamic_credits_theme_is_removed_deterministically(self) -> None:
        prefix = b'<!DOCTYPE html><html><body>credits'
        suffix = b'</body></html>'
        theme = (b'<link href="chrome://theme/colors.css?sets=ui%2Cchrome&amp;version='
                 b'123456" rel="stylesheet" type="text/css">')
        first = staging.normalize_credits_html(prefix + theme + suffix)
        second = staging.normalize_credits_html(prefix + theme.replace(b'123456', b'987654') + suffix)
        self.assertEqual(first, second)
        self.assertEqual(first, prefix + suffix)
        with self.assertRaisesRegex(ValueError, "Unexpected dynamic"):
            staging.normalize_credits_html(prefix + theme.replace(b'123456', b'bad') + suffix)

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
        self.privacy_source = self.source / sorted(staging.PRIVACY_PATCH_FILES)[0]
        self.privacy_source.parent.mkdir(parents=True)
        self.privacy_source.write_text("original browser value\n", encoding="utf-8")
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

    def args(self, approved: str | None = None, privacy: str | None = None,
             patch_file: Path | None = None, native: str | None = None,
             native_file: Path | None = None) -> argparse.Namespace:
        return argparse.Namespace(source_root=str(self.source), build_root=str(self.build),
                                  output=str(self.root / "staged"), commit=self.commit,
                                  version="155.0.8059.40", approved_build_patch_sha256=approved,
                                  approved_privacy_patch_sha256=privacy,
                                  privacy_patch_file=str(patch_file) if patch_file else None,
                                  approved_native_patch_sha256=native,
                                  native_patch_file=str(native_file) if native_file else None)

    @patch.object(staging, "extract_credits", return_value=b"<!DOCTYPE html>" + b"C" * 110_000)
    def test_clean_source_stages_runtime_and_credits(self, _extract) -> None:
        receipt = staging.stage(self.args())
        self.assertEqual(receipt["channel"], "stable")
        self.assertEqual(receipt["build_patch_sha256"], "")
        self.assertEqual(receipt["privacy_patch_sha256"], "")
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

    @patch.object(staging, "extract_credits", return_value=b"<!DOCTYPE html>" + b"C" * 110_000)
    def test_approved_public_privacy_patch_is_recorded(self, _extract) -> None:
        self.privacy_source.write_text("standardized browser value\n", encoding="utf-8")
        patch_bytes = subprocess.check_output(["git", "-C", str(self.source), "diff", "HEAD", "--binary", "--", *sorted(staging.PRIVACY_PATCH_FILES)])
        patch_file = self.root / "privacy.patch"
        patch_file.write_bytes(patch_bytes)
        with self.assertRaisesRegex(ValueError, "privacy patch differs"):
            staging.stage(self.args())
        with self.assertRaisesRegex(ValueError, "public privacy patch file"):
            staging.stage(self.args(privacy=hashlib.sha256(patch_bytes).hexdigest()))
        patch_file.write_bytes(patch_bytes + b"\n")
        with self.assertRaisesRegex(ValueError, "patch bytes differ"):
            staging.stage(self.args(privacy=hashlib.sha256(patch_bytes).hexdigest(), patch_file=patch_file))
        patch_file.write_bytes(patch_bytes)
        receipt = staging.stage(self.args(privacy=hashlib.sha256(patch_bytes).hexdigest(), patch_file=patch_file))
        self.assertEqual(receipt["privacy_patch_sha256"], hashlib.sha256(patch_bytes).hexdigest())

    def test_runtime_source_change_is_rejected(self) -> None:
        (self.source / "chrome" / "VERSION").write_text("MAJOR=156\nMINOR=0\nBUILD=1\nPATCH=0\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unapproved Chromium source changes"):
            staging.stage(self.args())

    def test_untracked_runtime_source_is_rejected(self) -> None:
        path = self.source / "third_party" / "blink" / "renderer" / "surprise.cc"
        path.parent.mkdir(parents=True)
        path.write_text("// Untracked runtime code must not be hidden in a build.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unapproved untracked Chromium source files"):
            staging.stage(self.args())

    @patch.object(staging, "probe_native_core", return_value={"engine_id": "neantik-chromium", "schema": 1})
    @patch.object(staging, "extract_credits", return_value=b"<!DOCTYPE html>" + b"C" * 110_000)
    @patch.object(staging, "export_native_persona_patch", return_value=b"native source patch\n")
    def test_native_persona_stage_requires_exact_public_patch(self, _export, _credits, _probe) -> None:
        expected = b"native source patch\n"
        digest = hashlib.sha256(expected).hexdigest()
        patch_file = self.root / "native.patch"
        patch_file.write_bytes(expected + b"extra")
        with self.assertRaisesRegex(ValueError, "Published native persona patch differs"):
            staging.stage(self.args(native=digest, native_file=patch_file))
        patch_file.write_bytes(expected)
        receipt = staging.stage(self.args(native=digest, native_file=patch_file))
        self.assertEqual(receipt["native_persona_patch_sha256"], digest)
        self.assertEqual(receipt["privacy_patch_sha256"], digest)
        self.assertEqual(receipt["native_persona_core_info"]["engine_id"], "neantik-chromium")

    def test_native_core_probe_rejects_missing_capability(self) -> None:
        info = {"engine_id": "neantik-chromium", "schema": 1, "version": "155.0.8059.40",
                "source_commit": self.commit,
                "capabilities": {"stable_seed": True, "hardware_concurrency": True,
                                 "device_memory": True, "canvas_opaque_srgb_uint8": False,
                                 "timezone": True}}

        def fake_run(arguments, **_kwargs):
            output = next(item.split("=", 1)[1] for item in arguments if item.startswith("--neantik-core-info="))
            Path(output).write_text(json.dumps(info), encoding="utf-8")
            return SimpleNamespace(returncode=0)

        with patch.object(staging.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "lacks required compiled capabilities"):
                staging.probe_native_core(self.build / "chrome.exe", "155.0.8059.40", self.commit)


if __name__ == "__main__":
    unittest.main()
