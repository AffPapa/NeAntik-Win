# Experimental native persona: evidence and release gates

Status: **development checkout only**, 2026-10-13. These changes are not in
the downloadable 0.8.1-preview core, and the manager does not offer a native
persona mode. Do not describe the current release as providing per-profile
Canvas or timezone changes.

The complete [experimental Chromium patch](chromium-native-persona-prototype.patch)
is now public for review. It is based on upstream commit
`cfaadc5a132d78e1828635aa8405a499f3e14864`, contains 14 modified
runtime/test files and 15 added source/web-test files, and has SHA-256
`7ec3200a9ce0c0c8bb0cab8e7070a7be39a6b5e08704d92c45d1dd4c4f35d133`.
It excludes the separate build-only compatibility patch. It supersedes the
0.8.x CPU/memory baseline for development; **do not apply both patches**.
The [export verifier](../tools/export_native_persona_patch.py) checks the
exact changed-file allowlist, reverse-application to the development checkout
and forward application from the pinned upstream files to byte-identical
sources without changing that checkout. Modified Chromium files retain their
upstream BSD-style license; new Chromium-tree files declare the same license.
No public binary has been built or released from this exported patch yet.

## What was measured on one Windows 11 x64 computer

The local Chromium 155 development build reports a compiled native capability
handshake. With a disposable profile and explicit test switches for a fixed
seed, three logical cores, 4 GiB device-memory bucket and `Europe/Berlin`, a
loopback page observed those CPU/memory/timezone values in its main document,
same-origin iframe, different-origin iframe, dedicated worker, Shared Worker
and Service Worker. The HTTP Device-Memory Client Hint matched the JavaScript
value. An invalid timezone exited with code 78 before a page loaded.

The [disposable Canvas probe](../tools/native_canvas_audit.py) passed repeat
reads, subregion parity, repeat PNG encoding, non-mutating export and clear-to-
transparent checks. Two fresh profiles with the same seed produced identical
pixel and PNG hashes; a different seed changed both. The **released** 0.8.1
core failed the seed-difference control as expected, confirming this feature
was not accidentally shipped. Reports containing local environment data stay
outside Git.

These are narrow functional checks, not a measurement of anonymity or
cross-site unlinkability. Per-profile stable Canvas changes may *increase*
fingerprint uniqueness. The present prototype changes opaque sRGB uint8
Canvas2D readbacks only; translucent content, wide-gamut/float16 paths,
WebGL/WebGPU, AudioContext, fonts, TLS, IP and many other surfaces remain
untouched. Cross-API and real-site compatibility are not yet established.

## Gates before any public release

1. Patch export and byte-for-byte source reconstruction are done. Before a
   release, rebuild from a clean application of this patch, verify license
   notices and record exact source/build hashes in the engine and ZIP receipts.
2. Choose the privacy model using empirical cohort and linkability testing.
   Do not enable stable per-profile variation merely because different hashes
   look like successful spoofing. Prefer coordinated, understandable defaults.
3. Persist a profile identity without leaking it through logs, diagnostics or
   backups unintentionally; define copy/restore/migration semantics and ensure
   the launcher rejects unsupported cores instead of silently running stock
   Chromium with ignored switches.
4. Extend automated checks to main and worker Canvas, `getImageData`,
   `toDataURL`, `toBlob`, OffscreenCanvas, partial transparency, color spaces,
   WebGL/WebGPU, timezone across `Date`/`Intl` and HTTP/JS coherence. Include
   same-seed restart, different-seed separation and negative controls.
5. Measure broken sites, graphics correctness, browser speed and memory on
   multiple GPUs/hardware classes and Windows 10/11. Run proxy, DNS, IPv4/IPv6,
   WebRTC/STUN/TURN and fail-closed network tests independently.
6. Build from a clean, pinned commit and publish only after packaged ZIP QA,
   source/secret scan, public download re-hash, changelog and site update.

None of these gates is waived by a passing local Canvas smoke test.
