"""Own-core identity, lifecycle and bundle checks; no compiled-core claims."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

import current_core as core
from nevision_win import AppPaths, BrowserLauncher, NeVisionApp, NeVisionError, ProfileDialog, Storage, timestamp, tk


class IdentityTests(unittest.TestCase):
    def test_windows155_memory_values_and_rejected_drafts_are_not_clamped(self):
        self.assertEqual(core.MEMORY_OPTIONS, ("2", "4", "8", "16", "32"))
        for memory in core.MEMORY_OPTIONS:
            identity = core.new_identity(memory=memory)
            self.assertEqual(identity["device_memory"], memory)
            self.assertIn("--neantik-device-memory=" + memory, core.identity_arguments(identity))
        for memory in ("0.25", "0.5", "1"):
            draft = {**core.new_identity(), "device_memory": memory}
            original = copy.deepcopy(draft)
            with self.subTest(memory=memory), self.assertRaisesRegex(core.CoreError, "Windows Chromium 155"):
                core.validate_identity(draft)
            self.assertEqual(draft, original)
            with self.assertRaises(core.CoreError):
                core.identity_arguments(draft)
    def test_timezone_optional_legacy_and_strict_flags(self):
        identity = core.new_identity(timezone="Asia/Bangkok")
        self.assertIn("--neantik-timezone=Asia/Bangkok", core.identity_arguments(identity))
        legacy = dict(identity)
        del legacy["timezone"]
        self.assertEqual(core.validate_identity(legacy)["timezone"], "system")
        self.assertFalse(any(flag.startswith("--neantik-timezone") for flag in core.identity_arguments(legacy)))
        for bad in ("", "../UTC", "Europe//Berlin", "UTC --no-sandbox", "Аsia/Bangkok", "Europe/Berlin\n", "Europe/" + "X" * 129, True):
            with self.subTest(value=bad), self.assertRaises(core.CoreError):
                core.validate_identity({**identity, "timezone": bad})

    def test_nonzero_uint64_and_exact_json_roundtrip(self):
        for random_value, expected in ((0, 1), (0xFFFFFFFFFFFFFFFE, 0xFFFFFFFFFFFFFFFF)):
            with patch.object(core.secrets, "randbelow", return_value=random_value):
                identity = core.new_identity()
            self.assertEqual(identity["seed"], expected)
            self.assertEqual(core.validate_identity(json.loads(core.serialize_identity(identity))), identity)
        self.assertIn("--neantik-fingerprint-seed=18446744073709551615", core.identity_arguments(identity))
        self.assertFalse(any("user-agent" in flag or "fingerprint-brand" in flag for flag in core.identity_arguments(identity)))

    def test_ordinary_and_reject_unknown_invalid_values(self):
        self.assertEqual(core.identity_arguments(core.ordinary_identity()), [])
        original = core.new_identity()
        for key, bad in (("seed", 0), ("seed", True), ("seed", 2**64), ("seed", "8"), ("schema", True),
                         ("hardware_concurrency", True), ("device_memory", "8 --no-sandbox"), ("mode", "shim")):
            value = {**original, key: bad}
            with self.subTest(key=key, bad=bad), self.assertRaises(core.CoreError):
                core.validate_identity(value)
        with self.assertRaises(core.CoreError):
            core.validate_identity({**original, "platform": "macos"})


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="neantik-identity-qa-")
        self.paths = AppPaths(Path(self.temp.name))
        self.storage = Storage(self.paths)
        self.identity = core.new_identity(cpu=4, memory="4", timezone="Europe/Berlin")
        self.profile_id = self.storage.save_profile({"name": "Native QA", "fingerprint": self.identity})

    def tearDown(self):
        self.temp.cleanup()

    def test_edit_and_restart_preserve_identity(self):
        self.storage.save_profile({"name": "Renamed"}, self.profile_id)
        self.assertEqual(Storage(self.paths).get_profile(self.profile_id)["fingerprint"], self.identity)
        self.assertEqual(self.storage.list_profiles()[0]["fingerprint"], self.identity)

    def test_legacy_invalid_memory_db_blob_and_browser_data_are_preserved(self):
        browser_file = self.storage.profile_path(self.profile_id) / "synthetic-session.txt"
        browser_file.write_bytes(b"unchanged browser session")
        for memory in ("0.25", "0.5", "1"):
            blob = json.dumps({**self.identity, "device_memory": memory}, sort_keys=True)
            with self.storage.connection() as db:
                db.execute("UPDATE profile_fingerprints SET config_json=? WHERE profile_id=?", (blob, self.profile_id))
            for read in (lambda: self.storage.get_profile(self.profile_id), self.storage.list_profiles):
                with self.subTest(memory=memory), self.assertRaisesRegex(NeVisionError, "Windows Chromium 155"):
                    read()
            with self.storage.connection() as db:
                saved = db.execute("SELECT config_json FROM profile_fingerprints WHERE profile_id=?", (self.profile_id,)).fetchone()[0]
            self.assertEqual(saved, blob)
            self.assertEqual(browser_file.read_bytes(), b"unchanged browser session")

    def test_old_profile_without_identity_row_is_explicit_ordinary(self):
        profile = self.storage.save_profile({"name": "Old ordinary"})
        with self.storage.connection() as db:
            db.execute("DELETE FROM profile_fingerprints WHERE profile_id=?", (profile,))
        self.assertEqual(self.storage.get_profile(profile)["fingerprint"], core.ordinary_identity())

    def test_clean_clone_gets_new_seed_and_no_browser_data(self):
        (self.storage.profile_path(self.profile_id) / "synthetic-cookie.txt").write_bytes(b"synthetic")
        view = SimpleNamespace(storage=self.storage, selected_profile=lambda: self.storage.get_profile(self.profile_id),
                               set_status=lambda _: None, refresh_profiles=lambda **_: None)
        NeVisionApp.clone_selected(view)
        clone_id = next(profile["id"] for profile in self.storage.list_profiles() if profile["id"] != self.profile_id)
        clone = self.storage.get_profile(clone_id)
        self.assertNotEqual(clone["fingerprint"]["seed"], self.identity["seed"])
        self.assertEqual(clone["fingerprint"]["hardware_concurrency"], 4)
        self.assertEqual(clone["fingerprint"]["device_memory"], "4")
        self.assertEqual(clone["fingerprint"]["timezone"], "Europe/Berlin")
        self.assertEqual(list(self.storage.profile_path(clone_id).iterdir()), [])

    def test_native_backup_restore_preserves_identity(self):
        (self.storage.profile_path(self.profile_id) / "fixture.txt").write_bytes(b"synthetic browser data")
        archive = self.storage.backup_profile(self.profile_id)
        restored = self.storage.restore_profile(archive)
        self.assertNotEqual(restored, self.profile_id)
        self.assertEqual(self.storage.get_profile(restored)["fingerprint"], self.identity)
        self.assertEqual((self.storage.profile_path(restored) / "fixture.txt").read_bytes(), b"synthetic browser data")

    def test_mode_conversion_does_not_reuse_existing_browser_data(self):
        (self.storage.profile_path(self.profile_id) / "fixture.txt").write_bytes(b"native data")
        with self.assertRaisesRegex(NeVisionError, "чистую копию"):
            self.storage.save_profile({"name": "Unsafe convert", "fingerprint": core.ordinary_identity()}, self.profile_id)
        self.assertEqual(self.storage.get_profile(self.profile_id)["fingerprint"], self.identity)

    def test_native_restore_recovery_preserves_identity_and_v2(self):
        restored_id = uuid.uuid4().hex
        staging = self.paths.profiles / (".restore-" + uuid.uuid4().hex + ".partial")
        staging.mkdir()
        (staging / "fixture.txt").write_bytes(b"recovery")
        profile = {"id": restored_id, "name": "Recovered native", "group_name": "", "tags": "", "notes": "",
                   "created_at": timestamp(), "updated_at": timestamp(), "fingerprint": self.identity}
        journal = self.storage._create_operation_journal({"operation": "restore", "profile": profile, "staging_dir": staging.name})
        self.assertEqual(json.loads(journal.read_text(encoding="utf-8"))["format"], "neantik-operation-v2")
        staging.rename(self.storage.profile_path(restored_id))
        recovered = Storage(self.paths)
        self.assertEqual(recovered.get_profile(restored_id)["fingerprint"], self.identity)
        self.assertFalse(journal.exists())
        with self.assertRaisesRegex(NeVisionError, "Формат журнала"):
            recovered._journal_restore_profile({"format": "nevision-operation-v1", "profile": profile})

    def test_native_launch_missing_engine_never_falls_back_to_stock(self):
        launcher = BrowserLauncher(self.storage)
        with patch.object(launcher, "resolve_browser") as stock, patch("nevision_win.subprocess.Popen") as popen:
            with self.assertRaisesRegex(NeVisionError, "Native-ядро"):
                launcher.launch(self.storage.get_profile(self.profile_id))
        stock.assert_not_called()
        popen.assert_not_called()

    def test_launch_uses_profile_seed_without_fake_ua(self):
        launcher = BrowserLauncher(self.storage)
        process = Mock()
        process.poll.return_value = None
        with patch.object(launcher.native_core, "resolve", return_value=Path("C:/fixture/chrome.exe")), patch.object(self.storage, "wait_for_chromium_lock"), patch("nevision_win.subprocess.Popen", return_value=process) as popen:
            launcher.launch(self.storage.get_profile(self.profile_id))
        argv = popen.call_args.args[0]
        for argument in core.identity_arguments(self.identity):
            self.assertIn(argument, argv)
        self.assertFalse(any("user-agent" in argument or "no-sandbox" in argument for argument in argv))


class ProfileFormTests(unittest.TestCase):
    def test_native_controls_fixed_footer_and_actual_save(self):
        with tempfile.TemporaryDirectory(prefix="neantik-profile-form-") as temporary:
            paths = AppPaths(Path(temporary))
            storage = Storage(paths)
            try:
                app = NeVisionApp(storage, paths)
            except tk.TclError as exc:
                self.skipTest(f"Tk display unavailable: {exc}")
            try:
                app.root.update()
                dialog = ProfileDialog(app)
                for scaling in (1.0, 1.5, 2.0):
                    app.root.tk.call("tk", "scaling", scaling)
                    dialog.update()
                    buttons = []
                    def collect(widget):
                        for child in widget.winfo_children():
                            if child.winfo_class() == "TButton" and child.cget("text") == "Сохранить":
                                buttons.append(child)
                            collect(child)
                    collect(dialog)
                    self.assertEqual(len(buttons), 1)
                    self.assertTrue(buttons[0].winfo_ismapped())
                    self.assertLessEqual(buttons[0].winfo_rooty() + buttons[0].winfo_height(), dialog.winfo_rooty() + dialog.winfo_height())
                dialog.mode.current(1)
                dialog.mode.event_generate("<<ComboboxSelected>>")
                dialog.update()
                self.assertEqual(str(dialog.hardware.cget("state")), "disabled")
                dialog.mode.current(0)
                dialog.mode.event_generate("<<ComboboxSelected>>")
                self.assertEqual(str(dialog.timezone.cget("state")), "readonly")
                dialog.name.insert(0, "Native form QA")
                dialog.hardware.set("4 потока · 4 GB")
                dialog.timezone.set("Europe/Berlin")
                seed = dialog.identity["seed"]
                dialog.save()
                saved = storage.get_profile(storage.list_profiles()[0]["id"])["fingerprint"]
                self.assertEqual(saved["seed"], seed)
                self.assertEqual(saved["timezone"], "Europe/Berlin")
                self.assertEqual(saved["hardware_concurrency"], 4)
            finally:
                app._executor.shutdown(wait=True)
                for timer in app.root.tk.call("after", "info"):
                    app.root.after_cancel(timer)
                app.root.destroy()


class BundleTests(unittest.TestCase):
    def test_runtime_info_requires_exact_commit_and_granular_capabilities(self):
        valid = {"engine_id": core.ENGINE_ID, "version": core.ENGINE_VERSION,
                 "source_commit": core.SOURCE_COMMIT, "schema": 1,
                 "capabilities": {key: True for key in core.REQUIRED_CAPABILITIES}}
        def run_probe(info):
            def fake_run(argv, **kwargs):
                output = next(argument.split("=", 1)[1] for argument in argv if argument.startswith("--neantik-core-info="))
                Path(output).write_text(json.dumps(info), encoding="utf-8")
                self.assertFalse(any(argument.startswith("--neantik-fingerprint-seed") for argument in argv))
                return SimpleNamespace(returncode=0)
            with patch.object(core.subprocess, "run", side_effect=fake_run):
                core.CoreResolver._probe(Path("synthetic-neantik.exe"))
        run_probe(valid)
        for field, wrong in (("version", "150.0.0.0"), ("source_commit", "0" * 40), ("schema", True)):
            with self.subTest(field=field), self.assertRaises(core.CoreError):
                run_probe({**valid, field: wrong})
        for value in (False, 1, None):
            bad = copy.deepcopy(valid)
            bad["capabilities"]["canvas_opaque_srgb_uint8"] = value
            bad["capabilities"]["canvas"] = True
            with self.subTest(capability=value), self.assertRaises(core.CoreError):
                run_probe(bad)

    def test_hash_cache_provenance_and_missing_native_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolver = core.CoreResolver(root)
            with self.assertRaises(core.CoreError):
                resolver.resolve()
            directory = root / core.ENGINE_DIRECTORY
            directory.mkdir(parents=True)
            files = {"chrome.exe": b"synthetic", "chrome.dll": b"synthetic dll"}
            for name, data in files.items():
                (directory / name).write_bytes(data)
            manifest = {"format": core.MANIFEST_FORMAT, "schema": 1, "engine_id": core.ENGINE_ID,
                        "version": core.ENGINE_VERSION, "source_commit": core.SOURCE_COMMIT,
                        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
            (directory / core.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(resolver, "_probe") as probe:
                self.assertEqual(resolver.resolve(), (directory / "chrome.exe").resolve())
                resolver.resolve()
                probe.assert_called_once()
                (directory / "chrome.dll").write_bytes(b"tampered payload")
                with self.assertRaises(core.CoreError):
                    resolver.resolve()


if __name__ == "__main__":
    unittest.main()
