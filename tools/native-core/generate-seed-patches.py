"""Generate native stages 001/002 against exact Chromium source; not a compiler.

Authored C++ sources live in core/native. Official immutable source is fetched
read-only; all replacement anchors must match exactly once. A disposable source
fixture proves git apply --check/apply for the generated sequence only. It never
claims compile success or touches the real Chromium checkout.
"""
from __future__ import annotations

import base64
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.request import urlopen
from urllib.error import HTTPError
import time

ROOT = Path(__file__).resolve().parents[2]
PIN = "cfaadc5a132d78e1828635aa8405a499f3e14864"
PATCHES = ROOT / "core" / "patches"
HEADER = "third_party/blink/public/common/fingerprinting/neantik_fingerprint.h"
SOURCE = "third_party/blink/common/fingerprinting/neantik_fingerprint.cc"
TEST = "third_party/blink/common/fingerprinting/neantik_fingerprint_unittest.cc"
MAIN = "chrome/app/chrome_main_delegate.cc"
FORWARD = "content/browser/renderer_host/render_process_host_impl.cc"
CPU = "third_party/blink/renderer/core/frame/navigator_concurrent_hardware.cc"
MEMORY = "third_party/blink/common/device_memory/approximated_device_memory.cc"


def fetch(path: str) -> str:
    url = f"https://chromium.googlesource.com/chromium/src/+/{PIN}/{path}?format=TEXT"
    for attempt in range(3):
        try:
            with urlopen(url, timeout=45) as response:
                return base64.b64decode(response.read()).decode("utf-8").replace("\r\n", "\n")
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(0.5 * (attempt + 1))


