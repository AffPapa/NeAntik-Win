"""Core regression tests for NeVision Win. Run: python -m unittest test_nevision_win.py"""

import ctypes
import json
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import tkinter as tk
import unittest
import uuid
import warnings
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from nevision_win import (
    AppPaths,
    BrowserLauncher,
    NATIVE_PREVIEW_PATCH_SHA256,
    PRIVACY_CHECK_URL,
    DARK_COLORS,
    LIGHT_COLORS,
    NeVisionError,
    NeVisionApp,
    PORTABILITY_WARNING,
    SecretVault,
    Storage,
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
    canonical_path_key,
    directory_size,
    filesystem_path,
    normalize_theme_preference,
    normalize_proxy_host,
    proxy_host_requires_local_name_resolution,
    palette_for_theme,
    proxy_endpoint,
    proxy_choices,
    profile_network_note,
    resolve_theme,
)
from privacy_defaults import ensure_managed_download_directory, initialize_privacy_defaults
from profile_identity import native_preview_identity, ordinary_identity


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nevision-unit-"))
        self.storage = Storage(AppPaths(self.root))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_startup_rejects_database_hardlink_before_sqlite_opens(self):
        portable_root = self.root / "hardlink-portable"
        data = portable_root / "Data"
        data.mkdir(parents=True)
        outside = self.root / "synthetic-outside-database"
        outside.write_bytes(b"synthetic-only")
        database = data / "nevision.db"
        try:
            os.link(outside, database)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"hardlink creation is unavailable in this environment: {exc}")

        with patch("nevision_win.sqlite3.connect") as connect:
            with self.assertRaisesRegex(NeVisionError, "hardlink"):
                Storage(AppPaths(portable_root))
        connect.assert_not_called()
        self.assertEqual(outside.read_bytes(), b"synthetic-only")
        self.assertEqual(database.read_bytes(), b"synthetic-only")

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_startup_rejects_data_junction_before_sqlite_opens_outside_database(self):
        portable_root = self.root / "isolated-portable"
        portable_root.mkdir()
        outside = self.root / "outside-data-target"
        outside.mkdir()
        data = portable_root / "Data"
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(data), str(outside)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode:
            self.skipTest("Windows junction creation is unavailable in this environment")

        try:
            attributes = getattr(data.lstat(), "st_file_attributes", 0)
            self.assertTrue(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            with patch("nevision_win.sqlite3.connect") as connect:
                with self.assertRaisesRegex(NeVisionError, "junction"):
                    Storage(AppPaths(portable_root))
            connect.assert_not_called()
            self.assertFalse((outside / "nevision.db").exists())
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            if data.is_junction():
                os.rmdir(data)

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_startup_rejects_profiles_junction_before_sqlite_opens(self):
        portable_root = self.root / "profiles-portable"
        Storage(AppPaths(portable_root))
        profiles = portable_root / "Data" / "Profiles"
        held = portable_root / "Data" / "Profiles-before-junction"
        outside = self.root / "outside-profiles-target"
        outside.mkdir()
        os.replace(profiles, held)
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(profiles), str(outside)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode:
            os.replace(held, profiles)
            self.skipTest("Windows junction creation is unavailable in this environment")

        try:
            attributes = getattr(profiles.lstat(), "st_file_attributes", 0)
            self.assertTrue(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            with patch("nevision_win.sqlite3.connect") as connect:
                with self.assertRaisesRegex(NeVisionError, "junction"):
                    Storage(AppPaths(portable_root))
            connect.assert_not_called()
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            if profiles.is_junction():
                os.rmdir(profiles)
            if held.exists():
                os.replace(held, profiles)

    def test_shared_proxy_count_uses_id_and_updates_after_reassignment(self):
        shared = self.storage.save_proxy({"name": "same", "scheme": "http", "host": "127.0.0.1", "port": 8080})
        other = self.storage.save_proxy({"name": "same", "scheme": "http", "host": "127.0.0.2", "port": 8080})
        first = self.storage.save_profile({"name": "First", "proxy_id": shared})
        second = self.storage.save_profile({"name": "Second", "proxy_id": shared})
        self.storage.save_profile({"name": "Third", "proxy_id": other})
        self.assertEqual(self.storage.count_profiles_for_proxy(shared), 2)
        self.assertEqual(self.storage.count_profiles_for_proxy(other), 1)
        self.assertIn("2 профилям", dict(self.storage.health_check(first))["Сетевой выход"])
        self.storage.save_profile({"name": "Second", "proxy_id": other}, second)
        self.assertEqual(self.storage.count_profiles_for_proxy(shared), 1)
        self.assertEqual(self.storage.count_profiles_for_proxy(other), 2)

    def test_network_note_does_not_promise_anonymity(self):
        self.assertIn("прямой внешний IP", profile_network_note(None))
        self.assertIn("общий внешний IP", profile_network_note("proxy-id", 2))
        self.assertIn("не подтверждены", profile_network_note("proxy-id", 1))

    def test_profile_path_accepts_only_generated_uuid_hex_ids(self):
        valid_id = uuid.uuid4().hex
        self.assertEqual(self.storage.profile_path(valid_id), self.storage.paths.profiles / valid_id)
        for invalid_id in (
            "../outside", r"..\outside", r"C:\outside", "C:/outside", "/outside",
            "A" * 32, "a" * 31, "a" * 33, "__data_recovery__",
        ):
            with self.subTest(profile_id=invalid_id), self.assertRaisesRegex(NeVisionError, "идентификатор профиля"):
                self.storage.profile_path(invalid_id)

    def test_corrupt_profile_id_cannot_backup_or_delete_outside_profiles(self):
        invalid_id = "../outside"
        outside = self.storage.paths.data / "outside"
        outside.mkdir()
        marker = outside / "synthetic-do-not-touch.txt"
        marker.write_text("synthetic outside-profile fixture", encoding="utf-8")
        with self.storage.connection() as db:
            db.execute(
                """INSERT INTO profiles(id, name, group_name, tags, notes, browser_family, created_at, updated_at)
                   VALUES (?, ?, '', '', '', '', ?, ?)""",
                (invalid_id, "Synthetic corrupt row", "2026-10-15T00:00:00Z", "2026-10-15T00:00:00Z"),
            )

        for operation in (self.storage.backup_profile, self.storage.delete_profile):
            with self.subTest(operation=operation.__name__), self.assertRaisesRegex(
                NeVisionError, "идентификатор профиля"
            ):
                operation(invalid_id)

        self.assertEqual(marker.read_text(encoding="utf-8"), "synthetic outside-profile fixture")
        self.assertIsNotNone(self.storage.get_profile(invalid_id))
        self.assertEqual(list(self.storage.paths.backups.iterdir()), [])

    def test_profile_template_moves_only_safe_fields_into_a_new_empty_profile(self):
        proxy_password = "synthetic-proxy-password-not-for-template"
        proxy_user = "synthetic-proxy-user-not-for-template"
        note = "synthetic-private-note-not-for-template"
        cookie = b"synthetic-cookie-not-for-template"
        proxy_id = self.storage.save_proxy({
            "name": "Private proxy", "scheme": "http", "host": "127.0.0.1",
            "port": 8080, "username": proxy_user, "password": proxy_password,
        })
        original_identity = ordinary_identity()
        original_id = self.storage.save_profile({
            "name": "QA profile", "group_name": "Research", "tags": "test",
            "notes": note, "proxy_id": proxy_id, "fingerprint": original_identity,
        })
        browser_data = self.storage.profile_path(original_id) / "Default"
        browser_data.mkdir()
        (browser_data / "Cookies").write_bytes(cookie)

        template_path = self.storage.export_profile_template(original_id)
        encoded = template_path.read_bytes()
        self.assertLessEqual(len(encoded), 64 * 1024)
        template = json.loads(encoded.decode("utf-8"))
        self.assertEqual(template, {
            "format": "neantik-profile-template-v1",
            "profile": {"name": "QA profile", "group_name": "Research", "tags": "test", "mode": "ordinary"},
        })
        for forbidden in (proxy_password.encode(), proxy_user.encode(), note.encode(), cookie,
                          original_id.encode(), proxy_id.encode()):
            self.assertNotIn(forbidden, encoded)

        destination = Storage(AppPaths(self.root / "other-portable"))
        first_id = destination.import_profile_template(template_path)
        second_id = destination.import_profile_template(template_path)
        self.assertNotEqual(first_id, second_id)
        for new_id in (first_id, second_id):
            imported = destination.get_profile(new_id)
            self.assertEqual((imported["name"], imported["group_name"], imported["tags"]),
                             ("QA profile", "Research", "test"))
            self.assertEqual(imported["notes"], "")
            self.assertIsNone(imported["proxy_id"])
            self.assertEqual(imported["fingerprint"]["mode"], "ordinary")
            self.assertEqual(list(destination.profile_path(new_id).iterdir()), [])
        self.assertEqual((browser_data / "Cookies").read_bytes(), cookie)

    def test_profile_template_rejects_untrusted_fields_without_partial_profile(self):
        destination = Storage(AppPaths(self.root / "other-portable"))
        base = {"format": "neantik-profile-template-v1", "profile": {
            "name": "Synthetic", "group_name": "", "tags": "", "mode": "ordinary",
        }}
        invalid = [
            {**base, "format": "unknown-template-v9"},
            {**base, "proxy_password": "synthetic-secret"},
            {**base, "profile": {**base["profile"], "notes": "synthetic-secret"}},
            {**base, "profile": {**base["profile"], "seed": "123"}},
            {**base, "profile": {**base["profile"], "mode": "legacy-native-unavailable"}},
            {**base, "profile": {**base["profile"], "name": " "}},
            {**base, "profile": {**base["profile"], "tags": 3}},
        ]
        template_path = self.root / "input.neantik-profile.json"
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                template_path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.assertRaises(NeVisionError):
                    destination.import_profile_template(template_path)
                self.assertEqual(destination.list_profiles(), [])
                self.assertEqual(list(destination.paths.profiles.iterdir()), [])
        for malformed in (b"{", b'{"format":"neantik-profile-template-v1","format":"neantik-profile-template-v1"}', b"x" * (64 * 1024 + 1)):
            with self.subTest(malformed_length=len(malformed)):
                template_path.write_bytes(malformed)
                with self.assertRaises(NeVisionError):
                    destination.import_profile_template(template_path)
                self.assertEqual(destination.list_profiles(), [])
                self.assertEqual(list(destination.paths.profiles.iterdir()), [])

    def test_native_profile_template_export_is_disabled(self):
        original_id = self.storage.save_profile({"name": "Native", "fingerprint": native_preview_identity()})
        with self.assertRaises(NeVisionError):
            self.storage.export_profile_template(original_id)

    def test_ordinary_profile_template_import_does_not_require_native_core(self):
        original_id = self.storage.save_profile({"name": "Ordinary"})
        template_path = self.storage.export_profile_template(original_id)
        destination = Storage(AppPaths(self.root / "other-portable"))
        imported_id = destination.import_profile_template(template_path)
        self.assertEqual(destination.get_profile(imported_id)["fingerprint"]["mode"], "ordinary")
        self.assertEqual(list(destination.profile_path(imported_id).iterdir()), [])

    def test_profile_template_export_never_overwrites_an_existing_file(self):
        original_id = self.storage.save_profile({"name": "Collision"})
        with patch("nevision_win.datetime") as fixed_clock, patch("nevision_win.uuid.uuid4") as fixed_uuid:
            fixed_clock.now.return_value = datetime(2026, 10, 14, 12, 0, 0)
            fixed_uuid.return_value.hex = "a" * 32
            template_path = self.storage.export_profile_template(original_id)
            original = template_path.read_bytes()
            with self.assertRaisesRegex(NeVisionError, "уже существует"):
                self.storage.export_profile_template(original_id)
        self.assertEqual(template_path.read_bytes(), original)
        self.assertEqual(len(list(self.storage.paths.backups.glob("*.neantik-profile.json"))), 1)

    def test_proxy_profile_backup_restore(self):
        clear = "local-password"
        self.assertEqual(SecretVault.decrypt(SecretVault.encrypt(clear)), clear)
        proxy_id = self.storage.save_proxy({"name": "p", "scheme": "http", "host": "127.0.0.1", "port": 8080, "username": "u", "password": clear})
        profile_id = self.storage.save_profile({"name": "A", "group_name": "QA", "tags": "test", "notes": "note", "proxy_id": proxy_id})
        folder = self.storage.profile_path(profile_id)
        (folder / "Default").mkdir(parents=True)
        (folder / "Default" / "state.txt").write_text("state", encoding="utf-8")
        archive = self.storage.backup_profile(profile_id)
        restored = self.storage.restore_profile(archive, "B")
        self.assertEqual((self.storage.profile_path(restored) / "Default" / "state.txt").read_text(encoding="utf-8"), "state")
        self.assertIsNone(self.storage.get_profile(restored)["proxy_id"])

    def test_backup_restore_rebases_managed_downloads_without_losing_files(self):
        profile_id = self.storage.save_profile({"name": "Portable downloads QA"})
        source = self.storage.profile_path(profile_id)
        self.assertTrue(initialize_privacy_defaults(source))
        (source / "Downloads" / "synthetic.txt").write_text("owned test file", encoding="utf-8")
        archive = self.storage.backup_profile(profile_id)
        restored_id = self.storage.restore_profile(archive, "Restored downloads QA")
        restored = self.storage.profile_path(restored_id)
        self.assertNotEqual(source, restored)
        self.assertTrue(ensure_managed_download_directory(restored))
        self.assertEqual((restored / "Downloads" / "synthetic.txt").read_text(encoding="utf-8"), "owned test file")
        prefs = json.loads((restored / "Default" / "Preferences").read_text(encoding="utf-8"))
        self.assertEqual(prefs["download"]["default_directory"], str(restored.resolve() / "Downloads"))

    def test_native_backup_restores_legacy_metadata_without_rewriting_it(self):
        identity = native_preview_identity()
        source_id = self.storage.save_profile({
            "name": "Native backup fixture",
            "fingerprint": identity,
        })
        source_file = self.storage.profile_path(source_id) / "Default" / "state.txt"
        source_file.parent.mkdir(parents=True)
        source_file.write_bytes(b"synthetic-native-profile")
        archive = self.storage.backup_profile(source_id)

        restored_id = self.storage.restore_profile(archive)

        self.assertEqual({profile["id"] for profile in self.storage.list_profiles()}, {source_id, restored_id})
        self.assertEqual(self.storage.get_profile(restored_id)["fingerprint"], identity)
        self.assertEqual(source_file.read_bytes(), b"synthetic-native-profile")
        self.assertEqual((self.storage.profile_path(restored_id) / "Default" / "state.txt").read_bytes(),
                         b"synthetic-native-profile")

        ordinary_id = self._profile_with_file("Ordinary backup fixture")
        ordinary_archive = self.storage.backup_profile(ordinary_id)
        restored_id = self.storage.restore_profile(ordinary_archive)
        self.assertIsNotNone(self.storage.get_profile(restored_id))

    def test_restore_rejects_zip_path_traversal_before_creating_profile(self):
        archive = self.storage.paths.backups / "unsafe.zip"
        manifest = {
            "format": "nevision-profile-backup-v1",
            "profile": {"name": "Unsafe", "group_name": "", "tags": "", "notes": ""},
        }
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("nevision-manifest.json", json.dumps(manifest))
            output.writestr("profile/../outside.txt", "must not be restored")

        with self.assertRaisesRegex(NeVisionError, "небезопасный путь"):
            self.storage.restore_profile(archive)
        self.assertEqual(self.storage.list_profiles(), [])

    def _profile_with_file(self, name: str = "A") -> str:
        profile_id = self.storage.save_profile({"name": name})
        folder = self.storage.profile_path(profile_id) / "Default"
        folder.mkdir(parents=True)
        (folder / "state.txt").write_text("state", encoding="utf-8")
        return profile_id

    def test_backup_paths_are_unique_and_atomic_failure_preserves_prior_backup(self):
        profile_id = self._profile_with_file()
        first = self.storage.backup_profile(profile_id)
        original = first.read_bytes()
        second = self.storage.backup_profile(profile_id)

        self.assertNotEqual(first, second)
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        with patch.object(zipfile.ZipFile, "write", side_effect=OSError("simulated write failure")):
            with self.assertRaisesRegex(NeVisionError, "Не удалось создать backup"):
                self.storage.backup_profile(profile_id)

        self.assertEqual(first.read_bytes(), original)
        self.assertFalse(list(self.storage.paths.backups.glob("*.partial")))

    def test_backup_verification_failure_preserves_prior_archive_and_removes_partial(self):
        profile_id = self._profile_with_file()
        first = self.storage.backup_profile(profile_id)
        original = first.read_bytes()

        with patch.object(Storage, "_verify_created_backup", side_effect=NeVisionError("synthetic CRC failure")):
            with self.assertRaisesRegex(NeVisionError, "synthetic CRC failure"):
                self.storage.backup_profile(profile_id)

        self.assertEqual(first.read_bytes(), original)
        self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [first])
        self.assertFalse(list(self.storage.paths.backups.glob("*.partial")))

    def test_created_backup_verifier_rejects_corrupted_member_crc(self):
        profile_id = self._profile_with_file()
        profile = self.storage.get_profile(profile_id)
        source = self.storage.profile_path(profile_id)
        files_to_archive = self.storage._backup_files(source)
        manifest = {
            "format": "nevision-profile-backup-v1",
            "created_at": "2026-10-15T00:00:00Z",
            "profile": {key: profile.get(key) for key in ("id", "name", "group_name", "tags", "notes", "browser_family")},
            "proxy_credentials_included": False,
            "browser_session_data_included": True,
            "encrypted": False,
        }
        archive_path = self.storage.paths.backups / "synthetic-corrupt.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("nevision-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for file_path, relative in files_to_archive:
                archive.write(file_path, Path("profile") / relative)

        with zipfile.ZipFile(archive_path, "r") as archive:
            member = archive.getinfo("profile/Default/state.txt")
            header_offset = member.header_offset
        with archive_path.open("r+b") as target:
            target.seek(header_offset)
            local_header = target.read(30)
            name_size = int.from_bytes(local_header[26:28], "little")
            extra_size = int.from_bytes(local_header[28:30], "little")
            target.seek(header_offset + 30 + name_size + extra_size + 1)
            original_byte = target.read(1)
            self.assertEqual(len(original_byte), 1)
            target.seek(-1, os.SEEK_CUR)
            target.write(bytes([original_byte[0] ^ 0x01]))

        with self.assertRaises(NeVisionError):
            Storage._verify_created_backup(archive_path, manifest, files_to_archive)

    def test_backup_enforces_the_same_limits_as_restore(self):
        profile_id = self.storage.save_profile({"name": "Many files"})
        folder = self.storage.profile_path(profile_id)
        (folder / "one.txt").write_text("1", encoding="utf-8")
        (folder / "two.txt").write_text("2", encoding="utf-8")

        with patch("nevision_win.MAX_BACKUP_FILES", 1):
            with self.assertRaisesRegex(NeVisionError, "слишком много файлов"):
                self.storage.backup_profile(profile_id)
        self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [])

    def test_backup_rejects_hardlink_to_file_outside_profile(self):
        profile_id = self.storage.save_profile({"name": "Hardlink boundary"})
        outside = self.root / "outside-synthetic.txt"
        outside.write_text("synthetic content outside profile", encoding="utf-8")
        linked = self.storage.profile_path(profile_id) / "linked.txt"
        try:
            os.link(outside, linked)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"Hardlinks unavailable: {exc}")

        with self.assertRaisesRegex(NeVisionError, "hardlink"):
            self.storage.backup_profile(profile_id)
        self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [])
        self.assertEqual(list(self.storage.paths.backups.glob("*.partial")), [])
        self.assertEqual(outside.read_text(encoding="utf-8"), "synthetic content outside profile")

    def test_backup_rejects_file_symlink_instead_of_silently_omitting_it(self):
        profile_id = self.storage.save_profile({"name": "File symlink boundary"})
        outside = self.root / "outside-synthetic-symlink-target.txt"
        outside.write_text("synthetic content outside profile", encoding="utf-8")
        linked = self.storage.profile_path(profile_id) / "linked.txt"
        try:
            linked.symlink_to(outside)
        except (NotImplementedError, OSError):
            # Exercise the fail-closed branch even when Windows symlink creation
            # is disabled for this account.
            linked.write_text("synthetic placeholder", encoding="utf-8")
            original_is_symlink = Path.is_symlink

            def fake_is_symlink(path):
                return path == filesystem_path(linked) or original_is_symlink(path)

            with patch.object(Path, "is_symlink", fake_is_symlink):
                with self.assertRaisesRegex(NeVisionError, "ссылки/reparse-файлы"):
                    self.storage.backup_profile(profile_id)
        else:
            with self.assertRaisesRegex(NeVisionError, "ссылки/reparse-файлы"):
                self.storage.backup_profile(profile_id)
        self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [])
        self.assertEqual(list(self.storage.paths.backups.glob("*.partial")), [])
        self.assertEqual(outside.read_text(encoding="utf-8"), "synthetic content outside profile")

    @unittest.skipUnless(hasattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT"), "Windows reparse attribute")
    def test_backup_rejects_reparse_file_without_partial_archive(self):
        profile_id = self.storage.save_profile({"name": "Reparse file boundary"})
        linked = self.storage.profile_path(profile_id) / "synthetic-reparse.txt"
        linked.write_text("synthetic file", encoding="utf-8")
        original_lstat = Path.lstat

        def fake_lstat(path, *args, **kwargs):
            value = original_lstat(path, *args, **kwargs)
            if path == filesystem_path(linked):
                return SimpleNamespace(st_mode=value.st_mode,
                                       st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return value

        with patch.object(Path, "lstat", fake_lstat):
            with self.assertRaisesRegex(NeVisionError, "ссылки/reparse-файлы"):
                self.storage.backup_profile(profile_id)
        self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [])
        self.assertEqual(list(self.storage.paths.backups.glob("*.partial")), [])
        self.assertEqual(linked.read_text(encoding="utf-8"), "synthetic file")

    @unittest.skipUnless(os.name == "nt" and hasattr(Path, "is_junction"),
                         "Windows junction behavior")
    def test_backup_rejects_directory_junction_without_partial_archive(self):
        profile_id = self.storage.save_profile({"name": "Directory junction boundary"})
        outside = self.root / "outside-synthetic-junction-target"
        outside.mkdir()
        marker = outside / "marker.txt"
        marker.write_text("synthetic content outside profile", encoding="utf-8")

        profile = self.storage.profile_path(profile_id)
        junction = profile / "Default" / "Network"
        junction.parent.mkdir(parents=True)
        command = Path(os.environ["WINDIR"]) / "System32" / "cmd.exe"
        result = subprocess.run(
            [str(command), "/d", "/c", "mklink", "/J", str(junction), str(outside)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode or not junction.is_junction():
            if junction.exists():
                junction.rmdir()
            self.skipTest("Windows junction creation is unavailable in this environment")

        try:
            with self.assertRaisesRegex(NeVisionError, "junction"):
                self.storage.backup_profile(profile_id)
            self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [])
            self.assertEqual(list(self.storage.paths.backups.glob("*.partial")), [])
            self.assertEqual(marker.read_text(encoding="utf-8"),
                             "synthetic content outside profile")
        finally:
            # Remove only the junction itself; never recurse into its target.
            if junction.is_junction():
                os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "Windows Chromium lockfile semantics")
    def test_backup_and_delete_refuse_an_externally_locked_chromium_profile(self):
        profile_id = self._profile_with_file("Locked profile")
        lock_file = self.storage.profile_path(profile_id) / "lockfile"
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        )
        create_file.restype = ctypes.c_void_p
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (ctypes.c_void_p,)
        close_handle.restype = ctypes.c_bool
        handle = create_file(str(lock_file), 0x40000000, 0x00000001, None, 2, 0x00000080, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)

        try:
            with self.assertRaisesRegex(NeVisionError, "занят запущенным Chromium"):
                self.storage.backup_profile(profile_id)
            with self.assertRaisesRegex(NeVisionError, "занят запущенным Chromium"):
                self.storage.delete_profile(profile_id)
            launcher = BrowserLauncher(self.storage)
            with patch.object(launcher, "resolve_browser", return_value=Path("C:/chrome.exe")):
                with patch("nevision_win.subprocess.Popen") as launch_process:
                    with self.assertRaisesRegex(NeVisionError, "занят запущенным Chromium"):
                        launcher.launch(self.storage.get_profile(profile_id))
                    launch_process.assert_not_called()
        finally:
            close_handle(handle)

        # A stale lockfile is deliberately not a false positive after Chrome exits.
        self.storage.ensure_profile_closed(profile_id)

        self.assertIsNotNone(self.storage.get_profile(profile_id))
        self.assertTrue(self.storage.profile_path(profile_id).is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows named mutex semantics")
    def test_profile_operation_lock_rejects_a_second_nevision_thread(self):
        profile_id = self._profile_with_file("Mutex profile")
        result: list[str] = []
        finished = threading.Event()

        def contender() -> None:
            try:
                with Storage(AppPaths(self.root)).profile_operation_lock(profile_id):
                    result.append("acquired")
            except NeVisionError as exc:
                result.append(str(exc))
            finally:
                finished.set()

        with self.storage.profile_operation_lock(profile_id):
            worker = threading.Thread(target=contender, daemon=True)
            worker.start()
            self.assertTrue(finished.wait(2), "Second operation did not return promptly")
        worker.join(2)

        self.assertEqual(len(result), 1)
        self.assertIn("другой операцией NeAntik Win", result[0])

    def test_startup_reconciles_interrupted_delete(self):
        profile_id = self._profile_with_file("Recover delete")
        source = self.storage.profile_path(profile_id)
        deleted_root = self.storage.data_deleted_root()
        deleted_root.mkdir(parents=True)
        target = deleted_root / "recover-delete"
        self.storage._create_operation_journal(
            {"operation": "delete", "profile_id": profile_id, "deleted_dir": target.name}
        )
        os.replace(source, target)

        recovered = Storage(AppPaths(self.root))

        self.assertIsNotNone(recovered.get_profile(profile_id))
        self.assertTrue((recovered.profile_path(profile_id) / "Default" / "state.txt").is_file())
        self.assertFalse(target.exists())
        self.assertEqual(list(recovered.paths.operations.glob("*.json")), [])

    def test_startup_reconciles_committed_delete_before_journal_cleanup_idempotently(self):
        profile_id = self._profile_with_file("Committed delete")
        unrelated_id = self._profile_with_file("Unrelated survivor")
        source = self.storage.profile_path(profile_id)
        marker = source / "Default" / "state.txt"
        expected_state = marker.read_bytes()

        class SimulatedPowerLoss(BaseException):
            pass

        # Interrupt the real delete operation after its SQLite commit, at the
        # last journal-cleanup step. BaseException models abrupt process loss.
        with patch.object(self.storage, "_discard_operation_journal", side_effect=SimulatedPowerLoss):
            with self.assertRaises(SimulatedPowerLoss):
                self.storage.delete_profile(profile_id)

        journals = list(self.storage.paths.operations.glob("*.json"))
        self.assertEqual(len(journals), 1)
        payload = json.loads(journals[0].read_text(encoding="utf-8"))
        target = self.storage.data_deleted_root() / payload["deleted_dir"]
        self.assertEqual(payload["operation"], "delete")
        self.assertFalse(source.exists())
        self.assertTrue(target.is_dir())
        self.assertIsNone(self.storage.get_profile(profile_id))

        recovered = Storage(AppPaths(self.root))
        self.assertIsNone(recovered.get_profile(profile_id))
        self.assertEqual((target / "Default" / "state.txt").read_bytes(), expected_state)
        self.assertIsNotNone(recovered.get_profile(unrelated_id))
        self.assertTrue((recovered.profile_path(unrelated_id) / "Default" / "state.txt").is_file())
        self.assertEqual(list(recovered.paths.operations.glob("*.json")), [])

        restarted = Storage(AppPaths(self.root))
        self.assertIsNone(restarted.get_profile(profile_id))
        self.assertEqual((target / "Default" / "state.txt").read_bytes(), expected_state)
        self.assertIsNotNone(restarted.get_profile(unrelated_id))

    def test_startup_reconciles_committed_restore_before_journal_cleanup_idempotently(self):
        source_id = self._profile_with_file("Restore commit source")
        source_state = self.storage.profile_path(source_id) / "Default" / "state.txt"
        expected_state = source_state.read_bytes()
        archive = self.storage.backup_profile(source_id)

        class SimulatedPowerLoss(BaseException):
            pass

        # Interrupt the real restore after its SQLite commit, before its journal
        # is removed, so startup exercises the committed-state recovery branch.
        with patch.object(self.storage, "_discard_operation_journal", side_effect=SimulatedPowerLoss):
            with self.assertRaises(SimulatedPowerLoss):
                self.storage.restore_profile(archive, "Committed restore")

        journals = list(self.storage.paths.operations.glob("*.json"))
        self.assertEqual(len(journals), 1)
        payload = json.loads(journals[0].read_text(encoding="utf-8"))
        restored_id = payload["profile"]["id"]
        restored_path = self.storage.profile_path(restored_id)
        marker = restored_path / "Default" / "state.txt"
        self.assertEqual(payload["operation"], "restore")
        self.assertTrue(restored_path.is_dir())
        self.assertIsNotNone(self.storage.get_profile(restored_id))
        self.assertEqual(marker.read_bytes(), expected_state)

        recovered = Storage(AppPaths(self.root))
        self.assertEqual(recovered.get_profile(restored_id)["name"], "Committed restore")
        self.assertEqual(marker.read_bytes(), expected_state)
        self.assertEqual(source_state.read_bytes(), expected_state)
        self.assertIsNotNone(recovered.get_profile(source_id))
        self.assertEqual(len(recovered.list_profiles()), 2)
        self.assertEqual(list(recovered.paths.operations.glob("*.json")), [])

        restarted = Storage(AppPaths(self.root))
        self.assertEqual(restarted.get_profile(restored_id)["name"], "Committed restore")
        self.assertEqual(marker.read_bytes(), expected_state)
        self.assertEqual(len(restarted.list_profiles()), 2)

    def test_startup_reconciles_interrupted_restore(self):
        profile_id = uuid.uuid4().hex
        staging = self.storage.paths.profiles / ".restore-interrupted.partial"
        staging.mkdir()
        (staging / "Default").mkdir()
        (staging / "Default" / "state.txt").write_text("restored", encoding="utf-8")
        now = "2026-07-26T10:00:00+00:00"
        self.storage._create_operation_journal(
            {
                "operation": "restore",
                "staging_dir": staging.name,
                "profile": {
                    "id": profile_id,
                    "name": "Recovered profile",
                    "group_name": "QA",
                    "tags": "recovery",
                    "notes": "journal",
                    "created_at": now,
                    "updated_at": now,
                },
            }
        )
        os.replace(staging, self.storage.profile_path(profile_id))

        recovered = Storage(AppPaths(self.root))

        self.assertEqual(recovered.get_profile(profile_id)["name"], "Recovered profile")
        self.assertEqual((recovered.profile_path(profile_id) / "Default" / "state.txt").read_text(encoding="utf-8"), "restored")
        self.assertEqual(list(recovered.paths.operations.glob("*.json")), [])

    def test_restore_recovery_after_profile_directory_publish_interruption(self):
        source_id = self._profile_with_file("Restore interruption source")
        archive = self.storage.backup_profile(source_id)
        original_replace = os.replace

        class InjectedInterruption(BaseException):
            pass

        def publish_then_interrupt(source, destination):
            source_path = Path(source)
            destination_path = Path(destination)
            destination_id = destination_path.name
            is_profile_publish = (
                source_path.is_dir()
                and source_path.name.startswith(".restore-")
                and source_path.parent.name.casefold() == "profiles"
                and destination_path.parent.name.casefold() == "profiles"
                and len(destination_id) == 32
                and all(character in "0123456789abcdef" for character in destination_id.casefold())
            )
            result = original_replace(source, destination)
            if is_profile_publish:
                raise InjectedInterruption()
            return result

        with patch("nevision_win.os.replace", side_effect=publish_then_interrupt):
            with self.assertRaises(InjectedInterruption):
                self.storage.restore_profile(archive, "Restored after interruption")

        journals = list(self.storage.paths.operations.glob("*.json"))
        self.assertEqual(len(journals), 1)
        restored_id = json.loads(journals[0].read_text(encoding="utf-8"))["profile"]["id"]
        restored_path = self.storage.profile_path(restored_id)
        self.assertTrue(restored_path.is_dir())
        self.assertFalse(
            any(profile["id"] == restored_id for profile in self.storage.list_profiles())
        )

        recovered = Storage(AppPaths(self.root))

        self.assertEqual(recovered.get_profile(restored_id)["name"], "Restored after interruption")
        self.assertEqual(
            (recovered.profile_path(restored_id) / "Default" / "state.txt").read_bytes(), b"state"
        )
        self.assertEqual(
            (recovered.profile_path(source_id) / "Default" / "state.txt").read_bytes(), b"state"
        )
        self.assertEqual(list(recovered.paths.operations.glob("*.json")), [])

    def test_profile_create_does_not_leave_a_record_when_folder_creation_fails(self):
        with patch.object(Path, "mkdir", side_effect=PermissionError("simulated mkdir failure")):
            with self.assertRaisesRegex(NeVisionError, "каталог профиля"):
                self.storage.save_profile({"name": "No folder"})
        self.assertEqual(self.storage.list_profiles(), [])

    def test_profile_delete_keeps_record_when_data_move_fails(self):
        profile_id = self._profile_with_file("Keep me")
        journal = self.storage.paths.operations / "simulated.json"
        with patch.object(self.storage, "_create_operation_journal", return_value=journal):
            with patch("nevision_win.os.replace", side_effect=OSError("simulated move failure")):
                with self.assertRaisesRegex(NeVisionError, "Data\\\\Deleted"):
                    self.storage.delete_profile(profile_id)
        self.assertIsNotNone(self.storage.get_profile(profile_id))
        self.assertTrue(self.storage.profile_path(profile_id).is_dir())

    def test_process_exit_after_profile_removal_is_safe(self):
        profile_id = self._profile_with_file("Finished")
        self.storage.delete_profile(profile_id)
        self.storage.touch_profile_exit(profile_id, 0)
        self.assertTrue(any(event["action"] == "profile.process_exited" for event in self.storage.list_events()))

    def test_restore_io_failure_leaves_no_profile_or_staging_directory(self):
        profile_id = self._profile_with_file("Source")
        archive = self.storage.backup_profile(profile_id)
        before_ids = {profile["id"] for profile in self.storage.list_profiles()}

        with patch("nevision_win.shutil.copyfileobj", side_effect=OSError("simulated copy failure")):
            with self.assertRaisesRegex(NeVisionError, "Не удалось распаковать backup"):
                self.storage.restore_profile(archive)

        self.assertEqual({profile["id"] for profile in self.storage.list_profiles()}, before_ids)
        self.assertEqual(list(self.storage.paths.profiles.glob(".restore-*.partial")), [])

    def test_missing_proxy_is_reported_as_a_user_safe_error(self):
        with self.assertRaisesRegex(NeVisionError, "proxy больше не существует"):
            self.storage.save_profile({"name": "Broken reference", "proxy_id": "missing-proxy"})


class ProxyHostTests(unittest.TestCase):
    def test_route_disclosure_distinguishes_name_from_ip_literal(self):
        self.assertTrue(proxy_host_requires_local_name_resolution("Proxy.Example"))
        self.assertTrue(proxy_host_requires_local_name_resolution("прокси.рф"))
        self.assertFalse(proxy_host_requires_local_name_resolution("192.0.2.14"))
        self.assertFalse(proxy_host_requires_local_name_resolution("[2001:db8::1]"))

    def test_dns_host_normalizes_case_idna_and_outer_whitespace(self):
        self.assertEqual(normalize_proxy_host("  EXAMPLE.COM.  "), "example.com")
        self.assertEqual(normalize_proxy_host("прокси.рф"), "xn--h1adldfi.xn--p1ai")

    def test_ipv4_host_keeps_single_address(self):
        self.assertEqual(normalize_proxy_host(" 192.0.2.14 "), "192.0.2.14")

    def test_ipv6_host_accepts_brackets_and_compresses_address(self):
        for value in ("[2001:0db8:0:0::1]", "2001:db8::1"):
            with self.subTest(value=value):
                self.assertEqual(normalize_proxy_host(value), "2001:db8::1")

    def test_host_rejects_urls_credentials_and_proxy_fallback_syntax(self):
        for value in ("http://example.com", "user:password@example.com", "example.com:8080", "example.com,direct://", "example.com;direct://", "example.com/path", "example.com?x=1", "example.com#fragment", "example.com\\path", "fe80::1%z;http=direct", "fe80::1%z,direct", "fe80::1%z\nother", "fe80::1%z\x00other"):
            with self.subTest(value=value):
                with self.assertRaises(NeVisionError):
                    normalize_proxy_host(value)

    def test_host_rejects_malformed_dns_labels_and_embedded_controls(self):
        for value in ("", ".", "a..b", "-proxy.example", "proxy-.example", "proxy_name.example", "a" * 64 + ".example", "proxy\t.example", "proxy\n.example", "[::1", "a." * 127 + "example"):
            with self.subTest(value=value):
                with self.assertRaises(NeVisionError):
                    normalize_proxy_host(value)

    def test_ipv6_endpoint_is_unambiguous_and_contains_no_credentials(self):
        endpoint = proxy_endpoint({"scheme": "https", "host": "2001:db8::8", "port": 8443, "username": "private-user", "password": "private-password", "password_protected": "opaque-vault-value"})
        self.assertEqual(endpoint, "https://[2001:db8::8]:8443")


class PortableCoreRegressionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nevision-regression-"))
        self.storage = Storage(AppPaths(self.root))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _archive(self, members, *, manifest=None, duplicate_manifest=False):
        archive_path = self.storage.paths.backups / (uuid.uuid4().hex + ".zip")
        if manifest is None:
            manifest = {"format": "nevision-profile-backup-v1", "profile": {"name": "Regression fixture"}}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("nevision-manifest.json", json.dumps(manifest))
                if duplicate_manifest:
                    archive.writestr("nevision-manifest.json", json.dumps(manifest))
                for member, content in members:
                    if isinstance(member, str):
                        # ZipInfo otherwise converts Windows backslashes while
                        # writing: preserve the deliberately malformed ZIP name.
                        raw_name = member
                        member = zipfile.ZipInfo(raw_name)
                        member.filename = raw_name
                        member.orig_filename = raw_name
                    archive.writestr(member, content)
        return archive_path

    def _assert_rejected_without_publication(self, archive_path):
        previous_ids = {profile["id"] for profile in self.storage.list_profiles()}
        previous_dirs = set(self.storage.paths.profiles.iterdir())
        with self.assertRaises(NeVisionError):
            self.storage.restore_profile(archive_path)
        self.assertEqual({profile["id"] for profile in self.storage.list_profiles()}, previous_ids)
        self.assertEqual(set(self.storage.paths.profiles.iterdir()), previous_dirs)
        self.assertEqual(list(self.storage.paths.operations.glob("*.json")), [])

    def _profile_with_proxy(self, *, scheme="http", username="", password="", host="127.0.0.1"):
        proxy_id = self.storage.save_proxy({"name": "Test proxy", "scheme": scheme, "host": host, "port": 8080, "username": username, "password": password})
        profile_id = self.storage.save_profile({"name": "Test profile", "proxy_id": proxy_id})
        return self.storage.get_profile(profile_id)

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_launch_path_rejects_real_data_profiles_and_profile_junctions(self):
        profile_id = self.storage.save_profile({"name": "Synthetic junction boundary"})
        launcher = BrowserLauncher(self.storage)
        command = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "cmd.exe"
        launcher.ensure_profile_path_is_isolated(profile_id)

        for redirected in ("Data", "Profiles", "profile"):
            with self.subTest(path=redirected):
                if redirected == "Data":
                    link = self.storage.paths.data
                    target = self.root / "outside-Data"
                    held = self.root / "Data-before-junction"
                    (target / "Profiles" / profile_id).mkdir(parents=True)
                elif redirected == "Profiles":
                    link = self.storage.paths.profiles
                    target = self.root / "outside-Profiles"
                    held = self.root / "Profiles-before-junction"
                    (target / profile_id).mkdir(parents=True)
                else:
                    link = self.storage.profile_path(profile_id)
                    target = self.root / "outside-profile"
                    held = self.root / "profile-before-junction"
                    target.mkdir()

                os.replace(link, held)
                try:
                    result = subprocess.run(
                        [str(command), "/d", "/c", "mklink", "/J", str(link), str(target)],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode:
                        self.skipTest("Windows junction creation is unavailable in this environment")
                    self.assertTrue(
                        link.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    )
                    with self.assertRaisesRegex(NeVisionError, "junction"):
                        launcher.ensure_profile_path_is_isolated(profile_id)
                finally:
                    if link.exists():
                        link.rmdir()
                    if held.exists():
                        os.replace(held, link)

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_launch_rejects_cookie_junction_before_resolve_pin_or_popen(self):
        profile = self._profile_with_proxy()
        profile_id = profile["id"]
        profile_dir = self.storage.profile_path(profile_id)
        cookie_store = profile_dir / "Default" / "Network" / "Cookies"
        cookie_store.parent.mkdir(parents=True)
        outside = self.root / "outside-cookie-store"
        outside.mkdir()
        marker = outside / "synthetic-marker"
        marker.write_bytes(b"synthetic-only")
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(cookie_store), str(outside)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode:
            self.skipTest("Windows junction creation is unavailable in this environment")

        try:
            attrs = getattr(cookie_store.lstat(), "st_file_attributes", 0)
            self.assertTrue(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            launcher = BrowserLauncher(self.storage)
            with patch.object(launcher, "resolve_browser") as resolve_browser, \
                    patch.object(self.storage, "pin_browser_family") as pin_browser, \
                    patch("nevision_win.subprocess.Popen") as popen:
                with self.assertRaisesRegex(NeVisionError, "junction"):
                    launcher._launch_locked(profile, profile_id)
            resolve_browser.assert_not_called()
            pin_browser.assert_not_called()
            popen.assert_not_called()
            self.assertEqual(marker.read_bytes(), b"synthetic-only")
        finally:
            cookie_store.rmdir()

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_launch_rejects_indexeddb_namespace_junction_before_resolve_pin_or_popen(self):
        profile = self._profile_with_proxy()
        profile_id = profile["id"]
        indexeddb = self.storage.profile_path(profile_id) / "Default" / "IndexedDB"
        indexeddb.mkdir(parents=True)
        origin_store = indexeddb / "https_example.test_0.indexeddb.leveldb"
        outside = self.root / "outside-indexeddb"
        outside.mkdir()
        marker = outside / "synthetic-marker"
        marker.write_bytes(b"synthetic-only")
        try:
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(origin_store), str(outside)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode:
                self.skipTest("Windows junction creation is unavailable in this environment")
            attrs = getattr(origin_store.lstat(), "st_file_attributes", 0)
            self.assertTrue(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            launcher = BrowserLauncher(self.storage)
            with patch.object(launcher, "resolve_browser") as resolve_browser, \
                    patch.object(self.storage, "pin_browser_family") as pin_browser, \
                    patch("nevision_win.subprocess.Popen") as popen:
                with self.assertRaisesRegex(NeVisionError, "junction"):
                    launcher._launch_locked(profile, profile_id)
            resolve_browser.assert_not_called()
            pin_browser.assert_not_called()
            popen.assert_not_called()
            self.assertEqual(marker.read_bytes(), b"synthetic-only")
        finally:
            origin_store.rmdir()

    def test_indexeddb_reparse_scan_fails_closed_at_entry_limit(self):
        profile_id = self.storage.save_profile({"name": "Synthetic bounded scan"})
        indexeddb = self.storage.profile_path(profile_id) / "Default" / "IndexedDB"
        indexeddb.mkdir(parents=True)
        (indexeddb / "origin-one").write_bytes(b"synthetic")
        (indexeddb / "origin-two").write_bytes(b"synthetic")
        launcher = BrowserLauncher(self.storage)
        launcher.PROFILE_REPARSE_SCAN_ENTRY_LIMIT = 1

        with self.assertRaisesRegex(NeVisionError, "слишком много элементов"):
            launcher.ensure_profile_path_is_isolated(profile_id)

    def test_isolation_check_rejects_local_storage_hardlink(self):
        profile_id = self.storage.save_profile({"name": "Synthetic Local Storage hardlink"})
        leveldb = self.storage.profile_path(profile_id) / "Default" / "Local Storage" / "leveldb"
        leveldb.mkdir(parents=True)
        linked_file = leveldb / "000003.log"
        linked_file.write_bytes(b"synthetic-only")
        outside = self.root / "synthetic-shared-log"
        try:
            os.link(linked_file, outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"hardlink creation is unavailable in this environment: {exc}")

        with self.assertRaisesRegex(NeVisionError, "hardlink"):
            BrowserLauncher(self.storage).ensure_profile_path_is_isolated(profile_id)

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_launch_rejects_local_storage_leveldb_junction_before_resolve_pin_or_popen(self):
        profile = self._profile_with_proxy()
        profile_id = profile["id"]
        leveldb = self.storage.profile_path(profile_id) / "Default" / "Local Storage" / "leveldb"
        leveldb.mkdir(parents=True)
        namespace = leveldb / "synthetic-origin"
        outside = self.root / "outside-local-storage-leveldb"
        outside.mkdir()
        marker = outside / "synthetic-marker"
        marker.write_bytes(b"synthetic-only")
        try:
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(namespace), str(outside)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode:
                self.skipTest("Windows junction creation is unavailable in this environment")
            attrs = getattr(namespace.lstat(), "st_file_attributes", 0)
            self.assertTrue(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            launcher = BrowserLauncher(self.storage)
            with patch.object(launcher, "resolve_browser") as resolve_browser, \
                    patch.object(self.storage, "pin_browser_family") as pin_browser, \
                    patch("nevision_win.subprocess.Popen") as popen:
                with self.assertRaisesRegex(NeVisionError, "junction"):
                    launcher._launch_locked(profile, profile_id)
            resolve_browser.assert_not_called()
            pin_browser.assert_not_called()
            popen.assert_not_called()
            self.assertEqual(marker.read_bytes(), b"synthetic-only")
        finally:
            if namespace.is_junction():
                os.rmdir(namespace)

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_isolation_check_rejects_cache_storage_namespace_junction(self):
        profile = self._profile_with_proxy()
        profile_id = profile["id"]
        cache_storage = (
            self.storage.profile_path(profile_id) / "Default" / "Service Worker" / "CacheStorage"
        )
        cache_storage.mkdir(parents=True)
        namespace = cache_storage / "synthetic-origin"
        outside = self.root / "outside-cache-storage"
        outside.mkdir()
        try:
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(namespace), str(outside)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode:
                self.skipTest("Windows junction creation is unavailable in this environment")
            attrs = getattr(namespace.lstat(), "st_file_attributes", 0)
            self.assertTrue(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            launcher = BrowserLauncher(self.storage)
            with patch.object(launcher, "resolve_browser") as resolve_browser, \
                    patch.object(self.storage, "pin_browser_family") as pin_browser, \
                    patch("nevision_win.subprocess.Popen") as popen:
                with self.assertRaisesRegex(NeVisionError, "junction"):
                    launcher._launch_locked(profile, profile_id)
            resolve_browser.assert_not_called()
            pin_browser.assert_not_called()
            popen.assert_not_called()
        finally:
            if namespace.is_junction():
                os.rmdir(namespace)

    def test_nested_reparse_scan_fails_closed_when_directory_cannot_be_scanned(self):
        profile_id = self.storage.save_profile({"name": "Synthetic scan error"})
        launcher = BrowserLauncher(self.storage)
        with patch("nevision_win.os.scandir", side_effect=PermissionError("synthetic access denial")):
            with self.assertRaisesRegex(NeVisionError, "Не удалось просмотреть вложенное хранилище"):
                launcher.ensure_profile_path_is_isolated(profile_id)

    def test_invalid_proxy_host_is_not_persisted(self):
        with self.assertRaises(NeVisionError):
            self.storage.save_proxy({"name": "Injected", "scheme": "http", "host": "example.com,direct://", "port": 8080})
        self.assertEqual(self.storage.list_proxies(), [])

    def test_proxy_host_is_normalized_before_persistence(self):
        proxy_id = self.storage.save_proxy({"name": "IDN", "scheme": "https", "host": "ПРОКСИ.РФ", "port": 443})
        self.assertEqual(self.storage.get_proxy(proxy_id)["host"], "xn--h1adldfi.xn--p1ai")

    def test_backup_manifest_describes_sensitive_unencrypted_browser_data(self):
        profile = self._profile_with_proxy(username="private-user", password="private-password")
        profile_dir = self.storage.profile_path(profile["id"])
        (profile_dir / "Default").mkdir()
        (profile_dir / "Default" / "Cookies").write_bytes(b"synthetic-session-data")
        archive_path = self.storage.backup_profile(profile["id"])
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("nevision-manifest.json"))
            self.assertIs(manifest["proxy_credentials_included"], False)
            self.assertIs(manifest["browser_session_data_included"], True)
            self.assertIs(manifest["encrypted"], False)
            self.assertNotIn("secrets_included", manifest)
            self.assertNotIn("proxy_id", manifest["profile"])
            self.assertNotIn("private-user", json.dumps(manifest))
            self.assertNotIn("private-password", json.dumps(manifest))
            self.assertEqual(archive.read("profile/Default/Cookies"), b"synthetic-session-data")

    def test_restore_rejects_windows_device_names_in_any_component(self):
        # Microsoft also reserves COM/LPT with ISO-8859-1 superscripts 1/2/3.
        # https://learn.microsoft.com/windows/win32/fileio/naming-a-file
        for name in ("CON", "nul.txt", "AuX", "PRN.log", "COM1", "lpt9.ext", "conin$", "CONOUT$.log", "COM\u00b9.txt", "LPT\u00b2", "COM\u00b3"):
            for location in (f"profile/Default/{name}", f"profile/{name}/file.txt"):
                with self.subTest(path=location):
                    self._assert_rejected_without_publication(self._archive([(location, "unsafe")]))

    def test_restore_rejects_windows_trailing_dots_and_spaces(self):
        for path in ("profile/Default/file.", "profile/Default/file ", "profile/folder./state", "profile/folder /state"):
            with self.subTest(path=path):
                self._assert_rejected_without_publication(self._archive([(path, "unsafe")]))

    def test_restore_rejects_windows_separators_streams_and_special_characters(self):
        for path in ("profile/Default/state:stream", "profile/C:/state", "profile/Default\\state", "profile/Default/state\x00hidden", "profile/Default/f?le", "profile/Default/f*le", 'profile/Default/f"le', "profile/Default/f<le", "profile/Default/f>le", "profile/Default/f|le", "profile/Default/f\x01le"):
            with self.subTest(path=path):
                self._assert_rejected_without_publication(self._archive([(path, "unsafe")]))

    def test_restore_rejects_empty_dot_and_parent_components(self):
        for path in ("profile//state", "profile/./state", "profile/Default/../state", "profile/Default//state"):
            with self.subTest(path=path):
                self._assert_rejected_without_publication(self._archive([(path, "unsafe")]))

    def test_restore_rejects_duplicate_zip_member_instead_of_overwriting(self):
        archive = self._archive([("profile/Default/state", "first"), ("profile/Default/state", "second")])
        self._assert_rejected_without_publication(archive)

    def test_restore_rejects_case_insensitive_windows_name_collision(self):
        archive = self._archive([("profile/Default/Preferences", "first"), ("profile/default/preferences", "second")])
        self._assert_rejected_without_publication(archive)

    def test_restore_rejects_file_directory_collisions_in_both_orders(self):
        entries = [("profile/Default/state", "file"), ("profile/Default/state/child", "child")]
        for members in (entries, list(reversed(entries))):
            with self.subTest(members=members):
                self._assert_rejected_without_publication(self._archive(members))

    def test_restore_rejects_symlinks_and_special_files(self):
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFSOCK):
            with self.subTest(mode=mode):
                member = zipfile.ZipInfo("profile/Default/link-or-device")
                member.create_system = 3
                member.external_attr = (mode | 0o600) << 16
                self._assert_rejected_without_publication(self._archive([(member, "../../external")]))

    def test_restore_rejects_duplicate_manifest_before_creating_profile(self):
        archive = self._archive([("profile/Default/state", "safe")], duplicate_manifest=True)
        self._assert_rejected_without_publication(archive)

    def test_restore_preflights_total_entry_count_before_zipfile_parses_directory(self):
        archive = self._archive([("ignored/one", ""), ("ignored/two", "")])
        with patch("nevision_win.MAX_BACKUP_FILES", 1), patch("nevision_win.MAX_BACKUP_ARCHIVE_ENTRIES", 2):
            with patch("nevision_win.zipfile.ZipFile") as open_zip:
                with self.assertRaisesRegex(NeVisionError, "слишком много записей"):
                    self.storage.restore_profile(archive)
                open_zip.assert_not_called()

    def test_restore_rejects_unknown_top_level_member_without_publication(self):
        archive = self._archive([("unexpected/file", "ignored synthetic data")])
        self._assert_rejected_without_publication(archive)

    def test_restore_preflights_central_directory_size_before_zipfile(self):
        archive = self._archive([("profile/Default/state", "synthetic")])
        with patch("nevision_win.MAX_BACKUP_CENTRAL_DIRECTORY_BYTES", 1):
            with patch("nevision_win.zipfile.ZipFile") as open_zip:
                with self.assertRaisesRegex(NeVisionError, "слишком большой каталог"):
                    self.storage.restore_profile(archive)
                open_zip.assert_not_called()

    def test_restore_reports_non_zip_input_as_invalid_backup(self):
        invalid = self.root / "not-a-zip.backup"
        invalid.write_bytes(b"synthetic invalid backup")
        self._assert_rejected_without_publication(invalid)

    def test_legacy_v1_backup_remains_readable_with_old_sensitivity_flag(self):
        manifest = {"format": "nevision-profile-backup-v1", "profile": {"name": "Legacy", "group_name": "QA"}, "secrets_included": False}
        archive = self._archive([("profile/Default/state", "legacy-content")], manifest=manifest)
        restored = self.storage.restore_profile(archive)
        self.assertEqual(self.storage.get_profile(restored)["group_name"], "QA")
        self.assertIsNone(self.storage.get_profile(restored)["proxy_id"])
        self.assertEqual((self.storage.profile_path(restored) / "Default" / "state").read_text(), "legacy-content")

    def test_socks5_with_any_credentials_fails_before_process_creation(self):
        launcher = BrowserLauncher(self.storage)
        for username, password in (("user", ""), ("", "password"), ("user", "password")):
            with self.subTest(username=bool(username), password=bool(password)):
                profile = self._profile_with_proxy(scheme="socks5", username=username, password=password)
                with patch.object(launcher, "resolve_browser", return_value=self.root / "chrome.exe"), patch("nevision_win.subprocess.Popen") as spawn:
                    with self.assertRaisesRegex(NeVisionError, "SOCKS5"):
                        launcher.launch(profile)
                    spawn.assert_not_called()
                self.assertIsNone(self.storage.get_profile(profile["id"])["last_launch_at"])
        # The guard must not disable stock Chromium's supported no-auth mode.
        profile = self._profile_with_proxy(scheme="socks5")
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(launcher, "resolve_browser", return_value=self.root / "chrome.exe"), patch.object(self.storage, "wait_for_chromium_lock"), patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
            launcher.launch(profile)
        self.assertIn("--proxy-server=socks5://127.0.0.1:8080", spawn.call_args.args[0])

    def test_missing_assigned_proxy_fails_closed_instead_of_launching_direct(self):
        profile = self._profile_with_proxy()
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "resolve_browser", return_value=self.root / "chrome.exe"), patch.object(self.storage, "get_proxy", return_value=None), patch("nevision_win.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(NeVisionError, "proxy отсутствует"):
                launcher.launch(profile)
            spawn.assert_not_called()

    def test_native_privacy_label_requires_bundled_receipt(self):
        launcher = BrowserLauncher(self.storage)
        self.assertFalse(launcher.has_native_privacy_baseline())
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        for name in ("chrome.exe", "chrome.dll", "icudtl.dat", "resources.pak"):
            (engine / name).write_bytes(b"fixture")
        receipt = engine / "ENGINE_PROVENANCE.json"
        receipt.write_text(json.dumps({"format": "neantik-chromium-source-build-v1",
                                       "privacy_patch_sha256": "a" * 64}), encoding="utf-8")
        self.assertTrue(launcher.has_native_privacy_baseline())
        receipt.write_text(json.dumps({"format": "neantik-chromium-source-build-v1",
                                       "privacy_patch_sha256": NATIVE_PREVIEW_PATCH_SHA256}), encoding="utf-8")
        self.assertFalse(launcher.has_native_privacy_baseline(),
                         "V5 ordinary mode has stock CPU/RAM, even when the patch is present")
        receipt.write_text(json.dumps({"format": "neantik-chromium-source-build-v1",
                                       "privacy_patch_sha256": "invalid"}), encoding="utf-8")
        self.assertFalse(launcher.has_native_privacy_baseline())

    def test_stale_launch_after_deletion_does_not_recreate_or_spawn_profile(self):
        profile_id = self.storage.save_profile({"name": "Deleted elsewhere"})
        stale_profile = self.storage.get_profile(profile_id)
        self.storage.delete_profile(profile_id)
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "resolve_browser", return_value=self.root / "chrome.exe"), patch("nevision_win.subprocess.Popen") as spawn:
            with self.assertRaises(NeVisionError):
                launcher.launch(stale_profile)
            spawn.assert_not_called()
        self.assertFalse(self.storage.profile_path(profile_id).exists())
        self.assertIsNone(self.storage.get_profile(profile_id))

    def test_launch_aborts_when_proxy_assignment_changed_after_ui_snapshot(self):
        profile_id = self.storage.save_profile({"name": "Changed elsewhere"})
        stale_profile = self.storage.get_profile(profile_id)
        proxy_id = self.storage.save_proxy({"name": "New route", "scheme": "http", "host": "192.0.2.5", "port": 8123})
        self.storage.save_profile({"name": "Changed elsewhere", "proxy_id": proxy_id}, profile_id)
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "resolve_browser", return_value=self.root / "chrome.exe"), patch("nevision_win.subprocess.Popen") as spawn:
            with self.assertRaises(NeVisionError):
                launcher.launch(stale_profile)
            spawn.assert_not_called()
        stale_assigned_profile = self.storage.get_profile(profile_id)
        self.storage.delete_proxy(proxy_id)
        with patch.object(launcher, "resolve_browser", return_value=self.root / "chrome.exe"), patch("nevision_win.subprocess.Popen") as spawn:
            with self.assertRaises(NeVisionError):
                launcher.launch(stale_assigned_profile)
            spawn.assert_not_called()

    def _try_competing_storage_on_another_thread(self):
        outcomes = []
        def contender():
            try:
                Storage(AppPaths(self.root))
                outcomes.append("opened")
            except NeVisionError:
                outcomes.append("busy")
            except Exception as error:
                outcomes.append(type(error).__name__)
        worker = threading.Thread(target=contender, daemon=True)
        worker.start()
        worker.join(5)
        self.assertFalse(worker.is_alive(), "Competing manager failed to return within 5 seconds")
        return outcomes

    @unittest.skipUnless(os.name == "nt", "Windows mutex across independent threads")
    def test_startup_recovery_cannot_undo_an_active_delete(self):
        profile_id = self.storage.save_profile({"name": "Delete race"})
        source = self.storage.profile_path(profile_id)
        (source / "state.txt").write_text("state", encoding="utf-8")
        original_replace = os.replace
        competing_outcomes = []
        moved_targets = []
        def interleave(source_arg, target_arg):
            original_replace(source_arg, target_arg)
            if canonical_path_key(Path(source_arg)) == canonical_path_key(source) and not moved_targets:
                moved_targets.append(Path(target_arg))
                competing_outcomes.extend(self._try_competing_storage_on_another_thread())
        with patch("nevision_win.os.replace", side_effect=interleave):
            self.storage.delete_profile(profile_id)
        self.assertEqual(competing_outcomes, ["busy"])
        self.assertIsNone(self.storage.get_profile(profile_id))
        self.assertFalse(source.exists())
        self.assertEqual((moved_targets[0] / "state.txt").read_text(), "state")
        self.assertEqual(list(self.storage.paths.operations.glob("*.json")), [])

    @unittest.skipUnless(os.name == "nt", "Windows mutex across independent threads")
    def test_startup_recovery_cannot_remove_active_restore_staging(self):
        archive_path = self._archive([("profile/Default/state.txt", "restore-state")])
        original_journal = self.storage._create_operation_journal
        competing_outcomes = []
        def interleave(payload):
            journal = original_journal(payload)
            competing_outcomes.extend(self._try_competing_storage_on_another_thread())
            return journal
        with patch.object(self.storage, "_create_operation_journal", side_effect=interleave):
            restored_id = self.storage.restore_profile(archive_path)
        self.assertEqual(competing_outcomes, ["busy"])
        self.assertEqual((self.storage.profile_path(restored_id) / "Default" / "state.txt").read_text(), "restore-state")
        self.assertEqual(list(self.storage.paths.operations.glob("*.json")), [])

    def test_http_https_proxy_arguments_never_expose_vault_credentials(self):
        launcher = BrowserLauncher(self.storage)
        for scheme in ("http", "https"):
            with self.subTest(scheme=scheme):
                profile = self._profile_with_proxy(scheme=scheme, username="secret-user", password="synthetic:пароль@/%", host="2001:db8::7")
                process = MagicMock()
                process.poll.return_value = None
                with patch.object(launcher, "resolve_browser", return_value=self.root / "chrome.exe"), patch.object(self.storage, "wait_for_chromium_lock"), patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
                    self.assertIs(launcher.launch(profile), process)
                arguments = spawn.call_args.args[0]
                self.assertIn(f"--proxy-server={scheme}://[2001:db8::7]:8080", arguments)
                self.assertNotIn("direct://", " ".join(arguments))
                for secret in ("secret-user", "synthetic:пароль@/%", profile["proxy_password_protected"]):
                    self.assertNotIn(secret, " ".join(arguments))
                self.assertEqual(spawn.call_args.kwargs["cwd"], str(self.storage.profile_path(profile["id"])))

    def test_extensions_page_targets_selected_profile_and_browser(self):
        launcher = BrowserLauncher(self.storage)
        for binary, url in (("chrome.exe", "chrome://extensions/"), ("msedge.exe", "edge://extensions/")):
            with self.subTest(binary=binary):
                profile_id = self.storage.save_profile({"name": f"Extensions {binary}"})
                profile = self.storage.get_profile(profile_id)
                process = MagicMock()
                process.poll.return_value = None
                with patch.object(launcher, "resolve_browser", return_value=self.root / binary), patch.object(self.storage, "wait_for_chromium_lock"), patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
                    launcher.launch(profile, extensions=True)
                arguments = spawn.call_args.args[0]
                self.assertIn(url, arguments)
                self.assertIn(f"--user-data-dir={self.storage.profile_path(profile_id)}", arguments)

    def test_first_launch_pins_family_and_rejects_later_browser_switch(self):
        profile_id = self.storage.save_profile({"name": "Pinned"})
        launcher = BrowserLauncher(self.storage)
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(launcher, "resolve_browser", return_value=self.root / "chrome.exe"), patch.object(self.storage, "wait_for_chromium_lock"), patch("nevision_win.subprocess.Popen", return_value=process):
            launcher.launch(self.storage.get_profile(profile_id))
        self.assertEqual(self.storage.get_profile(profile_id)["browser_family"], "chrome")

        with patch.object(launcher, "resolve_browser", return_value=self.root / "msedge.exe"), patch("nevision_win.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(NeVisionError, "закреплён за Chrome"):
                launcher.launch(self.storage.get_profile(profile_id))
            spawn.assert_not_called()

    def test_backup_restore_preserves_browser_family_pin(self):
        profile_id = self.storage.save_profile({"name": "Pinned backup"})
        self.storage.pin_browser_family(profile_id, "edge")
        archive = self.storage.backup_profile(profile_id)
        with zipfile.ZipFile(archive) as source:
            manifest = json.loads(source.read("nevision-manifest.json"))
        self.assertEqual(manifest["profile"]["browser_family"], "edge")
        restored_id = self.storage.restore_profile(archive)
        self.assertEqual(self.storage.get_profile(restored_id)["browser_family"], "edge")

    def test_custom_executable_rejects_unsupported_name(self):
        arbitrary = self.root / "arbitrary.exe"
        arbitrary.touch()
        self.storage.set_setting("browser_path", str(arbitrary))
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "KNOWN_BROWSERS", ()), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "missing")}), patch("nevision_win.winreg", None):
            self.assertEqual(launcher.available_browsers(), [])
        profile_id = self.storage.save_profile({"name": "Guarded"})
        with patch.object(launcher, "resolve_browser", return_value=arbitrary), patch("nevision_win.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(NeVisionError, "chrome.exe или msedge.exe"):
                launcher.launch(self.storage.get_profile(profile_id))
            spawn.assert_not_called()

    def test_per_user_chrome_and_edge_are_discovered_without_machine_installs(self):
        local = self.root / "User App Data"
        browsers = [local / "Google/Chrome/Application/chrome.exe", local / "Microsoft/Edge/Application/msedge.exe"]
        for browser in browsers:
            browser.parent.mkdir(parents=True)
            browser.touch()
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "KNOWN_BROWSERS", ()), patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), patch("nevision_win.winreg", None):
            self.assertEqual([path for _, path in launcher.available_browsers()], browsers)

    def test_bundled_chromium_is_default_without_installed_browser(self):
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        for name in ("chrome.exe", "chrome.dll", "icudtl.dat", "resources.pak", "ENGINE_PROVENANCE.json"):
            (engine / name).touch()
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "KNOWN_BROWSERS", ()), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "missing")}), patch("nevision_win.winreg", None):
            self.assertEqual(launcher.resolve_browser(), engine / "chrome.exe")
            self.assertEqual(launcher.browser_family(engine / "chrome.exe"), "chromium")
            profile_id = self.storage.save_profile({"name": "Portable"})
            process = MagicMock()
            process.poll.return_value = None
            with patch.object(self.storage, "wait_for_chromium_lock"), patch.object(launcher, "ensure_bundled_sandbox_access") as sandbox_acl, patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
                launcher.launch(self.storage.get_profile(profile_id))
            self.assertEqual(spawn.call_args.args[0][0], str(engine / "chrome.exe"))
            self.assertNotIn("--webrtc-ip-handling-policy=disable_non_proxied_udp", spawn.call_args.args[0])
            sandbox_acl.assert_called_once_with(engine)
            self.assertEqual(self.storage.get_profile(profile_id)["browser_family"], "chromium")
            preferences = self.storage.profile_path(profile_id) / "Default" / "Preferences"
            created = json.loads(preferences.read_text(encoding="utf-8"))
            self.assertEqual(created["profile"]["cookie_controls_mode"], 1)
            self.assertEqual(created["net"]["network_prediction_options"], 2)
            self.assertEqual(created["profile"]["default_content_setting_values"]["geolocation"], 2)
            self.assertEqual(created["download"]["default_directory"],
                             str(self.storage.profile_path(profile_id).resolve() / "Downloads"))
            self.assertTrue((self.storage.profile_path(profile_id) / "Downloads").is_dir())

            preferences.write_text('{"profile":{"cookie_controls_mode":0}}', encoding="utf-8")
            with patch.object(self.storage, "wait_for_chromium_lock"), patch.object(launcher, "ensure_bundled_sandbox_access"), patch("nevision_win.subprocess.Popen", return_value=process):
                launcher.launch(self.storage.get_profile(profile_id))
            self.assertEqual(preferences.read_text(encoding="utf-8"), '{"profile":{"cookie_controls_mode":0}}')

    def test_bundled_proxy_restricts_non_proxied_webrtc_udp(self):
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        for name in ("chrome.exe", "chrome.dll", "icudtl.dat", "resources.pak", "ENGINE_PROVENANCE.json"):
            (engine / name).touch()
        proxy_id = self.storage.save_proxy({"name": "QA HTTP", "scheme": "http", "host": "127.0.0.1", "port": 8080})
        profile_id = self.storage.save_profile({"name": "Proxy WebRTC", "proxy_id": proxy_id})
        launcher = BrowserLauncher(self.storage)
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(launcher, "KNOWN_BROWSERS", ()), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "missing")}), patch("nevision_win.winreg", None):
            with patch.object(self.storage, "wait_for_chromium_lock"), patch.object(launcher, "ensure_bundled_sandbox_access"), patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
                launcher.launch(self.storage.get_profile(profile_id), diagnostics=True)
        arguments = spawn.call_args.args[0]
        self.assertIn("--proxy-server=http://127.0.0.1:8080", arguments)
        self.assertIn("--webrtc-ip-handling-policy=disable_non_proxied_udp", arguments)
        self.assertIn("--proxy-bypass-list=<-loopback>", arguments)
        self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", arguments)
        self.assertIn("--disable-quic", arguments)
        self.assertIn(PRIVACY_CHECK_URL, arguments)

    def test_proxy_hostname_is_only_dns_exception(self):
        from nevision_win import bundled_proxy_privacy_arguments
        args = bundled_proxy_privacy_arguments({"host": "Proxy.Example"})
        self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE proxy.example", args)
        self.assertNotIn("--host-resolver-rules=MAP * ~NOTFOUND", args)

    def test_proxy_ip_literal_is_only_resolver_exception(self):
        from nevision_win import bundled_proxy_privacy_arguments
        self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 2001:db8::1", bundled_proxy_privacy_arguments({"host": "2001:db8::1"}))

    def test_bundled_acl_grant_is_limited_to_engine_and_cached(self):
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        (engine / "icudtl.dat").touch()
        launcher = BrowserLauncher(self.storage)
        with patch("nevision_win.subprocess.run", return_value=MagicMock(returncode=0)) as run:
            launcher.ensure_bundled_sandbox_access(engine)
            launcher.ensure_bundled_sandbox_access(engine)
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["icacls.exe", str(engine)])
        self.assertNotIn(str(self.storage.paths.data), " ".join(command))
        self.assertIn("*S-1-15-2-1:(OI)(CI)RX", command)

    def test_bundled_acl_rejects_link_before_permission_change(self):
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        linked = engine / "outside"
        try:
            linked.symlink_to(self.storage.paths.data, target_is_directory=True)
        except OSError:
            self.skipTest("Directory symlink creation is unavailable on this Windows account")
        launcher = BrowserLauncher(self.storage)
        with patch("nevision_win.subprocess.run") as run:
            with self.assertRaisesRegex(NeVisionError, "ссылка/junction"):
                launcher.ensure_bundled_sandbox_access(engine)
            run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_launch_rejects_profile_junction_before_process_or_profile_mutation(self):
        source_id = self.storage.save_profile({"name": "Junction source"})
        linked_id = self.storage.save_profile({"name": "Junction alias"})
        source = self.storage.profile_path(source_id)
        linked = self.storage.profile_path(linked_id)
        linked.rmdir()
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(linked), str(source)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode or not hasattr(linked, "is_junction") or not linked.is_junction():
            if linked.exists():
                linked.rmdir()
            self.skipTest("Windows junction creation is unavailable in this environment")
        try:
            launcher = BrowserLauncher(self.storage)
            profile = self.storage.get_profile(linked_id)
            with patch.object(launcher, "resolve_browser") as resolve_browser, \
                    patch.object(self.storage, "ensure_profile_closed") as ensure_closed, \
                    patch.object(self.storage, "pin_browser_family") as pin_family, \
                    patch("nevision_win.subprocess.Popen") as spawn:
                with self.assertRaisesRegex(NeVisionError, "junction"):
                    launcher.launch(profile)
            resolve_browser.assert_not_called()
            ensure_closed.assert_not_called()
            pin_family.assert_not_called()
            spawn.assert_not_called()
            self.assertEqual(self.storage.get_profile(linked_id)["browser_family"], "")
            self.assertFalse((source / "Default" / "Preferences").exists())
        finally:
            linked.rmdir()

    def test_unpinned_legacy_data_is_not_opened_with_new_bundled_chromium(self):
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        for name in ("chrome.exe", "chrome.dll", "icudtl.dat", "resources.pak", "ENGINE_PROVENANCE.json"):
            (engine / name).touch()
        profile_id = self.storage.save_profile({"name": "Legacy before pinning"})
        (self.storage.profile_path(profile_id) / "History").write_bytes(b"existing browser data")
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "KNOWN_BROWSERS", ()), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "missing")}), patch("nevision_win.winreg", None), patch("nevision_win.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(NeVisionError, "прежний браузер не определён"):
                launcher.launch(self.storage.get_profile(profile_id))
            spawn.assert_not_called()
        self.assertEqual(self.storage.get_profile(profile_id)["browser_family"], "")

    def test_incomplete_bundled_engine_does_not_fall_back_to_installed_browser(self):
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        (engine / "chrome.exe").touch()
        installed = self.root / "Installed" / "chrome.exe"
        installed.parent.mkdir()
        installed.touch()
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "KNOWN_BROWSERS", (("Chrome", installed),)), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "missing")}), patch("nevision_win.winreg", None):
            with self.assertRaisesRegex(NeVisionError, "распакован не полностью"):
                launcher.resolve_browser()

    def test_existing_chrome_profile_prefers_installed_chrome_over_new_bundled_core(self):
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        for name in ("chrome.exe", "chrome.dll", "icudtl.dat", "resources.pak", "ENGINE_PROVENANCE.json"):
            (engine / name).touch()
        installed = self.root / "Installed" / "chrome.exe"
        installed.parent.mkdir()
        installed.touch()
        profile_id = self.storage.save_profile({"name": "Legacy"})
        self.storage.pin_browser_family(profile_id, "chrome")
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "KNOWN_BROWSERS", (("Chrome", installed),)), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "missing")}), patch("nevision_win.winreg", None):
            process = MagicMock()
            process.poll.return_value = None
            with patch.object(self.storage, "wait_for_chromium_lock"), patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
                launcher.launch(self.storage.get_profile(profile_id))
            self.assertEqual(spawn.call_args.args[0][0], str(installed))

    def test_bundled_core_stays_default_with_legacy_browser_path(self):
        engine = self.root / "Engine" / "Chromium"
        engine.mkdir(parents=True)
        for name in ("chrome.exe", "chrome.dll", "icudtl.dat", "resources.pak", "ENGINE_PROVENANCE.json"):
            (engine / name).touch()
        legacy = self.root / "Legacy" / "chrome.exe"
        legacy.parent.mkdir()
        legacy.touch()
        self.storage.set_setting("browser_path", str(legacy))
        new_id = self.storage.save_profile({"name": "New bundled profile"})
        old_id = self.storage.save_profile({"name": "Old Chrome profile"})
        self.storage.pin_browser_family(old_id, "chrome")
        launcher = BrowserLauncher(self.storage)
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(launcher, "KNOWN_BROWSERS", ()), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "missing")}), patch("nevision_win.winreg", None), patch.object(launcher, "ensure_bundled_sandbox_access"), patch.object(self.storage, "wait_for_chromium_lock"), patch("nevision_win.subprocess.Popen", return_value=process) as spawn:
            launcher.launch(self.storage.get_profile(new_id))
            self.assertEqual(spawn.call_args.args[0][0], str(engine / "chrome.exe"))
            launcher.launch(self.storage.get_profile(old_id))
            self.assertEqual(spawn.call_args.args[0][0], str(legacy))
        self.assertEqual(self.storage.get_profile(new_id)["browser_family"], "chromium")
        self.assertEqual(self.storage.get_profile(old_id)["browser_family"], "chrome")

    def test_registry_discovery_deduplicates_paths_and_keeps_custom_choice_first(self):
        custom = self.root / "Chosen Browser" / "chrome.exe"
        registered = self.root / "Registered Browser" / "msedge.exe"
        for browser in (custom, registered):
            browser.parent.mkdir(parents=True)
            browser.touch()
        self.storage.set_setting("browser_path", str(custom))
        registry = MagicMock()
        registry.QueryValue.return_value = f'"{registered}"'
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "KNOWN_BROWSERS", (("Duplicate custom", custom),)), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "missing")}), patch("nevision_win.winreg", registry):
            discovered = launcher.available_browsers()
            self.assertEqual([path for _, path in discovered], [custom, registered])
            self.assertEqual(launcher.resolve_browser(), custom)


