"""Fast local controls for the disposable browser-session migration gate."""

from __future__ import annotations

from http.client import HTTPConnection
import json
import threading
import unittest

from upgrade_browser_session_integration import FixtureServer


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
        self.assertEqual(self.server.page_hits["write"], 1)
        status, _ = self.request("GET", "/case?token=wrong&phase=write")
        self.assertEqual(status, 404)

    def test_absolute_proxy_request_is_rejected(self) -> None:
        status, _ = self.request("GET", "http://example.invalid/elsewhere?token=synthetic-token")
        self.assertEqual(status, 404)
        self.assertEqual(self.server.rejected_proxy_requests, 1)
        status, _ = self.request("CONNECT", "example.invalid:443")
        self.assertEqual(status, 403)
        self.assertEqual(self.server.rejected_proxy_requests, 2)

    def test_report_rejects_duplicate_and_wrong_phase(self) -> None:
        payload = {"token": "synthetic-token", "phase": "write", "cookie": True,
                   "localStorage": True, "origin": "http://127.0.0.1"}
        status, _ = self.request("POST", "/report?token=synthetic-token", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        self.assertTrue(self.server.ready.is_set())
        status, _ = self.request("POST", "/report?token=synthetic-token", json.dumps(payload).encode())
        self.assertEqual(status, 400)
        self.server.phase = "read"
        status, _ = self.request("POST", "/report?token=synthetic-token", json.dumps(payload).encode())
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
