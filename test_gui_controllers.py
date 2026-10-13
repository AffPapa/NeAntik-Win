"""Synthetic controller checks; no Tk window, OS input, or user Data is used."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from nevision_win import AppPaths, NeVisionApp, NeVisionError, ProfileDialog, Storage
from profile_identity import ordinary_identity


class GuiControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="neantik-gui-controller-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.storage = Storage(AppPaths(self.root))

    def profile_dialog(self, name):
        app = SimpleNamespace(storage=self.storage, refresh_profiles=MagicMock())
        dialog = SimpleNamespace(
            app=app,
            profile=None,
            identity=ordinary_identity(),
            mode_choice=None,
            name=SimpleNamespace(get=lambda: name),
            group=SimpleNamespace(get=lambda: "QA"),
            tags=SimpleNamespace(get=lambda: "synthetic"),
            notes=SimpleNamespace(get=lambda *_: "local-only note"),
            proxy=SimpleNamespace(current=lambda: 0),
            proxy_ids=[""],
            destroy=MagicMock(),
        )
        return dialog

    def test_create_profile_save_selects_record_and_closes_dialog(self):
        dialog = self.profile_dialog("Synthetic GUI profile")

        ProfileDialog.save(dialog)

        profiles = self.storage.list_profiles()
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile["name"], "Synthetic GUI profile")
        self.assertEqual(profile["group_name"], "QA")
        self.assertTrue(self.storage.profile_path(profile["id"]).is_dir())
        dialog.app.refresh_profiles.assert_called_once_with(select_id=profile["id"])
        dialog.destroy.assert_called_once_with()

    def test_create_profile_invalid_name_preserves_dialog_and_data(self):
        dialog = self.profile_dialog("  ")

        with patch("nevision_win.messagebox.showerror") as show_error:
            ProfileDialog.save(dialog)

        self.assertEqual(self.storage.list_profiles(), [])
        dialog.app.refresh_profiles.assert_not_called()
        dialog.destroy.assert_not_called()
        show_error.assert_called_once()
        self.assertIn("имя", show_error.call_args.args[1])

    def backup_controller(self, profile_id):
        profile = self.storage.get_profile(profile_id)
        app = SimpleNamespace(
            root=object(),
            storage=self.storage,
            selected_profile=lambda: profile,
            _is_profile_active=lambda _id: False,
            _allow_profile_mutation=lambda _profile: True,
            set_status=MagicMock(),
        )

        def run_now(key, operation, completed, failed):
            self.assertEqual(key, f"backup:{profile_id}")
            try:
                completed(operation())
            except Exception as exc:
                failed(exc)
            return True

        app._run_in_background = MagicMock(side_effect=run_now)
        return app

    def test_backup_confirmation_completes_and_archive_has_manifest(self):
        profile_id = self.storage.save_profile({"name": "Synthetic backup"})
        profile_dir = self.storage.profile_path(profile_id)
        (profile_dir / "synthetic.txt").write_text("safe test content", encoding="utf-8")
        app = self.backup_controller(profile_id)

        with patch("nevision_win.messagebox.askyesno", return_value=True) as confirm, patch(
            "nevision_win.messagebox.showinfo"
        ) as show_info, patch("nevision_win.messagebox.showerror") as show_error:
            NeVisionApp.backup_selected(app)

        confirm.assert_called_once()
        app._run_in_background.assert_called_once()
        archives = list(self.storage.paths.backups.glob("*.zip"))
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(archives[0]) as archive:
            manifest = json.loads(archive.read("nevision-manifest.json"))
            self.assertFalse(manifest["encrypted"])
            self.assertTrue(manifest["browser_session_data_included"])
            self.assertEqual(archive.read("profile/synthetic.txt"), b"safe test content")
        self.assertIn("Backup создан", app.set_status.call_args.args[0])
        show_info.assert_called_once()
        show_error.assert_not_called()

    def test_backup_cancel_does_not_schedule_or_create_archive(self):
        profile_id = self.storage.save_profile({"name": "Cancel backup"})
        app = self.backup_controller(profile_id)

        with patch("nevision_win.messagebox.askyesno", return_value=False):
            NeVisionApp.backup_selected(app)

        app._run_in_background.assert_not_called()
        self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [])

    def test_backup_failure_reports_error_without_false_success(self):
        profile_id = self.storage.save_profile({"name": "Fail backup"})
        app = self.backup_controller(profile_id)

        with patch("nevision_win.messagebox.askyesno", return_value=True), patch.object(
            self.storage, "backup_profile", side_effect=NeVisionError("synthetic backup error")
        ), patch("nevision_win.messagebox.showinfo") as show_info, patch(
            "nevision_win.messagebox.showerror"
        ) as show_error:
            NeVisionApp.backup_selected(app)

        self.assertEqual(app.set_status.call_args.args[0], "Ошибка backup")
        show_error.assert_called_once()
        self.assertIn("synthetic backup error", show_error.call_args.args[1])
        show_info.assert_not_called()
        self.assertEqual(list(self.storage.paths.backups.glob("*.zip")), [])


if __name__ == "__main__":
    unittest.main()
