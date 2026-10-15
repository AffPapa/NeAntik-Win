"""Ordinary-browser-only profile contract tests."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
import tempfile
import zipfile
from unittest.mock import Mock, patch

import profile_identity as identity
from nevision_win import AppPaths, BrowserLauncher, NeVisionError, Storage


class OrdinaryIdentityTests(unittest.TestCase):
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

    def test_native_preview_metadata_is_accepted_for_legacy_recovery_but_never_launched(self):
        first = identity.native_preview_identity()
        second = identity.native_preview_identity()
        self.assertNotEqual(first["seed"], second["seed"])
        self.assertEqual(identity.validate_identity(first), first)
        self.assertEqual(identity.native_preview_identity(123456)["seed"], "123456")
        with self.assertRaisesRegex(identity.CoreError, "отключённый экспериментальный режим"):
            identity.identity_arguments(identity.native_preview_identity(123456))

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
                with self.assertRaises(NeVisionError):
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
            self.assertFalse(any(arg.startswith("--neantik-") for arg in args))
            self.assertFalse(any("fingerprint" in arg.lower() or "user-agent" in arg.lower() for arg in args))

    @unittest.skipUnless(sys.platform == "win32", "Windows junction launch gate")
    def test_launcher_rejects_network_junction_before_browser_selection_or_spawn(self):
        with tempfile.TemporaryDirectory(prefix="neantik-profile-junction-") as temporary:
            root = Path(temporary)
            storage = Storage(AppPaths(root))
            profile_a = storage.save_profile({"name": "Synthetic profile A"})
            profile_b = storage.save_profile({"name": "Synthetic profile B"})
            path_a = storage.profile_path(profile_a) / "Default" / "Network"
            path_b = storage.profile_path(profile_b) / "Default" / "Network"
            path_a.mkdir(parents=True)
            path_b.mkdir(parents=True)
            junction = path_a
            os.rmdir(junction)
            command = Path(os.environ["WINDIR"]) / "System32" / "cmd.exe"
            result = subprocess.run(
                [str(command), "/d", "/c", "mklink", "/J", str(junction), str(path_b)],
                capture_output=True, text=True, timeout=10, check=False,
            )
            try:
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                self.assertTrue(junction.is_junction())
                launcher = BrowserLauncher(storage)
                before_family = storage.get_profile(profile_a).get("browser_family")
                with patch.object(launcher, "resolve_browser") as resolve, \
                     patch.object(storage, "ensure_profile_closed") as ensure_closed, \
                     patch.object(storage, "pin_browser_family") as pin, \
                     patch("nevision_win.initialize_privacy_defaults") as initialize_defaults, \
                     patch("nevision_win.subprocess.Popen") as spawn:
                    with self.assertRaisesRegex(NeVisionError, "ключевом хранилище Chromium"):
                        launcher.launch(storage.get_profile(profile_a))
                resolve.assert_not_called()
                ensure_closed.assert_not_called()
                pin.assert_not_called()
                initialize_defaults.assert_not_called()
                spawn.assert_not_called()
                self.assertEqual(storage.get_profile(profile_a).get("browser_family"), before_family)
                self.assertTrue(path_b.is_dir())
            finally:
                # Remove only the junction itself; never recurse into its target.
                if junction.is_junction():
                    os.rmdir(junction)

    def test_native_preview_profile_is_blocked_and_unchanged_before_browser_selection(self):
        with tempfile.TemporaryDirectory(prefix="neantik-native-guard-") as temporary:
            root = Path(temporary)
            storage = Storage(AppPaths(root))
            original = identity.native_preview_identity(123456)
            profile_id = storage.save_profile({"name": "Preview", "fingerprint": original})
            launcher = BrowserLauncher(storage)
            with patch.object(launcher, "resolve_browser") as resolve, patch("nevision_win.subprocess.Popen") as spawn:
                with self.assertRaisesRegex(NeVisionError, "отключённый экспериментальный режим"):
                    launcher.launch(storage.get_profile(profile_id))
            resolve.assert_not_called()
            spawn.assert_not_called()
            self.assertEqual(storage.get_profile(profile_id)["fingerprint"], original)

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

    def test_schema1_legacy_marker_backup_restore_stays_blocked(self):
        with tempfile.TemporaryDirectory(prefix="neantik-legacy-marker-backup-") as temporary:
            storage = Storage(AppPaths(Path(temporary)))
            blocked = {"schema": 1, "mode": identity.LEGACY_UNAVAILABLE}
            profile_id = storage.save_profile({"name": "Legacy unavailable", "fingerprint": blocked})
            (storage.profile_path(profile_id) / "state.txt").write_text("synthetic", encoding="utf-8")

            archive = storage.backup_profile(profile_id)
            with zipfile.ZipFile(archive) as packed:
                manifest = json.loads(packed.read("nevision-manifest.json"))
            self.assertEqual(manifest["format"], "neantik-profile-backup-v3")
            self.assertEqual(manifest["profile"]["fingerprint"], blocked)

            restored_id = storage.restore_profile(archive)
            restored = storage.get_profile(restored_id)
            self.assertEqual(restored["fingerprint"], blocked)
            self.assertEqual((storage.profile_path(restored_id) / "state.txt").read_text(encoding="utf-8"), "synthetic")
            launcher = BrowserLauncher(storage)
            with patch.object(launcher, "resolve_browser") as resolve, patch("nevision_win.subprocess.Popen") as spawn:
                with self.assertRaisesRegex(NeVisionError, "отключённый экспериментальный режим"):
                    launcher.launch(restored)
            resolve.assert_not_called()
            spawn.assert_not_called()

    def test_native_backup_cannot_be_downgraded_or_launder_legacy_format(self):
        with tempfile.TemporaryDirectory(prefix="neantik-native-backup-format-") as temporary:
            root = Path(temporary)
            storage = Storage(AppPaths(root))
            fingerprint = identity.native_preview_identity(123456)
            for archive_format in ("nevision-profile-backup-v1", "neantik-profile-backup-v2"):
                archive = root / f"{archive_format}.zip"
                with zipfile.ZipFile(archive, "w") as packed:
                    packed.writestr("nevision-manifest.json", json.dumps({
                        "format": archive_format, "profile": {"name": "Invalid", "fingerprint": fingerprint}}))
                    packed.writestr("profile/state.txt", "fixture")
                with self.subTest(archive_format=archive_format), self.assertRaisesRegex(NeVisionError, "Формат backup"):
                    storage.restore_profile(archive)
            self.assertEqual(storage.list_profiles(), [])


if __name__ == "__main__":
    unittest.main()
