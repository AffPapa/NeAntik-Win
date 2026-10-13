"""Small unit checks for the self-hosted WebRTC UDP probe."""

import sys
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from webrtc_udp_integration import (ProbeHandler, evaluate_cases,
                                    is_stun_binding_request, netlog_udp_summary,
                                    run_case)


class StunPacketTests(unittest.TestCase):
    def test_route_control_cannot_run_without_proxy(self):
        with self.assertRaises(ValueError):
            run_case(Path("missing-chrome.exe"), Path("unused"), False,
                     "127.0.0.1", verify_proxy_route=True)

    def test_route_control_counts_only_reserved_probe_host(self):
        handler = object.__new__(ProbeHandler)
        handler.server = SimpleNamespace(server_port=40000, token="synthetic",
                                         rejected_external_requests=0,
                                         route_control_requests=0)
        handler.path = "http://neantik-route-control.invalid/"
        self.assertIsNone(handler.route())
        self.assertEqual(handler.server.route_control_requests, 1)
        handler.path = "http://unrelated.invalid/"
        self.assertIsNone(handler.route())
        self.assertEqual(handler.server.route_control_requests, 1)

    def test_diagnostic_sandbox_disable_can_never_be_a_privacy_pass(self):
        direct = {"stun_binding_requests": 5, "netlog": {"stun_destination_sends": 5}}
        proxy = {"stun_binding_requests": 0, "netlog": {"all_udp_sends": 0}}
        self.assertEqual(evaluate_cases(direct, proxy, False), "passed")
        self.assertEqual(evaluate_cases(direct, proxy, True), "diagnostic_control_only")
        proxy["netlog"]["all_udp_sends"] = 1
        self.assertEqual(evaluate_cases(direct, proxy, True), "inconclusive")

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
