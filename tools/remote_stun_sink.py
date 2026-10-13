"""Token-gated private-network STUN receipt counter for disposable QA.

Run in a separate network namespace (for example Ubuntu WSL). This only
counts UDP datagrams and STUN Binding requests; it never forwards traffic or
stores payloads, source addresses, or browsing data. Not a public STUN server.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import secrets
import socket
import threading
from urllib.parse import parse_qs, urlsplit


def is_binding_request(packet: bytes) -> bool:
    return len(packet) >= 20 and packet[:2] == b"\x00\x01" and packet[4:8] == b"\x21\x12\xa4\x42"


class Sink:
    def __init__(self, bind: str):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((bind, 0))
        self.socket.settimeout(0.2)
        self.port = self.socket.getsockname()[1]
        self.lock = threading.Lock()
        self.datagrams = 0
        self.binding_requests = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.receive, daemon=True)
        self.thread.start()

    def receive(self) -> None:
        while not self.stop.is_set():
            try:
                packet, _peer = self.socket.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            with self.lock:
                self.datagrams += 1
                if is_binding_request(packet):
                    self.binding_requests += 1

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return {"all_udp_datagrams": self.datagrams,
                    "stun_binding_requests": self.binding_requests}

    def reset(self) -> None:
        with self.lock:
            self.datagrams = 0
            self.binding_requests = 0

    def close(self) -> None:
        self.stop.set()
        self.socket.close()
        self.thread.join(timeout=2)


class Control(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, bind: str, sink: Sink, token: str, stop: threading.Event):
        super().__init__((bind, 0), Handler)
        self.sink = sink
        self.token = token
        self.stop = stop


class Handler(BaseHTTPRequestHandler):
    server: Control

    def log_message(self, *_args: object) -> None:
        pass

    def allowed(self, route: str) -> bool:
        parsed = urlsplit(self.path)
        return (not parsed.scheme and not parsed.netloc and parsed.path == route
                and parse_qs(parsed.query).get("token") == [self.server.token])

    def reply(self, status: int, value: dict) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self.allowed("/state"):
            self.reply(404, {"error": "not found"})
            return
        self.reply(200, self.server.sink.snapshot())

    def do_POST(self) -> None:
        if self.allowed("/reset"):
            self.server.sink.reset()
            self.reply(200, {"reset": True})
        elif self.allowed("/stop"):
            self.reply(200, {"stopping": True})
            self.server.stop.set()
        else:
            self.reply(404, {"error": "not found"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True, help="Private IPv4 address assigned to this QA network namespace")
    args = parser.parse_args()
    try:
        address = ipaddress.ip_address(args.bind)
        if address.version != 4 or not address.is_private or address.is_loopback:
            raise ValueError("Expected a non-loopback private IPv4 address")
    except ValueError as error:
        parser.error(str(error))
    sink = Sink(args.bind)
    stop = threading.Event()
    token = secrets.token_urlsafe(24)
    try:
        control = Control(args.bind, sink, token, stop)
        thread = threading.Thread(target=control.serve_forever, daemon=True)
        thread.start()
        print(json.dumps({"host": args.bind, "udp_port": sink.port,
                          "control_port": control.server_port, "token": token}), flush=True)
        stop.wait()
        control.shutdown()
        control.server_close()
        thread.join(timeout=2)
    finally:
        sink.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
