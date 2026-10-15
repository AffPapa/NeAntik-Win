"""Synthetic loopback coverage for the credential-free proxy protocol probe."""

from __future__ import annotations

import socketserver
import ssl
import threading
import unittest
from unittest.mock import patch

from proxy_diagnostics import diagnose_proxy


class _FixtureServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, reply: bytes):
        self.reply = reply
        self.received = bytearray()
        self.received_lock = threading.Lock()

        class Handler(socketserver.BaseRequestHandler):
            def handle(inner_self):
                connection = inner_self.request
                connection.settimeout(2)
                expected = 3 if reply.startswith(b"\x05") else None
                while expected is not None and len(self.received) < expected:
                    chunk = connection.recv(expected - len(self.received))
                    if not chunk:
                        break
                    with self.received_lock:
                        self.received.extend(chunk)
                if expected is None:
                    while len(self.received) < 1024:
                        chunk = connection.recv(min(128, 1024 - len(self.received)))
                        if not chunk:
                            break
                        with self.received_lock:
                            self.received.extend(chunk)
                        if b"\r\n\r\n" in self.received:
                            break
                connection.sendall(reply)

        super().__init__(("127.0.0.1", 0), Handler)

    def __enter__(self):
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=2)

    @property
    def endpoint(self):
        return {"host": "127.0.0.1", "port": self.server_address[1]}


def _proxy(server: _FixtureServer, scheme: str = "http") -> dict[str, object]:
    return {
        **server.endpoint,
        "scheme": scheme,
        "username": "synthetic-user-must-not-be-sent",
        "password_protected": "synthetic-encrypted-marker-must-not-be-read",
    }


