"""Real Tk event-loop regression tests. Synthetic data only; no external browser."""
from __future__ import annotations
import contextlib
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nevision_win as nv


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nevision-gui-")
        self.paths = nv.AppPaths(Path(self.temp.name))
        self.storage = nv.Storage(self.paths)
        self.profile = self.storage.save_profile({"name": "Тест · 日本語 · QA", "group_name": "QA"})
        self.app = nv.NeVisionApp(self.storage, self.paths)
        self.errors = []
        self.app.root.report_callback_exception = lambda *args: self.errors.append(str(args))
        self.app.root.update()

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.root.update()
            time.sleep(.005)

    def tearDown(self):
        self.app._executor.shutdown(wait=True)
        with contextlib.suppress(nv.tk.TclError):
            for timer in self.app.root.tk.call("after", "info"):
                self.app.root.after_cancel(timer)
            self.app.root.destroy()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def test_async_launch_does_not_block_event_loop(self):
        self.app.refresh_profiles(self.profile)
        class Process:
            def poll(self): return None
        ticks = []
        def launch(*args, **kwargs):
            time.sleep(.4)
            return Process()
        with patch.object(self.app.launcher, "launch", side_effect=launch), patch.object(self.app.launcher, "available_browsers", return_value=[("test", Path("test.exe"))]):
            started = time.monotonic()
            self.app.launch_selected()
            self.assertLess(time.monotonic() - started, .15)
            self.app.root.after(30, lambda: ticks.append(True))
            self.pump(.15)
            self.assertTrue(ticks)
            self.assertNotIn(self.profile, self.app.running)
            self.pump(.5)
            self.assertIn(self.profile, self.app.running)

    def test_background_queue_is_bounded_and_duplicate_rejected(self):
        for index in range(6):
            self.assertTrue(self.app._run_in_background(str(index), lambda: time.sleep(.1), lambda result: None))
        self.assertFalse(self.app._run_in_background("6", lambda: None, lambda result: None))
        self.assertFalse(self.app._run_in_background("0", lambda: None, lambda result: None))
        self.pump(.6)
        self.assertFalse(self.app._background_operations)

    def test_close_waits_for_operation_without_aborting_it(self):
        finished = []
        self.app._run_in_background("write", lambda: (time.sleep(.2), finished.append(True)), lambda result: None)
        with patch.object(self.app.root, "destroy") as destroy:
            self.app._request_close()
            destroy.assert_not_called()
            self.pump(.5)
            self.assertTrue(finished)
            destroy.assert_called_once()

    def test_clipboard_clear_preserves_new_user_content(self):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append("new synthetic text")
        self.app._clipboard_secret = "old synthetic password"
        self.app._clear_copied_password()
        self.assertEqual(self.app.root.clipboard_get(), "new synthetic text")
        self.app._clipboard_secret = "new synthetic text"
        self.app._clear_copied_password()
        with self.assertRaises(nv.tk.TclError):
            self.app.root.clipboard_get()

    def test_search_theme_and_selection(self):
        self.app.refresh_profiles(self.profile)
        for theme in (nv.THEME_LIGHT, nv.THEME_DARK):
            self.app.set_theme_preference(theme)
            self.app.root.update()
            self.assertEqual(self.app.selected_id, self.profile)
            self.assertEqual(self.app.active_theme, theme)
            style = nv.ttk.Style(self.app.root)
            self.assertEqual(style.lookup("Muted.TLabel", "background"), self.app.colors["panel"])
            self.assertEqual(style.lookup("Muted.TLabel", "foreground"), self.app.colors["muted"])
        self.app.search_var.set("no matching profile")
        self.pump(.25)
        self.assertEqual(self.app.profile_tree.get_children(), ())
        self.app.search_var.set("日本語")
        self.pump(.25)
        self.assertEqual(self.app.profile_tree.get_children(), (self.profile,))

    def test_external_status_detected_after_manager_restart(self):
        with patch.object(self.storage, "_windows_chromium_lock_is_active", return_value=True):
            self.app._watch_processes()
            self.pump(.3)
        self.assertIn(self.profile, self.app._active_profiles)
        self.assertEqual(self.app.profile_tree.item(self.profile, "values")[-1], "ОТКРЫТ")

    def test_profile_buttons_fit_minimum_window(self):
        self.app.root.geometry("1020x660")
        self.app.refresh_profiles(self.profile)
        self.app.root.update()
        def walk(widget):
            yield widget
            for child in widget.winfo_children(): yield from walk(child)
        for widget in walk(self.app.detail):
            if isinstance(widget, nv.IconButton):
                self.assertGreater(widget.winfo_width(), 60,
                                   f"button {widget.text!r} was {widget.winfo_width()}px inside {widget.master.winfo_width()}px")
                self.assertGreater(widget.winfo_height(), 20)
                self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), widget.master.winfo_width() + 1)
                self.assertLessEqual(widget.winfo_y() + widget.winfo_height(), widget.master.winfo_height() + 1)

    def test_icon_button_ignores_keyboard_repeat_until_release(self):
        buttons = []

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)

        button = next(widget for widget in walk(self.app.root)
                      if isinstance(widget, nv.IconButton))
        button.command = lambda: buttons.append("activated")

        for keysym in ("Return", "space"):
            with self.subTest(key=keysym):
                event = SimpleNamespace(keysym=keysym)
                button._on_key(event)
                button._on_key(event)
                self.assertEqual(len(buttons), 1)
                button._on_key_release(event)
                button._on_key(event)
                self.assertEqual(len(buttons), 2)
                button._on_key_release(event)
                buttons.clear()

        button._on_key(SimpleNamespace(keysym="a"))
        self.assertEqual(buttons, [])

    def test_duplicate_proxy_choices_do_not_change_assignment(self):
        payload = {"name": "Same", "scheme": "http", "host": "127.0.0.1", "port": 8080}
        first = self.storage.save_proxy(payload)
        second = self.storage.save_proxy(payload)
        self.assertNotEqual(first, second)
        self.storage.save_profile({"name": "With proxy", "proxy_id": first}, self.profile)
        dialog = nv.ProfileDialog(self.app, self.storage.get_profile(self.profile))
        self.app.root.update()
        self.assertEqual(dialog.proxy_ids[dialog.proxy.current()], first)
        dialog.save()
        self.assertEqual(self.storage.get_profile(self.profile)["proxy_id"], first)

    def test_profile_creation_dialog_requests_initial_name_focus(self):
        dialog = nv.ProfileDialog(self.app)
        self.pump(.05)
        self.assertTrue(dialog.winfo_viewable())
        self.assertIs(dialog.grab_current(), dialog)
        # focus_set() records the initial target even when this test process is
        # not the desktop foreground app and therefore cannot own active focus.
        self.assertIs(dialog.focus_lastfor(), dialog.name)

    def test_profile_form_wheel_scrolls_without_hijacking_notes(self):
        dialog = nv.ProfileDialog(self.app)
        dialog.geometry("560x300")
        self.app.root.update()
        canvas = dialog.form_canvas
        self.assertLess(canvas.yview()[1], 1.0)
        dialog.name.event_generate("<MouseWheel>", delta=-120)
        self.app.root.update()
        self.assertGreater(canvas.yview()[0], 0.0)
        canvas.yview_moveto(0)
        self.app.root.update()
        dialog.notes.event_generate("<MouseWheel>", delta=-120)
        self.app.root.update()
        self.assertEqual(canvas.yview()[0], 0.0)
        dialog.destroy()

    def test_proxy_hostname_disclosure_after_save(self):
        dialog = nv.ProxyDialog(self.app)
        self.app.root.update()
        dialog.name.insert(0, "Named proxy")
        dialog.host.insert(0, "proxy.example")
        dialog.port.insert(0, "8080")
        dialog.save()
        self.assertIn("Имя proxy может разрешаться локально", self.app.status_label.cget("text"))

    def test_new_profiles_are_ordinary_and_legacy_clone_is_empty_ordinary(self):
        ordinary_dialog = nv.ProfileDialog(self.app)
        self.app.root.update()
        self.assertTrue(ordinary_dialog.winfo_viewable())
        self.assertIs(ordinary_dialog.grab_current(), ordinary_dialog)
        self.assertFalse(hasattr(ordinary_dialog, "mode_choice"))
        ordinary_dialog.name.insert(0, "Ordinary")
        ordinary_dialog.save()
        ordinary = next(item for item in self.storage.list_profiles() if item["name"] == "Ordinary")
        self.assertEqual(ordinary["fingerprint"]["mode"], "ordinary")

        legacy_id = self.storage.save_profile({"name": "Legacy", "fingerprint": {
            "schema": 2, "mode": "native-persona-preview", "seed": "123456"}})
        legacy = self.storage.get_profile(legacy_id)
        self.app.refresh_profiles(legacy_id)
        self.app.clone_selected()
        clone = self.storage.get_profile(self.app.selected_id)
        self.assertEqual(clone["fingerprint"]["mode"], "ordinary")
        self.assertEqual(self.storage.get_profile(legacy_id)["fingerprint"], legacy["fingerprint"])
        self.assertEqual(list((self.paths.profiles / clone["id"]).iterdir()), [])

    def test_escape_closes_settings_dialog(self):
        dialog = nv.SettingsDialog(self.app)
        self.app.root.update()
        dialog.theme.focus_force()
        dialog.theme.event_generate("<Escape>")
        self.app.root.update()
        self.assertFalse(dialog.winfo_exists())

    def test_legacy_browser_path_is_hidden_until_requested(self):
        dialog = nv.SettingsDialog(self.app)
        self.app.root.update()
        self.assertFalse(dialog.compatibility.winfo_ismapped())
        dialog.toggle_compatibility()
        self.app.root.update()
        self.assertTrue(dialog.compatibility.winfo_ismapped())
        dialog.destroy()

    def test_settings_portability_warning_and_footer_are_visible(self):
        dialog = nv.SettingsDialog(self.app)
        self.app.root.update()
        dialog.settings_canvas.yview_moveto(1)
        self.app.root.update()
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        labels = [widget for widget in walk(dialog) if isinstance(widget, nv.ttk.Label)
                  and str(widget.cget("text")) == nv.PORTABILITY_WARNING]
        self.assertEqual(len(labels), 1)
        warning = labels[0]
        self.assertTrue(warning.winfo_ismapped())
        self.assertGreaterEqual(warning.winfo_rooty(), dialog.settings_canvas.winfo_rooty())
        self.assertLessEqual(warning.winfo_rooty() + warning.winfo_height(),
                             dialog.settings_canvas.winfo_rooty() + dialog.settings_canvas.winfo_height())
        route_labels = [str(widget.cget("text")) for widget in walk(dialog)
                        if isinstance(widget, nv.ttk.Label)]
        self.assertTrue(any("Тот же ПК и Windows-аккаунт" in value and "всю portable-папку" in value
                            for value in route_labels))
        self.assertIn("Другой ПК или Windows-аккаунт", route_labels)
        self.assertTrue(any("новый пустой профиль" in value and "proxy" in value
                            for value in route_labels))
        transfer_buttons = {str(widget.cget("text")): widget for widget in walk(dialog)
                            if isinstance(widget, nv.ttk.Button)}
        for label, method in (("Экспорт настроек…", "export_selected_template"),
                              ("Импорт настроек…", "import_profile_template")):
            button = transfer_buttons[label]
            self.assertTrue(button.winfo_ismapped())
            with patch.object(self.app, method) as action:
                button.invoke()
                self.app.root.update()
                action.assert_called_once_with()
                self.assertTrue(dialog.winfo_ismapped())
        save = [widget for widget in walk(dialog) if isinstance(widget, nv.ttk.Button)
                and str(widget.cget("text")) == "Сохранить"]
        self.assertEqual(len(save), 1)
        self.assertTrue(save[0].winfo_ismapped())
        dialog.destroy()

    def test_important_actions_have_plain_language_hints(self):
        self.app.refresh_profiles(self.profile)
        self.app.root.update()
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        buttons = {widget.text: widget for widget in walk(self.app.root) if isinstance(widget, nv.IconButton)}
        for label in ("Резервная копия", "Чистая копия", "Диагностика", "TCP-проверка proxy", "Удалить профиль"):
            self.assertIsNotNone(buttons[label].hint)
            self.assertGreater(len(buttons[label].hint.text), 20)
        hint = buttons["Чистая копия"].hint
        hint._show()
        self.assertIsNotNone(hint.popup)
        hint._hide()
        self.assertIsNone(hint.popup)

    def test_diagnostics_for_open_profile_copies_link_without_relaunch(self):
        self.app.refresh_profiles(self.profile)
        with patch.object(self.app, "_is_profile_active", return_value=True), patch.object(self.app.launcher, "launch") as launch, patch("nevision_win.messagebox.showinfo"):
            self.app.open_privacy_diagnostics()
        self.assertEqual(self.app.root.clipboard_get(), nv.PRIVACY_CHECK_URL)
        launch.assert_not_called()

    def test_profile_browser_label_matches_pinned_engine(self):
        self.storage.pin_browser_family(self.profile, "chromium")
        self.app.refresh_profiles(self.profile)
        self.app.root.update()
        def labels(widget):
            for child in widget.winfo_children():
                if isinstance(child, nv.tk.Label):
                    yield str(child.cget("text"))
                yield from labels(child)
        self.assertTrue(any("Встроенный Chromium" in value for value in labels(self.app.detail)))


if __name__ == "__main__": unittest.main(verbosity=2)
