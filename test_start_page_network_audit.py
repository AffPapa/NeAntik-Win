"""Pure tests for redacted startup NetLog summaries."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from start_page_network_audit import summarize_netlog  # noqa: E402


class StartPageNetlogTests(unittest.TestCase):
    def test_only_http_hosts_are_retained(self):
        report = summarize_netlog({
            "constants": {"logEventTypes": {"URL_REQUEST_START_JOB": 7}},
            "events": [
                {"type": 7, "params": {"url": "https://Example.com/path?private=token"}},
                {"type": 7, "params": {"url": "http://example.com/other"}},
                {"type": 7, "params": {"url": "chrome://newtab"}},
                {"type": 8, "params": {"url": "https://ignored.test/"}},
            ],
        })
        self.assertEqual(report, {"http_request_count": 2,
                                  "host_counts": {"example.com": 2}})

    def test_missing_event_metadata_fails(self):
        with self.assertRaises(ValueError):
            summarize_netlog({"events": []})


if __name__ == "__main__":
    unittest.main()
