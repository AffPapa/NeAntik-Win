"""Small unit checks for the self-hosted WebRTC UDP probe."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from webrtc_udp_integration import is_stun_binding_request


class StunPacketTests(unittest.TestCase):
    def test_binding_request(self):
        packet = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + bytes(range(12))
        self.assertTrue(is_stun_binding_request(packet))

    def test_rejects_short_and_wrong_packets(self):
        packet = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + bytes(range(12))
        self.assertFalse(is_stun_binding_request(packet[:-1]))
        self.assertFalse(is_stun_binding_request(b"\x00\x02" + packet[2:]))
        self.assertFalse(is_stun_binding_request(packet[:4] + b"FAIL" + packet[8:]))


if __name__ == "__main__":
    unittest.main()
