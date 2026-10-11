"""Generate006 from a hash-verified applied001..005 checkout; never edit it."""
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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    contract=json.loads((HERE/'buildspec.json').read_text())['patch_contract']
    if len(contract['patch_series'])!=5:
        raise RuntimeError('Expected exactly immutable001..005 as input')
    head=subprocess.check_output(['git','-C',str(args.source),'rev-parse','HEAD'],text=True).strip()
    if head!=seed.PIN:raise RuntimeError('Unexpected source HEAD')
    for entry in contract['patch_series']:
        if hashlib.sha256((seed.ROOT/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:
            raise RuntimeError('Input patch hash mismatch')
    for path,expected in contract['postimage_sha256'].items():
        if hashlib.sha256((args.source/path).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Input checkout postimage mismatch: '+path)
    before={p:(args.source/p).read_text(encoding='utf-8') for p in (seed.MAIN,seed.TEST)}
    after=dict(before)
    after[seed.MAIN]=seed.replace(after[seed.MAIN],r'\",\"capabilities\":{\"stable_seed\":true,',
        r'\",\"source_commit\":\"'+seed.PIN+r'\",\"capability_evidence\":\"compiled-source-only\",\"capabilities\":{\"stable_seed\":true,')
    after[seed.MAIN]=seed.replace(after[seed.MAIN],r'\"canvas\":false,\"timezone\":true},\"compiled_stage\":4}',
        r'\"canvas\":false,\"canvas_opaque_srgb_uint8\":true,\"canvas_float16\":false,\"canvas_display_p3\":false,\"canvas_translucent\":false,\"timezone\":true},\"compiled_stage\":6}')
    tests=r'''
TEST(NeAntikFingerprintTest, RejectsUnknownBareFlagsWithAndWithoutSeed) {
  for (bool seeded : {false, true}) {
    auto command = seeded ? Seeded() : base::CommandLine(base::CommandLine::NO_PROGRAM);
    command.AppendSwitch("neantik-unsupported-native-surface");
    std::string error;
    EXPECT_FALSE(ParseFingerprintConfig(command, &error));
    EXPECT_FALSE(error.empty());
  }
}

TEST(NeAntikFingerprintTest, RejectsMissingValuesForAllPersonaFlags) {
  for (const char* flag : {kSeedSwitch, kHardwareConcurrencySwitch,
                           kDeviceMemorySwitch, kTimeZoneSwitch}) {
    auto command = flag == std::string(kSeedSwitch)
        ? base::CommandLine(base::CommandLine::NO_PROGRAM) : Seeded();
    command.AppendSwitch(flag);
    std::string error;
    EXPECT_FALSE(ParseFingerprintConfig(command, &error)) << flag;
    EXPECT_FALSE(error.empty()) << flag;
  }
}

TEST(NeAntikFingerprintTest, CoreInfoWithoutPersonaDoesNotActivateIdentity) {
  base::CommandLine command(base::CommandLine::NO_PROGRAM);
  command.AppendSwitchASCII(kCoreInfoSwitch, "native-core-info.json");
  std::string error;
  EXPECT_FALSE(ParseFingerprintConfig(command, &error));
  EXPECT_TRUE(error.empty());
}
'''
    end='}  // namespace\n}  // namespace blink::neantik\n'
    after[seed.TEST]=seed.replace(after[seed.TEST],end,tests+'\n'+end)
    patch=seed.diff(before,after)
    patch_path=seed.PATCHES/'006-core-capability-scope.patch'
    patch_path.write_text(patch,encoding='utf-8',newline='\n')
    with tempfile.TemporaryDirectory(prefix='neantik006-check-') as temp:
        fixture=Path(temp)
        for p,s in before.items():
            dest=fixture/p;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(s,encoding='utf-8',newline='\n')
        subprocess.run(['git','init','--quiet',str(fixture)],check=True)
        subprocess.run(['git','-C',str(fixture),'config','core.autocrlf','false'],check=True)
        subprocess.run(['git','-C',str(fixture),'apply','--check',str(patch_path)],check=True)
        subprocess.run(['git','-C',str(fixture),'apply',str(patch_path)],check=True)
        for p,s in after.items():
            if (fixture/p).read_text()!=s:raise RuntimeError('006 postimage mismatch')
    postimages=dict(contract['postimage_sha256'])
    postimages.update({p:hashlib.sha256(s.encode()).hexdigest() for p,s in after.items()})
    proof={'source_commit':seed.PIN,'source_version':'155.0.8059.40',
        'patches':contract['patch_series']+[{'path':'core/patches/'+patch_path.name,
        'sha256':hashlib.sha256(patch.encode()).hexdigest()}],
        '006_exact_post005_apply_check':'passed','compilation':'not-run',
        'runtime_fingerprint_verification':'not-run','postimage_sha256':postimages}
    (seed.PATCHES/'capability-chain-provenance.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(proof,indent=2))

if __name__=='__main__':main()
