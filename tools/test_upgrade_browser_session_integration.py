"""Fast local controls for the disposable browser-session migration gate."""

from __future__ import annotations

from http.client import HTTPConnection
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import threading
import unittest
import zipfile

from upgrade_browser_session_integration import (
    PAGE, SERVICE_WORKER, STATE_FIELDS, FixtureServer, extract_compact_archive_root,
    validate_profile_root,
)


class ProfileBoundaryTests(unittest.TestCase):
    def test_plain_portable_profile_path_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "portable" / "Data" / "Profiles" / ("a" * 32)
            profile.mkdir(parents=True)
            validate_profile_root(profile)

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_data_profiles_and_profile_junctions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="neantik-session-junction-") as temporary:
            base = Path(temporary)
            for redirected in ("Data", "Profiles", "profile"):
                with self.subTest(redirected=redirected):
                    portable = base / redirected / "portable"
                    portable.mkdir(parents=True)
                    outside = base / redirected / "outside"
                    profile_id = "b" * 32
                    if redirected == "Data":
                        target = outside / "Data"
                        (target / "Profiles" / profile_id).mkdir(parents=True)
                        link = portable / "Data"
                    elif redirected == "Profiles":
                        (portable / "Data").mkdir()
                        target = outside / "Profiles"
                        (target / profile_id).mkdir(parents=True)
                        link = portable / "Data" / "Profiles"
                    else:
                        (portable / "Data" / "Profiles").mkdir(parents=True)
                        target = outside / "profile"
                        target.mkdir(parents=True)
                        link = portable / "Data" / "Profiles" / profile_id
                    result = subprocess.run(
                        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode:
                        self.skipTest("Windows junction creation is unavailable in this environment")
                    try:
                        attrs = getattr(link.lstat(), "st_file_attributes", 0)
                        self.assertTrue(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                        with self.assertRaisesRegex(RuntimeError, "unsafe_profile_path_reparse_point"):
                            validate_profile_root(portable / "Data" / "Profiles" / profile_id)
                    finally:
                        link.rmdir()


class MigrationFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FixtureServer("synthetic-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            headers = {"Content-Type": "application/json"} if body is not None else {}
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_page_uses_persistent_cookie_and_scoped_origin(self) -> None:
        status, body = self.request("GET", "/case?token=synthetic-token&phase=write")
        self.assertEqual(status, 200)
        self.assertIn(b"Max-Age=86400", body)
        for api in (b"indexedDB.open", b"caches.open", b"serviceWorker.register", b"Notification.permission"):
            self.assertIn(api, body)
        self.assertIn(b"caches.open('nevision_qa_cache')", body)
        self.assertIn(b"'/nevision-qa-cache-entry'", body)
        self.assertEqual(self.server.page_hits["write"], 1)
        status, _ = self.request("GET", "/case?token=wrong&phase=write")
        self.assertEqual(status, 404)

    def test_service_worker_script_is_loopback_token_scoped(self) -> None:
        status, body = self.request("GET", "/sw.js?token=synthetic-token")
        self.assertEqual(status, 200)
        self.assertIn(b"skipWaiting", body)
        self.assertIn(b"clients.claim", body)
        status, _ = self.request("GET", "/sw.js?token=wrong")
        self.assertEqual(status, 404)

    def test_absolute_proxy_request_is_rejected(self) -> None:
        status, _ = self.request("GET", "http://example.invalid/elsewhere?token=synthetic-token")
        self.assertEqual(status, 404)
        self.assertEqual(self.server.rejected_proxy_requests, 1)
        status, _ = self.request("CONNECT", "example.invalid:443")
        self.assertEqual(status, 403)
        self.assertEqual(self.server.rejected_proxy_requests, 2)

    def test_report_rejects_duplicate_and_wrong_phase(self) -> None:
        payload = {"token": "synthetic-token", "phase": "write",
                   **{field: True for field in STATE_FIELDS},
                   "notification": "denied",
                   "origin": f"http://127.0.0.1:{self.server.server_port}"}
        status, _ = self.request("POST", "/report?token=synthetic-token", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        self.assertTrue(self.server.ready.is_set())
        status, _ = self.request("POST", "/report?token=synthetic-token", json.dumps(payload).encode())
        self.assertEqual(status, 400)
        self.server.phase = "old-read"
        status, _ = self.request("POST", "/report?token=synthetic-token", json.dumps(payload).encode())
        self.assertEqual(status, 400)

    def test_report_rejects_missing_storage_assertions(self) -> None:
        payload = {"token": "synthetic-token", "phase": "write",
                   "cookie": True, "localStorage": True,
                   "notification": "denied",
                   "origin": f"http://127.0.0.1:{self.server.server_port}"}
        status, _ = self.request("POST", "/report?token=synthetic-token", json.dumps(payload).encode())
        self.assertEqual(status, 400)

    def test_page_failure_report_is_token_and_phase_scoped(self) -> None:
        payload = {"token": "synthetic-token", "phase": "write", "message": "synthetic failure"}
        status, _ = self.request("POST", "/failure?token=synthetic-token", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        self.assertEqual(self.server.failures["write"], "synthetic failure")
        self.assertTrue(self.server.ready.is_set())
        status, _ = self.request("POST", "/failure?token=wrong", json.dumps(payload).encode())
        self.assertEqual(status, 404)


class ArchivePathTests(unittest.TestCase):
    def test_archive_root_is_compacted_before_browser_profile_creation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="na-") as temporary:
            root = Path(temporary)
            archive_path = root / "synthetic.zip"
            archive_root = "NeAntikWin-portable-v9.9.9-preview"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(f"{archive_root}/Engine/Chromium/chrome.exe", b"synthetic")
            portable = extract_compact_archive_root(archive_path, root, archive_root, "o")
            self.assertEqual((portable / "Engine" / "Chromium" / "chrome.exe").read_bytes(), b"synthetic")
            self.assertFalse((root / "o-extract").exists())
            self.assertLess(len(str(portable / "Data" / "Profiles" / ("a" * 32) / "Default")),
                            len(str(root / "o-extract" / archive_root / "Data" / "Profiles" / ("a" * 32) / "Default")))


if __name__ == "__main__":
    unittest.main()
