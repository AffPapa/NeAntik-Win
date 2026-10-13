"""Pure tests for redacted startup NetLog summaries."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from start_page_network_audit import evaluate_proxy_route, summarize_netlog  # noqa: E402


class StartPageNetlogTests(unittest.TestCase):
    def test_only_http_hosts_are_retained(self):
        report = summarize_netlog({
            "constants": {"logEventTypes": {"URL_REQUEST_START_JOB": 7,
                                              "TCP_CONNECT": 8, "UDP_BYTES_SENT": 9}},
            "events": [
                {"type": 7, "params": {"url": "https://Example.com/path?private=token"}},
                {"type": 7, "params": {"url": "http://example.com/other"}},
                {"type": 7, "params": {"url": "chrome://newtab"}},
                {"type": 8, "phase": 2, "params": {"remote_address": "127.0.0.1:8080"}},
                {"type": 9, "params": {"address": "127.0.0.1:3478"}},
            ],
        })
        self.assertEqual(report, {"http_request_count": 2,
                                  "host_counts": {"example.com": 2},
                                  "tcp_remote_hosts": {"127.0.0.1": 1},
                                  "udp_send_count": 1})

    def test_missing_event_metadata_fails(self):
        with self.assertRaises(ValueError):
            summarize_netlog({"events": []})

    def test_proxy_route_requires_positive_control_and_no_direct_sends(self):
        case = {"proxy_observed_hosts": {"example.test": 1},
                "tcp_remote_hosts": {"127.0.0.1": 1}, "udp_send_count": 0}
        self.assertTrue(all(evaluate_proxy_route(case).values()))
        case["tcp_remote_hosts"]["203.0.113.1"] = 1
        self.assertFalse(evaluate_proxy_route(case)["tcp_only_to_loopback_proxy"])
        case["udp_send_count"] = 1
        self.assertFalse(evaluate_proxy_route(case)["no_udp_sends_in_netlog"])
        case["proxy_observed_hosts"] = {}
        self.assertFalse(evaluate_proxy_route(case)["proxy_observed_requests"])


if __name__ == "__main__":
    unittest.main()
