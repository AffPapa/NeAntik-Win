"""Small synthetic unit tests for the loopback-only WebSocket fixture."""

from __future__ import annotations

import socket
import unittest
from pathlib import Path
from urllib.parse import unquote

import websocket_route_integration as fixture


class WebSocketRouteFixtureTests(unittest.TestCase):
    def test_target_parser_allows_only_synthetic_host_without_credentials(self) -> None:
        self.assertEqual(fixture.endpoint_host_port("nevision-qa.invalid:1234"),
                         (fixture.HOST, 1234))
        for address in ("example.com:1234", "127.0.0.1:1234", "user@nevision-qa.invalid:1234",
                        "nevision-qa.invalid", "nevision-qa.invalid:99999"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                fixture.endpoint_host_port(address)

    def test_masked_client_frame_and_unmasked_server_frame(self) -> None:
        left, right = socket.socketpair()
        try:
            payload = b"hello"
            mask = b"\x01\x02\x03\x04"
            frame = bytes([0x81, 0x80 | len(payload)]) + mask + bytes(
                byte ^ mask[index % 4] for index, byte in enumerate(payload))
            right.sendall(frame)
            self.assertEqual(fixture.read_client_text_frame(left), "hello")
            self.assertEqual(fixture.websocket_text_frame("ack"), b"\x81\x03ack")
            with self.assertRaises(ValueError):
                fixture.websocket_text_frame("x" * 126)
        finally:
            left.close()
            right.close()

    def test_page_uses_only_synthetic_endpoint(self) -> None:
        page = unquote(fixture.page_url("wss", 1234, "a" * 32))
        self.assertIn("wss://nevision-qa.invalid:1234/socket/", page)
        self.assertIn("ack:", page)
        self.assertNotIn("https://", page)
        direct = fixture.page_html("ws", 1234, "a" * 32, "127.0.0.1")
        self.assertIn("ws://127.0.0.1:1234/socket/", direct)
        with self.assertRaises(ValueError):
            fixture.page_html("ws", 1234, "a" * 32, "example.org")

    def test_browser_flags_pin_only_wss_fixture_and_keep_sandbox(self) -> None:
        for protocol in ("ws", "wss"):
            for route in ("direct", "http", "socks5", "https", "http_unavailable",
                          "socks5_unavailable", "https_unavailable", "https_untrusted"):
                with self.subTest(protocol=protocol, route=route):
                    fixture_pin = "synthetic-target-pin" if protocol == "wss" else ""
                    if route.startswith("https") and route != "https_untrusted":
                        fixture_pin += ("," if fixture_pin else "") + "synthetic-proxy-pin"
                    flags = fixture.browser_arguments(Path("chrome.exe"), Path("synthetic-profile"),
                                                      protocol, route, 1234, 5678, "a" * 32, fixture_pin)
                    self.assertNotIn("--ignore-certificate-errors", flags)
                    self.assertNotIn("--no-sandbox", flags)
                    pins = [flag for flag in flags if flag.startswith("--ignore-certificate-errors-spki-list=")]
                    self.assertEqual(pins, ["--ignore-certificate-errors-spki-list=" + fixture_pin]
                                     if fixture_pin else [])
                    if route.startswith("https"):
                        self.assertIn("--proxy-server=https://127.0.0.1:5678", flags)
                        self.assertFalse(any(flag.startswith("--proxy-bypass-list=") and "nevision-qa.invalid" in flag
                                             for flag in flags))


if __name__ == "__main__":
    unittest.main()
