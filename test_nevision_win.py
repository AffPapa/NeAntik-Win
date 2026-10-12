"""Core regression tests for NeVision Win. Run: python -m unittest test_nevision_win.py"""

import ctypes
import json
import os
import shutil
import stat
import tempfile
import threading
import unittest
import uuid
import warnings
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from nevision_win import (
    AppPaths,
    BrowserLauncher,
    PRIVACY_CHECK_URL,
    DARK_COLORS,
    LIGHT_COLORS,
    NeVisionError,
    NeVisionApp,
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
    palette_for_theme,
    proxy_endpoint,
    proxy_choices,
    resolve_theme,
)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nevision-unit-"))
        self.storage = Storage(AppPaths(self.root))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

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

    def test_backup_enforces_the_same_limits_as_restore(self):
        profile_id = self.storage.save_profile({"name": "Many files"})
        folder = self.storage.profile_path(profile_id)
        (folder / "one.txt").write_text("1", encoding="utf-8")
        (folder / "two.txt").write_text("2", encoding="utf-8")

        with patch("nevision_win.MAX_BACKUP_FILES", 1):
            with self.assertRaisesRegex(NeVisionError, "слишком много файлов"):
                self.storage.backup_profile(profile_id)
        self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [])

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
        self.assertFalse(str(self.storage.profile_path("synthetic")).startswith("\\\\?\\"))


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
    def test_about_describes_actual_browser_bundle(self):
        app = object.__new__(NeVisionApp)
        app.root = MagicMock()
        app.launcher = MagicMock()
        with patch("nevision_win.messagebox.showinfo") as show:
            app.launcher.bundled_browser.return_value = Path("C:/portable/Engine/Chromium/chrome.exe")
            app.show_about()
            self.assertIn("входит Chromium", show.call_args.args[1])
            self.assertIn("установленный Chrome не требуется", show.call_args.args[1])
            app.launcher.bundled_browser.return_value = None
            app.show_about()
            self.assertIn("Собственного ядра", show.call_args.args[1])

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
        app.root.clipboard_get.return_value = "same-password"
        app._clipboard_secret = "same-password"
        app._clipboard_generation = 2
        app._clear_copied_password("same-password", 1)
        app.root.clipboard_clear.assert_not_called()
        app._clear_copied_password("same-password", 2)
        app.root.clipboard_clear.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
