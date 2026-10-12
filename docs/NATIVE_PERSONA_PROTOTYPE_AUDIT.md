# Experimental native persona: evidence and release gates

Status: **development checkout only**, 2026-10-13. These changes are not in
the downloadable 0.8.1-preview core. The unreleased manager source now has an
opt-in preview profile mode gated on an exact staged-core receipt and compiled
capability report; the downloadable manager does not offer it. Do not describe
the current release as providing per-profile Canvas or timezone changes.

The revised [experimental Chromium patch](chromium-native-persona-prototype-v2.patch)
is now public for review. It is based on upstream commit
`cfaadc5a132d78e1828635aa8405a499f3e14864`, contains 14 modified
runtime/test files and 15 added source/web-test files, and has SHA-256
`7c8b82c79ad8ab06f510729561fb4671e6bbddb3536ec888135be506fa806032`.
The original prototype patch remains in Git for comparison and must not be
mixed with this revision. V2 bounds exposed CPU count and memory to the stock
host values, with synthetic low-end tests; a second physical host is still a
release gate.
It excludes the separate build-only compatibility patch. It supersedes the
0.8.x CPU/memory baseline for development; **do not apply both patches**.
The [export verifier](../tools/export_native_persona_patch.py) checks the
exact changed-file allowlist, reverse-application to the development checkout
and forward application from the pinned upstream files to byte-identical
sources without changing that checkout. Modified Chromium files retain their
upstream BSD-style license; new Chromium-tree files declare the same license.
No public binary has been built or released from this exported patch yet.

The local staging tool now accepts this patch only with its exact approved
SHA-256 and exact public patch bytes. A development-core staging run recorded
the compiled `--neantik-core-info` handshake and matched the built `chrome.dll`
hash; the staged core passed the disposable Canvas probe and the six-context
CPU/memory/timezone audit. This is **not** a clean-from-scratch rebuild or a
portable release. In development source only, the manager can create and launch
an opt-in preview persona with a matching staged core; it rejects stock cores
instead of silently ignoring the native switches. The profile seed is stored
in the local database, passed in the browser command line and included in an
unencrypted v3 backup. It is a stable identifier, **not** a secret or an
anonymity guarantee. A clean clone gets a new seed; restore preserves it.

## What was measured on one Windows 11 x64 computer

The local Chromium 155 development build reports a compiled native capability
handshake. With a disposable profile and explicit test switches for a fixed
seed, three logical cores, 4 GiB device-memory bucket and `Europe/Berlin`, a
loopback page observed those CPU/memory/timezone values in its main document,
same-origin iframe, different-origin iframe, dedicated worker, Shared Worker
and Service Worker. The HTTP Device-Memory Client Hint matched the JavaScript
value. An invalid timezone exited with code 78 before a page loaded.

The [disposable loopback Canvas probe](../tools/native_canvas_audit.py) passed
repeat reads, subregion parity, repeat PNG encoding, `toBlob` decode parity,
OffscreenCanvas export/decode, dedicated-worker OffscreenCanvas parity,
non-mutating export and clear-to-transparent checks. Two fresh profiles with
the same seed produced identical pixel and PNG hashes; a different seed
changed both. The **released** 0.8.1 core failed the seed-difference control
as expected, confirming this feature was not accidentally shipped. The probe
rejects, rather than forwards, background requests outside loopback. Reports
containing local environment data stay outside Git.

These are narrow functional checks, not a measurement of anonymity or
cross-site unlinkability. Per-profile stable Canvas changes may *increase*
fingerprint uniqueness. The present prototype changes opaque sRGB uint8
Canvas2D readbacks only; translucent content, wide-gamut/float16 paths,
WebGL/WebGPU, AudioContext, fonts, TLS, IP and many other surfaces remain
untouched. Cross-API and real-site compatibility are not yet established.
Code review found that V1 could return CPU-thread and memory bucket values
larger than those of the host. V2 now bounds both values by stock Chromium's
observed host values, including the shared HTTP device-memory hint source.
The revised code still needs a completed rebuild, cross-context runtime test
and validation on a second hardware class before any release.

## Gates before any public release

1. Patch export, byte-for-byte source reconstruction and development-core
   staging with a compiled capability handshake are done. Before a release,
   rebuild from a clean application of this patch, verify license notices and
   record exact source/build hashes in the engine and ZIP receipts.
2. Choose the privacy model using empirical cohort and linkability testing.
   Do not enable stable per-profile variation merely because different hashes
   look like successful spoofing. Prefer coordinated, understandable defaults.
3. Persist a profile identity without leaking it through logs, diagnostics or
   backups unintentionally; define copy/restore/migration semantics and ensure
   the launcher rejects unsupported cores instead of silently running stock
   Chromium with ignored switches.
4. Extend automated checks beyond the now-passing main/dedicated-worker
   Canvas2D and OffscreenCanvas smoke test: partial transparency, color spaces,
   WebGL/WebGPU, timezone across `Date`/`Intl` and HTTP/JS coherence. Include
   same-seed restart, different-seed separation and negative controls.
   Bound CPU and memory claims to the host or an otherwise defensible cohort.
5. Measure broken sites, graphics correctness, browser speed and memory on
   multiple GPUs/hardware classes and Windows 10/11. Run proxy, DNS, IPv4/IPv6,
   WebRTC/STUN/TURN and fail-closed network tests independently.
6. Build from a clean, pinned commit and publish only after packaged ZIP QA,
   source/secret scan, public download re-hash, changelog and site update.

None of these gates is waived by a passing local Canvas smoke test.
