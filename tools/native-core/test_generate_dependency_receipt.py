import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('receipt',Path(__file__).with_name('generate-dependency-receipt.py'))
receipt=importlib.util.module_from_spec(spec);spec.loader.exec_module(receipt)

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.git={'src':{'url':'https://chromium.googlesource.com/chromium/src.git','rev':receipt.SOURCE_COMMIT}}
        self.cipd={'result':{'src/buildtools/win':[{'package':'gn/gn/windows-amd64','pin':{'package':'gn/gn/windows-amd64','instance_id':'A'*43}}]}}

    def test_only_actual_curated_fields(self):
        result=receipt.create_receipt(self.git,self.cipd)
        self.assertEqual(set(result),{'format','schema','source_commit','resolved_dependencies'})
        self.assertEqual(result['resolved_dependencies'][1]['instance_id'],'A'*43)
        self.assertNotIn('version',result['resolved_dependencies'][1])

    def test_bad_pin_and_missing_receipts_fail(self):
        for git,cipd in (({},self.cipd),(self.git,{'result':{}})):
            with self.assertRaises(ValueError):receipt.create_receipt(git,cipd)
        self.git['src']['rev']='main'
        with self.assertRaises(ValueError):receipt.create_receipt(self.git,self.cipd)

    def test_secrets_private_urls_and_queries_fail(self):
        for url in ('https://user:secret@chromium.googlesource.com/repo','https://example.com/repo',
                    'https://chromium.googlesource.com/repo?token=x','http://chromium.googlesource.com/repo',
                    'https://127.0.0.1/repo','https://chromium.googlesource.com/repo#secret'):
            with self.assertRaises(ValueError):receipt.public_origin(url)

    def test_paths_fail_closed(self):
        for value in ('C:/NeAntikSynthetic/file','/etc/secret','../repo','src/../repo',
                      'src\\repo','src//repo','src/token\n','<user-profile>/file',
                      'src/<invalid>','src/token?secret','src/file*'):
            with self.assertRaises(ValueError):receipt.relative(value)

    def test_declared_cipd_version_is_not_installed_pin(self):
        item=self.cipd['result']['src/buildtools/win'][0]
        item['pin']['instance_id']='version:latest'
        with self.assertRaises(ValueError):receipt.create_receipt(self.git,self.cipd)

    def test_unknown_package_and_duplicates_fail(self):
        entry=self.cipd['result']['src/buildtools/win'][0]
        self.cipd['result']['src/buildtools/win'].append(copy.deepcopy(entry))
        with self.assertRaises(ValueError):receipt.create_receipt(self.git,self.cipd)
        entry['package']=entry['pin']['package']='private/company/credentials'
        with self.assertRaises(ValueError):receipt.create_receipt(self.git,self.cipd)

if __name__=='__main__':unittest.main()
