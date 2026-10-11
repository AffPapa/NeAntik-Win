"""Owned-loopback WebRTC observations for the hash-verified own155 QA cycle.

Not a global network kill-switch test. No external STUN service or proxy mutation.
Synthetic tests of this module are never evidence of Chromium packet behavior.
"""
from __future__ import annotations

import html
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import struct
import threading
import uuid
from urllib.parse import urlsplit

import test_current_native_fingerprint as harness


COOKIE=0x2112A442


def stun_response(packet,address):
    """Recognize an exact unfragmented RFC5389 Binding request; no packet echo."""
    if len(packet)<20:return None
    kind,length,cookie=struct.unpack_from('!HHI',packet)
    if kind!=1 or cookie!=COOKIE or length%4 or len(packet)!=20+length:return None
    # XOR-MAPPED-ADDRESS IPv4: fixed owned listener only.
    port=address[1]^(COOKIE>>16)
    ip=struct.unpack('!I',socket.inet_aton(address[0]))[0]^COOKIE
    attribute=struct.pack('!HHBBHI',0x20,8,0,1,port,ip)
    return struct.pack('!HHI',0x101,len(attribute),COOKIE)+packet[8:20]+attribute


class OwnedStun:
    def __init__(self):
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.socket.bind(('127.0.0.1',0));self.socket.settimeout(.2)
        self.port=self.socket.getsockname()[1];self.count=0;self.datagrams=0
        self.stop=threading.Event();self.thread=threading.Thread(target=self.serve,daemon=True)
        self.thread.start()
    def serve(self):
        while not self.stop.is_set():
            try:packet,address=self.socket.recvfrom(65536)
            except socket.timeout:continue
            except OSError:break
            self.datagrams+=1
            response=stun_response(packet,address)
            if response is not None:
                self.count+=1
                try:self.socket.sendto(response,address)
                except OSError:pass
    def close(self):
        self.stop.set();self.socket.close();self.thread.join(timeout=1)


class OwnedProxy(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,origin,broken=False):
        super().__init__(('127.0.0.1',0),ProxyHandler)
        self.origin=origin;self.broken=broken;self.requests=[];self.thread=threading.Thread(target=self.serve_forever,daemon=True)
        self.thread.start()
    def close(self):self.shutdown();self.server_close();self.thread.join(timeout=1)


class OwnedUnavailableProxy:
    """Reserve an IPv4 TCP port exclusively; deliberately never listen."""
    def __init__(self):
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            self.socket.bind(('127.0.0.1',0));self.server_port=self.socket.getsockname()[1]
            self.requests=[]
            try:
                connection=socket.create_connection(('127.0.0.1',self.server_port),timeout=5)
            except ConnectionRefusedError:self.unavailable_checked=True;self.fixture_outcome='connection-refused'
            except TimeoutError:self.unavailable_checked=True;self.fixture_outcome='bounded-connect-timeout'
            else:
                connection.close();raise harness.HarnessError('Owned non-listening proxy did not refuse TCP')
        except BaseException:self.socket.close();raise
    def close(self):self.socket.close()


def proxy_neterror(dom):
    # Pinned155 components/neterror/resources/neterror.ts renders errorCode here.
    match=re.search(r'<div\s+class=["\']error-code["\']\s*>\s*(ERR_PROXY_CONNECTION_FAILED)\s*</div>',dom)
    return match.group(1) if match else None


def proxy_failure_netlog(data,expected_url):
    """Bind exact -130 to the owned URL_REQUEST's START_JOB begin/end pair."""
    if not isinstance(data,dict):return None
    constants=data.get('constants') or {};events=data.get('events')
    if not isinstance(constants,dict) or not isinstance(events,list) or len(events)>100000:return None
    maps=[constants.get(name) for name in ('logEventTypes','logSourceType','logEventPhase')]
    if not all(isinstance(value,dict) for value in maps):return None
    types,sources,phases=maps
    event_type=types.get('URL_REQUEST_START_JOB');source_type=sources.get('URL_REQUEST')
    begin=phases.get('PHASE_BEGIN');end=phases.get('PHASE_END')
    if not all(type(value) is int for value in (event_type,source_type,begin,end)) or begin==end:return None
    candidates={}
    for index,event in enumerate(events):
        if not isinstance(event,dict) or type(event.get('type')) is not int or event.get('type')!=event_type:continue
        source=event.get('source') or {};params=event.get('params') or {}
        if not isinstance(source,dict) or not isinstance(params,dict) or type(source.get('type')) is not int or source.get('type')!=source_type or type(source.get('id')) is not int or source['id']<0 or type(event.get('phase')) is not int:continue
        record=candidates.setdefault(source['id'],{'begins':[],'ends':[]})
        if event.get('phase')==begin:record['begins'].append((index,params.get('url')))
        elif event.get('phase')==end:record['ends'].append((index,params.get('net_error')))
    matches=[]
    for source_id,record in candidates.items():
        if len(record['begins'])!=1 or len(record['ends'])!=1:continue
        start,url=record['begins'][0];finish,error=record['ends'][0]
        if url==expected_url and start<finish and type(error) is int and error==-130:
            matches.append({'source_id':source_id,'event':'URL_REQUEST_START_JOB',
              'net_error':-130,'error_name':'ERR_PROXY_CONNECTION_FAILED','owned_url_matched':True})
    return matches[0] if len(matches)==1 else None


