"""Scratch-only MSFT TLB name-hash normalization proof; does not edit files.

Not integrated into Chromium. Only ASCII-name MSFT TLBs with a supported
header layout are accepted. Full immutable upstream equality is mandatory.
"""
import argparse
import ctypes
import hashlib
from pathlib import Path
import struct


def normalize_name_hashes(data: bytes, hasher) -> bytes:
    if len(data) < 84 or data[:8] != b'MSFT\x02\x00\x01\x00':
        raise ValueError('Unsupported MSFT TLB header')
    ntypes, flags, lcid = struct.unpack_from('<I', data, 32)[0], struct.unpack_from('<I', data, 20)[0], struct.unpack_from('<I', data, 12)[0]
    syskind = flags & 0xF
    if syskind not in (1, 3) or flags & 0x100 or not 0 < ntypes < 4096 or not 0 < lcid < 0x10000:
        raise ValueError('Unsupported TLB platform, locale or directory layout')
    directory = 84 + 4 * ntypes
    if directory + 15 * 16 > len(data):
        raise ValueError('Truncated TLB segment directory')
    sections = []
    for index in range(15):
        offset, length = struct.unpack_from('<II', data, directory + index * 16)
        if length:
            if offset % 4 or offset < directory + 15 * 16 or offset + length > len(data):
                raise ValueError('Invalid TLB segment range or alignment')
            sections.append((offset, offset + length))
    ordered = sorted(sections)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError('Overlapping TLB segments')
    hash_offset, hash_length = struct.unpack_from('<II', data, directory + 6 * 16)
    name_offset, name_length = struct.unpack_from('<II', data, directory + 7 * 16)
    if hash_length != 512 or name_length == 0 or name_length % 4 or any(offset < directory + 15 * 16 or offset + length > len(data) for offset, length in ((hash_offset, hash_length), (name_offset, name_length))) or not (hash_offset + hash_length <= name_offset or name_offset + name_length <= hash_offset):
        raise ValueError('Invalid or overlapping TLB name segments')
    records = []
    cursor = 0
    while cursor < name_length:
        if cursor + 12 > name_length:
            raise ValueError('Truncated TLB name record')
        packed = struct.unpack_from('<I', data, name_offset + cursor + 8)[0]
        length = packed & 0xFF
        end = cursor + 12 + length
        if length == 0 or end > name_length:
            raise ValueError('Invalid TLB name length')
        name = data[name_offset + cursor + 12:name_offset + end].decode('ascii')
        if any(ord(char) < 32 for char in name):
            raise ValueError('Unsupported TLB name characters')
        records.append((cursor, packed, name))
        cursor = (end + 3) & ~3
    if cursor != name_length or len(records) != struct.unpack_from('<I', data, 48)[0] or sum(len(name) for _, _, name in records) != struct.unpack_from('<I', data, 52)[0]:
        raise ValueError('TLB name count or padding mismatch')
    offsets = {record[0] for record in records}
    for relative, _, _ in records:
        link = struct.unpack_from('<I', data, name_offset + relative + 4)[0]
        if link != 0xFFFFFFFF and link not in offsets:
            raise ValueError('Invalid TLB name chain pointer')
    record_map = {relative: packed for relative, packed, _ in records}
    visited = set()
    for bucket in range(128):
        relative = struct.unpack_from('<I', data, hash_offset + bucket * 4)[0]
        while relative != 0xFFFFFFFF:
            if relative not in record_map or relative in visited or ((record_map[relative] >> 16) & 0x7F) != bucket:
                raise ValueError('Corrupt TLB name hash chain or bucket')
            visited.add(relative)
            relative = struct.unpack_from('<I', data, name_offset + relative + 4)[0]
    if visited != offsets:
        raise ValueError('TLB names are missing from hash buckets')
    buckets = [0xFFFFFFFF] * 128
    result = bytearray(data)
    for relative, packed, name in records:
        hash_value = hasher(syskind, lcid, name) & 0xFFFF
        bucket = hash_value & 0x7F
        struct.pack_into('<I', result, name_offset + relative + 4, buckets[bucket])
        struct.pack_into('<I', result, name_offset + relative + 8, (packed & 0xFFFF) | hash_value << 16)
        buckets[bucket] = relative
    struct.pack_into('<128I', result, hash_offset, *buckets)
    return bytes(result)


def windows_hasher():
    function = ctypes.WinDLL('oleaut32').LHashValOfNameSys
    function.argtypes = (ctypes.c_int, ctypes.c_uint32, ctypes.c_wchar_p)
    function.restype = ctypes.c_uint32
    return function


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual', type=Path, required=True)
    parser.add_argument('--expected', type=Path, required=True)
    args = parser.parse_args()
    actual, expected = args.actual.read_bytes(), args.expected.read_bytes()
    normalized = normalize_name_hashes(actual, windows_hasher())
    print('actual_sha256=' + hashlib.sha256(actual).hexdigest())
    print('normalized_sha256=' + hashlib.sha256(normalized).hexdigest())
    print('expected_sha256=' + hashlib.sha256(expected).hexdigest())
    print('changed_offsets=' + str([i for i, (a, b) in enumerate(zip(actual, normalized)) if a != b]))
    print('immutable_upstream_exact_match=' + str(normalized == expected))
    return 0 if normalized == expected else 1


if __name__ == '__main__':
    raise SystemExit(main())
