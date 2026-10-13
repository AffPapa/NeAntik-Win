"""Pure assertions for the disposable HTTPS-proxy 407 failure control."""

from pathlib import Path
import unittest

from https_proxy_integration import case_arguments, evaluate_case


class HTTPSProxyAuthFailureTests(unittest.TestCase):
    def test_auth_route_keeps_fixed_https_proxy_without_direct_fallback(self) -> None:
        arguments = case_arguments(
            Path("chrome.exe"), Path("synthetic-profile"),
            "https://127.0.0.1:44004/probe/synthetic",
            "https", 44003, "synthetic-public-key-pin")
        self.assertIn("--proxy-server=https://127.0.0.1:44003", arguments)
        self.assertIn("--proxy-bypass-list=<-loopback>", arguments)
        self.assertIn("--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", arguments)
        self.assertFalse(any("direct://" in argument for argument in arguments))
        self.assertFalse(any("user:pass" in argument for argument in arguments))

    def test_407_requires_challenge_error_zero_target_and_no_other_proxy(self) -> None:
        failed = {"exit_code": 0, "owned_processes_after_exit": 0,
                  "page_loaded": False, "net_errors": ["ERR_PROXY_AUTH_REQUESTED"]}
        self.assertEqual(evaluate_case("auth_required", failed, 0, 0, 0, 1)["status"], "PASS")
        self.assertEqual(evaluate_case("auth_required", failed, 1, 0, 0, 1)["status"], "FAIL")
        self.assertEqual(evaluate_case("auth_required", failed, 0, 1, 0, 1)["status"], "FAIL")
        self.assertEqual(evaluate_case("auth_required", failed, 0, 0, 1, 1)["status"], "FAIL")
        self.assertEqual(evaluate_case("auth_required", failed, 0, 0, 0, 0)["status"], "FAIL")
        failed["net_errors"] = []
        self.assertEqual(evaluate_case("auth_required", failed, 0, 0, 0, 1)["status"], "FAIL")
        failed["net_errors"] = ["ERR_INVALID_AUTH_CREDENTIALS"]
        self.assertEqual(evaluate_case("auth_required", failed, 0, 0, 0, 1)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
