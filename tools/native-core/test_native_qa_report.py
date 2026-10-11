"""Synthetic report validation tests, NOT native Chromium runtime proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import native_qa_report as v
from native_qa_synthetic_fixture import full_report

class ReportTests(unittest.TestCase):
    def setUp(self):
        self.verification = {'manifest_sha256': 'a'*64, 'files_verified': 5,
            'engine_id': 'neantik-chromium', 'version': v.fingerprint.VERSION,
            'source_commit': v.fingerprint.COMMIT,
            'source_commit_is_manifest_assertion_not_runtime_attestation': True}
        self.report = full_report(self.verification)

    def check(self, report):
        return v.validate_report(report, self.verification)

    def test_full_synthetic_report_and_assertion_order(self):
        self.assertGreater(self.check(self.report)['assertions_verified'], 300)
        self.report['assertions'].reverse()
        self.report['webrtc']['assertions'].reverse()
        self.check(self.report)

    def test_missing_unknown_duplicate_and_single_assertion(self):
        for section in ('visits', 'malformed_inputs'):
            for mutation in ('missing', 'unknown', 'duplicate'):
                bad = copy.deepcopy(self.report)
                data = bad[section]
                key = 'label' if section == 'visits' else 'name'
                if mutation == 'missing': data.pop()
                elif mutation == 'unknown': data[0][key] = 'invented'
                else: data[0][key] = data[1][key]
                with self.subTest(section=section, mutation=mutation), self.assertRaises(ValueError): self.check(bad)
        for mutation in ('single', 'unknown', 'duplicate', 'missing', 'untyped'):
            bad = copy.deepcopy(self.report)
            if mutation == 'single': bad['assertions'] = [{'passed': True}]
            elif mutation == 'unknown': bad['assertions'][0]['name'] = 'invented'
            elif mutation == 'duplicate': bad['assertions'][0] = copy.deepcopy(bad['assertions'][1])
            elif mutation == 'missing': bad['assertions'].pop()
            else: bad['assertions'][0]['passed'] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.check(bad)
        for key in ('probe', 'visits', 'malformed_inputs', 'webrtc'):
            bad = copy.deepcopy(self.report); bad.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError): self.check(bad)

    def test_identity_params_and_typed_process_observations(self):
        for key, value in (('seed', None), ('seed', True), ('expected_cpu', 16),
                           ('expected_cpu', True), ('expected_memory', '1'),
                           ('expected_timezone', 'Asia/Kolkata')):
            bad = copy.deepcopy(self.report); bad['visits'][1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): self.check(bad)
        for group in ('probe', 'visits', 'malformed_inputs', 'webrtc'):
            bad = copy.deepcopy(self.report)
            item = bad['probe'] if group == 'probe' else (bad['webrtc']['visits'][0] if group == 'webrtc' else bad[group][0])
            item['process']['active_processes'] = False
            with self.subTest(group=group), self.assertRaises(ValueError): self.check(bad)
        bad = copy.deepcopy(self.report); bad['visits'][1]['result']['main']['hardwareConcurrency'] = True
        with self.assertRaises(ValueError): self.check(bad)
        bad = copy.deepcopy(self.report); bad['visits'][1]['result']['main']['canvas']['first'] = '00'
        with self.assertRaisesRegex(ValueError, 'recomputed'): self.check(bad)

    def test_exact_probe_hash_status_errors(self):
        for mutate in (lambda r: r['verification'].update(manifest_sha256='b'*64),
                       lambda r: r['verification'].update(files_verified=True),
                       lambda r: r.update(harness_error='failed'),
                       lambda r: r.update(bundle_reverified_after_visits=1),
                       lambda r: r.update(status='failed'),
                       lambda r: r['probe']['actual_info']['capabilities'].update(webrtc_non_proxied_udp_proxied_webframes=1)):
            bad = copy.deepcopy(self.report); mutate(bad)
            with self.assertRaises(ValueError): self.check(bad)

    def test_network_cases_recomputed_and_netlog_proof(self):
        for mutation in ('missing', 'duplicate', 'unknown', 'counter_bool', 'stun', 'assertions'):
            bad = copy.deepcopy(self.report); visits = bad['webrtc']['visits']
            if mutation == 'missing': visits.pop()
            elif mutation == 'duplicate': visits[0]['label'] = visits[1]['label']
            elif mutation == 'unknown': visits[0]['label'] = 'invented'
            elif mutation == 'counter_bool': visits[0]['udp_datagrams'] = False
            elif mutation == 'stun': next(x for x in visits if x['label']=='native HTTP proxy')['udp_datagrams'] = 1
            else: bad['webrtc']['assertions'].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.check(bad)
        run = next(x for x in self.report['webrtc']['visits'] if 'unavailable' in x['label'])
        run['proxy_neterror'] = None
        run['proxy_failure_netlog'] = {'source_id': 7, 'event': 'URL_REQUEST_START_JOB',
            'net_error': -130, 'error_name': 'ERR_PROXY_CONNECTION_FAILED', 'owned_url_matched': True}
        self.check(self.report)
        for key, value in (('source_id', True), ('net_error', True), ('net_error', -102),
                           ('event', 'OTHER'), ('owned_url_matched', 1), ('error_name', 'OTHER')):
            bad = copy.deepcopy(self.report)
            next(x for x in bad['webrtc']['visits'] if 'unavailable' in x['label'])['proxy_failure_netlog'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(bad)

    def test_duplicate_json_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory(prefix='neantik-report-unit-') as root:
            path = Path(root)/'report.json'
            for text in ('{"status":"passed","status":"passed"}', '{"nested":{"x":1,"x":1}}', '{"x":NaN}', '{"x":1e999}', '{"x":-1e999}'):
                path.write_text(text)
                with self.assertRaises(ValueError): v.load_report(path)
            path.write_text(json.dumps(self.report))
            self.check(v.load_report(path))

    def test_png_timing_and_actual_bypass_observation_shapes(self):
        for value in (None, True, '1', -1, float('nan'), float('inf')):
            bad = copy.deepcopy(self.report)
            bad['visits'][0]['result']['largeCanvas']['pngMs'] = value
            with self.subTest(pngMs=value), self.assertRaises(ValueError): self.check(bad)
        for name in ('translucent', 'displayP3', 'float16'):
            for value in (None, {}, {'unsupported': ''}, {'unsupported': True}):
                bad = copy.deepcopy(self.report)
                bad['visits'][0]['result']['main']['canvas'][name] = value
                with self.subTest(name=name, value=value), self.assertRaises(ValueError): self.check(bad)
        self.report['visits'][0]['result']['main']['canvas']['displayP3'] = {'unsupported': 'synthetic unavailable'}
        self.report['visits'][0]['result']['main']['canvas']['float16'] = {'pixelFormat': 'rgba-float16', 'digest': 'a'*64}
        self.report['comparisons'] = v.fingerprint.comparisons(self.report['visits'])
        self.check(self.report)

    def test_comparison_recomputation_typed_exact_equality(self):
        for mutate in (lambda r: r.pop('comparisons'),
                       lambda r: r['comparisons']['timings']['A'].update(png_ms=True),
                       lambda r: r['comparisons']['timings']['A'].update(png_ms=1),
                       lambda r: r['comparisons']['timings']['A'].update(png_ms=float('nan')),
                       lambda r: r['comparisons']['known_bypass_observations']['float16'].update(protected=0),
                       lambda r: r['comparisons'].update(unknown='invented')):
            bad = copy.deepcopy(self.report); mutate(bad)
            with self.assertRaises(ValueError): self.check(bad)

    def test_ua_and_http_headers_are_real_typed_strings(self):
        for context in v.fingerprint.CONTEXTS:
            for mutation in ('both_boolean', 'header_boolean', 'empty', 'header_case_duplicate'):
                bad = copy.deepcopy(self.report)
                surface = bad['visits'][1]['result'][context]
                if mutation == 'both_boolean':
                    surface['userAgent'] = True
                    surface['requestHeaders']['User-Agent'] = True
                elif mutation == 'header_boolean':
                    surface['requestHeaders']['Sec-CH-Device-Memory'] = True
                elif mutation == 'empty': surface['userAgent'] = ''
                else: surface['requestHeaders']['user-agent'] = surface['userAgent']
                with self.subTest(context=context, mutation=mutation), self.assertRaises(ValueError): self.check(bad)

if __name__ == '__main__': unittest.main()
