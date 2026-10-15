"""Behavior tests for the source-only exporter, using disposable synthetic files."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('export-public-source.py')
SPEC = importlib.util.spec_from_file_location('public_export', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PublicExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='neantik-export-tests-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'source'
        self.root.mkdir()
        self.write('nevision_win.py', '# application fixture\n')
        self.write('proxy_diagnostics.py', '# imported application module fixture\n')
        self.write('test_proxy_diagnostics.py', '# synthetic loopback tests fixture\n')
        self.write('release-version.json', '{"version":"0.3.0-preview"}\n')
        self.write('tools/check-public-repo.ps1', SCRIPT.with_name('check-public-repo.ps1').read_text(encoding='utf-8-sig'))
        self.destination = self.parent / 'export'

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def test_experimental_engine_sources_are_excluded_from_app_export(self):
        for name in ('browser_engine.py', 'test_browser_engine.py', 'tests/fixtures/fingerprint.html',
                     'tools/engine.js', '.github/workflows/ci.yml', 'docs/PLAN.md',
                     'core/patches/003-canvas.patch', 'core/native/helper.cc',
                     'core/native/LICENSE', 'core/native/helper_tests.inc', 'current_core.py', 'test_current_core.py'):
            self.write(name, '# synthetic fixture\n')
        for name in ('Data/private.json', 'Engine/config.json', 'build/trace.txt',
                     'release/README.md', '.git/config', 'docs/qa/host.json',
                     'assets/private.key', 'tests/.env', 'unreviewed/new.py'):
            self.write(name, 'must never export\n')
        result = MODULE.export(self.root, self.destination)
        paths = {item['path'] for item in result['files']}
        self.assertIn('proxy_diagnostics.py', paths)
        self.assertIn('test_proxy_diagnostics.py', paths)
        self.assertNotIn('browser_engine.py', paths)
        self.assertNotIn('tests/fixtures/fingerprint.html', paths)
        self.assertNotIn('core/patches/003-canvas.patch', paths)
        self.assertNotIn('core/native/LICENSE', paths)
        self.assertNotIn('core/native/helper_tests.inc', paths)
        self.assertNotIn('current_core.py', paths)
        self.assertNotIn('Engine/config.json', paths)
        self.assertNotIn('docs/qa/host.json', paths)
        self.assertNotIn('assets/private.key', paths)
        self.assertNotIn('unreviewed/new.py', paths)
        self.assertTrue((self.destination / 'SOURCE_LICENSE_NOTICE.txt').is_file())
        self.assertEqual(json.loads((self.destination / 'export-manifest.json').read_text()), result)

    def test_secrets_in_new_text_types_abort_before_output(self):
        token = 'ghp_' + 'a' * 32
        for suffix in ('.js', '.html', '.toml', '.csv', '.inc'):
            with self.subTest(suffix=suffix):
                path = 'tools/unsafe' + suffix
                self.write(path, token)
                with self.assertRaisesRegex(ValueError, 'Possible GitHub token'):
                    MODULE.export(self.root, self.destination)
                self.assertFalse(self.destination.exists())
                (self.root / path).unlink()

    def test_local_host_paths_redacted_and_source_unchanged(self):
        original = 'Root <user-profile>\\Documents\\project and <user-profile>/Temp\n'
        self.write('PUBLISHING.md', original)
        MODULE.export(self.root, self.destination)
        copied = (self.destination / 'PUBLISHING.md').read_text()
        self.assertNotIn('SyntheticUser', copied)
        self.assertIn('<user-profile>', copied)
        self.assertEqual((self.root / 'PUBLISHING.md').read_text(), original)

    def test_fine_grained_github_token_rejected_without_value_in_error(self):
        token = 'github_' + 'pat_' + 'b' * 32
        self.write('tools/credential.toml', token)
        with self.assertRaisesRegex(ValueError, 'GitHub fine-grained token') as failure:
            MODULE.export(self.root, self.destination)
        self.assertNotIn(token, str(failure.exception))
        self.assertFalse(self.destination.exists())

    def test_existing_destination_is_never_overwritten(self):
        self.destination.mkdir()
        sentinel = self.destination / 'keep.txt'
        sentinel.write_text('user file')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            MODULE.export(self.root, self.destination)
        self.assertEqual(sentinel.read_text(), 'user file')

    def test_in_tree_destination_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside source tree'):
            MODULE.export(self.root, self.root / 'new-export')
        self.assertFalse((self.root / 'new-export').exists())

    def test_explicit_license_is_preserved_without_invented_notice(self):
        self.write('LICENSE', 'Owner-selected license fixture\n')
        MODULE.export(self.root, self.destination)
        self.assertEqual((self.destination / 'LICENSE').read_text(), 'Owner-selected license fixture\n')
        self.assertFalse((self.destination / 'SOURCE_LICENSE_NOTICE.txt').exists())

    def test_selected_symlink_rejected(self):
        link = self.root / 'tools' / 'linked.py'
        try:
            link.symlink_to(self.root / 'nevision_win.py')
        except OSError:
            self.skipTest('OS does not permit synthetic symlink creation')
        with self.assertRaisesRegex(ValueError, 'Reparse point'):
            MODULE.export(self.root, self.destination)
        self.assertFalse(self.destination.exists())


if __name__ == '__main__':
    unittest.main()
