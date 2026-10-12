"""Synthetic protocol/assessment checks; never Chromium runtime evidence."""
import socket
import copy
import struct
import threading
import unittest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import test_native_webrtc_privacy as qa


def fixture_cases():
    visits=[]
    for label in ('ordinary unproxied','native unproxied','native HTTP proxy','native broken HTTP proxy','native unavailable TCP proxy'):
        broken='broken' in label or 'unavailable' in label;unproxied='unproxied' in label
        visits.append({'label':label,'process':{'return_code':0,'active_processes':0},
          'stun_packets':1 if unproxied else 0,'udp_datagrams':1 if unproxied else 0,
          'stun_send_log_valid':True,'stun_send_events':1 if unproxied else 0,
          'stun_send_bytes':20 if unproxied else 0,
          'proxy_requests':0 if unproxied else 1,'origin_hits':0 if broken else 3,
          'result':None if broken else {'peerConnectionAvailable':True,'error':None,'iceGatheringState':'complete'},
          'dom_matches_server':not broken,'proxy_unavailable_checked':'unavailable' in label,
          'proxy_neterror':'ERR_PROXY_CONNECTION_FAILED' if 'unavailable' in label else None})
    return visits


class OwnedWebRtcTests(unittest.TestCase):
    def test_netlog_pairs_exact_owned_request_and_rejects_unrelated_errors(self):
        url='http://127.0.0.1:12345/webrtc?token=synthetic'
        data={'constants':{'logEventTypes':{'URL_REQUEST_START_JOB':42},'logSourceType':{'URL_REQUEST':1},
          'logEventPhase':{'PHASE_BEGIN':1,'PHASE_END':2}},'events':[
            {'type':42,'phase':1,'source':{'id':7,'type':1},'params':{'url':url}},
            {'type':42,'phase':2,'source':{'id':7,'type':1},'params':{'net_error':-130}}]}
        evidence=qa.proxy_failure_netlog(data,url)
        self.assertTrue(evidence['owned_url_matched']);self.assertEqual(evidence['net_error'],-130)
        for mutation in ('url','source','source_kind','event','phase','error','bool_error','reverse',
          'double_begin','double_end','missing_constants','missing_begin','bool_id'):
            bad=copy.deepcopy(data)
            if mutation=='url':bad['events'][0]['params']['url']='http://unrelated.invalid/'
            elif mutation=='source':bad['events'][1]['source']['id']=8
            elif mutation=='source_kind':bad['events'][1]['source']['type']=2
            elif mutation=='event':bad['events'][1]['type']=43
            elif mutation=='phase':bad['events'][1]['phase']=0
            elif mutation=='error':bad['events'][1]['params']['net_error']=-102
            elif mutation=='bool_error':bad['events'][1]['params']['net_error']=True
            elif mutation=='reverse':bad['events'].reverse()
            elif mutation=='double_begin':bad['events'].insert(0,copy.deepcopy(bad['events'][0]))
            elif mutation=='double_end':bad['events'].append(copy.deepcopy(bad['events'][1]))
            elif mutation=='missing_constants':bad['constants']={}
            elif mutation=='missing_begin':bad['events'].pop(0)
            else:bad['events'][0]['source']['id']=True
            with self.subTest(mutation=mutation):self.assertIsNone(qa.proxy_failure_netlog(bad,url))
        visits=fixture_cases();visits[4]['proxy_neterror']=None;visits[4]['proxy_failure_netlog']=evidence
        self.assertTrue(all(item['passed'] for item in qa.assessment(visits)))
        visits[4]['proxy_failure_netlog']['owned_url_matched']=False
        self.assertFalse(all(item['passed'] for item in qa.assessment(visits)))
    def test_owned_unavailable_proxy_port_is_reserved_and_not_listening(self):
        proxy=qa.OwnedUnavailableProxy()
        try:
            self.assertTrue(proxy.unavailable_checked)
            self.assertIn(proxy.fixture_outcome,('connection-refused','bounded-connect-timeout'))
            with self.assertRaises((ConnectionRefusedError,TimeoutError)):
                socket.create_connection(('127.0.0.1',proxy.server_port),timeout=5)
            other=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            try:
                with self.assertRaises(OSError):other.bind(('127.0.0.1',proxy.server_port))
            finally:other.close()
        finally:proxy.close()
    def test_unavailable_proxy_needs_exact_neterror_and_no_origin_hit(self):
        self.assertEqual(qa.proxy_neterror('<div class="error-code">ERR_PROXY_CONNECTION_FAILED</div>'),
          'ERR_PROXY_CONNECTION_FAILED')
        self.assertIsNone(qa.proxy_neterror('<div class="error-code">ERR_CONNECTION_REFUSED</div>'))
        self.assertIsNone(qa.proxy_neterror('ERR_PROXY_CONNECTION_FAILED in arbitrary log'))
        for key,value in (('proxy_unavailable_checked',False),('proxy_neterror',None),
            ('proxy_neterror','ERR_CONNECTION_REFUSED'),('origin_hits',1),('udp_datagrams',1),
            ('process',{'return_code':1,'active_processes':0})):
            visits=fixture_cases();visits[4][key]=value
            with self.subTest(key=key,value=value):
                self.assertFalse(all(item['passed'] for item in qa.assessment(visits)))
    def test_owned_stun_fixture_really_receives_and_replies(self):
        listener=qa.OwnedStun();client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(2)
        try:
            request=struct.pack('!HHI',1,0,qa.COOKIE)+b'0123456789ab'
            client.sendto(request,('127.0.0.1',listener.port))
            response,_=client.recvfrom(100)
            self.assertEqual(response[8:20],request[8:20]);self.assertEqual(listener.count,1)
        finally:client.close();listener.close()
    def test_owned_proxy_forward_broken_and_external_rejection(self):
        class Origin(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.server.hits+=1;self.send_response(200);self.end_headers();self.wfile.write(b'owned fixture')
        origin=ThreadingHTTPServer(('127.0.0.1',0),Origin);origin.hits=0
        thread=threading.Thread(target=origin.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{origin.server_port}'
        try:
            for broken,status in ((False,200),(True,502)):
                proxy=qa.OwnedProxy(url,broken)
                try:
                    connection=HTTPConnection('127.0.0.1',proxy.server_port,timeout=2)
                    connection.request('GET',url+'/webrtc?token=synthetic')
                    response=connection.getresponse();self.assertEqual(response.status,status);response.read();connection.close()
                    self.assertEqual(origin.hits,1)
                    self.assertTrue(proxy.requests[0]['test_document'])
                    connection=HTTPConnection('127.0.0.1',proxy.server_port,timeout=2)
                    connection.request('GET','http://example.invalid/webrtc')
                    response=connection.getresponse();self.assertEqual(response.status,403);response.read();connection.close()
                    self.assertEqual(origin.hits,1)
                finally:proxy.close()
        finally:origin.shutdown();origin.server_close();thread.join(timeout=1)
    def test_stun_exact_transaction_and_xor_address(self):
        transaction=b'0123456789ab'
        request=struct.pack('!HHI',1,0,qa.COOKIE)+transaction
        response=qa.stun_response(request,('127.0.0.1',23456))
        self.assertEqual(response[:8],struct.pack('!HHI',0x101,12,qa.COOKIE))
        self.assertEqual(response[8:20],transaction)
        self.assertEqual(struct.unpack_from('!H',response,26)[0]^(qa.COOKIE>>16),23456)
        ip=struct.unpack_from('!I',response,28)[0]^qa.COOKIE
        self.assertEqual(socket.inet_ntoa(struct.pack('!I',ip)),'127.0.0.1')
        for bad in (b'',request[:-1],request+b'x',b'xx'+request[2:],request[:4]+b'xxxx'+request[8:]):
            self.assertIsNone(qa.stun_response(bad,('127.0.0.1',23456)))
    def test_netlog_udp_send_evidence_is_bound_to_exact_owned_endpoint(self):
        data={'constants':{'logEventTypes':{'UDP_BYTES_SENT':7},
          'logSourceType':{'UDP_SOCKET':3}},'events':[
          {'type':7,'source':{'type':3,'id':1},'params':{'address':'192.168.1.120:54321','byte_count':20}},
          {'type':7,'source':{'type':3,'id':2},'params':{'address':'192.168.1.120:54322','byte_count':20}},
          {'type':7,'source':{'type':4,'id':3},'params':{'address':'192.168.1.120:54321','byte_count':20}}]}
        self.assertEqual(qa.owned_stun_udp_send_evidence(data,'192.168.1.120',54321),
          {'events':1,'bytes':20})
        self.assertIsNone(qa.owned_stun_udp_send_evidence({},'192.168.1.120',54321))
    def test_synthetic_valid_cases_are_internally_consistent(self):
        self.assertTrue(all(item['passed'] for item in qa.assessment(fixture_cases())))
    def test_zero_native_control_udp_cannot_pass(self):
        visits=fixture_cases();visits[1]['stun_packets']=0;visits[1]['udp_datagrams']=0
        visits[1]['stun_send_events']=0;visits[1]['stun_send_bytes']=0
        self.assertFalse(all(item['passed'] for item in qa.assessment(visits)))
    def test_proxied_owned_stun_socket_send_cannot_pass(self):
        visits=fixture_cases();visits[2]['stun_send_events']=1;visits[2]['stun_send_bytes']=20
        self.assertFalse(all(item['passed'] for item in qa.assessment(visits)))
    def test_leaked_udp_broken_direct_and_missing_proxy_cannot_pass(self):
        for index,key,value in ((2,'udp_datagrams',1),(3,'origin_hits',1),(2,'proxy_requests',0),(3,'proxy_requests',0)):
            visits=fixture_cases();visits[index][key]=value
            with self.subTest(index=index,key=key):
                self.assertFalse(all(item['passed'] for item in qa.assessment(visits)))
    def test_missing_result_error_or_scenario_cannot_pass(self):
        visits=fixture_cases();visits[2]['result']['error']='WebRTC unavailable'
        self.assertFalse(all(item['passed'] for item in qa.assessment(visits)))
        self.assertFalse(all(item['passed'] for item in qa.assessment([])))


if __name__=='__main__':unittest.main()
