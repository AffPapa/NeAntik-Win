"""Read-only official release/ref verification; no downloads of source/toolchains."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request


def request_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "NeAntik-native-core-pin-verifier"})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read(4 * 1024 * 1024).decode("utf-8")
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1]
    return json.loads(text)


def release_tuple(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    if len(parts) != 4 or not all(part.isdecimal() for part in parts):
        raise ValueError("Invalid official version")
    return tuple(int(part) for part in parts)


def select_stable_release(releases: list[dict]) -> dict:
    eligible = [item for item in releases if item.get("pinnable") is True and item.get("fraction", 0) >= 0.99]
    if not eligible:
        raise ValueError("No broadly available pinnable Windows stable release found")
    return max(eligible, key=lambda item: release_tuple(item["version"]))


def verify(spec: dict) -> dict:
    url = spec["chromium"]["version_history_url"]
    releases: list[dict] = []
    for _ in range(10):
        page = request_json(url)
        releases.extend(page.get("releases", []))
        if any(item.get("pinnable") is True and item.get("fraction", 0) >= 0.99 for item in releases):
            break
        token = page.get("nextPageToken")
        if not token:
            break
        base = spec["chromium"]["version_history_url"]
        url = base + "&pageToken=" + urllib.parse.quote(str(token), safe="")
    selected = select_stable_release(releases)
    ref_name = spec["chromium"]["tag"]
    refs = request_json("https://chromium.googlesource.com/chromium/src/+" + ref_name + "?format=JSON")
    commit = refs.get(ref_name, {}).get("value")
    depot_ref = request_json("https://chromium.googlesource.com/chromium/tools/depot_tools/+/" + spec["depot_tools"]["commit"] + "?format=JSON")
    depot_commit = depot_ref.get("commit")
    return {"selected_stable_version": selected["version"], "fraction": selected["fraction"],
            "pinnable": selected["pinnable"], "selected_since": selected.get("serving", {}).get("startTime"),
            "pinned_version": spec["chromium"]["version"], "pinned_commit": spec["chromium"]["commit"],
            "upstream_tag_commit": commit, "tag_matches": commit == spec["chromium"]["commit"],
            "current_stable_matches": selected["version"] == spec["chromium"]["version"],
            "depot_commit_matches": depot_commit == spec["depot_tools"]["commit"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=Path(__file__).with_name("buildspec.json"))
    args = parser.parse_args()
    try:
        result = verify(json.loads(args.spec.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all(result[key] for key in ("tag_matches", "current_stable_matches", "depot_commit_matches")) else 2
    except Exception as exc:
        print(f"Official pin verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
