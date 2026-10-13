# Experimental native persona: evidence and release gates

Status: **development checkout only**, 2026-10-13. These changes are not in
the downloadable 0.8.3-preview core (the same baseline engine as 0.8.2). The unreleased manager source now has an
opt-in preview profile mode gated on an exact staged-core receipt and compiled
capability report; the downloadable manager does not offer it. Do not describe
the current release as providing per-profile Canvas or timezone changes.

The revised [experimental Chromium patch](chromium-native-persona-prototype-v3.patch)
is now public for review. It is based on upstream commit
`cfaadc5a132d78e1828635aa8405a499f3e14864`, contains 14 modified
runtime/test files and 15 added source/web-test files, and has SHA-256
`40aeda86ee42b9c6b56227effd3842be3dd58aa4ee06bd337513641856ac0193`.
V1 and V2 remain in Git for comparison and must not be mixed with this revision.
V3 bounds exposed CPU count and memory to the stock host values and increments
the compiled-core handshake schema to 2. The staging tool rejects older
schema-1 binaries even when they advertise the same named capabilities.
Synthetic low-end tests cover the bound; a second physical host is still a
release gate.
It excludes the separate build-only compatibility patch. It supersedes the
0.8.x CPU/memory baseline for development; **do not apply both patches**.
The [export verifier](../tools/export_native_persona_patch.py) checks the
exact changed-file allowlist, reverse-application to the development checkout
and forward application from the pinned upstream files to byte-identical
sources without changing that checkout. Modified Chromium files retain their
upstream BSD-style license; new Chromium-tree files declare the same license.
A clean-from-scratch development binary has now been built from this patch;
no public binary has been released from it.

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

After the V3 schema-2 revision, an **incremental development-core rebuild**
completed on this Windows 11 host. Its compiled handshake reports schema 2,
Chromium `155.0.8059.40` and the pinned upstream commit. The disposable Canvas
probe passed again. The new [native context audit](../tools/native_persona_context_audit.py)
passed seven checks: six JavaScript contexts and the Device-Memory Client Hint
agreed, the same seed repeated, different seeds left common CPU/RAM/timezone
surfaces unchanged, and CPU/memory did not exceed the observed stock host.
The audit uses only loopback content and writes raw device observations outside
Git. The patched development checkout also passed 19 native fingerprint parser/
bounds tests, five native Canvas readback tests and three renderer-preference
tests. These are not a clean release build, cross-machine test or anonymity
score.

An **internal-only QA ZIP** was then packaged from the incremental core in a
separate build directory. Its archive verifier passed, the extracted EXE's
`--self-test` returned zero, four disposable launcher cases passed (ordinary
and native profiles, with and without a local proxy), and seven context checks
passed against the packaged core. Direct browser probes must first grant the
Windows AppContainer read permission to a **disposable copy** of the bundled
engine, exactly as the launcher does; omitting that step initially caused the
direct probe to fail. The audit tool now copies and prepares the core itself.
This QA ZIP deliberately reuses the source's current version number and is
**not publishable**: it is an incremental test artifact, not an immutable new
release from the clean build.

