# Chromium 155 conservative fingerprint-reduction baseline

Status: native source patch shipped in 0.8.x-preview, not an anonymity
claim. The app and browser are open source; the modified Chromium files retain
their upstream BSD-style license. See [the full implementation plan](MASTER_IMPLEMENTATION_PLAN.md).

This document describes a historical patch, not the 0.8.17-preview candidate.
That candidate uses stock Chromium and discloses `fingerprint_modification: false`;
it does not bundle or activate the patch below.

## What changes

The published [`chromium-privacy-baseline.patch`](chromium-privacy-baseline.patch)
modifies exactly three Chromium source files at upstream commit
`cfaadc5a132d78e1828635aa8405a499f3e14864`:

1. `NavigatorConcurrentHardware::hardwareConcurrency()` reports at most four
   logical CPU threads. It never reports more than the actual host. This is a
   JS-exposed signal in Window and Worker contexts, not a CPU scheduler limit.
2. `ApproximatedDeviceMemory` caps the existing coarse desktop memory bucket
   at 8 GiB instead of 32 GiB. The same shared value is consumed by
   `navigator.deviceMemory` and `Sec-CH-Device-Memory` when the site requests
   that Client Hint. Physical RAM is not restricted.
3. Upstream unit-test expectations for 16/32/64-GiB desktops are updated to
   the new 8-GiB cap. Other upstream tests and the browser sandbox are not
   disabled.

The SHA-256 of `git diff HEAD --binary --` for those three files, in the order
used by `tools/prepare_source_built_chromium.py`, is
`24977527be3635ac888d7527c9ff4176b06e2ddc09a1d982001564a316a5d8f7`.
For the historical Chromium 155.0.8059.40 build, the separate build-
compatibility diff was
`fcadf05210669f23925f165d28693e7713f9246c6d382ba7ba24289c4ce81079`.
Staging rejects any other tracked change, a mismatched diff hash, or a patch
file that cannot be reverse-applied to the exact source tree. The receipt and
release manifest both record the privacy diff hash; the archive verifier
requires them to agree and requires `fingerprint_modification: true`.

## Local observation on Windows 11 x64 (2026-10-12)

With two disposable loopback-only profiles per build, the clean source-built
Chromium exposed 16 logical threads and a 32-GiB memory bucket. The patched
build exposed 4 and 8 respectively. Main document, same-origin iframe,
dedicated worker, HTTP User-Agent and the observed Device-Memory Client Hint
were internally consistent in both builds. Post-release loopback QA on the
0.8.1 binary additionally checked a different-origin iframe, Shared Worker
and Service Worker; all agreed on the measured values in two disposable
profiles. The local reports remain outside
the Git repository because they contain device traits. The audit does not
prove that real sites cannot distinguish NeAntik from Chromium or correlate
two profiles.

## Why this is deliberately narrow

W3C explicitly allows implementation-defined bounds for Device Memory to
reduce fingerprinting risk, and a browser may report fewer logical cores than
the physical host. Both changes are conservative for low-end computers and
avoid per-profile random values. However, a 4/8 combination can itself
identify this modified browser cohort. On one computer, two profiles still
share language, timezone, GPU, screen, fonts, Canvas, Audio, TLS, IP and many
other signals. This patch does not alter any of those signals, proxy routing,
cookies or accounts. It is **not** a complete antidetect or anonymity mode.

## Build and QA gate

Apply the build-compatibility patch from `CHROMIUM_SOURCE_BUILD.md`, then apply
the privacy patch above to the pinned checkout. Build with the recorded GN
arguments and `autoninja -C out/NeAntik -j 4 chrome`; stage with
`--approved-build-patch-sha256`, `--approved-privacy-patch-sha256` and
`--privacy-patch-file`. Never disable Defender, Windows sandbox or certificate
validation to make a test pass. Verify the compiled binary and release ZIP in
fresh disposable folders, including Window/iframe/worker/Client Hint agreement,
profile separation and proxy tests. Windows 10, a second hardware class,
cross-site HTTPS, different hardware, incognito mode and broad site
compatibility are not yet validated and remain follow-up gates before a
stronger privacy claim.

Primary references: [Tor Browser fingerprinting protections](https://support.torproject.org/tor-browser/features/fingerprinting-protections/),
[W3C Device Memory API](https://www.w3.org/TR/device-memory/),
[MDN hardwareConcurrency](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/hardwareConcurrency).
