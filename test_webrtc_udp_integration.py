"""Small unit checks for the self-hosted WebRTC UDP probe."""

import sys
import json
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from webrtc_udp_integration import is_stun_binding_request, netlog_udp_summary


class StunPacketTests(unittest.TestCase):
    def test_binding_request(self):
        packet = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + bytes(range(12))
        self.assertTrue(is_stun_binding_request(packet))

    def test_rejects_short_and_wrong_packets(self):
        packet = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + bytes(range(12))
        self.assertFalse(is_stun_binding_request(packet[:-1]))
        self.assertFalse(is_stun_binding_request(b"\x00\x02" + packet[2:]))
        self.assertFalse(is_stun_binding_request(packet[:4] + b"FAIL" + packet[8:]))

    def test_netlog_counts_attempts_without_exposing_destinations(self):
        fixture = {"constants": {"logEventTypes": {"UDP_BYTES_SENT": 99}},
                   "events": [{"type": 99, "params": {"address": "192.168.1.2:30000"}},
                              {"type": 99, "params": {"address": "1.1.1.1:53"}},
                              {"type": 3, "params": {"address": "192.168.1.2:30000"}}]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "netlog.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            self.assertEqual(netlog_udp_summary(path, "192.168.1.2", 30000),
                             {"all_udp_sends": 2, "stun_destination_sends": 1,
                              "other_udp_sends": 1})


if __name__ == "__main__":
    unittest.main()
