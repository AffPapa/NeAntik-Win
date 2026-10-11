"""Package an already compiled own core from GN runtime dependencies; no downloads.

Default is a read-only plan. Failed staging directories are retained, never
recursively deleted. Runtime proof and release QA are separate requirements.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
import current_core as core


def safe_relative(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("Runtime dependency is not a string")
    if raw.startswith("./"):
        raw = raw[2:]
    parts = raw.split("/")
    if not raw or PurePosixPath(raw).is_absolute() or any(part in ("", ".", "..") or part.endswith((".", " ")) or re.search(r'[\\:<>"|?*\x00-\x1f]', part) or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))} for part in parts):
        raise ValueError("Unsafe GN runtime dependency")
    return raw


def regular_file(root: Path, raw: str) -> Path:
    target = root.joinpath(*safe_relative(raw).split("/"))
    cursor = target
    while cursor != root:
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError("Runtime dependency traverses a link/junction")
        cursor = cursor.parent
    if root.resolve() not in target.resolve().parents or not target.is_file():
        raise ValueError(f"Required runtime file missing: {raw}")
    return target


def runtime_inventory(output: Path, document: dict) -> dict[str, Path]:
    entries = document.get("//chrome:chrome", {}).get("runtime_deps")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Expected exact GN //chrome:chrome runtime_deps JSON")
    files, folded = {}, {}
    for raw in entries:
        relative = safe_relative(raw)
        # PDBs are debugging symbols, not browser runtime. GN lists them even
        # when symbol_level=0; every other declared dependency must exist.
        if relative.lower().endswith(".pdb"):
            continue
        previous = folded.get(relative.casefold())
        if previous is not None and previous != relative:
            raise ValueError("Case-colliding runtime dependencies")
        folded[relative.casefold()] = relative
        files[relative] = regular_file(output, relative)
    if not {"chrome.exe", "chrome.dll", "chrome_elf.dll", "resources.pak", "locales/en-US.pak"} <= files.keys():
        raise ValueError("Incomplete Chromium runtime file set")
    return files


def verify_source(source: Path, spec: dict) -> dict:
    module_spec = importlib.util.spec_from_file_location("native_package_gate", Path(__file__).with_name("verify-patch-series.py"))
    gate = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(gate)
    return gate.verify(source, REPOSITORY, spec)


def validate_dependency_receipt(receipt: dict) -> None:
    if not isinstance(receipt, dict) or set(receipt) - {"format", "schema", "source_commit", "resolved_dependencies"} or receipt.get("source_commit") != core.SOURCE_COMMIT:
        raise ValueError("Dependency receipt has unsupported or unpinned metadata")
    dependencies = receipt.get("resolved_dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("resolved_dependencies must be a nonempty list of public dependency records")
    for item in dependencies:
        if not isinstance(item, dict) or set(item) - {"path", "origin", "revision", "package", "version", "instance_id", "kind"} or not item.get("path") or not (item.get("revision") or item.get("instance_id") or item.get("version")):
            raise ValueError("Unsupported dependency receipt entry")
        safe_relative(item["path"])
        for key, value in item.items():
            if not isinstance(value, str) or not value or len(value) > 2048 or re.search(r"[\x00-\x1f\\]", value) or re.match(r"^[A-Za-z]:", value) or value.startswith("/"):
                raise ValueError("Dependency receipt may not contain local absolute paths or non-string values")
            if key == "origin" and (not value.startswith("https://") or "@" in value or "?" in value or "#" in value):
                raise ValueError("Dependency origin must be public credential-free HTTPS")


def query_runtime(source: Path, output: Path, build_root: Path) -> dict:
    gn = regular_file(source, "buildtools/win/gn.exe")
    config = build_root / "gitconfig"
    if not config.is_file():
        raise ValueError("Task-local gitconfig missing")
    env = dict(os.environ, GIT_CONFIG_GLOBAL=str(config), DEPOT_TOOLS_UPDATE="0", DEPOT_TOOLS_WIN_TOOLCHAIN="0")
    if not env.get("vs2026_install"):
        vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
        installation = subprocess.run([str(vswhere), "-latest", "-products", "*", "-version", "[18.0,19.0)", "-property", "installationPath"], capture_output=True, check=True, timeout=10)
        env["vs2026_install"] = installation.stdout.decode("utf-8").strip()
    result = subprocess.run([str(gn), "desc", str(output), "//chrome:chrome", "runtime_deps", "--format=json"], cwd=source, env=env, capture_output=True, timeout=180, check=True)
    if len(result.stdout) > 16 * 1024 * 1024:
        raise ValueError("GN runtime dependency report too large")
    return json.loads(result.stdout)


def package(source: Path, output: Path, destination: Path, credits: Path, licenses: Path,
            dependency_receipt: Path, execute: bool = False) -> dict:
    source, output = source.resolve(), output.resolve()
    destination = destination.absolute()
    if destination.name != "NeAntikChromium" or destination.parent.name != "Engine" or destination.exists():
        raise ValueError("Destination must be a new Engine/NeAntikChromium directory")
    for ancestor in (destination.parent, *destination.parent.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            raise ValueError("Destination traverses a link/junction")
    if source not in output.parents or output.is_symlink() or output.is_junction():
        raise ValueError("Output must remain inside the dedicated source checkout")
    spec = json.loads(Path(__file__).with_name("buildspec.json").read_text())
    actual_args = regular_file(output, "args.gn").read_text(encoding="utf-8")
    normalized_args = re.sub(r"\s+", "", re.sub(r"(?m)#.*$", "", actual_args))
    if normalized_args != re.sub(r"\s+", "", "".join(spec["gn_args"])):
        raise ValueError("Actual GN args differ from the exact pinned compact release configuration")
    proof = verify_source(source, spec)
    document = query_runtime(source, output, source.parent.parent)
    files = runtime_inventory(output, document)
    extras = {"LICENSE": regular_file(source, "LICENSE"),
              "credits.html": credits, "THIRD_PARTY_LICENSES.txt": licenses,
              "DEPENDENCY_RECEIPT.json": dependency_receipt}
    for name, path in extras.items():
        if name.casefold() in {item.casefold() for item in files} or not path.is_file() or path.is_symlink() or path.is_junction() or path.stat().st_size == 0:
            raise ValueError("Required nonempty license/provenance artifact missing or colliding")
    if "<html" not in credits.read_text(encoding="utf-8").lower():
        raise ValueError("Credits artifact is not generated HTML")
    receipt = json.loads(dependency_receipt.read_text(encoding="utf-8"))
    validate_dependency_receipt(receipt)
    files.update(extras)
    compiler = regular_file(source, "third_party/llvm-build/Release+Asserts/bin/clang-cl.exe")
    compiler_info = subprocess.run([str(compiler), "--version"], capture_output=True, check=True, timeout=15).stdout.decode("utf-8").strip()
    size = sum(path.stat().st_size for path in files.values())
    report = {"state": "read-only-package-plan", "runtime_file_count": len(files),
              "uncompressed_bytes": size, "destination": str(destination), "source_proof": proof}
    if not execute:
        return report
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < size + spec["resource_policy"]["os_reserve_gib"] * 1024**3:
        raise ValueError("Packaging would violate the OS disk reserve")
    stage = Path(tempfile.mkdtemp(prefix=".native-package-", dir=destination.parent))
    try:
        for raw, path in files.items():
            target = stage.joinpath(*raw.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            before = core.sha256_file(path)
            shutil.copy2(path, target)
            if core.sha256_file(target) != before or core.sha256_file(path) != before:
                raise ValueError("Build artifact changed while packaging")
        provenance = {"format": "neantik-native-build-provenance-v1", "source_commit": core.SOURCE_COMMIT,
                      "version": core.ENGINE_VERSION, "depot_tools_commit": spec["depot_tools"]["commit"],
                      "patches": spec["patch_contract"]["patch_series"], "gn_args": spec["gn_args"],
                      "gn_runtime_deps_sha256": hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest(),
                      "upstream_deps_sha256": core.sha256_file(source / "DEPS"),
                      "actual_gn_args_sha256": core.sha256_file(output / "args.gn"),
                      "compiler_version": compiler_info, "compiler_sha256": core.sha256_file(compiler),
                      "runtime_qa": "not-claimed-by-packaging-tool"}
        (stage / "BUILD_PROVENANCE.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        manifest = {"format": core.MANIFEST_FORMAT, "schema": 1, "engine_id": core.ENGINE_ID,
                    "version": core.ENGINE_VERSION, "source_commit": core.SOURCE_COMMIT,
                    "files": {path.relative_to(stage).as_posix(): core.sha256_file(path)
                              for path in sorted(stage.rglob("*")) if path.is_file()}}
        manifest_path = stage / core.MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # This verifies the compiled query contract, not fingerprint fixture QA.
        core.CoreResolver._probe(stage / "chrome.exe")
        manifest_hash = core.sha256_file(manifest_path)
        stage.rename(destination)
        report.update(state="packaged-runtime-info-verified", manifest_sha256=manifest_hash)
        return report
    except Exception as exc:
        raise ValueError(f"Packaging stopped; recoverable staging retained at {stage}: {exc}") from exc


def verify_existing(directory: Path, trusted_hash: str, qa_report: Path) -> dict:
    for ancestor in (directory.absolute(), *directory.absolute().parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            raise ValueError("Existing core path traverses a link/junction")
    directory = directory.resolve()
    if directory.name != "NeAntikChromium" or directory.parent.name != "Engine" or not re.fullmatch(r"[a-f0-9]{64}", trusted_hash or ""):
        raise ValueError("Exact own-core directory and external trusted manifest SHA-256 required")
    if core.sha256_file(directory / core.MANIFEST_NAME) != trusted_hash:
        raise ValueError("External trusted native manifest SHA-256 mismatch")
    report = json.loads(qa_report.read_text(encoding="utf-8"))
    verification = report.get("verification", {})
    assertions = report.get("assertions")
    if report.get("format") != "neantik-own155-native-qa-v1" or report.get("status") != "passed" or verification.get("manifest_sha256") != trusted_hash or report.get("bundle_reverified_after_visits") is not True or not isinstance(assertions, list) or not assertions or any(not isinstance(item, dict) or item.get("passed") is not True for item in assertions):
        raise ValueError("Independent own155 QA report does not attest this exact bundle")
    executable = core.CoreResolver(directory.parent.parent).resolve()
    return {"state": "existing-core-verified", "manifest_sha256": trusted_hash,
            "engine_version": core.ENGINE_VERSION, "executable": str(executable), "qa_status": "passed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("source", "output", "destination", "credits", "licenses", "dependency-receipt"):
        parser.add_argument("--" + flag, type=Path)
    parser.add_argument("--verify-existing", type=Path)
    parser.add_argument("--trusted-manifest-sha256")
    parser.add_argument("--qa-report", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_existing:
            if not args.trusted_manifest_sha256 or not args.qa_report or args.execute:
                raise ValueError("Existing-core verification requires --trusted-manifest-sha256 and --qa-report, not --execute")
            result = verify_existing(args.verify_existing, args.trusted_manifest_sha256, args.qa_report)
        else:
            if not all((args.source, args.output, args.destination, args.credits, args.licenses, args.dependency_receipt)):
                raise ValueError("Packaging requires source/output/destination/credits/licenses/dependency-receipt")
            result = package(args.source, args.output, args.destination, args.credits, args.licenses, args.dependency_receipt, args.execute)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"Native packaging failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
