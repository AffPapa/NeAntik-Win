"""Pure-data checks for the consented external HTTPS route audit."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from external_proxy_fail_closed_audit import (  # noqa: E402
    evaluate_external_route, evaluate_socks5_route, response_has_expected_json,
)


class ExternalRouteAuditTests(unittest.TestCase):
    def test_json_response_control(self):
        self.assertTrue(response_has_expected_json(
            b'<html><body><pre>{&quot;userAgent&quot;:&quot;Chromium&quot;}</pre></body></html>'))
        self.assertFalse(response_has_expected_json(b'<html><body>proxy error</body></html>'))

    def test_route_checks_reject_direct_fallback(self):
        direct = {"expected_json_rendered": True,
                  "host_counts": {"example.test": 1}}
        proxied = {"expected_json_rendered": False,
                   "host_counts": {"example.test": 1},
                   "proxy_observed_hosts": {"example.test": 1},
                   "tcp_remote_hosts": {"127.0.0.1": 1},
                   "udp_send_count": 0}
        self.assertTrue(all(evaluate_external_route("example.test", direct, proxied).values()))
        proxied["tcp_remote_hosts"]["203.0.113.1"] = 1
        self.assertFalse(evaluate_external_route("example.test", direct, proxied)["proxied_tcp_only_loopback"])
        proxied["expected_json_rendered"] = True
        self.assertFalse(evaluate_external_route("example.test", direct, proxied)["proxy_did_not_render_endpoint"])

    def test_socks_requires_domain_form_not_just_proxy_contact(self):
        direct = {"expected_json_rendered": True, "host_counts": {"example.test": 1}}
        proxied = {"expected_json_rendered": False,
                   "host_counts": {"example.test": 1},
                   "proxy_observed_hosts": {"example.test": 1},
                   "proxy_observed_address_types": {"3": 1},
                   "tcp_remote_hosts": {"127.0.0.1": 1}, "udp_send_count": 0}
        self.assertTrue(all(evaluate_socks5_route("example.test", direct, proxied).values()))
        proxied["proxy_observed_address_types"] = {"1": 1}
        self.assertFalse(evaluate_socks5_route("example.test", direct, proxied)[
            "socks5_proxy_received_domain_name"])


if __name__ == "__main__":
    unittest.main()