def read_proxy_failure_netlog(path,expected_url):
    if not path.is_file() or path.stat().st_size>8*1024*1024:return None
    try:return proxy_failure_netlog(harness.unique_json(path.read_text(encoding='utf-8')),expected_url)
    except (ValueError,UnicodeError,harness.HarnessError):return None


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_CONNECT(self):
        self.server.requests.append({'method':'CONNECT','allowed':False})
        self.send_error(403,'CONNECT is not covered by this HTTP-only test')
    def forward(self):
        parsed=urlsplit(self.path)
        expected=urlsplit(self.server.origin)
        allowed=parsed.scheme=='http' and parsed.hostname==expected.hostname and parsed.port==expected.port and not parsed.username
        self.server.requests.append({'method':self.command,'allowed':allowed,'broken':self.server.broken,
          'test_document':allowed and self.command=='GET' and parsed.path=='/webrtc'})
        if not allowed:return self.send_error(403,'Only the owned test origin is permitted')
        if self.server.broken:return self.send_error(502,'Owned broken-proxy fixture')
        length=int(self.headers.get('Content-Length','0'))
        if not 0<=length<=2*1024*1024:return self.send_error(413)
        body=self.rfile.read(length) if length else None
        connection=HTTPConnection(expected.hostname,expected.port,timeout=40)
        try:
            headers={key:value for key,value in self.headers.items() if key.lower() not in
              ('proxy-connection','connection','proxy-authorization','host')}
            path=parsed.path or '/'
            if parsed.query:path+='?'+parsed.query
            connection.request(self.command,path,body,headers)
            response=connection.getresponse();payload=response.read(2*1024*1024+1)
            if len(payload)>2*1024*1024:return self.send_error(502)
            self.send_response(response.status)
            for key,value in response.getheaders():
                if key.lower() not in ('connection','transfer-encoding','content-length'):self.send_header(key,value)
            self.send_header('Content-Length',str(len(payload)));self.end_headers()
            try:self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError):pass
        except OSError:self.send_error(502)
        finally:connection.close()
    do_GET=forward
    do_POST=forward


def assessment(visits):
    by={item['label']:item for item in visits};checks=[]
    def add(name,passed):checks.append({'name':'WebRTC: '+name,'passed':bool(passed)})
    required={'ordinary unproxied','native unproxied','native HTTP proxy','native broken HTTP proxy',
      'native unavailable TCP proxy'}
    add('all five owned network scenarios recorded',required<=by.keys())
    for label in required:
        visit=by.get(label,{})
        add(label+' owned process exited normally',visit.get('process',{}).get('return_code')==0 and
          visit.get('process',{}).get('active_processes')==0)
        if label=='native unavailable TCP proxy':
            evidence=visit.get('proxy_failure_netlog') or {}
            precise_failure=visit.get('proxy_neterror')=='ERR_PROXY_CONNECTION_FAILED' or (
              evidence.get('owned_url_matched') is True and type(evidence.get('net_error')) is int and
              evidence['net_error']==-130 and evidence.get('event')=='URL_REQUEST_START_JOB')
            add('unavailable TCP proxy produces precise Chromium neterror and no DIRECT fallback',
              visit.get('proxy_unavailable_checked') is True and precise_failure and
              visit.get('origin_hits')==0 and visit.get('result') is None)
            add('unavailable TCP proxy sends no STUN datagrams',visit.get('udp_datagrams')==0)
        elif label=='native broken HTTP proxy':
            add('broken proxy attempted and no DIRECT origin fallback',visit.get('proxy_requests',0)>0 and
              visit.get('origin_hits')==0 and visit.get('result') is None)
            add('broken proxy sends no STUN datagrams',visit.get('udp_datagrams')==0)
        else:
            result=visit.get('result') or {}
            add(label+' real page result agrees with dumpDOM',visit.get('dom_matches_server') is True and
              result.get('peerConnectionAvailable') is True and result.get('error') is None and
              result.get('iceGatheringState') in ('gathering','complete'))
            if 'unproxied' in label:
                add(label+' positive native STUN packets actually observed',visit.get('stun_packets',0)>0)
            else:
                add('explicit owned HTTP proxy was used',visit.get('proxy_requests',0)>0 and visit.get('origin_hits',0)>0)
                add('proxied native sends no STUN datagrams',visit.get('udp_datagrams')==0)
    return checks