On 2026-10-13 a separate clean-from-scratch Chromium build completed from the
final V3 sources. The resulting `chrome.exe` reports schema 2, Chromium
`155.0.8059.40`, and the pinned source commit. The staging tool verified the
exact patch and build-only patch hashes, source/build provenance, compiled
handshake, 36 runtime files, and bundled license/credits. A fresh loopback
Canvas probe and the seven-check context/Client-Hint audit both passed on this
clean staged core. A new **internal-only** portable ZIP was then built from
that core; its 1,066-file archive check, extracted EXE self-test, and four
ordinary/native launcher cases passed. Its SHA-256 is
`fb9f566cdc1bc6a37f6d699d42f839f8724a07ffb959bf15b372fb1d1accbc33`.
On a disposable extraction of this clean-build archive, 23 loopback proxy
assertions, 14 browser-storage isolation assertions and the third-party-cookie
positive/negative controls also passed. The application Python suite passed
115 tests with three skipped, and the release-tool suite passed 50 checks.
These tests do not observe a public network path.
In a manual GUI smoke on the disposable extracted ZIP, the manager window
opened, an ordinary profile was created from the form, its Launch button
started the bundled `Engine/Chromium/chrome.exe`, and both windows closed
normally with no QA processes left running. This checked the ordinary GUI
path only, not a V3 persona, backup UI or anonymous networking. The default
Chromium new-tab page displayed Google content; the current package must not
be described as preventing all browser-initiated third-party requests.
The next audit revision also compared `Date.getTimezoneOffset()` with `Intl`
timezone in all six browser contexts. Its eighth check passed on the clean
staged core, and the ordinary two-profile context audit stayed consistent.
The following loopback audit revision compared JavaScript high-entropy
`fullVersionList` and `platformVersion` with the corresponding HTTP Client
Hints. Both matched on the clean staged core in ordinary and opt-in V3 runs;
unit tests reject missing or contradictory hints. This does not test all
User-Agent Client Hints or prove real-site coherence.
It deliberately still uses the development source's `0.8.1-preview` filename
and must not overwrite the already-published, different 0.8.1 ZIP. Raw QA
reports and this internal ZIP remain outside Git.

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
larger than those of the host. V3 bounds both values by stock Chromium's
observed host values, including the shared HTTP device-memory hint source.
The clean-from-scratch rebuild is complete. The revised code still needs
broader cross-API and real-site compatibility tests, empirical cohort and
linkability evaluation, and validation on a second hardware class before any
release.

### Local linkability control: V3 Canvas is held from release

On 2026-10-13, the [disposable comparison tool](../tools/native_canvas_linkability_audit.py)
opened the same loopback Canvas probe in eight fresh baseline profiles and
eight fresh V3 profiles on this Windows 11 host. It used eight fixed test seeds
and repeated the first seed in another fresh profile. The byte-verified public
0.8.1 core produced **one** pixel hash and **one** PNG hash across the eight
seeds. The clean-build V3 core produced **eight** distinct pixel hashes and
**eight** distinct PNG hashes; the first seed's two hashes repeated in its
fresh profile. The local report is outside Git and contains only aggregate
counts and binary hashes, not raw Canvas values.

This is evidence that the V3 seed creates a repeatable, profile-specific
Canvas signal in the tested path. It is an **inference of linkability risk**,
not a real-site tracking demonstration or population entropy measurement.
The audit's release gate is
`blocked_by_stable_per_profile_canvas_identifier`: do not publish this V3
Canvas mode as a privacy feature. It remains an opt-in development test case.
The next design candidate is a common, coherent cohort value or a usable
permission-based restriction, evaluated against stock Chromium and a
consented multi-device cohort before any default or public release.

The 2026-10-13 expanded frame audit adds a SHA-256 of one Canvas2D scene and
WebGL vendor/renderer observations to the main, same-origin and cross-origin
frames, plus a pixel-readback comparison with a dedicated worker's
OffscreenCanvas. On the exact 0.8.3 public core, two disposable profiles
agreed in all measured contexts. On the clean V3 core, repeating a seed
repeated the measured surface, while changing the seed changed the Canvas
hashes; the non-Canvas
surfaces stayed equal. The V3 audit now reports these as separate checks, so
the linkability warning cannot be hidden inside a generic mismatch. This
remains a single-host, headless loopback observation, not a population study.

## Gates before any public release

1. Patch export, byte-for-byte source reconstruction, clean-core build,
   development staging, compiled capability handshake, license notices and
   source/build hashes in the engine and ZIP receipts are done locally.
   Repeat these checks after any source or build change before a release.
2. Resolve the measured V3 Canvas linkability warning above. Choose the
   privacy model using empirical cohort and linkability testing. Do not enable
   stable per-profile variation merely because different hashes look like
   successful spoofing. Prefer coordinated, understandable defaults.
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
