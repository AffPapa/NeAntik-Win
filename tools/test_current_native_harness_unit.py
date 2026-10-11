"""Synthetic unit tests of the QA validator; never evidence of browser behaviour."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import test_current_native_fingerprint as harness


def synthetic_case(label,seed,cpu=8,memory='8',zone='Europe/Berlin'):
    pixels=harness.expected_pixels(seed)
    data=bytes.fromhex(pixels)
    surface={'hardwareConcurrency':cpu,'deviceMemory':float(memory),'timezone':zone,
      **dict(zip(('winterOffset','summerOffset','beforeDst','afterDst'),harness.ZONE_EXPECTATIONS[zone])),
      'userAgent':'synthetic-unit-fixture','requestHeaders':{'User-Agent':'synthetic-unit-fixture','Sec-CH-Device-Memory':memory},
      'canvas':{'first':pixels,'repeated':pixels,'afterExports':pixels,'putImageData':pixels,'blob':pixels,'dataURL':pixels,
        'subrect':b''.join(data[(y*32+4)*4:(y*32+11)*4] for y in range(5,13)).hex(),
        'outOfBounds':'00000000','cleared':True}}
    result={key:copy.deepcopy(surface) for key in harness.CONTEXTS}
    result.update(early={key:surface[key] for key in harness.FIELDS},
      offscreen={'kind':'OffscreenCanvas',**copy.deepcopy(surface['canvas'])},
      largeCanvas={'width':2048,'height':2048,'readbackMs':[1,2,3],'lastDigest':'a'*64,'pngBytes':1})
    return {'label':label,'seed':seed,'expected_cpu':cpu,'expected_memory':memory,'expected_timezone':zone,
      'process':{'return_code':0,'active_processes':0,'peak_job_committed_bytes':50000000,
        'peak_process_committed_bytes':30000000},'dom_matches_server':True,'result':result}


class NativeHarnessValidatorTests(unittest.TestCase):
    def test_probe_requires_narrow_coverage_and_exact_source(self):
        info={'engine_id':'neantik-chromium','version':harness.VERSION,'source_commit':harness.COMMIT,
          'schema':1,'capability_evidence':'compiled-source-only','capabilities':dict.fromkeys(
            ('stable_seed','hardware_concurrency','device_memory','canvas_opaque_srgb_uint8','timezone'),True)}
        info['capabilities'].update(dict.fromkeys(
          ('canvas','canvas_float16','canvas_display_p3','canvas_translucent'),False))
        harness.validate_probe_info(info)
        for change in ('general_canvas','wrong_source','missing_narrow'):
            invalid=copy.deepcopy(info)
            if change=='general_canvas':invalid['capabilities']['canvas']=True
            elif change=='wrong_source':invalid['source_commit']='0'*40
            else:invalid['capabilities'].pop('canvas_opaque_srgb_uint8')
            with self.assertRaises(harness.HarnessError):harness.validate_probe_info(invalid)
    def cases(self):
        return [synthetic_case('Baseline',None),synthetic_case('A',123456),
                synthetic_case('A restart',123456),synthetic_case('B',987654),
                synthetic_case('Hardware timezone',765432,16,'16','America/New_York')]
    def test_complete_synthetic_assessment_is_consistent(self):
        self.assertTrue(all(item['passed'] for item in harness.assess(self.cases())))
    def test_missing_required_worker_cannot_pass(self):
        cases=self.cases();cases[1]['result']['serviceWorker']={'error':'unsupported'}
        self.assertFalse(all(item['passed'] for item in harness.assess(cases)))
    def test_stock_canvas_on_seeded_case_cannot_pass(self):
        cases=self.cases();cases[1]['result']['main']['canvas']['first']=harness.expected_pixels(None)
        self.assertFalse(all(item['passed'] for item in harness.assess(cases)))
    def test_false_result_missing_dom_or_descendant_cannot_pass(self):
        for field,value in [('dom_matches_server',False),('process',{'return_code':0,'active_processes':1})]:
            cases=self.cases();cases[1][field]=value
            self.assertFalse(all(item['passed'] for item in harness.assess(cases)))
    def test_dst_mismatch_and_header_memory_mismatch_cannot_pass(self):
        for path,value in [('afterDst',-60),('requestHeaders',{'User-Agent':'synthetic-unit-fixture','Sec-CH-Device-Memory':'32'})]:
            cases=self.cases();cases[1]['result']['crossIframe'][path]=value
            self.assertFalse(all(item['passed'] for item in harness.assess(cases)))
    def test_no_observations_and_duplicate_json_are_rejected(self):
        self.assertFalse(all(item['passed'] for item in harness.assess([])))
        with self.assertRaisesRegex(harness.HarnessError,'Duplicate JSON'):
            harness.unique_json('{"schema":1,"schema":2}')
    def test_native_reference_alpha_and_seed_invariants(self):
        a=bytes.fromhex(harness.expected_pixels(123456));b=bytes.fromhex(harness.expected_pixels(987654))
        ordinary=bytes.fromhex(harness.expected_pixels(None))
        self.assertEqual(len(a),32*24*4);self.assertNotEqual(a,b)
        self.assertTrue(all(a[index]==255 for index in range(3,len(a),4)))
        self.assertTrue(all(abs(x-y)<=1 for x,y in zip(a,ordinary)))
        self.assertEqual(harness.expected_pixels(123456),harness.expected_pixels(123456))
    def test_unknown_manifest_and_wrong_trusted_hash_fail_before_execution(self):
        with tempfile.TemporaryDirectory(prefix='neantik-validator-unit-') as temporary:
            root=Path(temporary);engine=root/harness.current_core.ENGINE_DIRECTORY;engine.mkdir(parents=True)
            manifest=engine/harness.current_core.MANIFEST_NAME
            manifest.write_text(json.dumps({'format':'unknown'}),encoding='utf-8')
            digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
            with self.assertRaisesRegex(harness.HarnessError,'Unknown native core'):
                harness.verify_bundle(root,digest)
            with self.assertRaisesRegex(harness.HarnessError,'trusted hash'):
                harness.verify_bundle(root,'0'*64)


if __name__=='__main__':unittest.main()
