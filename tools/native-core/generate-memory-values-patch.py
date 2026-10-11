"""Author008 against hash-verified post007, checking only a disposable fixture."""
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
    if len(contract['patch_series'])!=7:raise RuntimeError('Expected immutable001..007 input')
    if subprocess.check_output(['git','-C',str(args.source),'rev-parse','HEAD'],text=True).strip()!=seed.PIN:
        raise RuntimeError('Source pin mismatch')
    for entry in contract['patch_series']:
        if hashlib.sha256((seed.ROOT/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:
            raise RuntimeError('Prior patch changed')
    for path,expected in contract['postimage_sha256'].items():
        if hashlib.sha256((args.source/path).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Post007 source changed: '+path)
    before={p:(args.source/p).read_text(encoding='utf-8') for p in (seed.SOURCE,seed.TEST)}
    after=dict(before)
    after[seed.SOURCE]=seed.replace(after[seed.SOURCE],
        'constexpr std::array<std::pair<std::string_view, float>, 8> kValues = {{\n        {"0.25", 0.25f}, {"0.5", 0.5f}, {"1", 1.0f}, {"2", 2.0f},\n        {"4", 4.0f}, {"8", 8.0f}, {"16", 16.0f}, {"32", 32.0f}}};',
        '// Match exact Windows155 stock device-memory quantization limits.\n    constexpr std::array<std::pair<std::string_view, float>, 5> kValues = {{\n        {"2", 2.0f}, {"4", 4.0f}, {"8", 8.0f}, {"16", 16.0f},\n        {"32", 32.0f}}};')
    after[seed.SOURCE]=seed.replace(after[seed.SOURCE],
        'NeAntik device memory must be one of 0.25,0.5,1,2,4,8,16,32',
        'NeAntik Windows155 device memory must be one of 2,4,8,16,32')
    after[seed.TEST]=seed.replace(after[seed.TEST],
        'for (const char* value : {"0.25", "0.5", "1", "2", "4", "8", "16", "32"})',
        'for (const char* value : {"2", "4", "8", "16", "32"})')
    after[seed.TEST]=seed.replace(after[seed.TEST],
        'for (const char* value : {"", "0", "3", "64", "NaN", "inf", "8.0", "-8"})',
        'for (const char* value : {"", "0", "0.25", "0.5", "1", "3", "64",\n                           "NaN", "inf", "8.0", "-8"})')
    extra=r'''
TEST(NeAntikFingerprintTest, RejectsLegacyLowWindowsMemoryWithoutClamping) {
  for (const char* value : {"0.25", "0.5", "1"}) {
    auto command = Seeded();
    command.AppendSwitchASCII(kDeviceMemorySwitch, value);
    std::string error;
    EXPECT_FALSE(ParseFingerprintConfig(command, &error));
    EXPECT_NE(error.find("Windows155"), std::string::npos);
    EXPECT_EQ(command.GetSwitchValueASCII(kDeviceMemorySwitch), value);
  }
}
'''
    end='}  // namespace\n}  // namespace blink::neantik\n'
    after[seed.TEST]=seed.replace(after[seed.TEST],end,extra+'\n'+end)
    patch=seed.diff(before,after);patch_path=seed.PATCHES/'008-windows155-memory-values.patch'
    patch_path.write_text(patch,encoding='utf-8',newline='\n')
    with tempfile.TemporaryDirectory(prefix='neantik008-scratch-') as temp:
        fixture=Path(temp)
        for path,value in before.items():
            target=fixture/path;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(value,encoding='utf-8',newline='\n')
        subprocess.run(['git','init','--quiet',str(fixture)],check=True)
        subprocess.run(['git','-C',str(fixture),'config','core.autocrlf','false'],check=True)
        subprocess.run(['git','-C',str(fixture),'apply','--check',str(patch_path)],check=True)
        subprocess.run(['git','-C',str(fixture),'apply',str(patch_path)],check=True)
        for path,value in after.items():
            if (fixture/path).read_text()!=value:raise RuntimeError('008 postimage mismatch')
    postimages=dict(contract['postimage_sha256'])
    postimages.update({path:hashlib.sha256(value.encode()).hexdigest() for path,value in after.items()})
    proof={'source_commit':seed.PIN,'source_version':'155.0.8059.40',
        'patches':contract['patch_series']+[{'path':'core/patches/'+patch_path.name,
            'sha256':hashlib.sha256(patch.encode()).hexdigest()}],
        '008_exact_post007_scratch_apply_check':'passed',
        'actual_checkout_008_applied':False,'compilation':'not-run',
        'runtime_fingerprint_verification':'not-run','postimage_sha256':postimages}
    (seed.PATCHES/'memory-chain-provenance.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'patch_sha256':proof['patches'][-1]['sha256'],'postimages':len(postimages),'actual_checkout_008_applied':False}))

if __name__=='__main__':main()
