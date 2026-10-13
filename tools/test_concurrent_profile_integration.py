"""Fast synthetic checks for the concurrent A/B release harness."""

from __future__ import annotations

from http.client import HTTPConnection
import json
import threading
import unittest

from browser_integration import EMPTY, state
from concurrent_profile_integration import ConcurrentServer, assess


class ConcurrentProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ConcurrentServer()
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.close_server)

    def close_server(self) -> None:
        self.server.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)

    def request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            headers = {"Content-Type": "application/json"} if body is not None else {}
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_two_cases_have_distinct_tokens_and_page_config(self) -> None:
        token_a, _ = self.server.add_case("write", "synthetic-A")
        token_b, _ = self.server.add_case("write", "synthetic-B")
        self.assertNotEqual(token_a, token_b)
        status_a, page_a = self.request("GET", f"/case?token={token_a}")
        status_b, page_b = self.request("GET", f"/case?token={token_b}")
        self.assertEqual((status_a, status_b), (200, 200))
        self.assertIn(b"synthetic-A", page_a)
        self.assertNotIn(b"synthetic-A", page_b)
        self.assertIn(b"synthetic-B", page_b)

    def test_duplicate_post_and_absolute_proxy_are_rejected(self) -> None:
        token, _ = self.server.add_case("write", "synthetic-A")
        payload = json.dumps({"token": token, "error": None}).encode()
        self.assertEqual(self.request("POST", f"/report?token={token}", payload)[0], 200)
        self.assertEqual(self.request("POST", f"/report?token={token}", payload)[0], 400)
        self.assertEqual(self.request("GET", "http://example.invalid/foreign")[0], 404)
        self.assertEqual(self.request("CONNECT", "example.invalid:443")[0], 403)
        self.assertEqual(self.server.blocked_proxy_requests, 2)

    def test_assess_distinguishes_storage(self) -> None:
        a = {"before": EMPTY, "after": state("A"), "error": None}
        b = {"before": EMPTY, "after": state("B"), "error": None}
        self.assertTrue(all(assess(a, b, "A", "B").values()))
        self.assertFalse(assess(a, b, "A", "A")["a_b_not_equal"])
        self.assertFalse(assess(a, {**b, "before": state("A")}, "A", "B")["b_initially_empty"])
        self.assertFalse(assess(a, {**b, "error": "synthetic"}, "A", "B")["no_page_errors"])


if __name__ == "__main__":
    unittest.main()
