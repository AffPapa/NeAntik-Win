"""Real Tk event-loop regression tests. Synthetic data only; no external browser."""
from __future__ import annotations
import contextlib
from pathlib import Path
import sys
import tempfile
import time
import unittest
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
                self.assertGreater(widget.winfo_width(), 60)
                self.assertGreater(widget.winfo_height(), 20)
                self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), widget.master.winfo_width() + 1)
                self.assertLessEqual(widget.winfo_y() + widget.winfo_height(), widget.master.winfo_height() + 1)


if __name__ == "__main__": unittest.main(verbosity=2)
