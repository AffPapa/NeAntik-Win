import argparse
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.prepare_bundled_chromium import sha256, stage


class EngineStagingSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "browser.zip"
        self.commit = "a" * 40

    def args(self):
        return argparse.Namespace(
            snapshot_zip=str(self.archive), sha256=sha256(self.archive),
            revision="1716555", commit=self.commit, version="157.0.8101.0",
            output=str(self.root / "output"),
        )

    def revisions(self):
        return patch("tools.prepare_bundled_chromium.urllib.request.urlopen", return_value=io.BytesIO(
            ('{"chromium_revision":1716555,"got_revision":"' + self.commit + '"}').encode()
        ))

    def test_wrong_digest_rejected_before_any_output(self):
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr("chrome-win/chrome.exe", b"fake")
        args = self.args()
        args.sha256 = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            stage(args)
        self.assertFalse((self.root / "output").exists())

    def test_missing_version_manifest_rejected(self):
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr("chrome-win/chrome.exe", b"fake")
        with self.revisions(), self.assertRaisesRegex(ValueError, "version manifest"):
            stage(self.args())
        self.assertFalse((self.root / "output").exists())

    def test_traversal_rejected_before_extraction(self):
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr("chrome-win/157.0.8101.0.manifest", b"version")
            output.writestr("chrome-win/../outside.txt", b"secret")
        with self.revisions(), self.assertRaisesRegex(ValueError, "Unexpected ZIP path"):
            stage(self.args())
        self.assertFalse((self.root / "outside.txt").exists())

    def test_output_is_immutable(self):
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr("chrome-win/chrome.exe", b"fake")
        (self.root / "output").mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            stage(self.args())


if __name__ == "__main__":
    unittest.main()
