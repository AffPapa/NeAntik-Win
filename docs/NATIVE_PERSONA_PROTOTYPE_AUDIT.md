# Experimental native persona: evidence and release gates

Status: **development checkout only**, 2026-10-13. These changes are not in
the downloadable 0.8.1-preview core, and the manager does not offer a native
persona mode. Do not describe the current release as providing per-profile
Canvas or timezone changes.

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

1. Export a complete, reviewable native patch from the development checkout,
   including new files and exact upstream commit. Keep build-compatibility and
   runtime changes separate. Verify licensing and source/build hash provenance.
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
