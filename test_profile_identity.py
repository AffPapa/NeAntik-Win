"""Ordinary-browser-only profile contract tests."""
import unittest
from pathlib import Path
import tempfile
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


if __name__ == "__main__":
    unittest.main()