def replace(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Exact-source anchor matched {source.count(old)} times: {old[:100]}")
    return source.replace(old, new, 1)


def diff(before: dict[str, str], after: dict[str, str]) -> str:
    text = ""
    for path in sorted(after):
        original = before.get(path, "")
        if original == after[path]:
            continue
        text += "".join(difflib.unified_diff(original.splitlines(True), after[path].splitlines(True),
            fromfile=f"a/{path}" if path in before else "/dev/null", tofile=f"b/{path}", n=4))
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-canvas', action='store_true',
                        help='Also check the independently authored 003 canvas patch and record combined postimages')
    args = parser.parse_args()
    originals = {p: fetch(p) for p in (
        "third_party/blink/public/common/BUILD.gn", "third_party/blink/common/BUILD.gn",
        MAIN, FORWARD, CPU, MEMORY)}
    stage1 = dict(originals)
    for target, local in ((HEADER,"neantik_fingerprint.h"),(SOURCE,"neantik_fingerprint.cc"),
                          (TEST,"neantik_fingerprint_unittest.cc")):
        stage1[target] = (ROOT / "core" / "native" / local).read_text(encoding="utf-8")
    for file, anchor, insert in (
        ("third_party/blink/public/common/BUILD.gn", '    "fingerprinting_protection/noise_token.h",',
         '    "fingerprinting/neantik_fingerprint.h",\n'),
        ("third_party/blink/common/BUILD.gn", '    "frame/delegated_capability_request_token.cc",',
         '    "fingerprinting/neantik_fingerprint.cc",\n'),
        ("third_party/blink/common/BUILD.gn", '    "frame/delegated_capability_request_token_unittest.cc",',
         '    "fingerprinting/neantik_fingerprint_unittest.cc",\n')):
        stage1[file] = replace(stage1[file], anchor, insert + anchor)
    include = '#include "third_party/blink/public/common/features.h"'
    stage1[MAIN] = replace(stage1[MAIN], include, include + '\n#include "' + HEADER + '"')
    startup = 'std::optional<int> ChromeMainDelegate::BasicStartupComplete() {\n'
    startup_guard = r'''  // Validate before any browser navigation or sandboxed child accesses persona.
  const base::CommandLine& neantik_command =
      *base::CommandLine::ForCurrentProcess();
  std::string neantik_error;
  blink::neantik::ParseFingerprintConfig(neantik_command, &neantik_error);
  if (!neantik_error.empty()) {
    LOG(ERROR) << neantik_error;
    return 78;
  }
  if (neantik_command.HasSwitch(blink::neantik::kCoreInfoSwitch)) {
    // File handshake works with a Windows GUI subsystem binary without console.
    const std::string info =
        "{\"engine_id\":\"neantik-chromium\",\"schema\":1,\"version\":\"" +
        std::string(version_info::GetVersionNumber()) +
        "\",\"capabilities\":{\"stable_seed\":true,"
        "\"hardware_concurrency\":false,\"device_memory\":false,"
        "\"canvas\":false},\"compiled_stage\":1}";
    if (!base::WriteFile(neantik_command.GetSwitchValuePath(
                            blink::neantik::kCoreInfoSwitch), info)) {
      return 74;
    }
    return 0;
  }

'''
    stage1[MAIN] = replace(stage1[MAIN], startup, startup + startup_guard)
    stage1[FORWARD] = replace(stage1[FORWARD], include, include + '\n#include "' + HEADER + '"')
    anchor = '  renderer_cmd->CopySwitchesFrom(browser_cmd, kSwitchNames);\n'
    forwarding = '''
  // Every renderer (including out-of-process frames and worker renderers) gets
  // validated immutable persona input before any JavaScript context exists.
  static const char* const kNeAntikSwitches[] = {
      blink::neantik::kSeedSwitch,
      blink::neantik::kHardwareConcurrencySwitch,
      blink::neantik::kDeviceMemorySwitch,
  };
  renderer_cmd->CopySwitchesFrom(browser_cmd, kNeAntikSwitches);
'''
    stage1[FORWARD] = replace(stage1[FORWARD], anchor, anchor + forwarding)
    stage2 = dict(stage1)
    cpu_anchor = '#include "base/system/sys_info.h"'
    stage2[CPU] = replace(stage2[CPU], cpu_anchor, cpu_anchor + '\n#include "' + HEADER + '"')
    cpu_getter = 'unsigned NavigatorConcurrentHardware::hardwareConcurrency() const {\n'
    stage2[CPU] = replace(stage2[CPU], cpu_getter, cpu_getter + '''  if (const auto* config = neantik::GetFingerprintConfig()) {
    return config->hardware_concurrency;
  }
''')
    stage2[MEMORY] = replace(stage2[MEMORY], include, include + '\n#include "' + HEADER + '"')
    memory_getter = 'float ApproximatedDeviceMemory::GetApproximatedDeviceMemory() {\n'
    stage2[MEMORY] = replace(stage2[MEMORY], memory_getter, memory_getter + '''  // The native NavigatorDeviceMemory accessor and HTTP device-memory hints
  // share this exact source; no window-only or worker-only memory override.
  if (const auto* config = neantik::GetFingerprintConfig()) {
    return config->device_memory;
  }
''')
    stage2[MAIN] = replace(stage2[MAIN], r'\"hardware_concurrency\":false,\"device_memory\":false,',
                           r'\"hardware_concurrency\":true,\"device_memory\":true,')
    stage2[MAIN] = replace(stage2[MAIN], r'\"compiled_stage\":1}', r'\"compiled_stage\":2}')
    PATCHES.mkdir(parents=True, exist_ok=True)
    generated = []
    for name, before, after in (("0001-native-seed-state.patch",originals,stage1),
                               ("0002-native-cpu-memory.patch",stage1,stage2)):
        text = diff(before, after)
        path = PATCHES / name
        path.write_text(text, encoding="utf-8", newline="\n")
        generated.append({"path":str(path.relative_to(ROOT)).replace("\\","/"),
                          "sha256":hashlib.sha256(text.encode()).hexdigest()})
    combined = None
    with tempfile.TemporaryDirectory(prefix="neantik-exact-source-patch-check-") as temp:
        fixture = Path(temp)
        for file, text in originals.items():
            target = fixture / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        subprocess.run(["git", "init", "--quiet", str(fixture)], check=True)
        subprocess.run(["git", "-C", str(fixture), "config", "core.autocrlf", "false"], check=True)
        for patch in generated:
            path = str(ROOT / patch["path"])
            subprocess.run(["git", "-C", str(fixture), "apply", "--check", path], check=True)
            subprocess.run(["git", "-C", str(fixture), "apply", path], check=True)
        for file, text in stage2.items():
            if (fixture/file).read_text(encoding="utf-8") != text:
                raise RuntimeError(f"Applied source differs from authored target: {file}")
        if args.with_canvas:
            canvas_path = PATCHES / '003-canvas-readback.patch'
            canvas_text = canvas_path.read_text(encoding='utf-8')
            old_paths = [line[len('--- a/'):] for line in canvas_text.splitlines()
                         if line.startswith('--- a/')]
            new_paths = [line[len('+++ b/'):] for line in canvas_text.splitlines()
                         if line.startswith('+++ b/')]
            for file in set(old_paths):
                if Path(file).is_absolute() or '..' in Path(file).parts:
                    raise RuntimeError('Canvas patch contains an unsafe source path')
                if not (fixture/file).exists():
                    baseline = fetch(file)
                    target = fixture/file
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(baseline, encoding='utf-8', newline='\n')
            subprocess.run(['git','-C',str(fixture),'apply','--check',str(canvas_path)], check=True)
            subprocess.run(['git','-C',str(fixture),'apply',str(canvas_path)], check=True)
            combined_paths = {p for p,s in stage2.items() if originals.get(p) != s} | set(new_paths)
            combined = {'source_commit':PIN,'source_version':'155.0.8059.40',
                'patches':generated + [{'path':str(canvas_path.relative_to(ROOT)).replace('\\','/'),
                    'sha256':hashlib.sha256(canvas_text.encode()).hexdigest()}],
                'exact_source_sequence_apply_check':'passed','compilation':'not-run',
                'runtime_fingerprint_verification':'not-run',
                'postimage_sha256':{p:hashlib.sha256((fixture/p).read_bytes()).hexdigest()
                                   for p in sorted(combined_paths)}}
    proof = {"source_commit":PIN,"source_version":"155.0.8059.40",
        "patches":generated,"exact_source_apply_check":"passed",
        "compilation":"not-run","runtime_fingerprint_verification":"not-run",
        "baseline_file_sha256":{p:hashlib.sha256(s.encode()).hexdigest() for p,s in originals.items()},
        "postimage_sha256":{p:hashlib.sha256(s.encode()).hexdigest() for p,s in stage2.items()
                            if originals.get(p) != s}}
    (PATCHES/"seed-patch-provenance.json").write_text(json.dumps(proof,indent=2)+"\n",encoding="utf-8")
    if combined:
        (PATCHES/'combined-patch-provenance.json').write_text(json.dumps(combined,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(combined,indent=2))
    print(json.dumps(proof,indent=2))


if __name__ == "__main__":
    main()
