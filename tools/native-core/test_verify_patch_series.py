"""Real temporary Git trees verify the native source gate without user mutations."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

MODULE_PATH = Path(__file__).with_name("verify-patch-series.py")
module_spec = importlib.util.spec_from_file_location("native_patch_verifier", MODULE_PATH)
patches = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(patches)


class PatchGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="neantik-patch-gate-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.repository = self.root / "repo"
        self.source.mkdir()
        self.repository.mkdir()
        self.run_git("init", "-q")
        self.run_git("config", "core.autocrlf", "false")
        (self.source / "sample.cc").write_bytes(b"line one\nline two\nline three\n")
        self.run_git("add", "sample.cc")
        self.run_git("-c", "user.name=NeAntik QA", "-c", "user.email=qa@example.invalid", "commit", "-qm", "synthetic baseline")
        self.spec = {"chromium": {"commit": self.run_git("rev-parse", "HEAD").decode().strip()},
                     "patch_contract": {"patch_series": [], "postimage_sha256": {}}}

    def tearDown(self):
        self.temp.cleanup()

    def run_git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.source), *arguments], check=True, capture_output=True).stdout

    def prepare_patch(self):
        changed = b"line one\nmodified line two\nline three\n"
        (self.source / "sample.cc").write_bytes(changed)
        patch_file = self.repository / "001.patch"
        patch_file.write_bytes(self.run_git("diff"))
        self.spec["patch_contract"] = {"patch_series": [{"path": "001.patch", "sha256": patches.digest(patch_file)}],
                                      "postimage_sha256": {"sample.cc": hashlib.sha256(changed).hexdigest()}}

    def test_clean_baseline_and_missing_native_series(self):
        self.assertFalse(patches.verify(self.source, self.repository, self.spec, baseline=True)["native_fingerprint"])
        with self.assertRaises(ValueError):
            patches.verify(self.source, self.repository, self.spec)

    def test_applied_patch_hash_and_exact_postimage(self):
        self.prepare_patch()
        result = patches.verify(self.source, self.repository, self.spec)
        self.assertEqual(result["patch_count"], 1)
        self.assertFalse(result["native_fingerprint_tested"])
        self.assertEqual((self.source / "sample.cc").read_bytes(), b"line one\nmodified line two\nline three\n")

    def test_modified_patch_is_rejected(self):
        self.prepare_patch()
        with (self.repository / "001.patch").open("ab") as output:
            output.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "patch SHA"):
            patches.verify(self.source, self.repository, self.spec)

    def test_overlapping_patch_sequence_recovers_upstream(self):
        self.prepare_patch()
        self.run_git("add", "sample.cc")
        final = b"line one\nsecond modification\nline three\n"
        (self.source / "sample.cc").write_bytes(final)
        second = self.repository / "002.patch"
        second.write_bytes(self.run_git("diff"))
        self.spec["patch_contract"]["patch_series"].append({"path": "002.patch", "sha256": patches.digest(second)})
        self.spec["patch_contract"]["postimage_sha256"]["sample.cc"] = hashlib.sha256(final).hexdigest()
        self.assertEqual(patches.verify(self.source, self.repository, self.spec)["patch_count"], 2)
        self.assertEqual((self.source / "sample.cc").read_bytes(), final)

    def test_modified_source_same_file_is_rejected(self):
        self.prepare_patch()
        (self.source / "sample.cc").write_bytes(b"unreviewed same file content")
        with self.assertRaisesRegex(ValueError, "postimage SHA"):
            patches.verify(self.source, self.repository, self.spec)

    def test_unexpected_untracked_file_is_rejected(self):
        self.prepare_patch()
        (self.source / "unexpected.cc").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "allowlist"):
            patches.verify(self.source, self.repository, self.spec)
        with self.assertRaisesRegex(ValueError, "baseline"):
            patches.verify(self.source, self.repository, self.spec, baseline=True)


if __name__ == "__main__":
    unittest.main()
