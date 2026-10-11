"""UNIT TEST ONLY: constructed data, never actual native browser evidence."""
import copy
import native_qa_report as validator

def full_report(verification):
    h = validator.fingerprint
    visits = []
    for label, (seed, cpu, memory, zone) in validator.CASES.items():
        pixels = h.expected_pixels(seed)
        data = bytes.fromhex(pixels)
        values = {'hardwareConcurrency': cpu, 'deviceMemory': float(memory), 'timezone': zone,
                  **dict(zip(('winterOffset', 'summerOffset', 'beforeDst', 'afterDst'),
                             h.ZONE_EXPECTATIONS[zone]))}
        canvas = {'first': pixels, 'repeated': pixels, 'afterExports': pixels,
                  'putImageData': pixels, 'blob': pixels, 'dataURL': pixels,
                  'subrect': b''.join(data[(y*32+4)*4:(y*32+11)*4] for y in range(5, 13)).hex(),
                  'outOfBounds': '00000000', 'cleared': True}
        canvas.update(translucent='00'*3072,
                      displayP3={'colorSpace': 'display-p3', 'pixels': '00'*3072},
                      float16={'unsupported': 'synthetic fixture unavailable'})
        surface = {**values, 'canvas': canvas, 'userAgent': 'synthetic-unit-fixture',
                   'requestHeaders': {'User-Agent': 'synthetic-unit-fixture',
                                      'Sec-CH-Device-Memory': memory}}
        result = {context: copy.deepcopy(surface) for context in h.CONTEXTS}
        result.update(early=copy.deepcopy(values),
                      offscreen={'kind': 'OffscreenCanvas', **copy.deepcopy(canvas)},
                      largeCanvas={'width': 2048, 'height': 2048, 'readbackMs': [1, 2, 3],
                                   'lastDigest': 'a'*64, 'pngBytes': 1, 'pngMs': 1.0})
        visits.append({'label': label, 'seed': seed, 'expected_cpu': cpu,
                       'expected_memory': memory, 'expected_timezone': zone,
                       'process': {'return_code': 0, 'active_processes': 0,
                                   'peak_job_committed_bytes': 50000000,
                                   'peak_process_committed_bytes': 30000000},
                       'dom_matches_server': True, 'result': result})
    net = []
    for label in sorted(validator.NETWORK):
        broken = 'broken' in label or 'unavailable' in label
        unproxied = 'unproxied' in label
        net.append({'label': label, 'process': {'return_code': 0, 'active_processes': 0},
                    'stun_packets': 1 if unproxied else 0,
                    'udp_datagrams': 1 if unproxied else 0,
                    'proxy_requests': 0 if unproxied or 'unavailable' in label else 1,
                    'origin_hits': 0 if broken else 3,
                    'result': None if broken else {'peerConnectionAvailable': True,
                        'error': None, 'iceGatheringState': 'complete'},
                    'dom_matches_server': not broken,
                    'proxy_unavailable_checked': 'unavailable' in label,
                    'proxy_fixture_outcome': 'connection-refused' if 'unavailable' in label else None,
                    'proxy_neterror': 'ERR_PROXY_CONNECTION_FAILED' if 'unavailable' in label else None,
                    'proxy_failure_netlog': None})
    caps = dict.fromkeys(('stable_seed', 'hardware_concurrency', 'device_memory',
                         'canvas_opaque_srgb_uint8', 'timezone',
                         'webrtc_non_proxied_udp_proxied_webframes'), True)
    caps.update(dict.fromkeys(('canvas', 'canvas_float16', 'canvas_display_p3',
                              'canvas_translucent'), False))
    netchecks = validator.webrtc.assessment(net)
    return {'format': 'neantik-own155-native-qa-v1', 'status': 'passed',
            'verification': copy.deepcopy(verification), 'bundle_reverified_after_visits': True,
            'probe': {'actual_info': {'schema': 1, 'engine_id': 'neantik-chromium',
                'version': h.VERSION, 'source_commit': h.COMMIT,
                'capability_evidence': 'compiled-source-only', 'capabilities': caps},
                'process': {'return_code': 0, 'active_processes': 0}},
            'malformed_inputs': [{'name': name, 'passed': True,
                'process': {'return_code': 78, 'active_processes': 0}}
                for name in sorted(validator.MALFORMED)],
            'visits': visits, 'webrtc': {'visits': net, 'assertions': netchecks},
            'assertions': h.assess(visits) + netchecks, 'comparisons': h.comparisons(visits)}
