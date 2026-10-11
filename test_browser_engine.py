"""Identity lifecycle, argv validation and offline native engine integrity tests."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import browser_engine as engine


class IdentityTests(unittest.TestCase):
    def test_ordinary_has_no_fingerprint_arguments(self):
        value = engine.new_identity("ordinary")
        self.assertEqual(engine.fingerprint_arguments(value), [])
        self.assertEqual(engine.serialize_identity(value), '{"mode":"ordinary","schema":1}')

    def test_generate_once_and_roundtrip_keeps_seed(self):
        with patch.object(engine.secrets, "randbelow", return_value=4294967294) as random:
            value = engine.new_identity()
        random.assert_called_once_with(0xFFFFFFFF)
        self.assertEqual(engine.validate_identity(json.loads(engine.serialize_identity(value))), value)
        self.assertEqual(engine.fingerprint_arguments(value), engine.fingerprint_arguments(value))
        self.assertEqual(value["seed"], 4294967295)

    def test_separate_profiles_generate_new_identity(self):
        with patch.object(engine.secrets, "randbelow", side_effect=[12, 13]):
            first, clone = engine.new_identity(), engine.new_identity()
        self.assertNotEqual(first["seed"], clone["seed"])

    def test_minimum_random_result_still_generates_nonzero_seed(self):
        with patch.object(engine.secrets, "randbelow", return_value=0):
            self.assertEqual(engine.new_identity()["seed"], 1)

    def test_native_argv_is_documented_and_version_coherent(self):
        value = engine.new_identity(locale="ru-RU", timezone="Europe/Moscow")
        value["seed"] = 1
        argv = engine.fingerprint_arguments(value)
        self.assertIn("--fingerprint=1", argv)
        self.assertIn("--fingerprint-platform=windows", argv)
        self.assertIn("--fingerprint-brand-version=150.0.7871.186", argv)
        self.assertIn("--accept-lang=ru-RU,ru", argv)
        self.assertIn("--timezone=Europe/Moscow", argv)
        self.assertFalse(any("fingerprint-gpu" in item or "--no-sandbox" in item or "remote-debugging" in item for item in argv))

    def test_disable_surfaces_canonical_without_mutating_input(self):
        value = engine.new_identity()
        value["disable_spoofing"] = ["gpu", "audio"]
        self.assertEqual(engine.validate_identity(value)["disable_spoofing"], ["audio", "gpu"])
        self.assertEqual(value["disable_spoofing"], ["gpu", "audio"])
        self.assertIn("--disable-spoofing=audio,gpu", engine.fingerprint_arguments(value))

    def test_reject_malformed_overrides_and_injection(self):
        original = engine.new_identity()
        cases = [("seed", True), ("seed", 0), ("seed", -1), ("seed", 2**32), ("seed", "1"), ("schema", True),
                 ("mode", "javascript"), ("engine_id", "stock-chrome"), ("locale", "en-US --no-sandbox"),
                 ("timezone", "UTC\n--no-sandbox"), ("hardware_concurrency", True),
                 ("hardware_concurrency", 3), ("disable_spoofing", ["gpu", "gpu"]),
                 ("disable_spoofing", ["webrtc"]), ("disable_spoofing", [None]), ("disable_spoofing", "gpu")]
        for key, bad in cases:
            with self.subTest(key=key, bad=bad):
                value = copy.deepcopy(original)
                value[key] = bad
                with self.assertRaises(engine.EngineError):
                    engine.validate_identity(value)
        value = {**original, "user_agent": "anything"}
        with self.assertRaises(engine.EngineError):
            engine.validate_identity(value)
        with self.assertRaises(engine.EngineError):
            engine.validate_identity({"schema": 1, "mode": "ordinary", "seed": 1})

    def test_ordinary_cannot_launch_native_engine(self):
        with self.assertRaises(engine.EngineError):
            engine.build_native_launch_arguments(Path("missing"), engine.new_identity("ordinary"), Path("profile"))


class EngineBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = self.root / engine.ENGINE_RELATIVE_DIRECTORY
        self.directory.mkdir(parents=True)
        self.payloads = {"chrome.exe": b"synthetic exe", "chrome.dll": b"synthetic dll", "locales/en-US.pak": b"synthetic locale"}
        for name, payload in self.payloads.items():
            path = self.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        self.manifest = {"format": engine.ENGINE_MANIFEST_FORMAT, "engine_id": engine.ENGINE_ID,
                         "version": engine.ENGINE_VERSION, "archive_url": engine.ENGINE_ARCHIVE_URL,
                         "archive_sha256": engine.ENGINE_ARCHIVE_SHA256, "archive_size": engine.ENGINE_ARCHIVE_SIZE,
                         "executable": "chrome.exe", "experimental": True,
                         "files": {name: hashlib.sha256(payload).hexdigest() for name, payload in self.payloads.items()}}
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self):
        (self.directory / engine.ENGINE_MANIFEST_NAME).write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_complete_bundle_and_launch_argv(self):
        with patch.object(engine, "windows_file_version", return_value=engine.ENGINE_VERSION):
            result = engine.verify_engine(self.root)
            argv = engine.build_native_launch_arguments(self.root, engine.new_identity(), self.root / "профиль с пробелами")
        self.assertEqual(result.executable, self.directory / "chrome.exe")
        self.assertEqual(argv[1], f"--user-data-dir={self.root / 'профиль с пробелами'}")
        self.assertTrue(result.experimental)

    def test_no_stock_browser_fallback(self):
        with self.assertRaises(engine.EngineError):
            engine.verify_engine(self.root / "no engine")

    def test_missing_and_changed_payload(self):
        (self.directory / "chrome.dll").write_bytes(b"tampered")
        with self.assertRaisesRegex(engine.EngineError, "целостности"):
            engine.verify_engine(self.root)
        (self.directory / "chrome.dll").unlink()
        with self.assertRaisesRegex(engine.EngineError, "Отсутствует"):
            engine.verify_engine(self.root)

    def test_unknown_payload_is_rejected(self):
        (self.directory / "extra.dll").write_bytes(b"extra")
        with self.assertRaisesRegex(engine.EngineError, "Состав"):
            engine.verify_engine(self.root)

    def test_resolver_caches_hashes_and_invalidates_changed_bundle(self):
        resolver = engine.EngineResolver(self.root)
        with patch.object(engine, "windows_file_version", return_value=engine.ENGINE_VERSION), patch.object(engine, "_sha256", wraps=engine._sha256) as hash_file:
            first = resolver.resolve()
            calls = hash_file.call_count
            self.assertIs(resolver.resolve(), first)
            self.assertEqual(hash_file.call_count, calls)
            (self.directory / "chrome.dll").write_bytes(b"tampered much longer dll")
            with self.assertRaises(engine.EngineError):
                resolver.resolve()
            self.assertGreater(hash_file.call_count, calls)

    def test_wrong_provenance_and_version(self):
        for key, value in [("version", "154.0.1.1"), ("archive_url", "https://example.test/core.zip"),
                           ("archive_sha256", "0" * 64), ("experimental", 1), ("archive_size", True)]:
            with self.subTest(key=key):
                good = self.manifest[key]
                self.manifest[key] = value
                self.write_manifest()
                with self.assertRaises(engine.EngineError):
                    engine.verify_engine(self.root)
                self.manifest[key] = good

    def test_runtime_file_version_is_independently_checked(self):
        with patch.object(engine, "windows_file_version", side_effect=[engine.ENGINE_VERSION, "154.0.1.1"]):
            with self.assertRaisesRegex(engine.EngineError, "FileVersion"):
                engine.verify_engine(self.root)

    def test_invalid_manifest_paths_and_duplicate_case(self):
        for raw in ["../evil.dll", "C:/evil", "dir\\evil", "dir/../evil", "dir//evil", "con.dll", "name. ", "./chrome.exe"]:
            with self.subTest(raw=raw):
                with self.assertRaises(engine.EngineError):
                    engine._safe_relative(raw)
        self.manifest["files"]["CHROME.EXE"] = self.manifest["files"]["chrome.exe"]
        self.write_manifest()
        with self.assertRaises(engine.EngineError):
            engine.verify_engine(self.root)

    def test_wrong_archive_cannot_install_or_overwrite(self):
        archive = self.root / "invalid.zip"
        archive.write_bytes(b"not the pinned archive")
        original = (self.directory / "chrome.exe").read_bytes()
        with self.assertRaises(engine.EngineError):
            engine.install_verified_archive(self.root, archive)
        self.assertEqual((self.directory / "chrome.exe").read_bytes(), original)


class OfflineInstallerTests(unittest.TestCase):
    def test_staging_cleanup_requires_validated_direct_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "Engine"
            parent.mkdir()
            valid = parent / ".native-install-synthetic"
            valid.mkdir()
            (valid / "owned.bin").write_bytes(b"owned")
            engine._cleanup_install_staging(valid, parent)
            self.assertFalse(valid.exists())
            invalid_targets = [parent, parent / "other", root / ".native-install-outside", parent / "nested" / ".native-install-nested"]
            for target in invalid_targets:
                target.mkdir(parents=True, exist_ok=True)
                with self.subTest(target=target), patch.object(engine.shutil, "rmtree") as delete:
                    with self.assertRaises(engine.EngineError):
                        engine._cleanup_install_staging(target, parent)
                    delete.assert_not_called()

    def test_verified_zip_root_and_prefixed_archive(self):
        for prefix in ["", "upstream/"]:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / "synthetic.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr(prefix + "chrome.exe", b"exe")
                    output.writestr(prefix + "chrome.dll", b"dll")
                    output.writestr(prefix + "locales/en-US.pak", b"pak")
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                with patch.object(engine, "ENGINE_ARCHIVE_SHA256", digest), patch.object(engine, "ENGINE_ARCHIVE_SIZE", archive.stat().st_size), patch.object(engine, "windows_file_version", return_value=engine.ENGINE_VERSION):
                    destination = engine.install_verified_archive(root, archive)
                    self.assertEqual(engine.verify_engine(root).executable, destination / "chrome.exe")
                    with self.assertRaisesRegex(engine.EngineError, "уже существует"):
                        engine.install_verified_archive(root, archive)

    def test_pinned_but_unsafe_archive_is_rejected_before_extract(self):
        for bad_path in ["../escape.dll", "CHROME.EXE", "locales/../escape.dll", "con.dll"]:
            with self.subTest(path=bad_path), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / "synthetic.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr("chrome.exe", b"exe")
                    output.writestr("chrome.dll", b"dll")
                    output.writestr(bad_path, b"evil")
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                with patch.object(engine, "ENGINE_ARCHIVE_SHA256", digest), patch.object(engine, "ENGINE_ARCHIVE_SIZE", archive.stat().st_size):
                    with self.assertRaises(engine.EngineError):
                        engine.install_verified_archive(root, archive)
                self.assertFalse((root / engine.ENGINE_RELATIVE_DIRECTORY).exists())
                self.assertFalse(any((root / "Engine").glob(".native-install-*")))


if __name__ == "__main__":
    unittest.main()
