"""Pure regression checks for the disposable Canvas-switch comparison."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from canvas_readback_policy_audit import evaluate, evaluate_v4_smoke  # noqa: E402


CONTROL = {"outcomes": {"canvas2dPixels": "allowed", "canvas2dDataUrl": "allowed",
                        "workerCanvas2dPixels": "allowed", "webglReadPixels": "allowed"}}
BLOCKED = {"outcomes": {"canvas2dPixels": "SecurityError", "canvas2dDataUrl": "SecurityError",
                        "workerCanvas2dPixels": "SecurityError", "webglReadPixels": "SecurityError"}}


class CanvasPolicyEvaluationTests(unittest.TestCase):
    def test_complete_protection_requires_positive_control(self):
        self.assertTrue(all(evaluate(CONTROL, BLOCKED).values()))

    def test_webgl_hang_is_not_a_privacy_pass(self):
        blocked = {"timed_out": True, "outcomes": {},
                   "phases": ["canvas2d:SecurityError:SecurityError", "worker:SecurityError",
                              "webgl-start", "webgl-created"]}
        checks = evaluate(CONTROL, blocked)
        self.assertTrue(checks["switch_blocks_canvas2d"])
        self.assertFalse(checks["switch_blocks_webgl_without_hang"])

    def test_missing_control_cannot_pass(self):
        checks = evaluate({"outcomes": {}}, BLOCKED)
        self.assertFalse(checks["control_canvas2d_readable"])
        self.assertFalse(checks["control_webgl_readable"])

    def test_v4_smoke_all_readbacks_available(self):
        case = {**CONTROL, "rejected_external_requests": 0}
        self.assertTrue(all(evaluate_v4_smoke(case).values()))

    def test_v4_smoke_does_not_count_webgl_unavailable_as_pass(self):
        case = {"outcomes": {**CONTROL["outcomes"], "webglReadPixels": "unavailable"},
                "rejected_external_requests": 0}
        self.assertFalse(evaluate_v4_smoke(case)["webgl_readpixels_readable"])

    def test_v4_smoke_timeout_or_missing_worker_is_not_pass(self):
        case = {"timed_out": True, "outcomes": {"canvas2dPixels": "allowed",
                                                 "canvas2dDataUrl": "allowed"},
                "rejected_external_requests": 0}
        checks = evaluate_v4_smoke(case)
        self.assertFalse(checks["completed_without_timeout"])
        self.assertFalse(checks["canvas2d_dedicated_worker_readable"])


if __name__ == "__main__":
    unittest.main()
