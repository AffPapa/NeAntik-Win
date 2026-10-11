"""Validate complete recorded own155 QA, not authenticate fabricated observations.

Only an independently trusted actual QA run and bundle hash constitute runtime
evidence. This stdlib gate rejects incomplete or internally inconsistent reports;
recomputed checks reuse the authored harness rather than inventing new coverage.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import re
import sys

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import test_current_native_fingerprint as fingerprint
import test_native_webrtc_privacy as webrtc

CASES = {
    'Baseline': (None, 8, '8', 'Europe/Berlin'),
    'A': (123456, 8, '8', 'Europe/Berlin'),
    'A restart': (123456, 8, '8', 'Europe/Berlin'),
    'B': (987654, 8, '8', 'Europe/Berlin'),
    'Hardware timezone': (765432, 16, '16', 'America/New_York'),
}
MALFORMED = {'zero_seed', 'unknown_namespace', 'orphan_cpu', 'invalid_cpu',
             'unknown_iana', 'unsupported_windows_memory_0.25',
             'unsupported_windows_memory_0.5', 'unsupported_windows_memory_1'}
NETWORK = {'ordinary unproxied', 'native unproxied', 'native HTTP proxy',
           'native broken HTTP proxy', 'native unavailable TCP proxy'}

def require(condition, message):
    if not condition:
        raise ValueError('Independent own155 QA report: ' + message)

def load_report(path):
    require(path.is_file() and path.stat().st_size <= 64 * 1024**2, 'missing/oversized file')
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    def constant(value):
        raise ValueError('Independent own155 QA report: nonfinite JSON number')
    def float_value(value):
        number = float(value)
        require(math.isfinite(number), 'overflow/nonfinite JSON number')
        return number
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=constant, parse_float=float_value)

def records(value, key, names):
    require(type(value) is list and len(value) == len(names), 'exact scenario count required')
    out = {}
    for item in value:
        require(type(item) is dict, 'scenario must be an object')
        label = item.get(key)
        require(type(label) is str and label in names and label not in out,
                'unknown/duplicate scenario')
        out[label] = item
    require(set(out) == set(names), 'missing scenario')
    return out

def integer(value, minimum=0):
    return type(value) is int and value >= minimum

def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0

def typed_equal(value, expected):
    """No bool/int equality or nonfinite scalars in recomputed comparisons."""
    if type(value) is not type(expected):
        return False
    if type(value) is dict:
        return set(value) == set(expected) and all(typed_equal(value[k], expected[k]) for k in expected)
    if type(value) is list:
        return len(value) == len(expected) and all(typed_equal(x, y) for x, y in zip(value, expected))
    if type(value) in (int, float):
        return math.isfinite(value) and math.isfinite(expected) and value == expected
    return value == expected

def bypass_observations(canvas):
    require(type(canvas) is dict, 'main canvas observations missing')
    hex_pixels = lambda value: type(value) is str and re.fullmatch('[a-f0-9]{6144}', value) is not None
    # Actual JS fixture records translucent directly as a uint8 hex string.
    require(hex_pixels(canvas.get('translucent')), 'translucent bypass observation missing')
    for key in ('displayP3', 'float16'):
        value = canvas.get(key)
        require(type(value) is dict, 'bypass observation/unsupported object missing')
        if set(value) == {'unsupported'}:
            require(type(value['unsupported']) is str and bool(value['unsupported']), 'empty unsupported evidence')
        elif key == 'displayP3':
            require(set(value) == {'colorSpace', 'pixels'} and
                    type(value['colorSpace']) is str and bool(value['colorSpace']) and
                    hex_pixels(value['pixels']), 'invalid displayP3 observation')
        else:
            require(set(value) == {'pixelFormat', 'digest'} and
                    type(value['pixelFormat']) is str and bool(value['pixelFormat']) and
                    type(value['digest']) is str and re.fullmatch('[a-f0-9]{64}', value['digest']) is not None,
                    'invalid float16 observation')

def process(value, code, memory=False):
    require(type(value) is dict and type(value.get('return_code')) is int and
            value['return_code'] == code and type(value.get('active_processes')) is int and
            value['active_processes'] == 0, 'process exit/descendant evidence invalid')
    if memory:
        require(all(integer(value.get(k), 1) for k in
                    ('peak_job_committed_bytes', 'peak_process_committed_bytes')),
                'missing typed process memory evidence')

def surface(value, http=False):
    require(type(value) is dict and integer(value.get('hardwareConcurrency'), 1) and
            type(value.get('deviceMemory')) in (int, float) and
            math.isfinite(value['deviceMemory']) and value['deviceMemory'] > 0 and
            type(value.get('timezone')) is str and bool(value['timezone']) and
            all(type(value.get(k)) is int for k in
                ('winterOffset', 'summerOffset', 'beforeDst', 'afterDst')),
            'typed API observations missing')
    if http:
        headers = value.get('requestHeaders')
        require(type(value.get('userAgent')) is str and bool(value['userAgent']) and
                type(headers) is dict and all(type(k) is str and bool(k) and
                    type(v) is str for k, v in headers.items()),
                'typed JS/HTTP User-Agent observations missing')
        normalized = {k.lower(): v for k, v in headers.items()}
        require(len(normalized) == len(headers) and bool(normalized.get('user-agent')),
                'duplicate/empty HTTP User-Agent observation')

def assertion_map(value):
    require(type(value) is list and bool(value), 'assertions missing')
    out = {}
    for item in value:
        require(type(item) is dict and set(item) == {'name', 'passed'} and
                type(item.get('name')) is str and item['name'] and
                item['name'] not in out and type(item.get('passed')) is bool,
                'unknown/duplicate/untyped assertion')
        out[item['name']] = item['passed']
    return out

def validate_report(report, verification):
    require(type(report) is dict and report.get('format') == 'neantik-own155-native-qa-v1'
            and report.get('status') == 'passed' and
            report.get('bundle_reverified_after_visits') is True and
            not report.get('harness_error'), 'status/reverification/error invalid')
    actual = report.get('verification')
    require(type(actual) is dict and set(actual) == set(verification) and
            all(type(actual[k]) is type(v) and actual[k] == v for k, v in verification.items()),
            'exact bundle verification evidence mismatch')
    probe = report.get('probe')
    require(type(probe) is dict, 'probe missing')
    process(probe.get('process'), 0)
    try:
        fingerprint.validate_probe_info(probe.get('actual_info'))
    except (fingerprint.HarnessError, TypeError, KeyError) as exc:
        raise ValueError('Independent own155 QA report: invalid exact native probe') from exc
    rejected = records(report.get('malformed_inputs'), 'name', MALFORMED)
    for item in rejected.values():
        require(item.get('passed') is True, 'malformed case did not pass')
        process(item.get('process'), 78)
    visits = records(report.get('visits'), 'label', CASES)
    for label, run in visits.items():
        params = (run.get('seed'), run.get('expected_cpu'), run.get('expected_memory'),
                  run.get('expected_timezone'))
        expected = CASES[label]
        require(all(type(x) is type(y) and x == y for x, y in zip(params, expected)),
                'scenario identity parameters changed')
        process(run.get('process'), 0, memory=True)
        require(run.get('dom_matches_server') is True and type(run.get('result')) is dict,
                'DOM/server evidence missing')
        result = run['result']
        for context in fingerprint.CONTEXTS:
            surface(result.get(context), http=True)
        surface(result.get('early'))
        bypass_observations(result['main'].get('canvas'))
        perf = result.get('largeCanvas')
        require(type(perf) is dict and integer(perf.get('width'), 1) and
                integer(perf.get('height'), 1) and integer(perf.get('pngBytes'), 1) and
                finite_number(perf.get('pngMs')),
                'typed canvas performance evidence missing')
    network = report.get('webrtc')
    require(type(network) is dict, 'WebRTC observations missing')
    netvisits = records(network.get('visits'), 'label', NETWORK)
    for label, run in netvisits.items():
        process(run.get('process'), 0)
        require(all(integer(run.get(k)) for k in
                    ('stun_packets', 'udp_datagrams', 'proxy_requests', 'origin_hits')),
                'typed network counters missing')
        require(run['stun_packets'] <= run['udp_datagrams'], 'STUN count exceeds datagrams')
        require(type(run.get('dom_matches_server')) is bool, 'untyped network DOM agreement')
        if label == 'native unavailable TCP proxy':
            require(run.get('proxy_unavailable_checked') is True, 'unavailable proxy not checked')
            evidence = run.get('proxy_failure_netlog')
            if evidence is not None:
                require(type(evidence) is dict and integer(evidence.get('source_id')) and
                        type(evidence.get('net_error')) is int and evidence['net_error'] == -130 and
                        evidence.get('event') == 'URL_REQUEST_START_JOB' and
                        evidence.get('error_name') == 'ERR_PROXY_CONNECTION_FAILED' and
                        evidence.get('owned_url_matched') is True, 'invalid request-bound netlog evidence')
    try:
        fpchecks = fingerprint.assess(report['visits'])
        netchecks = webrtc.assessment(network['visits'])
    except (TypeError, KeyError, ValueError, AttributeError, OverflowError) as exc:
        raise ValueError('Independent own155 QA report: malformed observations') from exc
    expected = assertion_map(fpchecks + netchecks)
    require(all(expected.values()), 'recomputed observation checks failed')
    require(assertion_map(report.get('assertions')) == expected,
            'assertions do not exactly cover recomputed observations')
    require(assertion_map(network.get('assertions')) == assertion_map(netchecks),
            'nested WebRTC assertions mismatch')
    require(typed_equal(report.get('comparisons'), fingerprint.comparisons(report['visits'])),
            'comparison/timing/bypass summaries differ from recorded observations')
    return {'assertions_verified': len(expected), 'evidence': 'recorded-observations-recomputed'}
