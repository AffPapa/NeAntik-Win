"""Synthetic checks for IPv6 loopback proxy fixtures; never launches Chromium."""

from __future__ import annotations

import http.client
import socket
import threading
import unittest

from nevision_win import bundled_proxy_privacy_arguments, proxy_endpoint
from proxy_integration import (Evidence, HTTPProxy, IPv6SocksServer, LocalHTTPServer,
                               LocalIPv6HTTPServer, SocksProxy, Target, TEST_HOST, case_plan,
                               receive_exact)


class ProxyIntegrationTests(unittest.TestCase):
    def test_case_plan_ipv6_proxy_endpoints_and_product_arguments(self) -> None:
        cases = case_plan(41001, 41002, 42001, 42002, 43001, 43002)
        self.assertEqual(len({case[0] for case in cases}), len(cases))
        by_name = {case[0]: case for case in cases}
        for name, scheme, port in (
            ("http_proxy_endpoint_v6", "http", 42001),
            ("socks5_proxy_endpoint_v6", "socks5", 42002),
            ("http_proxy_endpoint_v6_unavailable", "http", 43002),
            ("socks5_proxy_endpoint_v6_unavailable", "socks5", 43002),
        ):
            self.assertEqual(by_name[name], (name, scheme, "::1", port, TEST_HOST))
            proxy = {"scheme": scheme, "host": "::1", "port": port}
            self.assertEqual(proxy_endpoint(proxy), f"{scheme}://[::1]:{port}")
            flags = bundled_proxy_privacy_arguments(proxy)
            self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE ::1", flags)
            self.assertIn("--proxy-bypass-list=<-loopback>", flags)
            self.assertFalse(any("DIRECT" in flag.upper() for flag in flags))
        self.assertTrue(all(case[2] in (None, "127.0.0.1", "::1") for case in cases))
        self.assertTrue(all(case[4] in (TEST_HOST, "127.0.0.1", "::1") for case in cases))

    def test_ipv6_http_proxy_fixture_forwards_only_owned_target(self) -> None:
        evidence = Evidence()
        evidence.tokens.add("synthetic")
        target = LocalHTTPServer(("127.0.0.1", 0), Target)
        proxy = LocalIPv6HTTPServer(("::1", 0), HTTPProxy)
        target.evidence = proxy.evidence = evidence
        proxy.target_port = target.server_port
        proxy.ipv6_target_port = 0
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (target, proxy)]
        try:
            for thread in threads:
                thread.start()
            connection = http.client.HTTPConnection("::1", proxy.server_port, timeout=5)
            connection.request("GET", f"http://{TEST_HOST}:{target.server_port}/probe?token=synthetic")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            body = response.read().decode("utf-8")
            self.assertIn('&quot;route&quot;: &quot;http&quot;', body)
            connection.close()
            connection = http.client.HTTPConnection("::1", proxy.server_port, timeout=5)
            connection.request("GET", "http://outside.invalid:80/probe?token=synthetic")
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            connection.close()
            self.assertEqual(len(evidence.requests), 1)
            self.assertEqual(len(evidence.forwards), 1)
        finally:
            for server in (target, proxy):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=5)

    def test_ipv6_socks_proxy_fixture_forwards_only_owned_target(self) -> None:
        evidence = Evidence()
        evidence.tokens.add("synthetic")
        target = LocalHTTPServer(("127.0.0.1", 0), Target)
        proxy = IPv6SocksServer(("::1", 0), SocksProxy)
        target.evidence = proxy.evidence = evidence
        proxy.target_port = target.server_port
        proxy.ipv6_target_port = 0
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (target, proxy)]
        try:
            for thread in threads:
                thread.start()
            with socket.create_connection(("::1", proxy.server_address[1]), timeout=5) as connection:
                connection.settimeout(5)
                connection.sendall(b"\x05\x01\x00")
                self.assertEqual(receive_exact(connection, 2), b"\x05\x00")
                host = TEST_HOST.encode("ascii")
                connection.sendall(b"\x05\x01\x00\x03" + bytes([len(host)]) + host
                                   + target.server_port.to_bytes(2, "big"))
                self.assertEqual(receive_exact(connection, 2), b"\x05\x00")
                receive_exact(connection, 8)
                connection.sendall(b"GET /probe?token=synthetic HTTP/1.1\r\n"
                                   + f"Host: {TEST_HOST}:{target.server_port}\r\nConnection: close\r\n\r\n".encode())
                response = b""
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    response += chunk
            self.assertIn(b"200 OK", response)
            self.assertIn(b"&quot;route&quot;: &quot;socks5&quot;", response)
            self.assertEqual(len(evidence.requests), 1)
            self.assertEqual(len(evidence.forwards), 1)
            self.assertEqual(evidence.forwards[0]["address_type"], 3)
        finally:
            for server in (target, proxy):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