@unittest.skipUnless(os.name == "nt", "Windows extended-path regression")
class WindowsLongPathTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="nevision-longpath-"))
        # Database/root stay below MAX_PATH, while real Chromium-style files,
        # long-name backups, journal partials, and restore staging exceed it.
        self.root = self.temp_root / ("Portable проверка " + "x" * 80)
        self.storage = Storage(AppPaths(self.root))
        self.relative = Path("Default") / "Extensions" / ("synthetic-" + "x" * 60) / ("version-" + "v" * 60) / "localFileSignInRedirection.html"
        self.payload = b"synthetic long-path content\x00\xff"

    def tearDown(self):
        # Only this test's freshly created fixture; never user profile data.
        root = filesystem_path(self.temp_root)
        for directory, _, files in os.walk(root):
            for name in files:
                item = Path(directory) / name
                if item.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY:
                    item.chmod(stat.S_IWRITE)
        shutil.rmtree(root)

    def _source_profile(self):
        profile_id = self.storage.save_profile({"name": "Synthetic-long-name-" + "n" * 35})
        item = filesystem_path(self.storage.profile_path(profile_id) / self.relative)
        self.assertGreater(len(str(self.storage.profile_path(profile_id) / self.relative)), 260)
        item.parent.mkdir(parents=True)
        item.write_bytes(self.payload)
        return profile_id, item

    def test_real_long_readonly_file_backup_restore_and_size(self):
        profile_id, item = self._source_profile()
        item.chmod(stat.S_IREAD)
        archive = self.storage.backup_profile(profile_id)
        self.assertGreater(len(str(archive)), 260)
        self.assertFalse(str(archive).startswith("\\\\?\\"), "UI-facing archive path stays ordinary")
        self.assertTrue(item.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
        self.assertEqual(directory_size(self.storage.profile_path(profile_id)), len(self.payload))
        with zipfile.ZipFile(filesystem_path(archive)) as zipped:
            member = "profile/" + self.relative.as_posix()
            self.assertIn(member, zipped.namelist())
            self.assertEqual(zipped.read(member), self.payload)
            self.assertFalse(any("\\" in name or ":" in name for name in zipped.namelist()))
        filesystem_path(archive).chmod(stat.S_IREAD)
        restored = self.storage.restore_profile(archive)
        self.assertEqual(filesystem_path(self.storage.profile_path(restored) / self.relative).read_bytes(), self.payload)
        self.assertEqual(item.read_bytes(), self.payload)

    def test_long_partial_backup_failure_leaves_no_partial_and_preserves_source(self):
        profile_id, item = self._source_profile()
        with patch.object(zipfile.ZipFile, "write", side_effect=OSError("synthetic failure")):
            with self.assertRaisesRegex(NeVisionError, "Не удалось создать backup"):
                self.storage.backup_profile(profile_id)
        self.assertEqual(list(filesystem_path(self.storage.paths.backups).iterdir()), [])
        self.assertEqual(item.read_bytes(), self.payload)

    def test_long_restore_failure_removes_nested_staging_without_ghost_profile(self):
        profile_id, _ = self._source_profile()
        archive = self.storage.backup_profile(profile_id)
        original_copy = shutil.copyfileobj
        def fail_after_write(source, destination):
            original_copy(source, destination)
            raise OSError("synthetic disk failure after long file write")
        with patch("nevision_win.shutil.copyfileobj", side_effect=fail_after_write):
            with self.assertRaisesRegex(NeVisionError, "Не удалось распаковать backup"):
                self.storage.restore_profile(archive)
        self.assertEqual([row["id"] for row in self.storage.list_profiles()], [profile_id])
        self.assertEqual(list(filesystem_path(self.storage.paths.profiles).glob(".restore-*.partial")), [])

    def test_long_restore_recovery_removes_orphan_staging(self):
        staging = self.storage.paths.profiles / ".restore-long-fixture.partial"
        item = filesystem_path(staging / self.relative)
        item.parent.mkdir(parents=True)
        item.write_bytes(self.payload)
        new_id = uuid.uuid4().hex
        self.storage._create_operation_journal({
            "operation": "restore", "staging_dir": staging.name,
            "profile": {"id": new_id, "name": "Synthetic", "group_name": "", "tags": "", "notes": "", "created_at": "2026-10-11", "updated_at": "2026-10-11"},
        })
        recovered = Storage(AppPaths(self.root))
        self.assertFalse(filesystem_path(staging).exists())
        self.assertIsNone(recovered.get_profile(new_id))
        self.assertEqual(list(filesystem_path(self.storage.paths.operations).iterdir()), [])

    def test_long_delete_and_interrupted_delete_recovery_preserve_content(self):
        profile_id, _ = self._source_profile()
        self.storage.delete_profile(profile_id)
        targets = list(filesystem_path(self.storage.data_deleted_root()).iterdir())
        self.assertEqual(len(targets), 1)
        self.assertGreater(len(str(targets[0])), 260)
        self.assertEqual((targets[0] / self.relative).read_bytes(), self.payload)
        self.assertIsNone(self.storage.get_profile(profile_id))
        second_id, source_item = self._source_profile()
        target = filesystem_path(self.storage.data_deleted_root() / ("Interrupted-" + "d" * 100))
        self.storage._create_operation_journal({"operation": "delete", "profile_id": second_id, "deleted_dir": target.name})
        os.replace(filesystem_path(self.storage.profile_path(second_id)), target)
        recovered = Storage(AppPaths(self.root))
        self.assertIsNotNone(recovered.get_profile(second_id))
        self.assertEqual(source_item.read_bytes(), self.payload)
        self.assertFalse(target.exists())

    def test_normal_and_extended_aliases_share_real_profile_mutex(self):
        profile_id, _ = self._source_profile()
        alias = Storage(AppPaths(filesystem_path(self.root)))
        self.assertEqual(self.storage._profile_mutex_name(profile_id), alias._profile_mutex_name(profile_id))
        self.assertEqual(self.storage._profile_mutex_name("__data_recovery__"), alias._profile_mutex_name("__data_recovery__"))
        result = []
        def contend():
            try:
                with alias.profile_operation_lock(profile_id):
                    result.append("acquired")
            except NeVisionError:
                result.append("busy")
        with self.storage.profile_operation_lock(profile_id):
            worker = threading.Thread(target=contend, daemon=True)
            worker.start()
            worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(result, ["busy"])

    def test_unc_extended_conversion_is_idempotent_and_does_not_affect_public_profile_path(self):
        unc = Path(r"\\synthetic.invalid\share\a\b")
        expected = Path(r"\\?\UNC\synthetic.invalid\share\a\b")
        self.assertEqual(filesystem_path(unc), expected)
        self.assertEqual(filesystem_path(expected), expected)
        self.assertFalse(str(self.storage.profile_path("a" * 32)).startswith("\\\\?\\"))


class ThemeTests(unittest.TestCase):
    def test_theme_preference_normalization_and_system_resolution(self):
        self.assertEqual(normalize_theme_preference("unexpected"), THEME_SYSTEM)
        self.assertEqual(normalize_theme_preference(THEME_LIGHT), THEME_LIGHT)
        self.assertEqual(resolve_theme(THEME_SYSTEM, apps_use_light=True), THEME_LIGHT)
        self.assertEqual(resolve_theme(THEME_SYSTEM, apps_use_light=False), THEME_DARK)
        self.assertEqual(resolve_theme(THEME_DARK, apps_use_light=True), THEME_DARK)

    def test_light_and_dark_palettes_are_complete_and_isolated(self):
        self.assertEqual(set(LIGHT_COLORS), set(DARK_COLORS))
        light = palette_for_theme(THEME_LIGHT)
        dark = palette_for_theme(THEME_DARK)
        self.assertNotEqual(light["panel"], dark["panel"])
        light["panel"] = "mutated"
        self.assertNotEqual(palette_for_theme(THEME_LIGHT)["panel"], "mutated")


class InterfaceLogicTests(unittest.TestCase):
    def test_extensions_action_warns_once_and_describes_permissions_and_fingerprint(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.selected_profile = MagicMock(return_value={
            "id": "synthetic-profile", "name": "Synthetic",
        })
        app._allow_profile_mutation = MagicMock(return_value=True)
        app._is_profile_active = MagicMock(return_value=True)

        with patch("nevision_win.messagebox.askyesno", return_value=True) as confirm, \
                patch("nevision_win.messagebox.showinfo") as show:
            app.launch_selected(extensions=True)
            app.launch_selected(extensions=True)

        self.assertEqual(confirm.call_count, 1)
        self.assertEqual(show.call_count, 2)
        warning = confirm.call_args.args[1]
        self.assertIn("отпечаток", warning)
        self.assertIn("данным профиля", warning)
        self.assertIn("разрешениям", warning)

    def test_extensions_action_cancel_does_not_open_or_mark_acknowledged(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.selected_profile = MagicMock(return_value={
            "id": "synthetic-profile", "name": "Synthetic",
        })
        app._allow_profile_mutation = MagicMock(return_value=True)
        app._is_profile_active = MagicMock()

        with patch("nevision_win.messagebox.askyesno", return_value=False) as confirm, \
                patch("nevision_win.messagebox.showinfo") as show:
            app.launch_selected(extensions=True)

        confirm.assert_called_once()
        app._is_profile_active.assert_not_called()
        show.assert_not_called()
        self.assertFalse(getattr(app, "_extensions_warning_acknowledged", False))

    def test_proxy_diagnostic_uses_protocol_probe_without_reading_vault_secret(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.selected_profile = MagicMock(return_value={
            "id": "synthetic-profile", "name": "Synthetic", "proxy_id": "synthetic-proxy"
        })
        app.storage = MagicMock()
        proxy = {
            "id": "synthetic-proxy", "name": "Loopback fixture", "scheme": "http",
            "host": "127.0.0.1", "port": 8080,
            "username": "synthetic-user", "password_protected": "synthetic-protected-marker",
        }
        app.storage.get_proxy.return_value = proxy
        app.set_status = MagicMock()
        app._run_in_background = MagicMock()

        with patch("nevision_win.SecretVault.decrypt", side_effect=AssertionError("vault must not be read")), \
             patch("nevision_win.diagnose_proxy", return_value=(True, "HTTP-ответ получен (код 200).")) as diagnose:
            app.test_selected_proxy()
            self.assertIn("без передачи пароля", app.set_status.call_args.args[0])
            work = app._run_in_background.call_args.args[1]
            result = work()
            diagnose.assert_called_once_with(proxy)
            with patch("nevision_win.messagebox.showinfo") as show:
                app._run_in_background.call_args.args[2](result)

        logged = " ".join(str(part) for call_args in app.storage.log.call_args.args for part in call_args)
        dialog_text = show.call_args.args[1]
        for value in ("synthetic-user", "synthetic-protected-marker"):
            self.assertNotIn(value, logged)
            self.assertNotIn(value, dialog_text)
        self.assertIn("OPTIONS *", dialog_text)
        self.assertIn("CONNECT", dialog_text)
        self.assertIn("DNS", dialog_text)

    def test_backup_success_reports_date_size_contents_and_offers_backup_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "synthetic-profile-backup.zip"
            archive.write_bytes(b"x" * 4096)
            fixed_time = datetime(2026, 10, 15, 12, 0, 0).timestamp()
            os.utime(archive, (fixed_time, fixed_time))

            app = object.__new__(NeVisionApp)
            app.root = MagicMock()
            app.selected_profile = MagicMock(return_value={
                "id": "synthetic-profile", "name": "Synthetic profile"
            })
            app._is_profile_active = MagicMock(return_value=False)
            app._allow_profile_mutation = MagicMock(return_value=True)
            app.storage = MagicMock()
            app.set_status = MagicMock()
            app._run_in_background = MagicMock()
            app.open_backup_folder = MagicMock()

            with patch("nevision_win.messagebox.askyesno", side_effect=[True, True]) as confirm:
                app.backup_selected()
                completed = app._run_in_background.call_args.args[2]
                completed(archive)

            self.assertEqual(confirm.call_count, 2)
            self.assertEqual(confirm.call_args.kwargs["default"], "no")
            summary = confirm.call_args_list[1].args[1]
            expected_date = datetime.fromtimestamp(fixed_time).astimezone().strftime("%d.%m.%Y %H:%M")
            for expected in (
                expected_date,
                "Размер: 4.0 KB",
                "cookies",
                "история",
                "активные сессии",
                "Пароли из Proxy vault не включены",
                "ZIP не зашифрован",
            ):
                with self.subTest(expected=expected):
                    self.assertIn(expected, summary)
            app.open_backup_folder.assert_called_once_with()

    def test_file_menu_exposes_backup_folder_action(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.colors = {
            "menu_bg": "#111111",
            "menu_text": "#eeeeee",
            "menu_active": "#222222",
            "menu_active_text": "#ffffff",
        }
        menus = [MagicMock() for _ in range(5)]
        with patch("nevision_win.tk.Menu", side_effect=menus):
            app._make_menu()

        commands = [call.kwargs for call in menus[1].add_command.call_args_list]
        backup_command = next(item for item in commands if item["label"] == "Открыть папку резервных копий")
        self.assertEqual(backup_command["command"].__self__, app)
        self.assertEqual(backup_command["command"].__name__, "open_backup_folder")

    def test_open_backup_folder_creates_and_opens_portable_backup_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            backup_path = Path(temporary) / "Data" / "Backups"
            app = object.__new__(NeVisionApp)
            app.root = MagicMock()
            app.storage = MagicMock()
            app.storage.paths.backups = backup_path

            with patch("nevision_win.os.startfile", create=True) as startfile, patch(
                "nevision_win.messagebox.showerror"
            ) as showerror:
                app.open_backup_folder()

            self.assertTrue(backup_path.is_dir())
            startfile.assert_called_once_with(str(filesystem_path(backup_path)))
            showerror.assert_not_called()

    def test_open_backup_folder_reports_shell_open_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            backup_path = Path(temporary) / "Data" / "Backups"
            app = object.__new__(NeVisionApp)
            app.root = MagicMock()
            app.storage = MagicMock()
            app.storage.paths.backups = backup_path

            with patch("nevision_win.os.startfile", create=True, side_effect=OSError("synthetic shell error")), patch(
                "nevision_win.messagebox.showerror"
            ) as showerror:
                app.open_backup_folder()

            self.assertTrue(backup_path.is_dir())
            self.assertIn("synthetic shell error", showerror.call_args.args[1])
            showerror.assert_called_once()

    def test_privacy_diagnostics_requires_explicit_consent_and_discloses_limits(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.selected_profile = MagicMock(return_value={"id": "synthetic-profile"})
        app.launch_selected = MagicMock()

        with patch("nevision_win.messagebox.askyesno", return_value=False) as confirm:
            app.open_privacy_diagnostics()
        confirm.assert_called_once()
        consent_text = confirm.call_args.args[1]
        for disclosure in (
            "внешний сайт", "IP-адрес", "proxy", "DNS", "WebRTC", "UDP", "анонимность"
        ):
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, consent_text)
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        app.launch_selected.assert_not_called()

        with patch("nevision_win.messagebox.askyesno", return_value=True):
            app.open_privacy_diagnostics()
        app.launch_selected.assert_called_once_with(diagnostics=True)

        app.selected_profile.return_value = None
        with patch("nevision_win.messagebox.askyesno") as confirm:
            app.open_privacy_diagnostics()
        confirm.assert_not_called()

    def test_profile_template_export_requires_selected_profile(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.storage = MagicMock()
        app.selected_id = None
        app.selected_profile = MagicMock(return_value=None)
        with patch("nevision_win.messagebox.showinfo") as info, patch(
            "nevision_win.messagebox.askyesno"
        ) as confirm:
            app.export_selected_template()
        self.assertIn("Сначала выберите профиль", info.call_args.args[1])
        info.assert_called_once()
        app.selected_profile.assert_not_called()
        confirm.assert_not_called()
        app.storage.export_profile_template.assert_not_called()

    def test_profile_template_export_warns_about_plaintext_metadata(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.storage = MagicMock()
        app.selected_id = "synthetic-id"
        app.selected_profile = MagicMock(return_value={"id": "synthetic-id"})
        app.set_status = MagicMock()
        app.storage.export_profile_template.return_value = Path("C:/synthetic/template.neantik-profile.json")
        with patch("nevision_win.messagebox.askyesno", return_value=False) as confirm:
            app.export_selected_template()
        self.assertIn("незашифрованный JSON", confirm.call_args.args[1])
        self.assertIn("личная информация", confirm.call_args.args[1])
        app.storage.export_profile_template.assert_not_called()
        with patch("nevision_win.messagebox.askyesno", return_value=True), patch("nevision_win.messagebox.showinfo"):
            app.export_selected_template()
        app.storage.export_profile_template.assert_called_once_with("synthetic-id")

    def test_profile_template_ui_distinguishes_import_from_sensitive_backup(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.storage = MagicMock()
        app.launcher = MagicMock()
        app.set_status = MagicMock()
        app.refresh_profiles = MagicMock()
        app.storage.import_profile_template.return_value = "new-synthetic-id"
        source = "C:/synthetic/settings.neantik-profile.json"
        with patch("nevision_win.filedialog.askopenfilename", return_value=source), patch(
            "nevision_win.messagebox.askyesno", return_value=False
        ) as confirm:
            app.import_profile_template()
        self.assertIn("сессии", confirm.call_args.args[1])
        app.storage.import_profile_template.assert_not_called()
        with patch("nevision_win.filedialog.askopenfilename", return_value=source), patch(
            "nevision_win.messagebox.askyesno", return_value=True
        ):
            app.import_profile_template()
        app.storage.import_profile_template.assert_called_once_with(Path(source))
        app.refresh_profiles.assert_called_once_with(select_id="new-synthetic-id")

    def test_portability_warning_explains_browser_data_and_proxy_limits(self):
        self.assertIn("пароли, cookies и сессии", PORTABILITY_WARNING)
        self.assertIn("DPAPI", PORTABILITY_WARNING)
        self.assertIn("App-Bound Encryption", PORTABILITY_WARNING)
        self.assertIn("Proxy-пароли в backup не включаются", PORTABILITY_WARNING)
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        with patch("nevision_win.messagebox.showinfo") as show:
            app.show_quick_guide()
        self.assertIn(PORTABILITY_WARNING, show.call_args.args[1])

    def test_restore_requires_portability_confirmation_before_starting(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.set_status = MagicMock()
        app._run_in_background = MagicMock()
        app.launcher = MagicMock()
        app.storage = MagicMock()
        archive = "C:/synthetic/backup.zip"
        with patch("nevision_win.filedialog.askopenfilename", return_value=archive), patch(
            "nevision_win.messagebox.askyesno", return_value=False
        ) as confirm:
            app.restore_backup()
        self.assertIn(PORTABILITY_WARNING, confirm.call_args.args[1])
        app._run_in_background.assert_not_called()
        app.set_status.assert_not_called()
        with patch("nevision_win.filedialog.askopenfilename", return_value=archive), patch(
            "nevision_win.messagebox.askyesno", return_value=True
        ):
            app.restore_backup()
        app._run_in_background.assert_called_once()
        restore_operation = app._run_in_background.call_args.args[1]
        restore_operation()
        app.storage.restore_profile.assert_called_once_with(Path(archive))
        app.set_status.assert_called_once_with("Восстанавливаю backup…")

    def test_about_describes_actual_browser_bundle(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.launcher = MagicMock()
        app.launcher.has_native_privacy_baseline.return_value = False
        with patch("nevision_win.messagebox.showinfo") as show:
            app.launcher.bundled_browser.return_value = Path("C:/portable/Engine/Chromium/chrome.exe")
            app.show_about()
            self.assertIn("входит Chromium", show.call_args.args[1])
            self.assertIn("установленный Chrome не требуется", show.call_args.args[1])
            app.launcher.bundled_browser.return_value = None
            app.show_about()
            self.assertIn("не задаёт fingerprint-переопределения", show.call_args.args[1])

    def test_duplicate_proxy_labels_keep_distinct_ids(self):
        proxies = [
            {"id": str(index), "name": "same", "scheme": "http", "host": "127.0.0.1", "port": 8080}
            for index in range(1, 4)
        ]
        labels, ids = proxy_choices(proxies)
        self.assertEqual(ids, ["", "1", "2", "3"])
        self.assertEqual(len(set(labels)), len(labels))
        self.assertEqual(labels[0], "— Без proxy —")

    def test_old_clipboard_timer_cannot_clear_new_copy(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app._clipboard_secret = "same-password"
        app._clipboard_generation = 2
        app._clipboard_sequence = 17
        with patch("nevision_win._clear_windows_clipboard_if_unchanged", return_value=True) as clear:
            app._clear_copied_password("same-password", 1)
            clear.assert_not_called()
            app._clear_copied_password("same-password", 2)
            clear.assert_called_once_with("same-password", 17)

    def test_clipboard_cleanup_keeps_retry_state_after_temporary_read_error(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app._clipboard_secret = "same-password"
        app._clipboard_generation = 1
        app._clipboard_sequence = 17

        with patch("nevision_win._clear_windows_clipboard_if_unchanged", side_effect=[False, True]) as clear:
            self.assertFalse(app._clear_copied_password("same-password", 1))
            self.assertEqual(app._clipboard_secret, "same-password")
            self.assertEqual(app.root.after.call_args.args[0], 1_000)

            app.root.after.call_args.args[1]()
            clear.assert_has_calls([call("same-password", 17), call("same-password", 17)])
            self.assertIsNone(app._clipboard_secret)

    def test_clipboard_clear_error_keeps_retry_state(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app._clipboard_secret = "same-password"
        app._clipboard_generation = 1
        app._clipboard_sequence = 23

        with patch("nevision_win._clear_windows_clipboard_if_unchanged", side_effect=[False, True]) as clear:
            self.assertFalse(app._clear_copied_password("same-password", 1))
            self.assertEqual(app._clipboard_secret, "same-password")
            app.root.after.call_args.args[1]()
            clear.assert_has_calls([call("same-password", 23), call("same-password", 23)])
            self.assertIsNone(app._clipboard_secret)

    def test_clipboard_cleanup_forgets_secret_if_clipboard_was_replaced(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app._clipboard_secret = "synthetic-password"
        app._clipboard_generation = 1
        app._clipboard_sequence = 29
        with patch("nevision_win._clear_windows_clipboard_if_unchanged", return_value=True) as clear:
            self.assertTrue(app._clear_copied_password("synthetic-password", 1))
        clear.assert_called_once_with("synthetic-password", 29)
        self.assertIsNone(app._clipboard_secret)
        self.assertIsNone(app._clipboard_sequence)

    def test_native_clipboard_sequence_change_prevents_clearing_same_text(self):
        # Synthetic Win32 API only; no system clipboard is opened by this test.
        user32 = MagicMock()
        kernel32 = MagicMock()
        user32.OpenClipboard.return_value = True
        user32.GetClipboardSequenceNumber.return_value = 42
        with patch("nevision_win.os.name", "nt"), patch(
            "nevision_win.ctypes.WinDLL", side_effect=[user32, kernel32]
        ):
            from nevision_win import _clear_windows_clipboard_if_unchanged
            self.assertTrue(_clear_windows_clipboard_if_unchanged("same synthetic text", 41))
        user32.GetClipboardData.assert_not_called()
        user32.EmptyClipboard.assert_not_called()
        user32.CloseClipboard.assert_called_once_with()

    def test_clipboard_sequence_number_preserves_unsigned_dword(self):
        user32 = MagicMock()
        user32.GetClipboardSequenceNumber.return_value = 0xF0000001
        with patch("nevision_win.os.name", "nt"), patch(
            "nevision_win.ctypes.WinDLL", return_value=user32
        ):
            from nevision_win import _windows_clipboard_sequence_number
            self.assertEqual(_windows_clipboard_sequence_number(), 0xF0000001)
        self.assertEqual(user32.GetClipboardSequenceNumber.restype, ctypes.c_uint)

    def test_native_clipboard_owned_text_is_cleared_under_open_lock(self):
        user32 = MagicMock()
        kernel32 = MagicMock()
        expected_password = "synthetic 🔒 password 😀"
        text_buffer = ctypes.create_unicode_buffer(expected_password)
        text_handle = ctypes.c_void_p(1234)
        user32.OpenClipboard.return_value = True
        user32.GetClipboardSequenceNumber.return_value = 43
        user32.GetClipboardData.return_value = text_handle
        kernel32.GlobalLock.return_value = ctypes.cast(text_buffer, ctypes.c_void_p)
        # Deliberately oversized allocation: only expected text + terminator is read.
        kernel32.GlobalSize.return_value = 512 * 1024 * 1024
        user32.EmptyClipboard.return_value = True
        with patch("nevision_win.os.name", "nt"), patch(
            "nevision_win.ctypes.WinDLL", side_effect=[user32, kernel32]
        ), patch("nevision_win.ctypes.wstring_at", wraps=ctypes.wstring_at) as read_text:
            from nevision_win import _clear_windows_clipboard_if_unchanged
            self.assertTrue(_clear_windows_clipboard_if_unchanged(expected_password, 43))
        user32.OpenClipboard.assert_called_once_with(None)
        kernel32.GlobalLock.assert_called_once_with(text_handle)
        kernel32.GlobalUnlock.assert_called_once_with(text_handle)
        user32.EmptyClipboard.assert_called_once_with()
        user32.CloseClipboard.assert_called_once_with()
        expected_units = len(expected_password.encode("utf-16-le")) // 2
        self.assertEqual(read_text.call_args.args[1], expected_units + 1)

    def test_oversized_expected_clipboard_secret_is_never_read(self):
        user32 = MagicMock()
        kernel32 = MagicMock()
        with patch("nevision_win.os.name", "nt"), patch(
            "nevision_win.ctypes.WinDLL", side_effect=[user32, kernel32]
        ):
            from nevision_win import MAX_CLIPBOARD_SECRET_CHARS, _clear_windows_clipboard_if_unchanged
            self.assertFalse(
                _clear_windows_clipboard_if_unchanged("x" * (MAX_CLIPBOARD_SECRET_CHARS + 1), 43)
            )
        user32.OpenClipboard.assert_not_called()

    def test_close_warns_and_stays_open_if_clipboard_cannot_be_checked(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app._clipboard_secret = "synthetic-password"
        app._clipboard_generation = 1
        app._clipboard_sequence = 1
        app._background_operations = set()
        app._closing = False
        app._executor = MagicMock()

        with patch("nevision_win._clear_windows_clipboard_if_unchanged", return_value=False), patch(
            "nevision_win.messagebox.askyesno", return_value=False
        ) as confirm:
            app._request_close()

        self.assertIn("может остаться в буфере", confirm.call_args.args[1])
        self.assertFalse(app._closing)
        self.assertEqual(app._clipboard_secret, "synthetic-password")
        app.root.destroy.assert_not_called()
        app._executor.shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
