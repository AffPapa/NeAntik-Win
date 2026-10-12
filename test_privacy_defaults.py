"""Tests for one-time, non-destructive Chromium privacy preferences."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from privacy_defaults import initialize_privacy_defaults


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
        self.assertEqual(prefs["profile"]["default_content_setting_values"], {
            "geolocation": 2,
            "notifications": 2,
            "media_stream_camera": 2,
            "media_stream_mic": 2,
        })
        self.assertEqual(list((self.root / "Default").iterdir()), [self.root / "Default" / "Preferences"])

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
