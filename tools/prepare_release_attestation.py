"""Validate a public NeAntik release archive before a review attestation.

This deliberately does not claim that the archive was built by GitHub Actions.
The workflow verifies an already-published artifact and attests that review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


REPOSITORY = "AffPapa/NeAntik-Win"
PREDICATE_TYPE = "https://affpapa.org/attestations/neantik-release-review/v1"
SOURCE_FIELDS = ("source_commit", "source_state", "source_tree_sha256")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(data: bytes, label: str) -> dict[str, Any]:
    if len(data) > 8 * 1024 * 1024:
        raise ValueError(f"{label} is unexpectedly large")
    value = json.loads(data.decode("utf-8", errors="strict"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _read_archive_json(archive: zipfile.ZipFile, path: str, label: str) -> dict[str, Any]:
    entry = archive.getinfo(path)
    if entry.file_size > 8 * 1024 * 1024:
        raise ValueError(f"{label} is unexpectedly large")
    return _read_json(archive.read(entry), label)


def build_predicate(
    release: dict[str, Any],
    archive_path: Path,
    checksum_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?", tag):
        raise ValueError("Release tag must be a plain NeAntik version tag")
    if release.get("draft") is not False:
        raise ValueError("Only a published, non-draft GitHub Release can be reviewed")
    if release.get("repository") != REPOSITORY:
        raise ValueError("Release repository does not match the fixed NeAntik repository")
    expected_url = f"https://github.com/{REPOSITORY}/releases/tag/{tag}"
    if release.get("html_url") != expected_url:
        raise ValueError("Release URL does not match its tag and repository")

    tag_commit = release.get("tag_commit")
    if not isinstance(tag_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", tag_commit):
        raise ValueError("Resolved annotated tag must target a full Git commit SHA")
    version = tag[1:]
    archive_name = f"NeAntikWin-portable-v{version}.zip"
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Release assets list is missing")
    by_name: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            raise ValueError("Malformed release asset metadata")
        name = asset["name"]
        if name in by_name:
            raise ValueError(f"Duplicate GitHub Release asset: {name}")
        by_name[name] = asset
    expected_assets = {archive_name, f"{archive_name}.sha256", archive_name.removesuffix(".zip") + ".manifest.json"}
    if not expected_assets.issubset(by_name):
        raise ValueError("Release must contain the ZIP, SHA-256 sidecar, and manifest")

    paths_by_name = {
        archive_name: archive_path,
        f"{archive_name}.sha256": checksum_path,
        archive_name.removesuffix(".zip") + ".manifest.json": manifest_path,
    }
    actual_hashes: dict[str, str] = {}
    for name, path in paths_by_name.items():
        asset = by_name[name]
        if type(asset.get("size")) is not int or asset["size"] < 0:
            raise ValueError(f"GitHub Release asset has invalid size metadata: {name}")
        size = path.stat().st_size
        digest_value = _sha256(path)
        if asset.get("size") != size:
            raise ValueError(f"Downloaded asset size differs from GitHub Release metadata: {name}")
        if asset.get("digest") != f"sha256:{digest_value}":
            raise ValueError(f"Downloaded asset SHA-256 differs from GitHub Release metadata: {name}")
        actual_hashes[name] = digest_value

    archive_size = archive_path.stat().st_size
    digest = actual_hashes[archive_name]

    checksum_text = checksum_path.read_text(encoding="utf-8-sig").strip()
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^\r\n]+)", checksum_text)
    if not match or match.group(1).lower() != digest or Path(match.group(2)).name != archive_name:
        raise ValueError("Downloaded SHA-256 sidecar does not match the ZIP")

    if manifest_path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Published manifest is unexpectedly large")
    published_manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    published_archive = published_manifest.get("archive", {})
    if (
        published_manifest.get("version") != version
        or published_manifest.get("source_commit") != tag_commit
        or published_manifest.get("source_state") != "clean"
        or published_archive.get("filename") != archive_name
        or published_archive.get("sha256") != digest
        or published_archive.get("size_bytes") != archive_size
    ):
        raise ValueError("Published manifest disagrees with the release tag or downloaded ZIP")

    root = f"NeAntikWin-portable-v{version}"
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("ZIP contains duplicate entries")
        if not names or any(
            name.startswith("/")
            or "\\" in name
            or ":" in name
            or any(part in {"", ".", ".."} for part in PurePosixPath(name).parts)
            for name in names
        ):
            raise ValueError("ZIP contains an unsafe path")
        if any(name.split("/", 1)[0] != root for name in names):
            raise ValueError("ZIP must have one root folder matching the release version")
        internal_manifest = _read_archive_json(archive, f"{root}/release-manifest.json", "release-manifest.json")
        provenance = _read_archive_json(archive, f"{root}/build-provenance.json", "build-provenance.json")
        frozen_version = _read_archive_json(archive, f"{root}/release-version.json", "release-version.json")
    if frozen_version.get("version") != version or internal_manifest.get("version") != version:
        raise ValueError("Embedded release version differs from the GitHub tag")
    if published_manifest.get("source_commit") != tag_commit or internal_manifest.get("source_commit") != tag_commit or provenance.get("source_commit") != tag_commit:
        raise ValueError("source_commit does not match the resolved annotated tag commit")
    for field in SOURCE_FIELDS[1:]:
        if not (published_manifest.get(field) == internal_manifest.get(field) == provenance.get(field)):
            raise ValueError(f"Embedded {field} values disagree")
    if provenance.get("source_state") != "clean":
        raise ValueError("Embedded source provenance does not claim a clean source tree")
    if not isinstance(provenance.get("source_tree_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", provenance["source_tree_sha256"]):
        raise ValueError("Embedded source tree digest is invalid")

    return {
        "schemaVersion": "https://in-toto.io/Statement/v1",
        "reviewType": PREDICATE_TYPE,
        "repository": REPOSITORY,
        "release": {"tag": tag, "url": expected_url},
        "source": {"annotatedTagCommit": tag_commit, "embeddedCommitMatched": True},
        "archive": {"filename": archive_name, "sizeBytes": archive_size, "sha256": digest},
        "checks": [
            "GitHub Release is published and not a draft",
            "annotated Git tag resolves to the embedded source commit",
            "GitHub asset size and digest match the downloaded ZIP",
            "published checksum sidecar and release manifest match the ZIP",
            "embedded version and source provenance match the tag",
            "full portable archive verifier passed before attestation creation",
        ],
        "limitations": [
            "This attestation records a post-publication review of an existing ZIP.",
            "It does not prove that GitHub Actions built the ZIP from source.",
            "It does not prove a reproducible build or independent source-to-binary review.",
            "It is not an Authenticode signature and does not establish Windows publisher identity.",
            "The Git tag target was resolved, but this workflow does not verify a cryptographic tag signature.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--checksum", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--predicate-out", required=True, type=Path)
    args = parser.parse_args()
    release = json.loads(args.release_json.read_text(encoding="utf-8"))
    predicate = build_predicate(release, args.archive, args.checksum, args.manifest)
    args.predicate_out.write_text(json.dumps(predicate, indent=2) + "\n", encoding="utf-8")
    print(f"Release review preparation: PASS ({predicate['release']['tag']}, sha256:{predicate['archive']['sha256']})")


if __name__ == "__main__":
    main()
