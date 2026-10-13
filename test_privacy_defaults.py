"""Tests for one-time, non-destructive Chromium privacy preferences."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from privacy_defaults import (DOWNLOAD_MARKER_NAME, ensure_managed_download_directory,
                              initialize_privacy_defaults)


class PrivacyDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Profile"

    def test_new_profile_receives_verified_defaults(self):
        self.assertTrue(initialize_privacy_defaults(self.root))
        prefs = json.loads((self.root / "Default" / "Preferences").read_text("utf-8"))
        self.assertEqual(prefs["profile"]["cookie_controls_mode"], 1)
        self.assertEqual(prefs["net"]["network_prediction_options"], 2)
        self.assertEqual(prefs["newtab_page_location_override"], "about:blank")
        self.assertEqual(prefs["profile"]["default_content_setting_values"], {
            "geolocation": 2,
            "notifications": 2,
            "media_stream_camera": 2,
            "media_stream_mic": 2,
        })
        self.assertEqual(prefs["download"]["default_directory"], str(self.root.resolve() / "Downloads"))
        self.assertFalse(prefs["download"]["prompt_for_download"])
        self.assertTrue((self.root / "Downloads").is_dir())
        self.assertTrue((self.root / DOWNLOAD_MARKER_NAME).is_file())
        self.assertEqual(list((self.root / "Default").iterdir()), [self.root / "Default" / "Preferences"])

    def test_managed_downloads_rebase_after_portable_move(self):
        self.assertTrue(initialize_privacy_defaults(self.root))
        moved = Path(self.temp.name) / "MovedProfile"
        shutil.move(self.root, moved)
        self.assertTrue(ensure_managed_download_directory(moved))
        prefs = json.loads((moved / "Default" / "Preferences").read_text("utf-8"))
        marker = json.loads((moved / DOWNLOAD_MARKER_NAME).read_text("utf-8"))
        self.assertEqual(prefs["download"]["default_directory"], str(moved.resolve() / "Downloads"))
        self.assertEqual(marker["path"], prefs["download"]["default_directory"])
        self.assertTrue((moved / "Downloads").is_dir())

    @unittest.skipUnless(os.name == "nt", "extended Win32 paths are Windows-only")
    def test_extended_internal_path_is_not_written_to_chromium_preferences(self):
        extended = Path("\\\\?\\" + str(self.root.resolve()))
        self.assertTrue(initialize_privacy_defaults(extended))
        prefs = json.loads((self.root / "Default" / "Preferences").read_text("utf-8"))
        self.assertEqual(prefs["download"]["default_directory"], str(self.root.resolve() / "Downloads"))
        self.assertTrue(ensure_managed_download_directory(extended))

    def test_custom_download_directory_is_never_overwritten(self):
        self.assertTrue(initialize_privacy_defaults(self.root))
        prefs_path = self.root / "Default" / "Preferences"
        prefs = json.loads(prefs_path.read_text("utf-8"))
        custom = str((Path(self.temp.name) / "Custom").resolve())
        prefs["download"]["default_directory"] = custom
        prefs_path.write_text(json.dumps(prefs), encoding="utf-8")
        moved = Path(self.temp.name) / "MovedProfile"
        shutil.move(self.root, moved)
        self.assertFalse(ensure_managed_download_directory(moved))
        self.assertEqual(json.loads((moved / "Default" / "Preferences").read_text("utf-8"))["download"]["default_directory"], custom)

    def test_old_profile_without_marker_is_not_retrofitted(self):
        (self.root / "Default").mkdir(parents=True)
        prefs = self.root / "Default" / "Preferences"
        prefs.write_text('{"download":{"default_directory":"C:\\\\Other"}}', encoding="utf-8")
        self.assertFalse(ensure_managed_download_directory(self.root))
        self.assertIn("Other", prefs.read_text("utf-8"))

    def test_followup_does_not_overwrite_user_changes(self):
        self.assertTrue(initialize_privacy_defaults(self.root))
        prefs = self.root / "Default" / "Preferences"
        prefs.write_text('{"profile":{"cookie_controls_mode":0}}', encoding="utf-8")
        self.assertFalse(initialize_privacy_defaults(self.root))
        self.assertEqual(prefs.read_text("utf-8"), '{"profile":{"cookie_controls_mode":0}}')

    def test_existing_state_without_preferences_is_not_retrofitted(self):
        (self.root / "Default").mkdir(parents=True)
        (self.root / "Default" / "Cookies").write_bytes(b"existing")
        self.assertFalse(initialize_privacy_defaults(self.root))
        self.assertFalse((self.root / "Default" / "Preferences").exists())

    def test_existing_root_state_is_not_retrofitted(self):
        self.root.mkdir()
        (self.root / "Local State").write_text("{}", encoding="utf-8")
        self.assertFalse(initialize_privacy_defaults(self.root))
        self.assertFalse((self.root / "Default").exists())

    def test_existing_preferences_are_not_parsed(self):
        (self.root / "Default").mkdir(parents=True)
        prefs = self.root / "Default" / "Preferences"
        prefs.write_bytes(b"not-json")
        self.assertFalse(initialize_privacy_defaults(self.root))
        self.assertEqual(prefs.read_bytes(), b"not-json")

    def test_rejects_linked_default_directory(self):
        external = Path(self.temp.name) / "External"
        external.mkdir()
        self.root.mkdir()
        try:
            (self.root / "Default").symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink unavailable: {error}")
        with self.assertRaises(ValueError):
            initialize_privacy_defaults(self.root)
        self.assertEqual(list(external.iterdir()), [])

    def test_rejects_linked_root(self):
        external = Path(self.temp.name) / "External"
        external.mkdir()
        try:
            self.root.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink unavailable: {error}")
        with self.assertRaises(ValueError):
            initialize_privacy_defaults(self.root)
        self.assertEqual(list(external.iterdir()), [])

    def test_concurrent_preference_creation_is_preserved(self):
        real_link = os.link
        preferences = self.root / "Default" / "Preferences"

        def concurrent_write(source, target):
            preferences.write_bytes(b"user-preferences")
            return real_link(source, target)

        with mock.patch("privacy_defaults.os.link", side_effect=concurrent_write):
            self.assertFalse(initialize_privacy_defaults(self.root))
        self.assertEqual(preferences.read_bytes(), b"user-preferences")
        self.assertEqual(list(preferences.parent.iterdir()), [preferences])


if __name__ == "__main__":
    unittest.main()
