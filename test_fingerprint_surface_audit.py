"""Pure regression checks for the private loopback fingerprint audit."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from fingerprint_surface_audit import evaluate  # noqa: E402


def report():
    common = {"userAgent": "Chromium test", "platform": "Win32", "language": "en-US",
              "languages": ["en-US"], "hardwareConcurrency": 4, "deviceMemory": 8,
              "timezone": "Etc/UTC"}
    window = {**common, "screen": [1000, 800, 24], "devicePixelRatio": 1}
    return {"surfaces": {"main": window.copy(), "iframe": window.copy(),
                         "crossOriginFrame": window.copy(), "worker": common.copy(),
                         "sharedWorker": common.copy(), "serviceWorker": common.copy()},
            "http": {"userAgent": "Chromium test"},
            "client_hints": {"deviceMemory": "8"},
            "blocked_external_requests": 0}


class FingerprintAuditEvaluationTests(unittest.TestCase):
    def test_consistent_contexts_and_client_hint(self):
        self.assertTrue(all(evaluate([report()])[0].values()))

    def test_mismatched_worker_value_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["worker"]["hardwareConcurrency"] = 16
        self.assertFalse(evaluate([value])[0]["main_worker_common"])

    def test_mismatched_cross_origin_frame_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["crossOriginFrame"]["deviceMemory"] = 16
        self.assertFalse(evaluate([value])[0]["main_cross_origin_frame"])

    def test_mismatched_shared_worker_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["sharedWorker"]["hardwareConcurrency"] = 16
        self.assertFalse(evaluate([value])[0]["main_shared_worker_common"])

    def test_mismatched_service_worker_is_rejected(self):
        value = deepcopy(report())
        value["surfaces"]["serviceWorker"]["deviceMemory"] = 16
        self.assertFalse(evaluate([value])[0]["main_service_worker_common"])

    def test_mismatched_client_hint_is_rejected(self):
        value = report()
        value["client_hints"]["deviceMemory"] = "16"
        self.assertFalse(evaluate([value])[0]["device_memory_hint_parity"])

    def test_malformed_client_hint_is_rejected(self):
        value = report()
        value["client_hints"]["deviceMemory"] = "unparseable"
        self.assertFalse(evaluate([value])[0]["device_memory_hint_parity"])

    def test_unobserved_hint_fails_the_audit(self):
        value = report()
        value["client_hints"]["deviceMemory"] = None
        self.assertFalse(evaluate([value])[0]["device_memory_hint_parity"])

if __name__ == "__main__":
    unittest.main()