def run_webrtc_checks(browser,root):
    state={};origin=harness.Server(state);origin.cross=f'http://127.0.0.1:{origin.server_port}'
    thread=threading.Thread(target=origin.serve_forever,daemon=True);thread.start()
    visits=[]
    try:
        for label,native,proxied,broken in [('ordinary unproxied',False,False,False),
            ('native unproxied',True,False,False),('native HTTP proxy',True,True,False),
            ('native broken HTTP proxy',True,True,True),('native unavailable TCP proxy',True,True,False)]:
            token=uuid.uuid4().hex;stun=OwnedStun();proxy=None
            try:
                case={'ready':threading.Event(),'result':None,'lock':threading.Lock(),
                  'stun_url':f'stun:127.0.0.1:{stun.port}','origin_hits':0}
                state[token]=case
                url=f'http://127.0.0.1:{origin.server_port}/webrtc?token={token}'
                folder=root/('webrtc-'+label.replace(' ','-'));folder.mkdir()
                netlog=folder/'net-log.json'
                arguments=[str(browser),'--headless','--dump-dom',f'--user-data-dir={folder}',
                  '--timeout=30000' if 'unavailable' in label else '--timeout=15000',
                  '--no-first-run','--no-default-browser-check','--disable-background-networking',
                  '--disable-component-update','--disable-sync','--disable-extensions','--disable-quic',
                  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']
                if native:arguments+=harness.current_core.identity_arguments(harness.current_core.new_identity())
                if 'unavailable' in label:arguments+=['--log-net-log='+str(netlog)]
                if proxied:
                    proxy=OwnedUnavailableProxy() if label=='native unavailable TCP proxy' else OwnedProxy(
                      f'http://127.0.0.1:{origin.server_port}',broken)
                    arguments+=[f'--proxy-server=http://127.0.0.1:{proxy.server_port}','--proxy-bypass-list=<-loopback>']
                else:arguments+=['--no-proxy-server']
                stdout,stderr,process=harness.run_owned(arguments+[url],folder,60 if 'unavailable' in label else 40)
                match=re.search(r'<pre id="current-webrtc-result">(.*?)</pre>',stdout.decode('utf-8','replace'),re.S)
                dom=harness.unique_json(html.unescape(match.group(1))) if match else None
                visits.append({'label':label,'process':process,'stun_packets':stun.count,'udp_datagrams':stun.datagrams,
                  'origin_hits':case['origin_hits'],'proxy_requests':sum(item.get('test_document',False) for item in proxy.requests) if proxy else 0,
                  'result':case['result'],'dom_matches_server':case['result'] is not None and dom==case['result'],
                  'proxy_unavailable_checked':getattr(proxy,'unavailable_checked',False),
                  'proxy_fixture_outcome':getattr(proxy,'fixture_outcome',None),
                  'proxy_neterror':proxy_neterror(stdout.decode('utf-8','replace')),
                  'proxy_failure_netlog':read_proxy_failure_netlog(netlog,url) if 'unavailable' in label else None,
                  'stderr_tail':stderr.decode('utf-8','replace').replace(str(root),'<qa-root>')[-1000:]})
            finally:
                if proxy:proxy.close()
                stun.close()
    finally:origin.shutdown();origin.server_close();thread.join(timeout=1)
    return {'visits':visits,'assertions':assessment(visits),
      'limitations':['Owned IPv4 loopback STUN and HTTP-only proxy; no remote NIC or real external IP observation.',
        'Implicit loopback HTTP bypass explicitly removed with <-loopback>; this does not prove every destination bypass rule.',
        'CONNECT/TLS/SOCKS, extensions, other UDP APIs and global kill-switch are NOT covered.',
        'HTTP 502 and exclusively reserved non-listening TCP proxy both tested; Windows may refuse or drop SYN until timeout. DNS failure, authentication and proxy failover lists are not covered.',
        'Broken-proxy case never loads JS; no STUN there alone is not evidence of the WebRTC policy.',
        'Unproxied native positive control must actually emit valid STUN; zero traffic cannot produce a passing result.']}
