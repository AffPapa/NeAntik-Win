"""Author stage004 against the immutable applied001/002/003 source fixture.

Checks exact ordered textual application, not compilation or runtime coverage.
The earlier patch files and authored stage001 sources are never rewritten.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('seed_generator',HERE/'generate-seed-patches.py')
seed=importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)
ROOT=seed.ROOT
PATCHES=seed.PATCHES
TZ='third_party/blink/renderer/core/timezone/timezone_controller.cc'


def main():
    proof=json.loads((PATCHES/'combined-patch-provenance.json').read_text(encoding='utf-8'))
    input_patches=[]
    paths=set()
    for item in proof['patches']:
        p=ROOT/item['path']
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise RuntimeError('Prior patch changed: '+item['path'])
        input_patches.append(p)
        paths.update(line[6:] for line in raw.decode().splitlines() if line.startswith('--- a/'))
    paths.add(TZ)
    originals={p:seed.fetch(p) for p in paths}
    with tempfile.TemporaryDirectory(prefix='neantik-timezone-exact-source-') as temp:
        fixture=Path(temp)
        for p,s in originals.items():
            target=fixture/p;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(s,encoding='utf-8',newline='\n')
        subprocess.run(['git','init','--quiet',str(fixture)],check=True)
        subprocess.run(['git','-C',str(fixture),'config','core.autocrlf','false'],check=True)
        for p in input_patches:
            subprocess.run(['git','-C',str(fixture),'apply','--check',str(p)],check=True)
            subprocess.run(['git','-C',str(fixture),'apply',str(p)],check=True)
        all_paths=set(originals)|set(proof['postimage_sha256'])
        before={p:(fixture/p).read_text(encoding='utf-8') for p in all_paths}
        after=dict(before)
        replace=seed.replace
        after[seed.HEADER]=replace(after[seed.HEADER],
            'inline constexpr char kCoreInfoSwitch[] = "neantik-core-info";',
            'inline constexpr char kTimeZoneSwitch[] = "neantik-timezone";\ninline constexpr char kCoreInfoSwitch[] = "neantik-core-info";')
        after[seed.HEADER]=replace(after[seed.HEADER], '  float device_memory = 8.0f;',
            '  float device_memory = 8.0f;\n  std::string time_zone;  // Empty only when no override was requested.')
        after[seed.HEADER]=replace(after[seed.HEADER],
            '// Immutable, thread-safe one-time snapshot.',
            '// Call after ContentMainRunner initializes ICU, before sandbox/pages.\nBLINK_COMMON_EXPORT bool ValidateFingerprintTimeZone(\n    const FingerprintConfig& config, std::string* error);\n\n// Immutable, thread-safe one-time snapshot.')
        s=after[seed.SOURCE]
        s=replace(s,'#include "base/command_line.h"',
            '#include "base/command_line.h"\n#include "base/no_destructor.h"\n#include "third_party/icu/source/i18n/unicode/timezone.h"')
        s=replace(s,'name != kDeviceMemorySwitch && name != kCoreInfoSwitch)',
            'name != kDeviceMemorySwitch && name != kTimeZoneSwitch &&\n        name != kCoreInfoSwitch)')
        s=replace(s,'command_line.HasSwitch(kDeviceMemorySwitch)) {\n      *error',
            'command_line.HasSwitch(kDeviceMemorySwitch) ||\n        command_line.HasSwitch(kTimeZoneSwitch)) {\n      *error')
        s=replace(s,'  return config;\n}\n\nconst FingerprintConfig*',r'''  if (command_line.HasSwitch(kTimeZoneSwitch)) {
    config.time_zone = command_line.GetSwitchValueASCII(kTimeZoneSwitch);
    if (config.time_zone.empty() || config.time_zone.size() > 128) {
      *error = "NeAntik timezone must be a nonempty IANA identifier";
      return std::nullopt;
    }
    for (char c : config.time_zone) {
      if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || c == '/' || c == '_' ||
            c == '-' || c == '+')) {
        *error = "Malformed NeAntik IANA timezone";
        return std::nullopt;
      }
    }
  }
  return config;
}

bool ValidateFingerprintTimeZone(const FingerprintConfig& config,
                                 std::string* error) {
  CHECK(error);
  error->clear();
  if (config.time_zone.empty()) {
    return true;
  }
  UErrorCode status = U_ZERO_ERROR;
  UBool is_system_id = false;
  icu::UnicodeString canonical;
  icu::TimeZone::getCanonicalID(
      icu::UnicodeString(config.time_zone.c_str(), -1, US_INV),
      canonical, is_system_id, status);
  if (U_FAILURE(status) || !is_system_id) {
    *error = "Unknown NeAntik IANA timezone";
    return false;
  }
  return true;
}

const FingerprintConfig*''')
        s=replace(s,'  static const std::optional<FingerprintConfig> config = [] {',
            '  static const base::NoDestructor<std::optional<FingerprintConfig>> config([] {')
        s=replace(s,'  }();\n  return config.has_value() ? &config.value() : nullptr;',
            '  }());\n  return config->has_value() ? &config->value() : nullptr;')
        after[seed.SOURCE]=s
        common='third_party/blink/common/BUILD.gn'
        after[common]=replace(after[common],'    "//base",\n',
            '    "//base",\n    "//third_party/icu",\n') if after[common].count('    "//base",\n')==1 else replace(after[common],
            '  # If use_blink is used then it needs to depend on //media',
            '  # Native NeAntik timezone validation uses ICU on desktop too.\n  if (!is_android) {\n    deps += [ "//third_party/icu" ]\n  }\n\n  # If use_blink is used then it needs to depend on //media')
        after[seed.TEST]=replace(after[seed.TEST],'#include "base/command_line.h"',
            '#include "base/command_line.h"\n#include "base/test/icu_test_util.h"')
        tests=(ROOT/'core/native/neantik_timezone_tests.inc').read_text(encoding='utf-8')
        end='}  // namespace\n}  // namespace blink::neantik\n'
        after[seed.TEST]=replace(after[seed.TEST],end,tests+'\n'+end)
        forward='      blink::neantik::kDeviceMemorySwitch,\n'
        after[seed.FORWARD]=replace(after[seed.FORWARD],forward,
            forward+'      blink::neantik::kTimeZoneSwitch,\n')
        main=after[seed.MAIN]
        main=replace(main,'void ChromeMainDelegate::PreSandboxStartup() {\n',r'''void ChromeMainDelegate::PreSandboxStartup() {
  // ContentMainRunner has initialized ICU at this point, before V8 contexts.
  if (const auto* config = blink::neantik::GetFingerprintConfig()) {
    std::string error;
    if (!blink::neantik::ValidateFingerprintTimeZone(*config, &error)) {
      LOG(ERROR) << error;
      base::Process::TerminateCurrentProcessImmediately(78);
    }
  }
''')
        main=replace(main,r'\"canvas\":false},\"compiled_stage\":2}',
            r'\"canvas\":false,\"timezone\":true},\"compiled_stage\":4}')
        after[seed.MAIN]=main
        tz=after[TZ]
        tz=replace(tz,'#include "third_party/blink/public/common/features.h"',
            '#include "third_party/blink/public/common/features.h"\n#include "'+seed.HEADER+'"')
        constructor='    host_timezone_id_ = GetCurrentTimezoneId();\n  }\n}'
        tz=replace(tz,constructor,'''    host_timezone_id_ = GetCurrentTimezoneId();
  }
  if (const auto* config = neantik::GetFingerprintConfig();
      config && !config->time_zone.empty()) {
    CHECK(SetIcuTimeZoneAndNotifyV8(String::FromUtf8(config->time_zone)));
  }
}''')
        tz=replace(tz,'void TimeZoneController::Init() {\n',r'''void TimeZoneController::Init() {
  // Force profile ICU initialization even if a WebUI skips monitor binding.
  if (const auto* config = neantik::GetFingerprintConfig();
      config && !config->time_zone.empty()) {
    instance();
  }
''')
        tz=replace(tz,'TimeZoneController::SetTimeZoneOverride(const String& timezone_id) {\n',r'''TimeZoneController::SetTimeZoneOverride(const String& timezone_id) {
  if (const auto* config = neantik::GetFingerprintConfig();
      config && !config->time_zone.empty() &&
      !CanonicalEquals(timezone_id, String::FromUtf8(config->time_zone))) {
    return {TimeZoneOverrideStatus::kAlreadyInEffect, nullptr};
  }
''')
        tz=replace(tz,'void TimeZoneController::ChangeTimeZoneOverride(const String& timezone_id) {\n',r'''void TimeZoneController::ChangeTimeZoneOverride(const String& timezone_id) {
  if (const auto* config = neantik::GetFingerprintConfig();
      config && !config->time_zone.empty() &&
      !CanonicalEquals(timezone_id, String::FromUtf8(config->time_zone))) {
    return;
  }
''')
        anchor='bool TimeZoneController::SetIcuTimeZoneAndNotifyV8(const String& timezone_id) {\n  DCHECK(!timezone_id.empty());\n'
        tz=replace(tz,anchor,anchor+r'''  String effective_timezone = timezone_id;
  if (const auto* config = neantik::GetFingerprintConfig();
      config && !config->time_zone.empty()) {
    effective_timezone = String::FromUtf8(config->time_zone);
  }
''')
        # Only the conversion inside SetIcu... is changed, not canonical matching.
        anchor='      icu::UnicodeString(timezone_id.Ascii().data(), -1, US_INV)));'
        tz=replace(tz,anchor,'      icu::UnicodeString(effective_timezone.Ascii().data(), -1, US_INV)));')
        after[TZ]=tz
        test_root='third_party/blink/web_tests/http/tests/neantik/'
        for local,relative in (('timezone.html','timezone.html'),('timezone-expected.txt','timezone-expected.txt'),
                               ('timezone-surface.js','resources/timezone-surface.js')):
            after[test_root+relative]=(ROOT/'core/native'/local).read_text(encoding='utf-8')
        after[test_root+'resources/timezone-frame.html']='<!doctype html><script src="timezone-surface.js"></script><script>parent.postMessage(timezoneSurface(),"*");</script>\n'
        after[test_root+'resources/timezone-worker.js']="importScripts('timezone-surface.js');postMessage(timezoneSurface());\n"
        after[test_root+'resources/timezone-shared.js']="importScripts('timezone-surface.js');onconnect=e=>e.ports[0].postMessage(timezoneSurface());\n"
        after[test_root+'resources/timezone-service.js']="importScripts('timezone-surface.js');self.addEventListener('install',e=>e.waitUntil(self.skipWaiting()));self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));self.addEventListener('message',e=>e.ports[0].postMessage(timezoneSurface()));\n"
        # Invoke explicitly with documented additional-driver-flag values.
        # Never invent an upstream VirtualTestSuite maintainer address.
        patch_text=seed.diff(before,after)
        patch_path=PATCHES/'004-native-timezone.patch'
        patch_path.write_text(patch_text,encoding='utf-8',newline='\n')
        subprocess.run(['git','-C',str(fixture),'apply','--check',str(patch_path)],check=True)
        subprocess.run(['git','-C',str(fixture),'apply',str(patch_path)],check=True)
        for p,s in after.items():
            if (fixture/p).read_text(encoding='utf-8')!=s:
                raise RuntimeError('Timezone postimage mismatch: '+p)
        changed=set(proof['postimage_sha256'])|{p for p,s in after.items() if before.get(p)!=s}
        final={'source_commit':seed.PIN,'source_version':'155.0.8059.40',
            'patches':proof['patches']+[{'path':str(patch_path.relative_to(ROOT)).replace('\\','/'),
            'sha256':hashlib.sha256(patch_text.encode()).hexdigest()}],
            'exact_source_sequence_apply_check':'passed','compilation':'not-run',
            'runtime_fingerprint_verification':'not-run',
            'postimage_sha256':{p:hashlib.sha256((fixture/p).read_bytes()).hexdigest() for p in sorted(changed)}}
        (PATCHES/'timezone-chain-provenance.json').write_text(json.dumps(final,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(final,indent=2))


if __name__=='__main__':main()
