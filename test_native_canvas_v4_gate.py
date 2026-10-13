"""Synthetic, side-effect-free regression tests for the V4 local Canvas gate."""

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
from urllib.request import build_opener, ProxyHandler

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import native_canvas_v4_gate as gate  # noqa: E402
from native_canvas_audit import ProbeServer  # noqa: E402


def result(value: int) -> dict:
    return {"pixelHash": value, "pngHash": value + 100000,
            **{name: True for name in gate.REQUIRED}}


def complete_matrix() -> dict:
    return {(profile, session, site): result(
        1 + profile * 100 + session * 10 + site_index)
        for profile in range(gate.PROFILE_COUNT)
        for session in range(gate.SESSION_COUNT)
        for site_index, site in enumerate(gate.SITES)}


class V4CanvasGateTests(unittest.TestCase):
    def test_exact_saved_profile_restart_site_matrix_passes_locally(self):
        summary = gate.summarize_matrix(complete_matrix())
        self.assertEqual(summary["cases_measured"], 12)
        self.assertEqual(summary["restarts_per_profile"], 2)
        self.assertEqual(summary["local_gate"], "PASS")
        self.assertNotIn("pixelHash", json.dumps(summary))
        self.assertNotIn("pngHash", json.dumps(summary))

    def test_both_loopback_hosts_serve_identical_canvas_scene(self):
        servers = [ProbeServer("synthetic_token_a"), ProbeServer("synthetic_token_b")]
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
        try:
            for thread in threads:
                thread.start()
            opener = build_opener(ProxyHandler({}))
            pages = []
            for site, server in zip(gate.SITES, servers):
                url = f"http://{site}:{server.server_port}/case?token={server.token}"
                with opener.open(url, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    pages.append(response.read().decode("utf-8").replace(server.token, "TOKEN"))
            self.assertEqual(pages[0], pages[1])
            self.assertIn("getImageData", pages[0])
            self.assertIn("toDataURL", pages[0])
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=5)

    def test_v3_stable_per_profile_identifier_is_blocked(self):
        matrix = complete_matrix()
        for profile in range(gate.PROFILE_COUNT):
            for session in range(gate.SESSION_COUNT):
                for site in gate.SITES:
                    matrix[(profile, session, site)] = result(profile + 1)
        summary = gate.summarize_matrix(matrix)
        self.assertEqual(summary["local_gate"], "FAIL")
        self.assertFalse(summary["checks"]["same_session_sites_differ_on_both_surfaces"])
        self.assertFalse(summary["checks"]["saved_profile_changes_on_each_restart_on_both_surfaces"])
        self.assertNotIn("pixelHash", json.dumps(summary))

    def test_one_stable_surface_is_enough_to_fail(self):
        matrix = complete_matrix()
        for profile in range(gate.PROFILE_COUNT):
            for session in range(gate.SESSION_COUNT):
                matrix[(profile, session, "localhost")]["pngHash"] = (
                    matrix[(profile, session, "127.0.0.1")]["pngHash"])
        self.assertEqual(gate.summarize_matrix(matrix)["local_gate"], "FAIL")

    def test_missing_case_is_inconclusive_not_pass(self):
        matrix = complete_matrix()
        matrix.pop((0, 2, "localhost"))
        with self.assertRaisesRegex(gate.Inconclusive, "incomplete_profile_session_site_matrix"):
            gate.summarize_matrix(matrix)

    def test_failed_canvas_invariant_is_observed_failure(self):
        matrix = complete_matrix()
        matrix[(0, 0, "localhost")][gate.REQUIRED[0]] = False
        with self.assertRaisesRegex(gate.ObservedFailure, "canvas_invariant"):
            gate.summarize_matrix(matrix)

    def test_non_integer_or_page_error_is_inconclusive(self):
        for bad in (True, "fingerprint", None):
            with self.subTest(value=bad):
                probe = result(42)
                probe["pixelHash"] = bad
                with self.assertRaises(gate.Inconclusive):
                    gate.validate_result(probe)
        with self.assertRaisesRegex(gate.Inconclusive, "probe_script_error"):
            gate.validate_result({"error": "synthetic private URL"})

    def test_measure_reuses_each_profile_for_three_sessions(self):
        visits: list[tuple[str, int]] = []

        def fake_session(_chrome, profile, _root, seed):
            visits.append((str(profile), seed))
            profile_id = 0 if profile.name.endswith("-0") else 1
            session = sum(entry[0] == str(profile) for entry in visits) - 1
            return ({site: result(1 + profile_id * 100 + session * 10 + site_index)
                     for site_index, site in enumerate(gate.SITES)}, 0)

        with patch.object(gate, "_one_session", side_effect=fake_session):
            summary = gate.measure(Path("synthetic-chrome.exe"))
        self.assertEqual(summary["local_gate"], "PASS")
        self.assertEqual(len(visits), 6)
        self.assertEqual(len({path for path, _ in visits}), 2)
        self.assertEqual(len({seed for _, seed in visits}), 2)
        self.assertEqual([seed for _, seed in visits[:3]], [visits[0][1]] * 3)
        self.assertEqual([seed for _, seed in visits[3:]], [visits[3][1]] * 3)

    def test_cli_incomplete_probe_is_nonzero_and_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chrome = root / "chrome.exe"
            chrome.write_bytes(b"synthetic fixture")
            (root / "chrome.dll").write_bytes(b"synthetic core")
            output = root / "audit.json"
            arguments = ["gate", "--chrome", str(chrome), "--output", str(output)]
            with patch.object(sys, "argv", arguments), \
                    patch.object(gate, "measure", side_effect=gate.Inconclusive("probe_script_error")), \
                    redirect_stdout(StringIO()):
                status = gate.main()
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(status, 3)
            self.assertEqual(report["status"], "INCONCLUSIVE")
            self.assertEqual(report["reason_code"], "probe_script_error")
            self.assertNotIn("pixelHash", json.dumps(report))

    def test_cli_observed_invariant_failure_is_fail_not_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chrome = root / "chrome.exe"
            chrome.write_bytes(b"synthetic fixture")
            (root / "chrome.dll").write_bytes(b"synthetic core")
            output = root / "audit.json"
            arguments = ["gate", "--chrome", str(chrome), "--output", str(output)]
            with patch.object(sys, "argv", arguments), \
                    patch.object(gate, "measure", side_effect=gate.ObservedFailure("canvas_invariant_failed")), \
                    redirect_stdout(StringIO()):
                status = gate.main()
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(status, 2)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["reason_code"], "canvas_invariant_failed")


if __name__ == "__main__":
    unittest.main()
