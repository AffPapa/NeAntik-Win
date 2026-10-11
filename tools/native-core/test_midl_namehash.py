"""Bounded TLB metadata normalization regressions, no OS locale changes."""
import importlib.util
import os
from pathlib import Path
import struct
import unittest

module_spec = importlib.util.spec_from_file_location('midl_namehash', Path(__file__).with_name('midl-namehash-diagnostic.py'))
normalizer = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(normalizer)
if os.environ.get('NEANTIK_MIDL_SOURCE'):
    source_spec = importlib.util.spec_from_file_location('actual_chromium_midl', os.environ['NEANTIK_MIDL_SOURCE'])
    actual_source = importlib.util.module_from_spec(source_spec)
    source_spec.loader.exec_module(actual_source)
    normalizer.normalize_name_hashes = actual_source.NormalizeNameHashes


def fixture():
    data = bytearray(872)
    data[:8] = b'MSFT\x02\x00\x01\x00'
    struct.pack_into('<I', data, 12, 1033)
    struct.pack_into('<I', data, 20, 3)
    struct.pack_into('<I', data, 32, 1)
    struct.pack_into('<I', data, 48, 2)
    struct.pack_into('<I', data, 52, 6)
    directory = 88
    struct.pack_into('<II', data, directory + 6 * 16, 328, 512)
    struct.pack_into('<II', data, directory + 7 * 16, 840, 32)
    struct.pack_into('<128I', data, 328, *([0xFFFFFFFF] * 128))
    for offset, name in ((840, b'One'), (856, b'Two')):
        struct.pack_into('<III', data, offset, 0xFFFFFFFF, 0xFFFFFFFF, (0xDEAD << 16) | len(name))
        data[offset + 12:offset + 15] = name
        data[offset + 15] = 0x57
    struct.pack_into('<I', data, 328 + (0xDEAD & 0x7F) * 4, 16)
    struct.pack_into('<I', data, 860, 0)
    return bytes(data)


class NameHashTests(unittest.TestCase):
    def hasher(self, syskind, lcid, name):
        self.assertEqual((syskind, lcid), (3, 1033))
        return {'One': 0x1234, 'Two': 0x1334}[name]

    def test_metadata_only_collision_chain_and_idempotency(self):
        source = fixture()
        result = normalizer.normalize_name_hashes(source, self.hasher)
        self.assertEqual(result, normalizer.normalize_name_hashes(result, self.hasher))
        self.assertEqual(struct.unpack_from('<I', result, 328 + (0x34 * 4))[0], 16)
        self.assertEqual(struct.unpack_from('<I', result, 856 + 4)[0], 0)
        allowed = set(range(328, 840)) | set(range(844, 852)) | set(range(860, 868))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(source, result)) if a != b))
        self.assertEqual(result[852:856], source[852:856])

    def test_semantic_bytes_are_never_repaired(self):
        source = bytearray(fixture())
        source[100] = 0x55
        result = normalizer.normalize_name_hashes(bytes(source), self.hasher)
        self.assertEqual(result[100], 0x55)
        self.assertNotEqual(result, normalizer.normalize_name_hashes(fixture(), self.hasher))

    def test_invalid_header_and_directory_fail_closed(self):
        for data in (b'', fixture()[:100], b'INVALID!' + fixture()[8:]):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                normalizer.normalize_name_hashes(data, self.hasher)
        for offset, value in ((20, 2), (20, 0x103), (32, 4096), (12, 0), (48, 3), (52, 7), (88 + 6 * 16, 860), (88 + 6 * 16 + 4, 16), (88 + 7 * 16 + 4, 10000)):
            bad = bytearray(fixture())
            struct.pack_into('<I', bad, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                normalizer.normalize_name_hashes(bytes(bad), self.hasher)

    def test_non_ascii_and_invalid_name_pointers_fail_closed(self):
        for offset, value in ((852, 0xFF), (852, 0), (848, 0), (844, 7)):
            bad = bytearray(fixture())
            bad[offset] = value
            with self.subTest(offset=offset), self.assertRaises((ValueError, UnicodeDecodeError)):
                normalizer.normalize_name_hashes(bytes(bad), self.hasher)

    def test_corrupt_hash_graph_and_other_segment_overlap_rejected(self):
        for offset, value in ((844, 0), (860, 16), (328 + (0xDEAD & 0x7F) * 4, 7), (328 + (0xDEAD & 0x7F) * 4, 0xFFFFFFFF), (88, 840), (88 + 4, 16), (88 + 7 * 16, 841)):
            bad = bytearray(fixture())
            struct.pack_into('<I', bad, offset, value)
            # For a declared overlapping active segment, set both words.
            if offset == 88:
                struct.pack_into('<I', bad, 92, 16)
            if offset == 92:
                struct.pack_into('<I', bad, 88, 840)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                normalizer.normalize_name_hashes(bytes(bad), self.hasher)


if __name__ == '__main__':
    unittest.main()
