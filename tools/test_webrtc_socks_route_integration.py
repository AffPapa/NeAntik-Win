"""Synthetic, browser-free checks for the private SOCKS5 STUN route gate."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import unittest

from webrtc_udp_integration import RouteSocksServer, evaluate_socks_case


class Target(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


def connect_socks(port: int, host: str, target_port: int) -> tuple[socket.socket, bytes]:
    client = socket.create_connection(("127.0.0.1", port), timeout=3)
    client.settimeout(3)
    client.sendall(b"\x05\x01\x00")
    if client.recv(2) != b"\x05\x00":
        raise AssertionError("SOCKS5 no-auth handshake failed")
    host_bytes = host.encode("ascii")
    client.sendall(b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes +
                   target_port.to_bytes(2, "big"))
    return client, client.recv(10)


class RouteSocksTests(unittest.TestCase):
    def test_only_the_disposable_page_is_forwarded(self) -> None:
        page = ThreadingHTTPServer(("127.0.0.1", 0), Target)
        proxy = RouteSocksServer(page.server_port)
        threads = [threading.Thread(target=server.serve_forever, daemon=True)
                   for server in (page, proxy)]
        for worker in threads:
            worker.start()
        try:
            with self.subTest("allowlisted page"):
                client, reply = connect_socks(proxy.server_address[1], "127.0.0.1", page.server_port)
                with client:
                    self.assertEqual(reply[:2], b"\x05\x00")
                    client.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                    response = b""
                    while True:
                        chunk = client.recv(1024)
                        if not chunk:
                            break
                        response += chunk
                    self.assertTrue(response.endswith(b"\r\n\r\nok"))
            with self.subTest("synthetic route control"):
                client, reply = connect_socks(proxy.server_address[1],
                                              "neantik-route-control.invalid", 80)
                with client:
                    self.assertEqual(reply[:2], b"\x05\x02")
            with self.subTest("unrelated destination denied"):
                client, reply = connect_socks(proxy.server_address[1], "example.invalid", 443)
                with client:
                    self.assertEqual(reply[:2], b"\x05\x02")
            self.assertEqual(proxy.snapshot(), {"route_control_requests": 1,
                                                "proxied_page_requests": 1,
                                                "rejected_external_requests": 1})
        finally:
            for server in (proxy, page):
                server.shutdown()
                server.server_close()
            for worker in threads:
                worker.join(timeout=3)

    def test_socks_gate_requires_positive_and_route_controls(self) -> None:
        direct = {"stun_binding_requests": 2, "netlog": {"stun_destination_sends": 2}}
        proxy = {"proxy_bound": True, "proxy_scheme": "socks5",
                 "stun_binding_requests": 0, "all_udp_datagrams": 0,
                 "netlog": {"all_udp_sends": 0}, "route_control_requests": 1,
                 "proxied_page_requests": 2}
        self.assertEqual(evaluate_socks_case(direct, proxy), "passed")
        for key in ("stun_binding_requests", "all_udp_datagrams", "route_control_requests",
                    "proxied_page_requests"):
            broken = dict(proxy, **{key: 1 if key in ("stun_binding_requests", "all_udp_datagrams") else 0})
            self.assertEqual(evaluate_socks_case(direct, broken), "inconclusive")
        self.assertEqual(evaluate_socks_case({**direct, "stun_binding_requests": 0}, proxy),
                         "inconclusive")
        self.assertEqual(evaluate_socks_case(direct, {**proxy, "proxy_scheme": "http"}),
                         "inconclusive")


if __name__ == "__main__":
    unittest.main()
