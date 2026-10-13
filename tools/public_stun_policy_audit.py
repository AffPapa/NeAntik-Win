"""Bounded external STUN control for the bundled Chromium proxy policy.

Uses Cloudflare's documented public STUN endpoint with disposable profiles and
a loopback-only page. Cloudflare sees the test host's network IP. No site login,
browser history, raw candidate address or NetLog leaves the private test run.
No server-side receipt, DNS, IPv6 or TURN guarantee follows from a pass.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from native_persona_context_audit import prepare_disposable_engine
from webrtc_udp_integration import run_case


STUN_HOST = "stun.cloudflare.com"
STUN_PORT = 3478


class PublicStunEndpoint:
    """No server-side counters are available from a third-party STUN service."""

    port = STUN_PORT

    def reset(self) -> None:
        pass

    def snapshot(self) -> dict[str, None]:
        return {"stun_binding_requests": None, "all_udp_datagrams": None}


def classify(direct: dict, proxy: dict) -> dict:
    def types(case: dict) -> list[str]:
        value = case.get("candidate_types")
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("ICE candidate type measurement missing")
        return sorted(set(value))

    direct_types, proxy_types = types(direct), types(proxy)
    direct_udp = direct.get("netlog", {}).get("all_udp_sends")
    proxy_udp = proxy.get("netlog", {}).get("all_udp_sends")
    if (type(direct_udp) is not int or direct_udp < 0 or
            type(proxy_udp) is not int or proxy_udp < 0):
        raise ValueError("NetLog UDP counters missing")
    checks = {
        "direct_external_stun_response_observed": "srflx" in direct_types and direct_udp > 0,
        "proxy_no_ice_candidates_observed": not proxy_types,
        "proxy_no_udp_sends_observed": proxy_udp == 0,
    }
    if not checks["proxy_no_ice_candidates_observed"] or not checks["proxy_no_udp_sends_observed"]:
        status = "FAIL"
    elif checks["direct_external_stun_response_observed"]:
        status = "PASS"
    else:
        status = "INCONCLUSIVE"
    return {"status": status, "checks": checks,
            "direct_candidate_types": direct_types, "proxy_candidate_types": proxy_types,
            "direct_udp_sends": direct_udp, "proxy_udp_sends": proxy_udp}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chrome = args.chrome.resolve()
    if (os.name != "nt" or chrome.name.lower() != "chrome.exe" or
            not chrome.is_file() or not chrome.with_name("chrome.dll").is_file()):
        parser.error("An existing Windows chrome.exe and adjacent chrome.dll are required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("Output must be a new path in an existing directory")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "one Windows host, disposable direct/proxy profiles, external STUN without server logs; not a DNS/IPv6/TURN or anonymity certificate",
              "external_stun": f"{STUN_HOST}:{STUN_PORT}",
              "chrome_exe_sha256": sha256(chrome),
              "chrome_dll_sha256": sha256(chrome.with_name("chrome.dll")),
              "status": "INCONCLUSIVE"}
    try:
        with tempfile.TemporaryDirectory(prefix="neantik-public-stun-engine-") as engine_dir:
            disposable_chrome = prepare_disposable_engine(chrome, Path(engine_dir))
            with tempfile.TemporaryDirectory(prefix="neantik-public-stun-qa-") as test_dir:
                root = Path(test_dir)
                endpoint = PublicStunEndpoint()
                direct = run_case(disposable_chrome, root, False, STUN_HOST,
                                  force_default_policy=True, remote_sink=endpoint)
                proxy = run_case(disposable_chrome, root, True, STUN_HOST,
                                 remote_sink=endpoint)
        report.update(classify(direct, proxy))
    except Exception as error:
        # Browser exceptions may embed URLs or addresses; retain only the class.
        report["reason_code"] = type(error).__name__
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report.get("checks"),
                      "report": str(args.output), "reason_code": report.get("reason_code")},
                     ensure_ascii=False))
    return {"PASS": 0, "FAIL": 2}.get(report["status"], 3)


if __name__ == "__main__":
    raise SystemExit(main())
