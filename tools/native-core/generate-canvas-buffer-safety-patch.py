"""Author patch 011 from the verified ten-patch Chromium155 source state."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
RELATIVE = "third_party/blink/renderer/platform/graphics/neantik_canvas_readback.cc"
PATCH = ROOT / "core/patches/011-canvas-safe-channel-index.patch"
PROVENANCE = ROOT / "core/patches/canvas-buffer-safety-chain-provenance.json"


def load_module(path: Path, name: str):
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Dedicated Chromium155 checkout with exactly patches001–010 applied")
    args = parser.parse_args()
    source = args.source.resolve()
    spec_path = ROOT / "tools/native-core/buildspec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    contract = spec["patch_contract"]
    if len(contract["patch_series"]) != 10 or PATCH.exists() or PROVENANCE.exists():
        raise RuntimeError("Expected the immutable ten-patch input and unused patch011 paths")

    gate = load_module(ROOT / "tools/native-core/verify-patch-series.py", "canvas_patch_gate")
    proof = gate.verify(source, ROOT, spec)
    if proof.get("mode") != "native-uncompiled" or proof.get("native_fingerprint_tested") is not False:
        raise RuntimeError("Prior source gate did not return the expected honest state")

    target = source / Path(RELATIVE)
    before = target.read_text(encoding="utf-8")
    after = before
    after = after.replace("#include <utility>\n", "#include <array>\n#include <utility>\n", 1)
    old = "      const size_t channels[3] = {rgba ? 0u : 2u, 1u, rgba ? 2u : 0u};"
    new = ("      const std::array<size_t, 3> channels = {\n"
           "          rgba ? 0u : 2u, 1u, rgba ? 2u : 0u};")
    if before.count(old) != 1 or after.count("#include <array>\n") != 1:
        raise RuntimeError("Exact reviewed C-array anchor/include was not unique")
    after = after.replace(old, new, 1)
    patch_text = gate_seed_diff(RELATIVE, before, after)

    with tempfile.TemporaryDirectory(prefix="neantik011-canvas-") as temporary:
        fixture = Path(temporary)
        subprocess.run(["git", "init", "--quiet", str(fixture)], check=True)
        subprocess.run(["git", "-C", str(fixture), "config", "core.autocrlf", "false"], check=True)
        fixture_file = fixture.joinpath(*RELATIVE.split("/"))
        fixture_file.parent.mkdir(parents=True, exist_ok=True)
        fixture_file.write_text(before, encoding="utf-8", newline="\n")
        patch_temp = fixture / "011.patch"
        patch_temp.write_text(patch_text, encoding="utf-8", newline="\n")
        subprocess.run(["git", "-C", str(fixture), "apply", "--check", str(patch_temp)], check=True)
        subprocess.run(["git", "-C", str(fixture), "apply", str(patch_temp)], check=True)
        if fixture_file.read_text(encoding="utf-8") != after:
            raise RuntimeError("Scratch-applied Canvas patch did not produce the expected source")

    PATCH.write_text(patch_text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    new_contract = json.loads(json.dumps(contract))
    new_contract["patch_series"].append({"path": PATCH.relative_to(ROOT).as_posix(), "sha256": digest})
    new_contract["postimage_sha256"][RELATIVE] = hashlib.sha256(after.encode("utf-8")).hexdigest()
    spec["patch_contract"] = new_contract
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    provenance = {
        "source_commit": spec["chromium"]["commit"],
        "source_version": spec["chromium"]["version"],
        "patches": new_contract["patch_series"],
        "011_exact_ten_patch_source_gate": "passed",
        "011_scratch_apply_check": "passed",
        "actual_checkout_state_at_generation": "patch011-not-yet-applied",
        "compilation": "not-run",
        "runtime_fingerprint_verification": "not-run",
        "postimage_sha256": new_contract["postimage_sha256"],
    }
    PROVENANCE.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8", newline="\n")
    print(json.dumps({"patch": str(PATCH), "patch_sha256": digest,
                      "verified_postimages": len(new_contract["postimage_sha256"]),
                      "actual_checkout_state_at_generation": "patch011-not-yet-applied"}, indent=2))
    return 0


def gate_seed_diff(relative: str, before: str, after: str) -> str:
    import difflib
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile=f"a/{relative}", tofile=f"b/{relative}", n=4))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Canvas patch authoring failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
