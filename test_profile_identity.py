"""Ordinary-browser-only profile contract tests."""
import unittest
import json
from pathlib import Path
import tempfile
import zipfile
from unittest.mock import Mock, patch

import profile_identity as identity
from nevision_win import (AppPaths, BrowserLauncher, NATIVE_PREVIEW_PATCH_SHA256,
                          NeVisionError, Storage)


class OrdinaryIdentityTests(unittest.TestCase):
    @staticmethod
    def fake_bundled_core(root: Path, native: bool) -> Path:
        engine = root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        for name in ("chrome.exe", "chrome.dll", "icudtl.dat", "resources.pak"):
            (engine / name).write_bytes(b"fixture")
        receipt = {"format": "neantik-chromium-source-build-v1", "chromium_version": "155.0.8059.40",
                   "source_commit": "cfaadc5a132d78e1828635aa8405a499f3e14864",
                   "privacy_patch_sha256": NATIVE_PREVIEW_PATCH_SHA256 if native else "a" * 64}
        if native:
            receipt["native_persona_patch_sha256"] = NATIVE_PREVIEW_PATCH_SHA256
            receipt["native_persona_core_info"] = {
                "engine_id": "neantik-chromium", "schema": 1,
                "version": receipt["chromium_version"], "source_commit": receipt["source_commit"],
                "capabilities": {key: True for key in ("stable_seed", "hardware_concurrency",
                                                  "device_memory", "canvas_opaque_srgb_uint8", "timezone")}}
        (engine / "ENGINE_PROVENANCE.json").write_text(json.dumps(receipt), encoding="utf-8")
        return engine / "chrome.exe"

    def test_ordinary_profiles_never_add_browser_override_flags(self):
        ordinary = identity.ordinary_identity()
        self.assertEqual(identity.validate_identity(ordinary), ordinary)
        self.assertEqual(identity.identity_arguments(ordinary), [])
        self.assertEqual(identity.serialize_identity(ordinary), '{"mode":"ordinary","schema":1}')

    def test_legacy_native_metadata_is_reduced_to_non_runnable_marker(self):
        legacy = {"schema": 1, "mode": "native", "engine_id": "old", "seed": 123,
                  "hardware_concurrency": 8, "device_memory": "8", "timezone": "UTC"}
        safe = identity.validate_identity(legacy)
        self.assertEqual(safe, {"schema": 1, "mode": identity.LEGACY_UNAVAILABLE})
        self.assertNotIn("seed", identity.serialize_identity(legacy))
        with self.assertRaises(identity.CoreError):
            identity.identity_arguments(legacy)

    def test_unknown_profile_metadata_is_rejected(self):
        for invalid in ({"schema": True, "mode": "ordinary"},
                        {"schema": 1, "mode": "ordinary", "seed": 1},
                        {"schema": 2, "mode": "ordinary"}):
            with self.subTest(invalid=invalid), self.assertRaises(identity.CoreError):
                identity.validate_identity(invalid)

    def test_new_native_preview_identity_is_canonical_and_distinct(self):
        first = identity.native_preview_identity()
        second = identity.native_preview_identity()
        self.assertNotEqual(first["seed"], second["seed"])
        self.assertEqual(identity.validate_identity(first), first)
        self.assertEqual(identity.native_preview_identity(123456)["seed"], "123456")
        self.assertEqual(identity.identity_arguments(identity.native_preview_identity(123456)), [
            "--neantik-fingerprint-seed=123456", "--neantik-hardware-concurrency=4",
            "--neantik-device-memory=8", "--neantik-timezone=UTC"])

    def test_native_preview_rejects_malformed_or_legacy_seed(self):
        for seed in (0, -1, 2**64, True):
            with self.subTest(seed=seed), self.assertRaises(identity.CoreError):
                identity.native_preview_identity(seed)
        for seed in (123, "0", "01", "-1", "1e3", str(2**64), " 123"):
            with self.subTest(seed=seed), self.assertRaises(identity.CoreError):
                identity.validate_identity({"schema": 2, "mode": identity.NATIVE_PREVIEW, "seed": seed})
        with self.assertRaises(identity.CoreError):
            identity.validate_identity({**identity.native_preview_identity(123), "timezone": "UTC"})

    def test_legacy_native_profile_is_never_started_in_stock_browser(self):
        with tempfile.TemporaryDirectory(prefix="neantik-no-native-launch-") as temporary:
            storage = Storage(AppPaths(Path(temporary)))
            profile_id = storage.save_profile({"name": "Legacy", "fingerprint": {
                "schema": 1, "mode": "native", "engine_id": "old", "seed": 42,
                "hardware_concurrency": 8, "device_memory": "8"}})
            launcher = BrowserLauncher(storage)
            with patch.object(launcher, "resolve_browser") as stock, patch("nevision_win.subprocess.Popen") as spawn:
                with self.assertRaisesRegex(NeVisionError, "экспериментальный профиль"):
                    launcher.launch(storage.get_profile(profile_id))
            stock.assert_not_called()
            spawn.assert_not_called()

    def test_ordinary_launch_uses_only_stock_browser_arguments(self):
        with tempfile.TemporaryDirectory(prefix="neantik-ordinary-launch-") as temporary:
            storage = Storage(AppPaths(Path(temporary)))
            profile_id = storage.save_profile({"name": "Ordinary"})
            launcher = BrowserLauncher(storage)
            process = Mock()
            process.poll.return_value = None
            stock_browser = Path(temporary) / "chrome.exe"
            with patch.object(launcher, "resolve_browser", return_value=stock_browser), \
                 patch.object(storage, "wait_for_chromium_lock"), \
                 patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
                launcher.launch(storage.get_profile(profile_id))
            args = spawn.call_args.args[0]
            self.assertEqual(args[0], str(stock_browser))
            self.assertEqual(identity.identity_arguments(storage.get_profile(profile_id)["fingerprint"]), [])
            self.assertFalse(any("fingerprint" in arg.lower() or "user-agent" in arg.lower() for arg in args))

    def test_native_preview_rejects_old_core_before_spawn(self):
        with tempfile.TemporaryDirectory(prefix="neantik-native-guard-") as temporary:
            root = Path(temporary)
            storage = Storage(AppPaths(root))
            profile_id = storage.save_profile({"name": "Preview", "fingerprint": identity.native_preview_identity(123456)})
            self.fake_bundled_core(root, native=False)
            launcher = BrowserLauncher(storage)
            with patch("nevision_win.subprocess.Popen") as spawn:
                with self.assertRaisesRegex(NeVisionError, "проверенное встроенное ядро"):
                    launcher.launch(storage.get_profile(profile_id))
            spawn.assert_not_called()

    def test_native_preview_uses_only_verified_bundled_core(self):
        with tempfile.TemporaryDirectory(prefix="neantik-native-launch-") as temporary:
            root = Path(temporary)
            storage = Storage(AppPaths(root))
            profile_id = storage.save_profile({"name": "Preview", "fingerprint": identity.native_preview_identity(123456)})
            engine = self.fake_bundled_core(root, native=True)
            launcher = BrowserLauncher(storage)
            process = Mock()
            process.poll.return_value = None
            with patch.object(launcher, "ensure_bundled_sandbox_access"), \
                 patch.object(storage, "wait_for_chromium_lock"), \
                 patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
                launcher.launch(storage.get_profile(profile_id))
            args = spawn.call_args.args[0]
            self.assertEqual(args[0], str(engine))
            self.assertIn("--neantik-fingerprint-seed=123456", args)
            self.assertIn("--neantik-timezone=UTC", args)
            self.assertEqual(storage.get_profile(profile_id)["browser_family"], "chromium")

    def test_native_preview_backup_restore_preserves_identity_in_v3(self):
        with tempfile.TemporaryDirectory(prefix="neantik-native-backup-") as temporary:
            storage = Storage(AppPaths(Path(temporary)))
            identity_value = identity.native_preview_identity(123456)
            profile_id = storage.save_profile({"name": "Preview", "fingerprint": identity_value})
            (storage.profile_path(profile_id) / "smoke.txt").write_text("disposable", encoding="utf-8")
            archive = storage.backup_profile(profile_id)
            with zipfile.ZipFile(archive) as packed:
                manifest = json.loads(packed.read("nevision-manifest.json"))
            self.assertEqual(manifest["format"], "neantik-profile-backup-v3")
            self.assertEqual(manifest["profile"]["fingerprint"], identity_value)
            restored_id = storage.restore_profile(archive)
            self.assertNotEqual(restored_id, profile_id)
            self.assertEqual(storage.get_profile(restored_id)["fingerprint"], identity_value)
            self.assertEqual((storage.profile_path(restored_id) / "smoke.txt").read_text(encoding="utf-8"), "disposable")


if __name__ == "__main__":
    unittest.main()
