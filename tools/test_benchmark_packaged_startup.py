"""Synthetic, offline checks for the packaged-startup harness."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from benchmark_packaged_startup import extract_verified, sha256, summarize, validate_members


ROOT = "NeAntikWin-portable-v0.8.7-preview"


class ArchiveSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="neantik-startup-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.archive_path = self.folder / "synthetic.zip"
        self.verifier = self.folder / "verifier.ps1"
        self.verifier.write_text("# synthetic verifier fixture\n", encoding="utf-8")

    def make_archive(self, extra: list[tuple[str, bytes]] | None = None) -> None:
        with zipfile.ZipFile(self.archive_path, "w") as archive:
            archive.writestr(f"{ROOT}/release-manifest.json", json.dumps({
                "version": "0.8.7-preview", "source_commit": "a" * 40,
                "executable": "NeAntikWin.exe"}))
            archive.writestr(f"{ROOT}/NeAntikWin.exe", b"synthetic executable")
            for name, content in extra or []:
                archive.writestr(name, content)

    def test_safe_synthetic_extraction_records_exact_hashes(self) -> None:
        self.make_archive()
        destination = self.folder / "extracted"
        with patch("benchmark_packaged_startup.subprocess.run") as verifier:
            verifier.return_value.returncode = 0
            executable, provenance = extract_verified(self.archive_path, destination,
                                                      sha256(self.archive_path), self.verifier)
        self.assertEqual(executable.read_bytes(), b"synthetic executable")
        self.assertEqual(provenance["zip_sha256"], sha256(self.archive_path))
        self.assertEqual(provenance["exe_sha256"], sha256(executable))
        self.assertEqual(provenance["source_commit"], "a" * 40)
        self.assertFalse((destination / ROOT / "Data").exists())
        self.assertEqual(verifier.call_count, 1)

    def test_hash_mismatch_rejects_before_verifier_or_extraction(self) -> None:
        self.make_archive()
        destination = self.folder / "extracted"
        with patch("benchmark_packaged_startup.subprocess.run") as verifier:
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                extract_verified(self.archive_path, destination, "0" * 64, self.verifier)
        verifier.assert_not_called()
        self.assertFalse(destination.exists())

    def test_verifier_failure_rejects_before_extraction(self) -> None:
        self.make_archive()
        destination = self.folder / "extracted"
        with patch("benchmark_packaged_startup.subprocess.run") as verifier:
            verifier.return_value.returncode = 1
            with self.assertRaisesRegex(ValueError, "verifier failed"):
                extract_verified(self.archive_path, destination, sha256(self.archive_path),
                                 self.verifier)
        self.assertFalse(destination.exists())

    def test_traversal_and_runtime_data_rejected(self) -> None:
        for name in (f"{ROOT}/../escape.txt", f"{ROOT}/Data/private.txt",
                     f"{ROOT}/c:/drive.txt", f"{ROOT}/AUX.txt"):
            with self.subTest(name=name):
                self.make_archive([(name, b"fixture")])
                with zipfile.ZipFile(self.archive_path) as archive:
                    with self.assertRaises(ValueError):
                        validate_members(archive)

    def test_casefold_collision_rejected(self) -> None:
        self.make_archive([(f"{ROOT}/NEANTIKWIN.EXE", b"collision")])
        with zipfile.ZipFile(self.archive_path) as archive:
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                validate_members(archive)

    def test_symlink_rejected(self) -> None:
        self.make_archive()
        item = zipfile.ZipInfo(f"{ROOT}/link")
        item.create_system = 3
        item.external_attr = 0o120777 << 16
        with zipfile.ZipFile(self.archive_path, "a") as archive:
            archive.writestr(item, "target")
        with zipfile.ZipFile(self.archive_path) as archive:
            with self.assertRaisesRegex(ValueError, "link or special"):
                validate_members(archive)

    def test_summary_uses_observations_not_unmeasured_readiness(self) -> None:
        result = summarize([{"window_observed_ms": number} for number in (2, 5, 3, 4, 1)])
        self.assertEqual(result["median_window_observed_ms"], 3)
        self.assertEqual(result["spread_window_observed_ms"], 4)
        self.assertNotIn("ui_ready_ms", result)


if __name__ == "__main__":
    unittest.main()
