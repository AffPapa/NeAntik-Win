"""Pure checks for the isolated HTTPS proxy route harness."""

from pathlib import Path
import unittest

from https_proxy_integration import case_arguments, evaluate_case


class HTTPSProxyIntegrationTests(unittest.TestCase):
    def test_unknown_case_cannot_silently_pass_as_negative(self) -> None:
        result = {"exit_code": 0, "owned_processes_after_exit": 0,
                  "page_loaded": False, "net_errors": []}
        with self.assertRaises(ValueError):
            evaluate_case("misspelled_negative", result, 0, 0)

    def test_https_proxy_arguments_are_fixed_and_no_direct_fallback(self) -> None:
        args = case_arguments(Path("chrome.exe"), Path("profile"),
                              "https://neantik-https-proxy-qa.invalid/probe/example",
                              "https", 44001, "synthetic-public-key-pin")
        self.assertIn("--proxy-server=https://127.0.0.1:44001", args)
        self.assertIn("--proxy-bypass-list=<-loopback>", args)
        self.assertIn("--disable-quic", args)
        self.assertIn("--ignore-certificate-errors-spki-list=synthetic-public-key-pin", args)
        self.assertNotIn("--ignore-certificate-errors", args)
        self.assertNotIn("--no-sandbox", args)
        self.assertFalse(any("direct://" in arg for arg in args))

    def test_missing_pin_is_not_global_certificate_bypass(self) -> None:
        args = case_arguments(Path("chrome.exe"), Path("profile"), "https://example.invalid/",
                              "https", 44001, None)
        self.assertFalse(any("ignore-certificate" in arg for arg in args))

    def test_ipv6_https_proxy_endpoint_uses_product_bracketing_and_strict_route(self) -> None:
        args = case_arguments(Path("chrome.exe"), Path("profile"),
                              "https://neantik-https-proxy-qa.invalid/probe/example",
                              "https", 44002, "synthetic-public-key-pin", "::1")
        self.assertIn("--proxy-server=https://[::1]:44002", args)
        self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE ::1", args)
        self.assertIn("--proxy-bypass-list=<-loopback>", args)
        self.assertFalse(any("direct://" in arg for arg in args))

    def test_positive_requires_target_and_connect(self) -> None:
        result = {"exit_code": 0, "owned_processes_after_exit": 0,
                  "page_loaded": True, "net_errors": []}
        self.assertEqual(evaluate_case("tls_proxy_connect", result, 1, 1)["status"], "PASS")
        self.assertEqual(evaluate_case("tls_proxy_connect", result, 1, 0)["status"], "FAIL")
        self.assertEqual(evaluate_case("tls_proxy_connect_v6", result, 1, 1)["status"], "PASS")
        self.assertEqual(evaluate_case("tls_proxy_connect_v6", result, 1, 0)["status"], "FAIL")
        self.assertEqual(evaluate_case("tls_proxy_connect_v6", result, 1, 1, 1)["status"], "FAIL")

    def test_failed_certificate_requires_error_and_zero_target(self) -> None:
        result = {"exit_code": 0, "owned_processes_after_exit": 0,
                  "page_loaded": False, "net_errors": ["ERR_PROXY_CERTIFICATE_INVALID"]}
        self.assertEqual(evaluate_case("cert_untrusted", result, 0, 0)["status"], "PASS")
        self.assertEqual(evaluate_case("cert_untrusted", result, 1, 0)["status"], "FAIL")
        result["net_errors"] = []
        self.assertEqual(evaluate_case("cert_untrusted", result, 0, 0)["status"], "FAIL")
        result["net_errors"] = ["ERR_PROXY_CERTIFICATE_INVALID"]
        self.assertEqual(evaluate_case("cert_untrusted_v6", result, 0, 0)["status"], "PASS")
        self.assertEqual(evaluate_case("cert_untrusted_v6", result, 0, 0, 1)["status"], "FAIL")

    def test_dead_proxy_requires_specific_error_and_zero_target(self) -> None:
        result = {"exit_code": 0, "owned_processes_after_exit": 0,
                  "page_loaded": False, "net_errors": ["ERR_PROXY_CONNECTION_FAILED"]}
        self.assertEqual(evaluate_case("dead_proxy_port", result, 0, 0)["status"], "PASS")
        self.assertEqual(evaluate_case("dead_proxy_port", result, 1, 0)["status"], "FAIL")
        self.assertEqual(evaluate_case("dead_proxy_port_v6", result, 0, 0)["status"], "PASS")
        self.assertEqual(evaluate_case("dead_proxy_port_v6", result, 1, 0)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
