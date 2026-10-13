"""Export or verify the experimental Chromium V4b native-persona patch.

The export is deterministic and includes untracked new files without staging
or modifying the Chromium checkout. It refuses unrelated source changes.
This prototype patch supersedes, rather than stacks on, the 0.8.x baseline.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile


UPSTREAM_COMMIT = "cfaadc5a132d78e1828635aa8405a499f3e14864"
BUILD_ONLY = {"DEPS", "build/toolchain/win/midl.py"}
TRACKED_RUNTIME = {
    "chrome/app/chrome_main_delegate.cc",
    "chrome/browser/renderer_preferences_util.cc",
    "chrome/browser/renderer_preferences_util.h",
    "chrome/browser/renderer_preferences_util_unittest.cc",
    "content/browser/renderer_host/render_process_host_impl.cc",
    "content/renderer/worker/embedded_shared_worker_stub.cc",
    "third_party/blink/common/BUILD.gn",
    "third_party/blink/common/device_memory/approximated_device_memory.cc",
    "third_party/blink/public/common/BUILD.gn",
    "third_party/blink/public/web/web_shared_worker.h",
    "third_party/blink/renderer/core/exported/web_shared_worker_impl.cc",
    "third_party/blink/renderer/core/exported/web_shared_worker_impl.h",
    "third_party/blink/renderer/core/frame/navigator_concurrent_hardware.cc",
    "third_party/blink/renderer/core/html/build.gni",
    "third_party/blink/renderer/core/html/canvas/html_canvas_element.cc",
    "third_party/blink/renderer/core/offscreencanvas/offscreen_canvas.cc",
    "third_party/blink/renderer/core/timezone/timezone_controller.cc",
    "third_party/blink/renderer/core/workers/worker_global_scope.cc",
    "third_party/blink/renderer/core/workers/worker_global_scope.h",
    "third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc",
    "third_party/blink/renderer/modules/service_worker/service_worker_global_scope.cc",
    "third_party/blink/renderer/modules/service_worker/service_worker_global_scope.h",
    "third_party/blink/renderer/platform/BUILD.gn",
}
NEW_RUNTIME = {
    "third_party/blink/common/fingerprinting/neantik_fingerprint.cc",
    "third_party/blink/common/fingerprinting/neantik_fingerprint_unittest.cc",
    "third_party/blink/public/common/fingerprinting/neantik_fingerprint.h",
    "third_party/blink/renderer/core/html/canvas/neantik_canvas_site_key.cc",
    "third_party/blink/renderer/core/html/canvas/neantik_canvas_site_key.h",
    "third_party/blink/renderer/platform/graphics/neantik_canvas_readback.cc",
    "third_party/blink/renderer/platform/graphics/neantik_canvas_readback.h",
    "third_party/blink/renderer/platform/graphics/neantik_canvas_readback_test.cc",
    "third_party/blink/web_tests/http/tests/neantik/resources/timezone-frame.html",
    "third_party/blink/web_tests/http/tests/neantik/resources/timezone-service.js",
    "third_party/blink/web_tests/http/tests/neantik/resources/timezone-shared.js",
    "third_party/blink/web_tests/http/tests/neantik/resources/timezone-surface.js",
    "third_party/blink/web_tests/http/tests/neantik/resources/timezone-worker.js",
    "third_party/blink/web_tests/http/tests/neantik/timezone-expected.txt",
    "third_party/blink/web_tests/http/tests/neantik/timezone.html",
    "third_party/blink/web_tests/neantik/canvas-readback-expected.txt",
    "third_party/blink/web_tests/neantik/canvas-readback.html",
}


def git(source: Path, *args: str, expected: tuple[int, ...] = (0,), data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", "-C", str(source), *args], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode not in expected:
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): "
                           f"{result.stderr.decode(errors='replace')[-500:]}")
    return result.stdout


def names(raw: bytes) -> set[str]:
    return {name for name in raw.decode("utf-8").splitlines() if name}


def export(source: Path) -> bytes:
    if git(source, "rev-parse", "HEAD").decode().strip() != UPSTREAM_COMMIT:
        raise RuntimeError("Chromium checkout is not at the pinned upstream commit")
    modified = names(git(source, "diff", "HEAD", "--name-only"))
    untracked = names(git(source, "ls-files", "--others", "--exclude-standard"))
    if modified != BUILD_ONLY | TRACKED_RUNTIME:
        raise RuntimeError(f"Unexpected changed tracked paths: {sorted(modified ^ (BUILD_ONLY | TRACKED_RUNTIME))}")
    if untracked != NEW_RUNTIME:
        raise RuntimeError(f"Unexpected new paths: {sorted(untracked ^ NEW_RUNTIME)}")
    for path in NEW_RUNTIME:
        candidate = source / path
        if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 200_000:
            raise RuntimeError(f"Invalid new source file: {path}")
    patch = bytearray(git(source, "diff", "HEAD", "--binary", "--", *sorted(TRACKED_RUNTIME)))
    for path in sorted(NEW_RUNTIME):
        patch.extend(git(source, "diff", "--no-index", "--binary", "--", "/dev/null", path,
                         expected=(1,)))
    if not patch or len(patch) > 1_000_000:
        raise RuntimeError("Prototype patch is empty or unexpectedly large")
    git(source, "-c", "core.autocrlf=false", "apply", "--reverse", "--check", "-", data=bytes(patch))
    with tempfile.TemporaryDirectory(prefix="neantik-native-patch-verify-") as temporary:
        upstream = Path(temporary)
        for path in TRACKED_RUNTIME:
            target = upstream / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git(source, "show", f"HEAD:{path}"))
        git(upstream, "-c", "core.autocrlf=false", "apply", "--check", "-", data=bytes(patch))
        git(upstream, "-c", "core.autocrlf=false", "apply", "-", data=bytes(patch))
        for path in TRACKED_RUNTIME | NEW_RUNTIME:
            applied = (upstream / path).read_bytes()
            current = (source / path).read_bytes()
            if applied != current:
                raise RuntimeError(f"Patch application did not reproduce {path}: "
                                   f"applied={hashlib.sha256(applied).hexdigest()} ({len(applied)} B), "
                                   f"checkout={hashlib.sha256(current).hexdigest()} ({len(current)} B)")
    return bytes(patch)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true", help="Compare with an existing patch without overwriting it")
    args = parser.parse_args()
    source = args.source_root.resolve(strict=True)
    if not (source / ".git").exists() and git(source, "rev-parse", "--show-toplevel").decode().strip().casefold() != str(source).casefold():
        parser.error("Source root is not a Chromium Git checkout")
    patch = export(source)
    digest = hashlib.sha256(patch).hexdigest()
    if args.verify:
        if not args.output.is_file() or args.output.read_bytes() != patch:
            raise RuntimeError("Published prototype patch differs from the current checkout")
    else:
        if args.output.exists() or not args.output.parent.is_dir():
            parser.error("Output path must be new and its parent must exist")
        args.output.write_bytes(patch)
    print(f"native_persona_patch_sha256={digest} bytes={len(patch)} verify={args.verify}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
