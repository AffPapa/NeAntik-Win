"""Evidence-only QA for our exact Chromium155 native core, never the150 prototype.

Requires a trusted manifest SHA-256 from the release/build verification step.
Checks every bundle member, runs the compiled core-info command, then observes
normal web APIs in fresh loopback profiles. No CDP, extensions, stealth injection
or stock fallback. Any missing result, timeout or unsupported required API fails.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import statistics
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
import current_core

VERSION = '155.0.8059.40'
COMMIT = 'cfaadc5a132d78e1828635aa8405a499f3e14864'
FIXTURES = Path(__file__).with_name('fixtures')
CONTEXTS = ('main','sameIframe','crossIframe','dedicatedWorker','sharedWorker','serviceWorker')
FIELDS = ('hardwareConcurrency','deviceMemory','timezone','winterOffset','summerOffset','beforeDst','afterDst')
ZONE_EXPECTATIONS = {'Europe/Berlin':(-60,-120,-60,-120),
                     'America/New_York':(300,240,240,240),
                     'Asia/Kolkata':(-330,-330,-330,-330)}
MASK = (1 << 64) - 1


class HarnessError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise HarnessError(message)


def file_hash(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def unique_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:
                raise HarnessError('Duplicate JSON key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs)


def verify_bundle(portable_root, trusted_digest):
    require(current_core.ENGINE_VERSION == VERSION and current_core.SOURCE_COMMIT == COMMIT,
            'Harness and application core pins disagree')
    require(re.fullmatch('[a-f0-9]{64}', trusted_digest) is not None, 'Trusted manifest hash must be lowercase SHA-256')
    directory = portable_root.resolve() / current_core.ENGINE_DIRECTORY
    require(directory.is_dir(), 'Own current native bundle is missing')
    for parent in (directory,directory.parent):
        require(not parent.is_symlink() and not parent.is_junction(),'Native bundle root is linked')
    manifest_path = directory / current_core.MANIFEST_NAME
    require(manifest_path.is_file() and manifest_path.stat().st_size <= 2*1024*1024,'Missing or oversized manifest')
    require(file_hash(manifest_path) == trusted_digest,'Manifest differs from independently trusted hash')
    manifest = unique_json(manifest_path.read_text(encoding='utf-8'))
    require(isinstance(manifest,dict),'Manifest must be an object')
    for key,value in {'format':current_core.MANIFEST_FORMAT,'engine_id':'neantik-chromium',
                      'version':VERSION,'source_commit':COMMIT,'schema':1}.items():
        require(type(manifest.get(key)) is type(value) and manifest[key] == value,'Unknown native core '+key)
    files=manifest.get('files')
    require(isinstance(files,dict) and {'chrome.exe','chrome.dll'} <= files.keys(),'Native runtime files missing from manifest')
    seen=set()
    reserved={'con','prn','aux','nul',*(f'com{i}' for i in range(1,10)),*(f'lpt{i}' for i in range(1,10))}
    for name,digest in files.items():
        require(isinstance(name,str) and name and not PurePosixPath(name).is_absolute() and
                '\\' not in name and ':' not in name and name.casefold() != current_core.MANIFEST_NAME,
                'Unsafe native member name')
        parts=name.split('/')
        require(all(part not in ('','.','..') and not part.endswith(('.',' ')) and
                    part.split('.')[0].casefold() not in reserved for part in parts),'Unsafe native member component')
        require(name.casefold() not in seen,'Duplicate native member')
        seen.add(name.casefold())
        require(isinstance(digest,str) and re.fullmatch('[a-f0-9]{64}',digest),'Invalid native member hash')
        member=directory.joinpath(*parts)
        require(member.is_file() and not member.is_symlink() and not member.is_junction(),'Linked or missing native member')
        require(file_hash(member)==digest,'Native member hash mismatch: '+name)
    actual=set()
    for member in directory.rglob('*'):
        require(not member.is_symlink() and not member.is_junction(),'Native tree contains a link')
        if member.is_file() and member != manifest_path:
            actual.add(member.relative_to(directory).as_posix().casefold())
    require(actual==seen,'Manifest and actual native tree differ')
    return directory/'chrome.exe', {'manifest_sha256':trusted_digest,'files_verified':len(seen),
        'engine_id':'neantik-chromium','version':VERSION,'source_commit':COMMIT,
        'source_commit_is_manifest_assertion_not_runtime_attestation':True}


class BasicLimits(ctypes.Structure):
    _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',wintypes.DWORD),
      ('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active_limit',wintypes.DWORD),
      ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
class IoCounters(ctypes.Structure):
    _fields_=[(name,ctypes.c_uint64) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
class ExtendedLimits(ctypes.Structure):
    _fields_=[('basic',BasicLimits),('io',IoCounters),('process_memory',ctypes.c_size_t),
      ('job_memory',ctypes.c_size_t),('peak_process_memory',ctypes.c_size_t),('peak_job_memory',ctypes.c_size_t)]
class Accounting(ctypes.Structure):
    _fields_=[(name,ctypes.c_int64) for name in ('user','kernel','period_user','period_kernel')]+[
      (name,wintypes.DWORD) for name in ('faults','total','active','terminated')]


class OwnedJob:
    def __init__(self):
        require(os.name=='nt','This harness requires Windows Jobs')
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        for name,args,result in (
            ('CreateJobObjectW',[ctypes.c_void_p,wintypes.LPCWSTR],wintypes.HANDLE),
            ('SetInformationJobObject',[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD],wintypes.BOOL),
            ('QueryInformationJobObject',[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p],wintypes.BOOL),
            ('AssignProcessToJobObject',[wintypes.HANDLE,wintypes.HANDLE],wintypes.BOOL),
            ('CloseHandle',[wintypes.HANDLE],wintypes.BOOL)):
            function=getattr(self.kernel,name);function.argtypes=args;function.restype=result
        self.handle=self.kernel.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        limits=ExtendedLimits();limits.basic.flags=0x2000
        if not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            error=ctypes.WinError(ctypes.get_last_error());self.close();raise error
    def assign(self,process):
        if not self.kernel.AssignProcessToJobObject(self.handle,int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
    def statistics(self):
        account=Accounting();limits=ExtendedLimits()
        for klass,value in ((1,account),(9,limits)):
            if not self.kernel.QueryInformationJobObject(self.handle,klass,ctypes.byref(value),ctypes.sizeof(value),None):
                raise ctypes.WinError(ctypes.get_last_error())
        return {'active_processes':int(account.active),'total_processes':int(account.total),
          'cpu_seconds':(account.user+account.kernel)/10_000_000,
          'peak_job_committed_bytes':int(limits.peak_job_memory),
          'peak_process_committed_bytes':int(limits.peak_process_memory)}
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None


GATE="""import sys,subprocess
if sys.stdin.buffer.read(1)!=b'G':raise SystemExit(97)
raise SystemExit(subprocess.run(sys.argv[1:],stdin=subprocess.DEVNULL,
  creationflags=subprocess.CREATE_NO_WINDOW).returncode)