class ProxyDiagnosticTests(unittest.TestCase):
    def test_http_response_is_only_a_protocol_response_and_never_sends_credentials(self):
        with _FixtureServer(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n") as server:
            with patch("nevision_win.SecretVault.decrypt", side_effect=AssertionError("must not decrypt")):
                success, message = diagnose_proxy(_proxy(server))
        request = bytes(server.received)
        self.assertTrue(success)
        self.assertIn("HTTP-ответ получен (код 200)", message)
        self.assertIn("CONNECT и маршрут до сайта не проверялись", message)
        self.assertTrue(request.startswith(b"OPTIONS * HTTP/1.1\r\n"))
        self.assertIn(f"Host: 127.0.0.1:{server.server_address[1]}\r\n".encode(), request)
        self.assertNotIn(b"CONNECT", request)
        self.assertNotIn(b"Authorization", request)
        self.assertNotIn(b"synthetic-user-must-not-be-sent", request)
        self.assertNotIn(b"synthetic-encrypted-marker-must-not-be-read", request)

    def test_http_407_is_reported_without_sending_any_saved_authentication(self):
        with _FixtureServer(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n") as server:
            success, message = diagnose_proxy(_proxy(server))
        self.assertFalse(success)
        self.assertIn("требует авторизацию", message)
        self.assertIn("не отправлялись", message)
        self.assertNotIn(b"synthetic-user-must-not-be-sent", server.received)

    def test_http_401_is_not_mislabeled_as_proxy_authentication_challenge(self):
        with _FixtureServer(b"HTTP/1.1 401 Unauthorized\r\n\r\n") as server:
            success, message = diagnose_proxy(_proxy(server))
        self.assertFalse(success)
        self.assertIn("HTTP 401", message)
        self.assertIn("не стандартный proxy challenge 407", message)
        self.assertNotIn(b"Authorization", server.received)

    def test_rejected_options_probe_is_not_reported_as_proxy_success(self):
        with _FixtureServer(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n") as server:
            success, message = diagnose_proxy(_proxy(server))
        self.assertFalse(success)
        self.assertIn("кодом 405", message)
        self.assertIn("поддержку CONNECT она не проверяла", message)

    def test_connected_http_endpoint_that_closes_without_response_is_not_tcp_failure(self):
        with _FixtureServer(b"") as server:
            success, message = diagnose_proxy(_proxy(server))
        self.assertFalse(success)
        self.assertIn("TCP доступен", message)
        self.assertIn("корректный ответ proxy не получен", message)

    def test_socks5_offers_only_no_auth(self):
        with _FixtureServer(b"\x05\x00") as server:
            success, message = diagnose_proxy(_proxy(server, "socks5"))
        self.assertTrue(success)
        self.assertIn("SOCKS5", message)
        self.assertIn("Маршрут до сайта не проверялся", message)
        self.assertEqual(bytes(server.received), b"\x05\x01\x00")

    def test_socks5_auth_required_result_does_not_send_credentials(self):
        with _FixtureServer(b"\x05\x02") as server:
            success, message = diagnose_proxy(_proxy(server, "socks5"))
        self.assertFalse(success)
        self.assertIn("SOCKS5 требует авторизацию", message)
        self.assertEqual(bytes(server.received), b"\x05\x01\x00")

    def test_socks5_rejection_is_not_misreported_as_success(self):
        with _FixtureServer(b"\x05\xff") as server:
            success, message = diagnose_proxy(_proxy(server, "socks5"))
        self.assertFalse(success)
        self.assertIn("не принимает режим без авторизации", message)
        self.assertEqual(bytes(server.received), b"\x05\x01\x00")

    def test_https_uses_default_strict_tls_context(self):
        class FakeConnection:
            def __init__(self):
                self.sent = b""
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                pass
            def settimeout(self, _value):
                pass
            def sendall(self, value):
                self.sent += value
            def recv(self, _size):
                return b"HTTP/1.1 200 OK\r\n"

        raw = FakeConnection()
        wrapped = FakeConnection()
        context = ssl.create_default_context()
        proxy = {"host": "proxy.example.invalid", "port": 443, "scheme": "https"}
        with patch("proxy_diagnostics.socket.create_connection", return_value=raw), \
             patch("proxy_diagnostics.ssl.create_default_context", return_value=context) as context_factory, \
             patch.object(context, "wrap_socket", return_value=wrapped) as wrap:
            success, message = diagnose_proxy(proxy)
        self.assertTrue(success)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        context_factory.assert_called_once_with()
        wrap.assert_called_once_with(raw, server_hostname="proxy.example.invalid")
        self.assertIn("TLS-сертификат проверен", message)
        self.assertEqual(
            wrapped.sent,
            b"OPTIONS * HTTP/1.1\r\nHost: proxy.example.invalid:443\r\nConnection: close\r\n\r\n",
        )

    def test_https_certificate_error_fails_closed(self):
        class FakeConnection:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                pass
            def settimeout(self, _value):
                pass

        raw = FakeConnection()
        context = ssl.create_default_context()
        with patch("proxy_diagnostics.socket.create_connection", return_value=raw), \
             patch("proxy_diagnostics.ssl.create_default_context", return_value=context), \
             patch.object(context, "wrap_socket", side_effect=ssl.SSLCertVerificationError("synthetic")):
            success, message = diagnose_proxy({"host": "127.0.0.1", "port": 443, "scheme": "https"})
        self.assertFalse(success)
        self.assertIn("не прошёл проверку", message)

    def test_invalid_proxy_input_does_not_connect(self):
        with patch("proxy_diagnostics.socket.create_connection") as connect:
            success, message = diagnose_proxy({"scheme": "direct", "host": "127.0.0.1", "port": 80})
        self.assertFalse(success)
        self.assertIn("неверные параметры", message)
        connect.assert_not_called()

    def test_invalid_host_is_rejected_before_dns_or_tcp(self):
        with patch("proxy_diagnostics.socket.create_connection") as connect:
            success, message = diagnose_proxy({"host": "proxy.example\r\nX-Test: injected", "port": 8080, "scheme": "http"})
        self.assertFalse(success)
        self.assertIn("неверные параметры", message)
        connect.assert_not_called()

    def test_socks5_greeting_handles_a_fragmented_tcp_reply(self):
        class FragmentedConnection:
            def __init__(self):
                self.parts = [b"\x05", b"\x00"]
                self.sent = b""
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                pass
            def settimeout(self, _value):
                pass
            def sendall(self, value):
                self.sent += value
            def recv(self, _size):
                return self.parts.pop(0) if self.parts else b""

        connection = FragmentedConnection()
        proxy = {"host": "127.0.0.1", "port": 1080, "scheme": "socks5"}
        with patch("proxy_diagnostics.socket.create_connection", return_value=connection):
            success, message = diagnose_proxy(proxy)
        self.assertTrue(success)
        self.assertIn("SOCKS5", message)
        self.assertEqual(connection.sent, b"\x05\x01\x00")

    def test_connection_timeout_has_user_safe_message(self):
        with patch("proxy_diagnostics.socket.create_connection", side_effect=TimeoutError("synthetic endpoint detail")):
            success, message = diagnose_proxy({"host": "127.0.0.1", "port": 8080, "scheme": "http"})
        self.assertFalse(success)
        self.assertIn("TCP", message)
        self.assertNotIn("synthetic endpoint detail", message)


if __name__ == "__main__":
    unittest.main()
