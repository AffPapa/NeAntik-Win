"""Author009 only in repository and disposable scratch; never modify checkout."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('seed_generator',HERE/'generate-seed-patches.py')
seed=importlib.util.module_from_spec(spec);spec.loader.exec_module(seed)
SOURCE='chrome/browser/renderer_preferences_util.cc'
HEADER='chrome/browser/renderer_preferences_util.h'
TEST='chrome/browser/renderer_preferences_util_unittest.cc'
CAPABILITY='webrtc_non_proxied_udp_proxied_webframes'

def transform(before,tests):
    after=dict(before)
    s=after[SOURCE]
    s=seed.replace(s,'#include "base/logging.h"',
        '#include "base/check.h"\n#include "base/command_line.h"\n#include "base/logging.h"')
    s=seed.replace(s,'#include "chrome/common/pref_names.h"',
        '#include "chrome/common/chrome_switches.h"\n#include "chrome/common/pref_names.h"')
    s=seed.replace(s,'#include "third_party/blink/public/common/peerconnection/webrtc_ip_handling_policy.h"',
        '#include "third_party/blink/public/common/fingerprinting/neantik_fingerprint.h"\n#include "third_party/blink/public/common/peerconnection/webrtc_ip_handling_policy.h"')
    s=seed.replace(s,'namespace renderer_preferences_util {\n',r'''namespace renderer_preferences_util {

void ApplyNeAntikProxiedWebRtcPolicy(
    blink::RendererPreferences* prefs,
    bool native_persona,
    const base::CommandLine& command_line) {
  CHECK(prefs);
  if (!native_persona ||
      !command_line.HasSwitch(switches::kProxyServer) ||
      command_line.GetSwitchValueNative(switches::kProxyServer).empty()) {
    return;
  }
  // Website-frame routing policy only: not a system network kill-switch or
  // an assertion about privileged standalone extension processes.
  prefs->webrtc_ip_handling_policy =
      blink::mojom::WebRtcIpHandlingPolicy::kDisableNonProxiedUdp;
  // Matching per-URL preferences otherwise supersede the global enum.
  prefs->webrtc_ip_handling_urls.clear();
}
''')
    s=seed.replace(s,'  if (pref_service->IsManagedPreference(\n          prefs::kWebRTCPostQuantumKeyAgreement)) {',
        '  ApplyNeAntikProxiedWebRtcPolicy(\n      prefs, blink::neantik::GetFingerprintConfig() != nullptr,\n      *base::CommandLine::ForCurrentProcess());\n\n  if (pref_service->IsManagedPreference(\n          prefs::kWebRTCPostQuantumKeyAgreement)) {')
    after[SOURCE]=s
    h=seed.replace(after[HEADER],'class Profile;',
        'namespace base {\nclass CommandLine;\n}\n\nclass Profile;')
    h=seed.replace(h,'// Copies system configuration preferences into |prefs|.',
        '// Narrow in-memory policy helper; native/proxy predicates are explicit for\n// unit tests. Production caller supplies immutable native persona state.\nvoid ApplyNeAntikProxiedWebRtcPolicy(\n    blink::RendererPreferences* prefs,\n    bool native_persona,\n    const base::CommandLine& command_line);\n\n// Copies system configuration preferences into |prefs|.')
    after[HEADER]=h
    t=seed.replace(after[TEST],'#include "base/memory/raw_ptr.h"',
        '#include "base/command_line.h"\n#include "base/memory/raw_ptr.h"')
    t=seed.replace(t,'#include "chrome/common/pref_names.h"',
        '#include "chrome/common/chrome_switches.h"\n#include "chrome/common/pref_names.h"')
    after[TEST]=t+'\n'+tests
    after[seed.MAIN]=seed.replace(after[seed.MAIN],
        r'\"timezone\":true},\"compiled_stage\":6}',
        r'\"timezone\":true,\"'+CAPABILITY+r'\":true},\"compiled_stage\":9}')
    return after

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    contract=json.loads((HERE/'buildspec.json').read_text())['patch_contract']
    if len(contract['patch_series'])!=8:raise RuntimeError('Expected immutable001..008 input')
    if subprocess.check_output(['git','-C',str(args.source),'rev-parse','HEAD'],text=True).strip()!=seed.PIN:
        raise RuntimeError('Wrong source commit')
    for entry in contract['patch_series']:
        if hashlib.sha256((seed.ROOT/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:
            raise RuntimeError('Prior patch modified')
    for path,digest in contract['postimage_sha256'].items():
        if hashlib.sha256((args.source/path).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Post008 source changed')
    before={p:(args.source/p).read_text(encoding='utf-8') for p in (SOURCE,HEADER,TEST,seed.MAIN)}
    # New target baselines must exactly equal immutable upstream, not local edits.
    for path in (SOURCE,HEADER,TEST):
        original=subprocess.check_output(['git','-C',str(args.source),'show','HEAD:'+path]).decode('utf-8')
        if before[path]!=original:raise RuntimeError('Unexpected WebRTC target modification')
    tests=(seed.ROOT/'core/native/neantik_webrtc_policy_tests.inc').read_text(encoding='utf-8')
    after=transform(before,tests)
    patch=seed.diff(before,after);patch_path=seed.PATCHES/'009-native-proxy-webrtc-policy.patch'
    patch_path.write_text(patch,encoding='utf-8',newline='\n')
    with tempfile.TemporaryDirectory(prefix='neantik009-candidate-') as temporary:
        fixture=Path(temporary)
        for path,value in before.items():
            target=fixture/path;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(value,encoding='utf-8',newline='\n')
        subprocess.run(['git','init','--quiet',str(fixture)],check=True)
        subprocess.run(['git','-C',str(fixture),'config','core.autocrlf','false'],check=True)
        subprocess.run(['git','-C',str(fixture),'apply','--check',str(patch_path)],check=True)
        subprocess.run(['git','-C',str(fixture),'apply',str(patch_path)],check=True)
        for path,value in after.items():
            if (fixture/path).read_text()!=value:raise RuntimeError('009 postimage mismatch')
    postimages=dict(contract['postimage_sha256'])
    postimages.update({p:hashlib.sha256(v.encode()).hexdigest() for p,v in after.items()})
    proof={'source_commit':seed.PIN,'source_version':'155.0.8059.40',
        'patches':contract['patch_series']+[{'path':'core/patches/'+patch_path.name,
            'sha256':hashlib.sha256(patch.encode()).hexdigest()}],
        '009_exact_post008_scratch_apply_check':'passed','actual_checkout_009_applied':False,
        'compilation':'not-run','runtime_webrtc_verification':'not-run',
        'capability_scope':CAPABILITY,'postimage_sha256':postimages}
    (seed.PATCHES/'webrtc-candidate-provenance.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'patch_sha256':proof['patches'][-1]['sha256'],'postimages':len(postimages),'actual_applied':False}))

if __name__=='__main__':main()
