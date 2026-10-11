"""Pinned native-core QA against disposable profiles and loopback fixtures.

No CDP, Playwright, extension, JS fingerprint injector, or runtime dependency.
JS below only reads normal web APIs. Headless is explicitly not headed GUI QA.
Run --help for interface. The ZIP and every extracted runtime member are verified
before any browser process is created. Only newly owned processes are stopped.
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
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid
import zipfile

PIN = "4d549c326e51ebbabf562fd365eb5380d9d4a81200da2c60f075c688d9a77e03"
VERSION = "150.0.7871.186"
SOURCE = "https://github.com/adryfish/fingerprint-chromium/releases/tag/150.0.7871.186"

READ_JS = r"""
async function digest(value) {
  const bytes = typeof value === 'string' ? new TextEncoder().encode(value) : value;
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
}
async function readSurface() {
  const n = navigator;
  const out = {userAgent:n.userAgent, platform:n.platform, language:n.language,
    languages:Array.from(n.languages || []), hardwareConcurrency:n.hardwareConcurrency,
    deviceMemory:n.deviceMemory ?? null, webdriver:n.webdriver ?? null,
    timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,
    offsetWinter:new Date('2026-01-15T12:00:00Z').getTimezoneOffset(),
    offsetSummer:new Date('2026-07-15T12:00:00Z').getTimezoneOffset(),
    userAgentData:null, canvas:null, webgl:null};
  if (n.userAgentData) {
    try { out.userAgentData = await n.userAgentData.getHighEntropyValues(
      ['architecture','bitness','model','platformVersion','fullVersionList','wow64']); }
    catch(e) {out.userAgentData={unsupported:String(e)};}
  }
  const makeCanvas = () => {
    if (typeof document !== 'undefined') return document.createElement('canvas');
    if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(300,120);
    throw new Error('Canvas API unavailable');
  };
  try {
    const c=makeCanvas(); c.width=300; c.height=120;
    const x=c.getContext('2d'); x.fillStyle='#f60';x.fillRect(3,4,240,85);
    x.font='18px Arial';x.fillStyle='#069';x.fillText('NeAntik native QA Ω 123',9,40);
    x.beginPath();x.arc(60,60,21,0,Math.PI*1.7);x.stroke();
    const pixels=()=>x.getImageData(0,0,300,120).data;
    out.canvas={first:await digest(pixels()),second:await digest(pixels()),
      textWidth:x.measureText('NeAntik native QA Ω 123').width};
    if(c.toDataURL) {
      out.canvas.dataURLFirst=await digest(c.toDataURL());
      out.canvas.dataURLSecond=await digest(c.toDataURL());
    } else out.canvas.dataURLUnsupported='OffscreenCanvas has no toDataURL';
  }catch(e){out.canvas={unsupported:String(e)};}
  try {
    const gl=makeCanvas().getContext('webgl');
    if(!gl)throw new Error('No WebGL context');
    const ext=gl.getExtension('WEBGL_debug_renderer_info');
    out.webgl={vendor:gl.getParameter(gl.VENDOR),renderer:gl.getParameter(gl.RENDERER),
      unmaskedVendor:ext?gl.getParameter(ext.UNMASKED_VENDOR_WEBGL):null,
      unmaskedRenderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):null,
      maxTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE)};
  }catch(e){out.webgl={unsupported:String(e)};}
  if(typeof window!=='undefined') out.window={screenWidth:screen.width,screenHeight:screen.height,
    availWidth:screen.availWidth,availHeight:screen.availHeight,colorDepth:screen.colorDepth,
    devicePixelRatio,innerWidth,innerHeight,outerWidth,outerHeight,
    prefersDark:matchMedia('(prefers-color-scheme: dark)').matches};
  return out;
}
"""
MAIN_JS = r"""
const early = {userAgent:navigator.userAgent,platform:navigator.platform,
  hardwareConcurrency:navigator.hardwareConcurrency,language:navigator.language,
  timezone:Intl.DateTimeFormat().resolvedOptions().timeZone};
