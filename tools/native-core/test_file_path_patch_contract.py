"""Source-contract regression only; cannot establish C++ compilation success."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class FilePathContractTests(unittest.TestCase):
    def test_generator_template_defines_file_path_before_path_value_use(self):
        source = (ROOT / 'core/native/neantik_fingerprint.cc').read_text()
        self.assertIn('#include "base/files/file_path.h"', source)
        self.assertLess(source.index('#include "base/files/file_path.h"'), source.index('GetSwitchValuePath'))

    def test_supplementary_patch_only_adds_defining_include(self):
        patch = (ROOT / 'core/patches/010-define-core-info-file-path.patch').read_text()
        additions = [line for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
        removals = [line for line in patch.splitlines() if line.startswith('-') and not line.startswith('---')]
        self.assertEqual(additions, ['+#include "base/files/file_path.h"'])
        self.assertEqual(removals, [])
        self.assertIn('a/third_party/blink/common/fingerprinting/neantik_fingerprint.cc', patch)

if __name__ == '__main__': unittest.main()
