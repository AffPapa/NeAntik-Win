"""Offline safety tests for the manually dispatched public second-host gate."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import public_second_host_gate as gate


class Download(io.BytesIO):
    status = 200


class SecondHostGateTests(unittest.TestCase):
    def test_only_literal_preview_tag_and_lowercase_hashes(self) -> None:
        self.assertEqual(gate.validated_inputs("v0.8.15-preview", "a" * 64, "b" * 40),
                         ("v0.8.15-preview", "a" * 64, "b" * 40))
        for tag in ("v0.8.15-preview;echo bad", "../../v0.8.15-preview", "v0.8.15-preview\n",
                    "v0.8.15", "v0.8.15-preview/other"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                gate.validated_inputs(tag, "a" * 64, "b" * 40)
        with self.assertRaises(ValueError):
            gate.validated_inputs("v0.8.15-preview", "A" * 64, "b" * 40)
        with self.assertRaises(ValueError):
            gate.validated_inputs("v0.8.15-preview", "a" * 64, "b" * 39)

    def test_public_release_asset_exact_name_and_url(self) -> None:
        tag = "v0.8.15-preview"
        name = f"NeAntikWin-portable-{tag}.zip"
        url = f"https://github.com/{gate.REPOSITORY}/releases/download/{tag}/{name}"
        self.assertEqual(gate.release_asset(tag), (url, name))
        with self.assertRaises(ValueError):
            gate.release_asset(tag + "/redirect")

    def test_download_requires_exact_size_and_sha_before_extraction(self) -> None:
        payload = b"synthetic ZIP bytes for hash gate"
        expected = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "candidate.zip"
            with patch.object(gate.urllib.request, "urlopen", return_value=Download(payload)):
                gate.download_exact("https://example.invalid/file.zip", target, expected)
            self.assertEqual(target.read_bytes(), payload)
            with patch.object(gate.urllib.request, "urlopen", return_value=Download(payload)):
                with self.assertRaises(ValueError):
                    gate.download_exact("https://example.invalid/file.zip", Path(folder) / "bad.zip",
                                        "0" * 64)
            with patch.object(gate.urllib.request, "urlopen", return_value=Download(payload)):
                with self.assertRaises(ValueError):
                    with patch.object(gate, "MAX_ARCHIVE_BYTES", len(payload) - 1):
                        gate.download_exact("https://example.invalid/file.zip", Path(folder) / "size.zip",
                                            expected)

    def test_runner_source_must_match_release_build_inputs(self) -> None:
        names = ("nevision_win.py", "profile_identity.py", "privacy_defaults.py", "release-version.json")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository, portable = root / "source", root / "portable"
            repository.mkdir()
            portable.mkdir()
            records = []
            for name in names:
                payload = f"fixture-{name}".encode()
                (repository / name).write_bytes(payload)
                records.append({"path": name, "sha256": hashlib.sha256(payload).hexdigest()})
            (portable / "build-provenance.json").write_text(
                json.dumps({"source_files": records}), encoding="utf-8")
            gate.assert_runner_source_matches_release(repository, portable)
            (repository / "nevision_win.py").write_bytes(b"unexpected product change")
            with self.assertRaises(ValueError):
                gate.assert_runner_source_matches_release(repository, portable)

    def test_bundled_chromium_is_inside_engine_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            portable = Path(folder)
            engine = portable / "Engine" / "Chromium"
            engine.mkdir(parents=True)
            chrome = engine / "chrome.exe"
            chrome.write_bytes(b"synthetic binary")
            self.assertEqual(gate.bundled_chromium(portable), (engine, chrome))
            chrome.unlink()
            with self.assertRaises(ValueError):
                gate.bundled_chromium(portable)


if __name__ == "__main__":
    unittest.main()
