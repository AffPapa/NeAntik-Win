"""Synthetic unit tests for the additional V4 Canvas context gate."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import build_opener, ProxyHandler, Request

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import native_canvas_v4_context_gate as gate  # noqa: E402


def sample(main_value: int, cross_value: int | None = None) -> dict:
    def value(number: int) -> dict:
        return {"pixelHash": number, "pngHash": number + 1000}

    return {"contexts": {name: value(cross_value if name == "crossSiteFrame" and cross_value is not None else main_value)
                         for name in gate.CONTEXTS}}


class V4ContextGateTests(unittest.TestCase):
    def test_complete_site_session_and_worker_matrix_passes_without_raw_values(self):
        summary = gate.summarize([sample(20), sample(40)])
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(len(summary["checks"]), 11)
        self.assertTrue(all(summary["checks"].values()))
        self.assertNotIn("pixelHash", json.dumps(summary))
        self.assertNotIn("pngHash", json.dumps(summary))
        self.assertNotIn("1020", json.dumps(summary))

    def test_stock_canvas_fails_restart(self):
        summary = gate.summarize([sample(20), sample(20)])
        self.assertEqual(summary["status"], "FAIL")
        self.assertFalse(summary["checks"]["main_changes_after_restart"])

    def test_cross_site_iframe_must_use_top_level_site_key(self):
        summary = gate.summarize([sample(20, 30), sample(40, 50)])
        self.assertEqual(summary["status"], "FAIL")
        self.assertFalse(summary["checks"]["crossSiteFrame_matches_main"])

    def test_stable_worker_exposes_session_policy_bypass(self):
        first, second = sample(20), sample(40)
        second["contexts"]["dedicatedWorker"] = first["contexts"]["dedicatedWorker"]
        summary = gate.summarize([first, second])
        self.assertEqual(summary["status"], "FAIL")
        self.assertFalse(summary["checks"]["dedicatedWorker_changes_after_restart"])
        self.assertFalse(summary["checks"]["dedicatedWorker_matches_main"])

    def test_shared_or_service_worker_unavailable_is_not_run_never_pass(self):
        for name in ("sharedWorker", "serviceWorker"):
            with self.subTest(context=name):
                sessions = [sample(20), sample(40)]
                for session in sessions:
                    session["contexts"][name] = {"unavailable": True}
                summary = gate.summarize(sessions)
                self.assertEqual(summary["status"], "INCONCLUSIVE")
                self.assertEqual(summary["context_status"][name], "NOT RUN")
                self.assertNotIn(f"{name}_matches_main", summary["checks"])

    def test_missing_or_error_context_is_inconclusive(self):
        sessions = [sample(20), sample(40)]
        sessions[0]["contexts"].pop("serviceWorker")
        with self.assertRaisesRegex(gate.Inconclusive, "context_matrix_incomplete"):
            gate.summarize(sessions)
        sessions = [sample(20), sample(40)]
        sessions[0]["contexts"]["serviceWorker"] = {"error": True}
        with self.assertRaisesRegex(gate.Inconclusive, "context_script_error"):
            gate.summarize(sessions)

    def test_boolean_hash_is_not_a_valid_measurement(self):
        sessions = [sample(20), sample(40)]
        sessions[0]["contexts"]["main"]["pixelHash"] = True
        with self.assertRaisesRegex(gate.Inconclusive, "context_surface_missing"):
            gate.summarize(sessions)

    def test_restarts_reuse_only_one_disposable_profile(self):
        visits = []

        def fake_session(_chrome, profile, root):
            visits.append((profile, root))
            return [sample(20), sample(40)][len(visits) - 1]

        with patch.object(gate, "_one_session", side_effect=fake_session):
            result = gate.measure(Path("synthetic-chrome.exe"))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(visits), 2)
        self.assertEqual(visits[0][0], visits[1][0])
        self.assertTrue(visits[0][0].name.startswith("synthetic"))

    def test_loopback_fixture_rejects_wrong_host_and_never_forwards(self):
        token = "synthetic_token"
        config = {"token": token, "parentOrigin": "http://127.0.0.1"}
        server = gate.ContextServer("127.0.0.1", token, "main", config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = build_opener(ProxyHandler({}))
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with opener.open(f"{url}/main?token={token}", timeout=5) as response:
                page = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertIn("crossSiteFrame", page)
                self.assertIn("serviceWorker", page)
            with opener.open(f"{url}/canvas-worker.js?token={token}", timeout=5) as response:
                worker = response.read().decode("utf-8")
                self.assertIn("ServiceWorkerGlobalScope", worker)
                self.assertIn("SharedWorkerGlobalScope", worker)
            with self.assertRaises(Exception):
                opener.open(Request(f"{url}/main?token={token}",
                                    headers={"Host": "external.invalid"}), timeout=5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_cli_inconclusive_output_has_no_raw_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chrome = root / "chrome.exe"
            chrome.write_bytes(b"synthetic browser")
            (root / "chrome.dll").write_bytes(b"synthetic core")
            output = root / "report.json"
            with patch.object(sys, "argv", ["gate", "--chrome", str(chrome),
                                            "--output", str(output)]), \
                    patch.object(gate, "measure", return_value=gate.summarize([
                        sample(20), sample(20)])), redirect_stdout(StringIO()):
                status = gate.main()
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(status, 2)
            self.assertEqual(report["status"], "FAIL")
            self.assertNotIn("pixelHash", json.dumps(report))
            self.assertNotIn("pngHash", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