fetch('/early?token='+TOKEN,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(early)}).catch(()=>{});
function bounded(p,label) {
  return Promise.race([p,new Promise(r=>setTimeout(()=>r({unsupported:label+' timed out'}),10000))]);
}
function frame(origin,label) {
  return bounded(new Promise(resolve=>{
    const f=document.createElement('iframe');
    const receive=e=>{if(e.source===f.contentWindow && e.data?.label===label){
      removeEventListener('message',receive);resolve(e.data.result);}};
    addEventListener('message',receive);
    f.src=origin+'/frame?token='+TOKEN+'&label='+label;document.body.append(f);
  }),label);
}
function dedicated() {
  if(!globalThis.Worker)return Promise.resolve({unsupported:'Worker unavailable'});
  return bounded(new Promise(resolve=>{const w=new Worker('/worker.js?token='+TOKEN);
    w.onmessage=e=>{w.terminate();resolve(e.data);};w.onerror=e=>resolve({unsupported:String(e.message)});
  }),'dedicatedWorker');
}
function shared() {
  if(!globalThis.SharedWorker)return Promise.resolve({unsupported:'SharedWorker unavailable'});
  return bounded(new Promise(resolve=>{const w=new SharedWorker('/shared.js?token='+TOKEN);
    w.port.onmessage=e=>{w.port.close();resolve(e.data);};w.port.start();
    w.onerror=e=>resolve({unsupported:String(e.message)});
  }),'sharedWorker');
}
async function service() {
  if(!navigator.serviceWorker)return {unsupported:'ServiceWorker unavailable'};
  try {
    const reg=await navigator.serviceWorker.register('/service.js?token='+TOKEN,{scope:'/'});
    await navigator.serviceWorker.ready;
    return await bounded(new Promise(resolve=>{const channel=new MessageChannel();
      channel.port1.onmessage=e=>{channel.port1.close();resolve(e.data);};
      reg.active.postMessage('read',[channel.port2]);
    }),'serviceWorker');
  }catch(e){return {unsupported:String(e)};}
}
(async()=>{
  let result;
  try {
    const [main,sameIframe,crossIframe,dedicatedWorker,sharedWorker,serviceWorker]=await Promise.all([
      bounded(readSurface(),'main'),frame(location.origin,'same'),frame(CROSS,'cross'),dedicated(),shared(),bounded(service(),'service registration')]);
    const headers=await (await fetch('/headers?token='+TOKEN)).json();
    result={token:TOKEN,early,main,sameIframe,crossIframe,dedicatedWorker,sharedWorker,serviceWorker,headers};
  }catch(e){result={token:TOKEN,error:String(e)};}
  document.getElementById('native-result').textContent=JSON.stringify(result);
  await fetch('/report?token='+TOKEN,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});
})();
"""


def file_hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_runtime(archive: Path, browser: Path) -> dict:
    if file_hash(archive) != PIN:
        raise RuntimeError('Pinned archive SHA-256 mismatch: refusing execution')
    with zipfile.ZipFile(archive) as z:
        exe_entries = [i for i in z.infolist() if PurePosixPath(i.filename).name.lower() == 'chrome.exe']
        if len(exe_entries) != 1 or browser.name.lower() != 'chrome.exe':
            raise RuntimeError('Expected exactly one chrome.exe archive member')
        prefix = PurePosixPath(exe_entries[0].filename).parent
        count = 0
        manifest = []
        for info in z.infolist():
            p = PurePosixPath(info.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in info.filename:
                raise RuntimeError('Unsafe archive member')
            if info.is_dir():
                continue
            try:
                rel = p.relative_to(prefix)
            except ValueError:
                continue
            target = browser.parent.joinpath(*rel.parts).resolve()
            if not target.is_relative_to(browser.parent.resolve()) or target.is_symlink():
                raise RuntimeError('Runtime member escapes browser directory')
            with z.open(info) as stream:
                expected = hashlib.file_digest(stream, 'sha256').hexdigest()
            if not target.is_file() or target.stat().st_size != info.file_size or file_hash(target) != expected:
                raise RuntimeError(f'Runtime differs from pinned ZIP: {rel}')
            count += 1
            manifest.append({'path':str(rel),'bytes':info.file_size,'sha256':expected})
        return {'archive_sha256':PIN,'files_verified':count,'runtime_manifest':manifest}


class Job:
    """Own only a gated launcher and its children; never enumerate personal jobs."""
    def __init__(self):
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.k.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        self.k.CreateJobObjectW.restype=wintypes.HANDLE
        self.k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        self.k.AssignProcessToJobObject.restype=wintypes.BOOL
        self.k.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT]
        self.k.TerminateJobObject.restype=wintypes.BOOL
        self.k.CloseHandle.argtypes=[wintypes.HANDLE]
        self.k.CloseHandle.restype=wintypes.BOOL
        self.handle=self.k.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
    def assign(self,p):
        if not self.k.AssignProcessToJobObject(self.handle,int(p._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.handle:
            self.k.TerminateJobObject(self.handle,98)
            self.k.CloseHandle(self.handle)
            self.handle=None


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,state):
        super().__init__(('127.0.0.1',0),Handler)
        self.state=state
        self.cross_port=0


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,code,body,mime='text/plain; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Accept-CH','Sec-CH-UA-Full-Version-List, Sec-CH-UA-Platform-Version, Sec-CH-UA-Arch, Sec-CH-UA-Bitness')
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def parsed(self):
        u=urlsplit(self.path)
        if u.scheme or u.netloc:return None,'',{}
        q=parse_qs(u.query)
        return self.server.state.get(q.get('token',[''])[0]),u.path,q
    def do_CONNECT(self):self.reply(403,b'No external forwarding')
    def do_GET(self):
        case,path,q=self.parsed()
        if case is None:return self.reply(403,b'No external forwarding')
        token=q['token'][0]
        case['requests'].append({'port':self.server.server_port,'path':path,'headers':dict(self.headers)})
        if path=='/':
            js='const TOKEN='+json.dumps(token)+';const CROSS='+json.dumps(f'http://127.0.0.1:{self.server.cross_port}')+';'+READ_JS+MAIN_JS
            page='<html><head><meta charset="utf-8"><title>Native fingerprint QA</title></head><body><pre id="native-result">pending</pre><img alt="barrier" src="/barrier?token='+token+'"><script>'+js+'</script></body></html>'
            self.reply(200,page.encode(),'text/html; charset=utf-8')
        elif path=='/frame':
            js=READ_JS+'readSurface().then(result=>parent.postMessage({label:'+json.dumps(q['label'][0])+',result},"*"));'
            self.reply(200,('<!doctype html><script>'+js+'</script>').encode(),'text/html; charset=utf-8')
        elif path in ('/worker.js','/shared.js','/service.js'):
            suffix={'/worker.js':'readSurface().then(result=>postMessage(result));',
              '/shared.js':'onconnect=e=>{const p=e.ports[0];readSurface().then(result=>p.postMessage(result));};',
              '/service.js':"self.addEventListener('install',e=>e.waitUntil(self.skipWaiting()));self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));self.addEventListener('message',e=>e.waitUntil(readSurface().then(r=>e.ports[0].postMessage(r))));"}[path]
            self.reply(200,(READ_JS+suffix).encode(),'application/javascript')
        elif path=='/headers':self.reply(200,json.dumps(dict(self.headers)).encode(),'application/json')
        elif path=='/barrier':
            case['event'].wait(35)
            self.reply(200,b'','image/png')
        else:self.reply(404,b'Not found')
    def do_POST(self):
        case,path,q=self.parsed()
        if case is None or path not in ('/report','/early'):return self.reply(404,b'Not found')
        length=int(self.headers.get('Content-Length','0'))
        if length>200000:return self.reply(413,b'Too large')
        try:case['early' if path=='/early' else 'result']=json.loads(self.rfile.read(length))
        except (ValueError,UnicodeDecodeError):return self.reply(400,b'Invalid JSON')
        if path=='/report':case['event'].set()
        self.reply(200,b'OK')


GATE="""import sys, subprocess
if sys.stdin.buffer.read(1)!=b'G':raise SystemExit(97)
raise SystemExit(subprocess.run(sys.argv[1:],stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW).returncode)
"""


def visit(browser,profile,seed,server,label):
    token=uuid.uuid4().hex
    case={'event':threading.Event(),'result':None,'early':None,'requests':[]}
    server.state[token]=case
    profile.mkdir(exist_ok=True)
    flags=[str(browser),'--headless','--dump-dom','--timeout=25000',f'--user-data-dir={profile}',
      '--no-first-run','--no-default-browser-check','--disable-background-networking',
      '--disable-component-update','--disable-sync','--disable-quic','--metrics-recording-only',
      f'--proxy-server=http://127.0.0.1:{server.server_port}',
      '--proxy-bypass-list=127.0.0.1;localhost',
      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
      f'--fingerprint={seed}','--fingerprint-platform=windows','--fingerprint-brand=Chrome',
      f'--fingerprint-brand-version={VERSION}','--fingerprint-hardware-concurrency=8',
      '--timezone=Europe/Berlin','--lang=en-US','--accept-lang=en-US,en',
      f'http://127.0.0.1:{server.server_port}/?token={token}']
    job=Job()
    p=None
    start=time.perf_counter()
    try:
        p=subprocess.Popen([sys.executable,'-I','-S','-c',GATE,*flags],cwd=profile,
          stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
          creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
        job.assign(p)
        timed_out=False
        try:
            stdout,stderr=p.communicate(input=b'G',timeout=45)
        except subprocess.TimeoutExpired:
            timed_out=True
            job.close()
            stdout,stderr=p.communicate(timeout=10)
        result=case['result']
        match=re.search(r'<pre id="native-result">(.*?)</pre>',stdout.decode('utf-8','replace'),re.S)
        dom=json.loads(html.unescape(match.group(1))) if match else None
        return {'label':label,'seed':seed,'return_code':p.returncode,'timed_out':timed_out,
          'seconds':round(time.perf_counter()-start,3),'result':result,
          'early_received':case['early'],'dom_equals_report':dom is not None and dom==result,'requests':case['requests'],
          'stderr_tail':stderr.decode('utf-8','replace')[-4000:]}
    finally:
        job.close()
        if p:
            p.communicate(timeout=10)


COMMON=('userAgent','platform','language','languages','hardwareConcurrency','deviceMemory',
        'timezone','offsetWinter','offsetSummer','userAgentData')


def assess(visits):
    checks=[]
    def add(name,passed,details=None):checks.append({'name':name,'passed':bool(passed),'details':details})
    for visit_result in visits:
        label=visit_result['label']; r=visit_result.get('result') or {}
        add(label+': completed server/DOM agreement',visit_result['return_code']==0 and visit_result['dom_equals_report'] and 'error' not in r)
        main=r.get('main',{})
        add(label+': Windows platform/CPU/timezone',main.get('platform')=='Win32' and main.get('hardwareConcurrency')==8 and main.get('timezone')=='Europe/Berlin')
        early=r.get('early',{})
        add(label+': early script agrees',all(early.get(k)==main.get(k) for k in early) and bool(early))
        for surface in ('sameIframe','crossIframe','dedicatedWorker','sharedWorker','serviceWorker'):
            value=r.get(surface,{})
            supported=isinstance(value,dict) and 'unsupported' not in value and bool(value)
            add(label+': '+surface+' common fields agree',supported and all(value.get(k)==main.get(k) for k in COMMON),value if not supported else None)
        canvas=main.get('canvas') or {}
        add(label+': repeated canvas pixels stable',bool(canvas.get('first')) and canvas.get('first')==canvas.get('second'))
        add(label+': repeated canvas dataURL stable',bool(canvas.get('dataURLFirst')) and canvas.get('dataURLFirst')==canvas.get('dataURLSecond'))
        h={k.lower():v for k,v in r.get('headers',{}).items()}
        add(label+': HTTP UA equals JS',h.get('user-agent')==main.get('userAgent') and bool(h.get('user-agent')))
        add(label+': HTTP Accept-Language',h.get('accept-language','').startswith('en-US'))
        add(label+': HTTP CH platform',h.get('sec-ch-ua-platform')=='"Windows"',h.get('sec-ch-ua-platform'))
        add(label+': requested version visible',('Chrome/'+VERSION) in main.get('userAgent',''))
    if len(visits)==3 and all((v.get('result') or {}).get('main') for v in visits):
        a,a2,b=(v['result']['main'] for v in visits)
        add('A restart common fields stable',all(a.get(k)==a2.get(k) for k in COMMON))
        add('A restart canvas pixels stable',a['canvas'].get('first')==a2['canvas'].get('first') and bool(a['canvas'].get('first')))
        add('A/B seeds yield different canvas pixels',a['canvas'].get('first')!=b['canvas'].get('first'))
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser',type=Path,required=True)
    parser.add_argument('--verified-archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'method':'Pinned native headless Chromium, loopback JS read-only fixture; no CDP',
      'core_version':VERSION,'source':SOURCE,'os':platform.platform(),'python':platform.python_version(),
      'limitations':['Headless only; native GUI/extensions require separate tests.',
        'No anti-bot-service bypass claim; local exposed APIs only.',
        'Audio/WebGPU/real WebRTC routing and cross-origin service workers not measured.',
        'Firefox-style oscpu unsupported in Chromium; omitted.',
        'A consistent advertised surface is not proof of an undetectable identity.'], 'status':'started','visits':[]}
    root=None; servers=[]
    try:
        if os.name!='nt':raise RuntimeError('This harness owns Windows Jobs and requires Windows')
        report['verification']=verify_runtime(args.verified_archive.resolve(),args.browser.resolve())
        root=Path(tempfile.mkdtemp(prefix='neantik-native-fingerprint-'))
        report['disposable_root']=str(root)
        state={}; a=Server(state); b=Server(state); servers=[a,b]
        a.cross_port=b.server_port;b.cross_port=a.server_port
        for server in servers:threading.Thread(target=server.serve_forever,daemon=True).start()
        for label,profile,seed in [('A',root/'A',123456),('A restart',root/'A',123456),('B',root/'B',987654)]:
            report['visits'].append(visit(args.browser.resolve(),profile,seed,a,label))
        report['assertions']=assess(report['visits'])
        report['status']='passed' if all(c['passed'] for c in report['assertions']) else 'failed'
    except Exception as error:
        report['status']='harness_error';report['error']=f'{type(error).__name__}: {error}'
    finally:
        for server in servers:server.shutdown();server.server_close()
        # Retain raw disposable test profiles for inspection; never touch user Data.
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'output':str(args.output),'assertions':len(report.get('assertions',[])),
      'failed':[c['name'] for c in report.get('assertions',[]) if not c['passed']], 'error':report.get('error')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
