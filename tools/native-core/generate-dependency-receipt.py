"""Capture actual Git HEADs and installed CIPD pins, never declared DEPS versions.

gclient revinfo --actual is restricted to Git because its CIPD implementation
can fall back to remote describe of a declared version. CIPD pins come only from
the official local `cipd installed -root ... -json-output ...` command. GCS
download declarations are not guessed or represented as resolved Git/CIPD pins.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

SOURCE_COMMIT='cfaadc5a132d78e1828635aa8405a499f3e14864'
DEPOT_COMMIT='a03dfbf7f2d1cefa2795d81d59ca4f16c8616a8f'
PUBLIC_HOSTS=frozenset(x+'.googlesource.com' for x in
    ('aomedia','boringssl','chromium','dawn','pdfium','quiche','skia','swiftshader','webrtc'))

def relative(raw):
    if not isinstance(raw,str) or not raw or len(raw)>1024 or re.search(r'[\\:<>"|?*\x00-\x20]',raw):
        raise ValueError('Unsafe dependency path')
    if PurePosixPath(raw).is_absolute() or any(x in ('','.','..') for x in raw.split('/')):
        raise ValueError('Unsafe dependency path')
    return raw

def public_origin(raw):
    if not isinstance(raw,str) or re.search(r'[\x00-\x20\\]',raw):
        raise ValueError('Unsafe dependency origin')
    u=urlsplit(raw)
    if u.scheme!='https' or u.hostname not in PUBLIC_HOSTS or u.username or u.password or u.query or u.fragment or u.port or not u.path or '@' in raw:
        raise ValueError('Dependency origin is not an approved public upstream URL')
    return raw

def create_receipt(git_info,installed):
    if not isinstance(git_info,dict) or not git_info:
        raise ValueError('Actual Git dependency report is missing')
    root=git_info.get('src',{})
    if root.get('rev')!=SOURCE_COMMIT or root.get('url')!='https://chromium.googlesource.com/chromium/src.git':
        raise ValueError('Actual source root is not pinned')
    records=[]
    for path,item in sorted(git_info.items()):
        if not isinstance(item,dict) or set(item)!={'url','rev'} or not re.fullmatch(r'[a-f0-9]{40}',str(item.get('rev',''))):
            raise ValueError('Actual Git report has an unresolved revision')
        records.append({'path':relative(path),'origin':public_origin(item['url']),
            'revision':item['rev'],'kind':'git'})
    if not isinstance(installed,dict) or set(installed)!={'result'} or not isinstance(installed['result'],dict) or not installed['result']:
        raise ValueError('Installed CIPD report is missing')
    seen=set()
    for path,packages in sorted(installed['result'].items()):
        relative(path)
        if not isinstance(packages,list) or not packages:raise ValueError('Invalid installed package list')
        for item in packages:
            if not isinstance(item,dict) or not isinstance(item.get('pin'),dict):raise ValueError('Missing installed CIPD pin')
            pin=item['pin'];package=pin.get('package');instance=pin.get('instance_id')
            if not isinstance(package,str) or not re.fullmatch(r'(?:chromium|infra|gn|skia|build)/[A-Za-z0-9_./-]+',package) or item.get('package')!=package:
                raise ValueError('Unknown or malformed installed package name')
            relative(package)
            if not isinstance(instance,str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,64}',instance):raise ValueError('Unresolved installed CIPD instance')
            identity=(path,package)
            if identity in seen:raise ValueError('Duplicate installed CIPD package')
            seen.add(identity)
            records.append({'path':path,'package':package,'instance_id':instance,'kind':'cipd'})
    return {'format':'neantik-resolved-dependency-receipt','schema':1,
        'source_commit':SOURCE_COMMIT,'resolved_dependencies':records}

def command(arguments,cwd,env):
    result=subprocess.run(arguments,cwd=cwd,env=env,capture_output=True,timeout=240)
    if result.returncode:raise ValueError('Read-only dependency command failed; raw output withheld')
    return result.stdout.decode('utf-8').strip()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',type=Path,required=True)
    parser.add_argument('--depot-tools',type=Path,required=True)
    parser.add_argument('--gitconfig',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    client=args.client.resolve();depot=args.depot_tools.resolve()
    if not args.gitconfig.is_file() or not (client/'.gclient').is_file():raise ValueError('Required client/config missing')
    env=dict(os.environ,DEPOT_TOOLS_UPDATE='0',DEPOT_TOOLS_WIN_TOOLCHAIN='0',GIT_CONFIG_GLOBAL=str(args.gitconfig.resolve()))
    if command(['git','-C',str(depot),'rev-parse','HEAD'],client,env)!=DEPOT_COMMIT:raise ValueError('depot_tools pin mismatch')
    if command(['git','-C',str(client/'src'),'rev-parse','HEAD'],client,env)!=SOURCE_COMMIT:raise ValueError('Chromium source pin mismatch')
    with tempfile.TemporaryDirectory(prefix='neantik-resolved-dependencies-') as temp:
        git_path=Path(temp)/'git.json';cipd_path=Path(temp)/'cipd.json'
        command([str(depot/'gclient.bat'),'revinfo','--actual','--ignore-dep-type=cipd',
            '--ignore-dep-type=gcs','--output-json='+str(git_path)],client,env)
        command([str(depot/'cipd.bat'),'installed','-root',str(client),'-json-output',str(cipd_path)],client,env)
        receipt=create_receipt(json.loads(git_path.read_text()),json.loads(cipd_path.read_text()))
    # Reject tool pin movement during capture and serialize only curated records.
    if command(['git','-C',str(depot),'rev-parse','HEAD'],client,env)!=DEPOT_COMMIT:raise ValueError('depot_tools changed during capture')
    if command(['git','-C',str(client/'src'),'rev-parse','HEAD'],client,env)!=SOURCE_COMMIT:raise ValueError('Source changed during capture')
    output=args.output.absolute()
    if output.exists() or not output.parent.is_dir() or any(p.is_symlink() or p.is_junction() for p in (output.parent,*output.parent.parents)):
        raise ValueError('Receipt output must be a new file in an existing non-linked directory')
    raw=(json.dumps(receipt,indent=2)+'\n').encode('utf-8')
    with output.open('xb') as handle:handle.write(raw)
    print(json.dumps({'records':len(receipt['resolved_dependencies']),
        'git':sum(x['kind']=='git' for x in receipt['resolved_dependencies']),
        'cipd':sum(x['kind']=='cipd' for x in receipt['resolved_dependencies']),
        'sha256':hashlib.sha256(raw).hexdigest()}))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.TimeoutExpired):
        raise SystemExit('Dependency receipt capture failed; private diagnostics withheld')
