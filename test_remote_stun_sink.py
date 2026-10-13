"""Pure protocol checks for the private-network QA STUN receiver."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from remote_stun_sink import is_binding_request  # noqa: E402
from wsl_stun_route_audit import RemoteSink  # noqa: E402


class StunReceiverTests(unittest.TestCase):
    def test_binding_request_magic_and_type_required(self) -> None:
        packet = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + b"x" * 12
        self.assertTrue(is_binding_request(packet))
        self.assertFalse(is_binding_request(packet[:19]))
        self.assertFalse(is_binding_request(b"\x01\x01" + packet[2:]))
        self.assertFalse(is_binding_request(packet[:4] + b"\x00\x00\x00\x00" + packet[8:]))

    def test_remote_handshake_rejects_bad_ports_or_token(self) -> None:
        with self.assertRaises(RuntimeError):
            RemoteSink({"host": "172.31.50.56", "udp_port": 0,
                        "control_port": 40000, "token": "x" * 30})
        with self.assertRaises(RuntimeError):
            RemoteSink({"host": "172.31.50.56", "udp_port": 40000,
                        "control_port": 40001, "token": "short"})


if __name__ == "__main__":
    unittest.main()
