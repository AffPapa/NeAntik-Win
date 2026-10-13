"""Bounded synthetic storage upgrade/rollback gate for two exact portable ZIPs.

Example:
  python tools/upgrade_rollback_integration.py --old-zip PUBLIC_0.8.5.zip \
    --candidate-zip CANDIDATE_0.8.6.zip --candidate-sha256 EXPECTED_SHA256 \
    --report PRIVATE_REPORT.json

Both inputs must be verified archives. This tests same-Windows-account storage
compatibility using the source commits embedded in those archives. It does not
test the packaged GUI, browser sessions, cross-account DPAPI, or in-place update.
The disposable old folder is never given to the candidate for mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

OLD_VERSION = "0.8.5-preview"
NEW_VERSION = "0.8.6-preview"
OLD_PUBLIC_SHA256 = "cc5d14702aa0facffbd88839e5b45645e871f3aab962c454bccf5895ab946dc4"
SOURCE_FILES = ("nevision_win.py", "profile_identity.py", "privacy_defaults.py", "release-version.json")

# This worker runs in an isolated subprocess so modules from the two source
# commits cannot cross-contaminate imports. It creates only synthetic data.
WORKER = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from nevision_win import AppPaths, SecretVault, Storage

action, root = sys.argv[2], Path(sys.argv[3])
storage = Storage(AppPaths(root))
fixture_value = "synthetic-neantik-upgrade-only"
if action == "seed":
    proxy_id = storage.save_proxy({"name":"Synthetic proxy", "scheme":"http",
        "host":"127.0.0.1", "port":8765, "username":"fixture", "password":fixture_value})
    profile_id = storage.save_profile({"name":"Synthetic upgrade", "group_name":"QA",
        "tags":"fixture", "notes":"old-snapshot", "proxy_id":proxy_id})
    storage.pin_browser_family(profile_id, "chromium")
    state = storage.profile_path(profile_id) / "Default" / "synthetic-state.txt"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("synthetic profile state", encoding="utf-8")

profiles = storage.list_profiles()
assert len(profiles) == 1, "exactly one synthetic profile required"
profile = storage.get_profile(profiles[0]["id"])
assert profile and profile["name"] == "Synthetic upgrade"
assert profile["group_name"] == "QA" and profile["tags"] == "fixture"
assert profile["browser_family"] == "chromium"
assert profile["fingerprint"] == {"schema":1,"mode":"ordinary"}
proxy = storage.get_proxy(profile["proxy_id"])
assert proxy and proxy["host"] == "127.0.0.1" and proxy["port"] == 8765
assert proxy["password_protected"] and fixture_value not in proxy["password_protected"]
assert SecretVault.decrypt(proxy["password_protected"]) == fixture_value
assert (storage.profile_path(profile["id"]) / "Default" / "synthetic-state.txt").read_text(encoding="utf-8") == "synthetic profile state"
if action == "upgrade":
    assert profile["notes"] == "old-snapshot"
    storage.save_profile({"name":profile["name"], "group_name":profile["group_name"],
        "tags":profile["tags"], "notes":"candidate-only", "proxy_id":profile["proxy_id"]}, profile["id"])
    assert storage.get_profile(profile["id"])["notes"] == "candidate-only"
else:
    assert profile["notes"] == "old-snapshot"
print(json.dumps({"status":"passed", "app_version":storage.get_setting("app_version"),
    "profile_count":len(profiles), "same_account_dpapi":True,
    "profile_state":True, "browser_family":True, "proxy_binding":True}))
'''


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def data_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted((root / "Data").rglob("*")):
        if item.is_file():
            digest.update(item.relative_to(root).as_posix().encode("utf-8"))
            digest.update(bytes.fromhex(file_hash(item)))
    return digest.hexdigest()


def inspect_archive(path: Path, expected_hash: str, expected_version: str) -> tuple[str, str]:
    if file_hash(path) != expected_hash.lower():
        raise ValueError(f"{expected_version}: archive SHA-256 mismatch")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not names:
            raise ValueError("Duplicate or empty archive members")
        roots = set()
        for item in archive.infolist():
            name = item.filename
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith(("/", "\\")) or "\\" in name or
                    any(part in ("", ".", "..") for part in parts) or
                    (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe archive member")
            roots.add(parts[0])
            if len(parts) > 1 and parts[1].lower() == "data":
                raise ValueError("Archive contains Data")
        expected_root = f"NeAntikWin-portable-v{expected_version}"
        if roots != {expected_root}:
            raise ValueError("Unexpected archive root")
        manifest = json.loads(archive.read(f"{expected_root}/release-manifest.json"))
        if manifest.get("version") != expected_version:
            raise ValueError("Manifest version mismatch")
        commit = manifest.get("source_commit")
        if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("Invalid source commit")
        return expected_root, commit


def git_source(repo: Path, commit: str, destination: Path) -> None:
    destination.mkdir()
    for name in SOURCE_FILES:
        result = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=repo,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        (destination / name).write_bytes(result.stdout)


def run_worker(source: Path, action: str, root: Path, expected_version: str) -> dict:
    process = subprocess.run([sys.executable, "-c", WORKER, str(source), action, str(root)],
                             cwd=source, capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise RuntimeError(f"{expected_version} {action}: synthetic storage worker failed (exit {process.returncode})")
    result = json.loads(process.stdout.strip())
    if result.get("status") != "passed" or result.get("app_version") != expected_version:
        raise RuntimeError(f"{expected_version} {action}: unexpected version or result")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-zip", type=Path, required=True, help="Previously downloaded public 0.8.5 ZIP")
    parser.add_argument("--candidate-zip", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    old_zip, new_zip = args.old_zip.resolve(strict=True), args.candidate_zip.resolve(strict=True)
    old_root, old_commit = inspect_archive(old_zip, OLD_PUBLIC_SHA256, OLD_VERSION)
    new_root, new_commit = inspect_archive(new_zip, args.candidate_sha256, NEW_VERSION)
    # The old source must belong to the tagged public release, not an arbitrary
    # coincidentally named archive. The embedded source commit is authoritative.
    tag = subprocess.check_output(["git", "rev-parse", "v0.8.5-preview^{commit}"], cwd=repo, text=True).strip()
    subprocess.run(["git", "merge-base", "--is-ancestor", old_commit, tag], cwd=repo, check=True)
    report = {"format":"neantik-upgrade-rollback-storage-v1", "status":"not_run",
              "old_zip_sha256":OLD_PUBLIC_SHA256, "candidate_zip_sha256":args.candidate_sha256.lower(),
              "old_source_commit":old_commit, "candidate_source_commit":new_commit,
              "coverage":"synthetic same-account storage/profile/proxy/DPAPI; no GUI or browser session"}
    with tempfile.TemporaryDirectory(prefix="neantik-upgrade-rollback-") as temporary:
        qa = Path(temporary)
        old_source, new_source = qa / "source-old", qa / "source-new"
        git_source(repo, old_commit, old_source)
        git_source(repo, new_commit, new_source)
        with zipfile.ZipFile(old_zip) as archive:
            archive.extractall(qa / "old")
        with zipfile.ZipFile(new_zip) as archive:
            archive.extractall(qa / "new")
        old_portable = qa / "old" / old_root
        new_portable = qa / "new" / new_root
        report["old_seed"] = run_worker(old_source, "seed", old_portable, OLD_VERSION)
        original_digest = data_digest(old_portable)
        shutil.copytree(old_portable / "Data", new_portable / "Data", dirs_exist_ok=False)
        if data_digest(new_portable) != original_digest:
            raise RuntimeError("Copied Data differs from the preserved old snapshot")
        report["candidate_upgrade"] = run_worker(new_source, "upgrade", new_portable, NEW_VERSION)
        if data_digest(old_portable) != original_digest:
            raise RuntimeError("Candidate changed the preserved old snapshot")
        report["old_rollback"] = run_worker(old_source, "check", old_portable, OLD_VERSION)
        report["status"] = "passed"
        report["preserved_old_snapshot"] = True
        report["candidate_copy_changed"] = data_digest(new_portable) != original_digest
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