"""


def run_owned(arguments,folder,timeout=65):
    job=OwnedJob();process=None;started=time.monotonic()
    try:
        process=subprocess.Popen([sys.executable,'-I','-S','-c',GATE,*arguments],cwd=folder,
          stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
          creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
        job.assign(process)
        stdout,stderr=process.communicate(input=b'G',timeout=timeout)
        deadline=time.monotonic()+5
        stats=job.statistics()
        while stats['active_processes'] and time.monotonic()<deadline:
            time.sleep(0.1);stats=job.statistics()
        require(stats['active_processes']==0,'Owned browser descendants did not exit naturally')
        return stdout,stderr,{'return_code':process.returncode,'elapsed_seconds':time.monotonic()-started,**stats}
    finally:
        job.close()  # Contains only the gated new helper and its descendants.
        if process:
            try:process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                if process.poll() is None:process.kill()
                process.communicate(timeout=5)


def probe(browser,root):
    folder=root/'probe';folder.mkdir();output=folder/'info.json'
    _,_,stats=run_owned([str(browser),f'--user-data-dir={folder / "profile"}',
      f'--neantik-core-info={output}','--no-first-run','--no-default-browser-check'],folder,20)
    require(stats['return_code']==0 and output.is_file() and output.stat().st_size<=65536,'Actual core-info handshake failed')
    info=unique_json(output.read_text(encoding='utf-8'))
    validate_probe_info(info)
    return {'actual_info':info,'process':stats,'scope':'Authored capability declaration; observations still required'}


def validate_probe_info(info):
    require(isinstance(info,dict),'Core-info is not an object')
    require(info.get('engine_id')=='neantik-chromium' and info.get('version')==VERSION and
            info.get('source_commit')==COMMIT and type(info.get('schema')) is int and
            info['schema']==1,'Actual binary is not our exact core')
    require(info.get('capability_evidence')=='compiled-source-only',
            'Unrecognized capability declaration evidence contract')
    caps=info.get('capabilities')
    require(isinstance(caps,dict) and all(caps.get(name) is True for name in
      ('stable_seed','hardware_concurrency','device_memory','canvas_opaque_srgb_uint8','timezone')),
      'Actual core is incomplete for the required fingerprint test cycle')
    require(all(caps.get(name) is False for name in
      ('canvas','canvas_float16','canvas_display_p3','canvas_translucent')),
      'Core-info overstated unsupported Canvas coverage')


def malformed_input_checks(browser,root):
    checks=[]
    cases={'zero_seed':['--neantik-fingerprint-seed=0'],
      'unknown_namespace':['--neantik-not-a-feature=1'],
      'orphan_cpu':['--neantik-hardware-concurrency=8'],
      'invalid_cpu':['--neantik-fingerprint-seed=123','--neantik-hardware-concurrency=0'],
      'unknown_iana':['--neantik-fingerprint-seed=123','--neantik-timezone=Not/AReal_Zone']}
    for label,flags in cases.items():
        folder=root/('reject-'+label);folder.mkdir()
        _,stderr,stats=run_owned([str(browser),f'--user-data-dir={folder / "profile"}',
          '--headless','--no-first-run','--no-default-browser-check',*flags],folder,20)
        require(stats['return_code']==78,'Malformed native input was not rejected: '+label)
        checks.append({'name':label,'passed':True,'process':stats,
          'stderr_tail':stderr.decode('utf-8','replace').replace(str(root),'<qa-root>')[-1000:]})
    return checks


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,state):
        super().__init__(('127.0.0.1',0),Handler);self.state=state;self.cross=''
        self.read_js=(FIXTURES/'current-native-surfaces.js').read_text(encoding='utf-8')
        self.driver_js=(FIXTURES/'current-native-driver.js').read_text(encoding='utf-8')


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,body,mime='text/plain; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('Accept-CH','Device-Memory, Sec-CH-Device-Memory, Sec-CH-UA-Full-Version-List')
        self.send_header('Permissions-Policy','ch-device-memory=(self "'+self.server.cross+'")')
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def case(self):
        parsed=urlsplit(self.path)
        if parsed.scheme or parsed.netloc:return None,'',{}
        query=parse_qs(parsed.query)
        return self.server.state.get(query.get('token',[''])[0]),parsed.path,query
    def do_CONNECT(self):self.reply(403,b'No external proxy forwarding')
    def do_GET(self):
        case,path,query=self.case()
        if case is None:return self.reply(403,b'Unknown test token; no forwarding')
        token=query['token'][0]
        config='const CONFIG='+json.dumps({'token':token,'cross':self.server.cross})+';'
        script=config+self.server.read_js
        if path=='/case':
            page='<!doctype html><meta charset="utf-8"><title>Own155 native QA</title><pre id="current-native-result">pending</pre>'
            page+='<img src="/barrier?token='+token+'" alt="load barrier"><script>'+script+self.server.driver_js+'</script>'
            return self.reply(200,page.encode(),'text/html; charset=utf-8')
        if path=='/frame':
            script+='fpReadSurface().then(result=>parent.postMessage({label:'+json.dumps(query['label'][0])+',result},"*"));'
            return self.reply(200,('<script>'+script+'</script>').encode(),'text/html; charset=utf-8')
        if path in ('/worker.js','/shared.js','/service.js'):
            endings={'/worker.js':'fpReadSurface().then(result=>postMessage(result));',
              '/shared.js':'onconnect=e=>{const p=e.ports[0];fpReadSurface().then(result=>p.postMessage(result));};',
              '/service.js':"oninstall=e=>e.waitUntil(skipWaiting());onactivate=e=>e.waitUntil(clients.claim());onmessage=e=>e.waitUntil(fpReadSurface().then(result=>e.ports[0].postMessage(result)));"}
            return self.reply(200,(script+endings[path]).encode(),'application/javascript; charset=utf-8')
        if path=='/headers':return self.reply(200,json.dumps(dict(self.headers)).encode(),'application/json')
        if path=='/barrier':
            case['ready'].wait(55);return self.reply(200,b'','image/png')
        self.reply(404,b'Unknown fixture route')
    def do_POST(self):
        case,path,query=self.case()
        if case is None or path!='/report':return self.reply(404,b'Unknown report')
        try:
            length=int(self.headers.get('Content-Length','0'))
            require(0<length<=2*1024*1024,'Report size invalid')
            result=unique_json(self.rfile.read(length).decode('utf-8'))
            require(isinstance(result,dict) and result.get('token')==query['token'][0],'Report token mismatch')
            with case['lock']:
                require(case['result'] is None,'Duplicate report')
                case['result']=result
            self.reply(200,b'OK');case['ready'].set()
        except (ValueError,UnicodeError,HarnessError):self.reply(400,b'Invalid report')


def mix(seed,position):
    value=(seed ^ 0x43414e5641530001 ^ ((position+0x9e3779b97f4a7c15)&MASK))&MASK
    value=((value^(value>>30))*0xbf58476d1ce4e5b9)&MASK
    value=((value^(value>>27))*0x94d049bb133111eb)&MASK
    return value^(value>>31)


def expected_pixels(seed=None):
    result=bytearray()
    for y in range(24):
        for x in range(32):
            rgb=(198,146,72) if 2<=x<11 and 3<=y<10 else (43,87,131)
            bits=mix(seed,(y<<32)|x) if seed is not None else None
            result.extend((value if bits is None else (value&254)|((bits>>channel)&1)) for channel,value in enumerate(rgb))
            result.append(255)
    return result.hex()


def visit(browser,root,server,label,seed,cpu=8,memory='8',zone='Europe/Berlin'):
    token=uuid.uuid4().hex
    case={'ready':threading.Event(),'result':None,'lock':threading.Lock()};server.state[token]=case
    profile=root/('A' if label in ('A','A restart') else label.replace(' ','-'));profile.mkdir(exist_ok=True)
    args=[str(browser),'--headless','--dump-dom',f'--user-data-dir={profile}','--timeout=55000',
      '--no-first-run','--no-default-browser-check','--disable-background-networking',
      '--disable-component-update','--disable-sync','--disable-extensions','--disable-quic',
      '--metrics-recording-only','--site-per-process',f'--proxy-server=http://127.0.0.1:{server.server_port}',
      '--proxy-bypass-list=127.0.0.1;localhost',
      '--host-resolver-rules=MAP localhost 127.0.0.1, MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']
    if seed is not None:
        identity=current_core.new_identity(cpu=cpu,memory=memory);identity['seed']=seed
        args+=current_core.identity_arguments(identity)+[f'--neantik-timezone={zone}']
    args+=[f'http://127.0.0.1:{server.server_port}/case?token={token}']
    stdout,stderr,stats=run_owned(args,profile)
    match=re.search(r'<pre id="current-native-result">(.*?)</pre>',stdout.decode('utf-8','replace'),re.S)
    dom=unique_json(html.unescape(match.group(1))) if match else None
    result=case['result']
    return {'label':label,'seed':seed,'expected_cpu':cpu,'expected_memory':memory,'expected_timezone':zone,
      'process':stats,'result':result,'dom_matches_server':result is not None and dom==result,
      'stderr_tail':stderr.decode('utf-8','replace').replace(str(root),'<qa-root>')[-3000:]}


def assess(visits):
    checks=[]
    def add(name,condition):checks.append({'name':name,'passed':bool(condition)})
    for run in visits:
        label=run['label'];result=run.get('result') or {};seed=run['seed']
        add(label+': complete server/DOM result and natural exit',run['process'].get('return_code')==0 and
            run['process'].get('active_processes')==0 and run.get('dom_matches_server') and 'error' not in result)
        expected=expected_pixels(seed)
        expected_bytes=bytes.fromhex(expected)
        subregion=b''.join(expected_bytes[(y*32+4)*4:(y*32+11)*4] for y in range(5,13)).hex()
        main=result.get('main') or {}
        for context in CONTEXTS:
            surface=result.get(context) or {};canvas=surface.get('canvas') or {}
            add(label+': '+context+' returned real API observations',bool(surface) and 'error' not in surface)
            if seed is not None:
                wanted={'hardwareConcurrency':run['expected_cpu'],'deviceMemory':float(run['expected_memory']),
                  'timezone':run['expected_timezone'],**dict(zip(('winterOffset','summerOffset','beforeDst','afterDst'),
                  ZONE_EXPECTATIONS[run['expected_timezone']]))}
                add(label+': '+context+' CPU/memory/IANA/DST match',all(surface.get(key)==value for key,value in wanted.items()))
            add(label+': '+context+' pixels match native reference',canvas.get('first')==expected)
            for field in ('repeated','afterExports','putImageData','blob'):
                add(label+': '+context+' '+field+' consistency',canvas.get(field)==expected)
            if context in ('main','sameIframe','crossIframe'):
                add(label+': '+context+' HTML dataURL consistency',canvas.get('dataURL')==expected)
            add(label+': '+context+' subrect/OOB/clear semantics',canvas.get('subrect')==subregion and
                canvas.get('outOfBounds')=='00000000' and canvas.get('cleared') is True)
            headers={key.lower():value for key,value in (surface.get('requestHeaders') or {}).items()}
            add(label+': '+context+' HTTP UA matches JS',bool(headers.get('user-agent')) and headers['user-agent']==surface.get('userAgent'))
            if seed is not None:
                memory_header=headers.get('sec-ch-device-memory',headers.get('device-memory'))
                try:matches=float(memory_header)==float(run['expected_memory'])
                except (TypeError,ValueError):matches=False
                add(label+': '+context+' HTTP device-memory matches JS',matches)
        add(label+': early first-script values match main',bool(result.get('early')) and all(
            result['early'].get(key)==main.get(key) for key in FIELDS))
        offscreen=result.get('offscreen') or {}
        add(label+': main OffscreenCanvas matches native reference',offscreen.get('kind')=='OffscreenCanvas' and
            all(offscreen.get(key)==expected for key in ('first','repeated','blob','afterExports','putImageData')))
        perf=result.get('largeCanvas') or {}
        add(label+': large-canvas timing and output captured',perf.get('width')==2048 and perf.get('height')==2048 and
            isinstance(perf.get('readbackMs'),list) and len(perf['readbackMs'])==3 and all(
                type(value) in (int,float) and math.isfinite(value) and value>=0 for value in perf['readbackMs']) and
            isinstance(perf.get('lastDigest'),str) and re.fullmatch('[a-f0-9]{64}',perf['lastDigest']) is not None and
            isinstance(perf.get('pngBytes'),int) and perf['pngBytes']>0)
        add(label+': native process memory accounting captured',
            run['process'].get('peak_job_committed_bytes',0)>0 and run['process'].get('peak_process_committed_bytes',0)>0)
    by_label={run['label']:run for run in visits}
    add('Required baseline/A/A-restart/B/hardware-timezone cases present',
        {'Baseline','A','A restart','B','Hardware timezone'} <= by_label.keys())
    if {'A','A restart','B'} <= by_label.keys():
        a,again,b=(by_label[name].get('result') or {} for name in ('A','A restart','B'))
        for context in CONTEXTS:
            x,y,z=(value.get(context) or {} for value in (a,again,b))
            add(context+': A/A restart identity stable',bool(x) and all(x.get(k)==y.get(k) for k in FIELDS) and
                (x.get('canvas') or {}).get('first')==(y.get('canvas') or {}).get('first'))
            add(context+': A/B canvas seeds differ',bool((x.get('canvas') or {}).get('first')) and
                (x.get('canvas') or {}).get('first')!=(z.get('canvas') or {}).get('first'))
    return checks


def comparisons(visits):
    by_label={run['label']:run for run in visits}
    baseline=(by_label.get('Baseline',{}).get('result') or {}).get('largeCanvas') or {}
    timings={};bypass={}
    for run in visits:
        perf=(run.get('result') or {}).get('largeCanvas') or {}
        if isinstance(perf.get('readbackMs'),list) and len(perf['readbackMs'])==3:
            median=statistics.median(perf['readbackMs'])
            reference=statistics.median(baseline['readbackMs']) if baseline.get('readbackMs') else None
            timings[run['label']]={'readback_median_ms':median,'png_ms':perf.get('pngMs'),
                'readback_ratio_to_no_persona_same_core':median/reference if reference else None,
                'peak_job_committed_bytes':run['process'].get('peak_job_committed_bytes')}
    a=(by_label.get('A',{}).get('result') or {}).get('main') or {}
    b=(by_label.get('B',{}).get('result') or {}).get('main') or {}
    for name in ('translucent','displayP3','float16'):
        x=(a.get('canvas') or {}).get(name);y=(b.get('canvas') or {}).get(name)
        bypass[name]={'A':x,'B':y,'same_across_different_seeds':x==y if x is not None and y is not None else None,
                     'protected':False}
    return {'timings':timings,'known_bypass_observations':bypass,
      'limitations':'One baseline visit and three readbacks per case; no p95/cold-start or controlled lab performance claim.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable-root',type=Path,required=True)
    parser.add_argument('--trusted-manifest-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report={'format':'neantik-own155-native-qa-v1','created_utc':datetime.now(timezone.utc).isoformat(),
      'method':'Hash-verified own155 Windows core; actual core-info; loopback normal API observations; gated owned Windows Jobs',
      'os':platform.platform(),'python':platform.python_version(),'status':'started','visits':[],
      'limitations':['Headless only; GUI/extensions/real account flows need separate release QA.',
        'Canvas reference verifies opaque sRGB uint8; P3/float16/translucent bypass observations are recorded, not protected.',
        'Low-bit projection retains high RGB bits; no undetectability or bot-service bypass claim.',
        'Cross-site iframe policy forced; per-frame native process IDs are not inspected.',
        'Job peak memory includes all owned Chromium children and the gated Python helper, not only Canvas buffers.',
        'IANA test zones are fixtures; all ICU IDs and transitions are not exhaustively tested.']}
    servers=[];root=None
    try:
        require(os.name=='nt','Windows required')
        browser,verification=verify_bundle(args.portable_root,args.trusted_manifest_sha256)
        report['verification']=verification
        root=Path(tempfile.mkdtemp(prefix='neantik-own155-qa-'))
        report['probe']=probe(browser,root)
        report['malformed_inputs']=malformed_input_checks(browser,root)
        state={};server=Server(state);cross=Server(state);servers=[server,cross]
        server.cross=f'http://localhost:{cross.server_port}';cross.cross=f'http://127.0.0.1:{server.server_port}'
        for current in servers:threading.Thread(target=current.serve_forever,daemon=True).start()
        for label,seed,cpu,memory,zone in [('Baseline',None,8,'8','Europe/Berlin'),('A',123456,8,'8','Europe/Berlin'),
            ('A restart',123456,8,'8','Europe/Berlin'),('B',987654,8,'8','Europe/Berlin'),
            ('Hardware timezone',765432,16,'16','America/New_York')]:
            report['visits'].append(visit(browser,root,server,label,seed,cpu,memory,zone))
        report['assertions']=assess(report['visits'])
        report['comparisons']=comparisons(report['visits'])
        report['status']='passed' if report['assertions'] and all(item['passed'] for item in report['assertions']) else 'failed'
        _,final_verification=verify_bundle(args.portable_root,args.trusted_manifest_sha256)
        report['bundle_reverified_after_visits']=final_verification==verification
        if not report['bundle_reverified_after_visits']:report['status']='failed'
    except Exception as error:
        report['status']='failed';report['harness_error']=f'{type(error).__name__}: {error}'
        if root:report['harness_error']=report['harness_error'].replace(str(root),'<qa-root>')
    finally:
        for server in servers:server.shutdown();server.server_close()
        # Retain only disposable owned profiles for failure investigation; do not delete user files.
        report['disposable_profiles_retained']=root is not None
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'assertions':len(report.get('assertions',[])),
      'failed_checks':[item['name'] for item in report.get('assertions',[]) if not item['passed']],
      'error':report.get('harness_error')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
