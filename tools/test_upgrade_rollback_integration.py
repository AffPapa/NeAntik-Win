"""Pure archive-validation checks; the full upgrade gate uses exact ZIPs."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from upgrade_rollback_integration import file_hash, inspect_archive, validate_release_pair


class UpgradeArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="neantik-upgrade-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.archive_path = Path(self.temporary.name) / "fixture.zip"
        self.root = "NeAntikWin-portable-v0.8.6-preview"

    def make_archive(self, extra_name: str | None = None) -> None:
        with zipfile.ZipFile(self.archive_path, "w") as archive:
            archive.writestr(f"{self.root}/release-manifest.json", json.dumps({
                "version": "0.8.6-preview", "source_commit": "a" * 40,
            }))
            if extra_name:
                archive.writestr(extra_name, "synthetic fixture")

    def test_accepts_minimal_safe_metadata(self) -> None:
        self.make_archive()
        self.assertEqual(inspect_archive(self.archive_path, file_hash(self.archive_path),
                                         "0.8.6-preview"), (self.root, "a" * 40))

    def test_rejects_checksum_mismatch(self) -> None:
        self.make_archive()
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            inspect_archive(self.archive_path, "0" * 64, "0.8.6-preview")

    def test_rejects_embedded_data(self) -> None:
        self.make_archive(f"{self.root}/Data/fixture.txt")
        with self.assertRaisesRegex(ValueError, "contains Data"):
            inspect_archive(self.archive_path, file_hash(self.archive_path), "0.8.6-preview")

    def test_rejects_path_traversal(self) -> None:
        self.make_archive(f"{self.root}/../outside.txt")
        with self.assertRaisesRegex(ValueError, "Unsafe archive member"):
            inspect_archive(self.archive_path, file_hash(self.archive_path), "0.8.6-preview")

    def test_explicit_release_pair_accepts_adjacent_preview_versions(self) -> None:
        validate_release_pair("0.8.6-preview", "a" * 64, "0.8.7-preview", "B" * 64)

    def test_explicit_release_pair_rejects_downgrade_or_equal_version(self) -> None:
        for candidate in ("0.8.5-preview", "0.8.6-preview"):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(ValueError, "newer"):
                validate_release_pair("0.8.6-preview", "a" * 64, candidate, "b" * 64)

    def test_explicit_release_pair_rejects_invalid_hash_or_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "old SHA-256"):
            validate_release_pair("0.8.6-preview", "bad", "0.8.7-preview", "b" * 64)
        with self.assertRaisesRegex(ValueError, "candidate preview version"):
            validate_release_pair("0.8.6-preview", "a" * 64, "0.8.7-dev", "b" * 64)


if __name__ == "__main__":
    unittest.main()
