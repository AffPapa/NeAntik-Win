# Fingerprint surface matrix and evidence plan

Status: 2026-10-14. This is an engineering inventory, not an anonymity score.
The historical table below preserves the comparison of 0.8.5-preview
(same core as 0.8.3) and the held V3 prototype. The opt-in V4b core was
published in [0.8.6-preview](RELEASE_PUBLICATION_0.8.6-preview.md); the
current [0.8.8-preview V5](RELEASE_PUBLICATION_0.8.8-preview.md) changes its
session-key transport, not the full fingerprint coverage.
An empty or inconsistent measurement is a failure of the audit, not proof of
privacy. Raw reports can reveal device traits and stay outside the repository.

## Published V4b delta and bounded evidence

| Surface | Public 0.8.6-preview V4b | Boundary |
| --- | --- | --- |
| Canvas2D and OffscreenCanvas | Opt-in opaque sRGB uint8 readbacks use a fresh in-memory session key and top-level-site scope, not V3's persistent per-profile Canvas seed. Main document, embedded same-/cross-site frames and dedicated/shared/service workers were measured. | 12/12 two-site/restart cases and 6/6 context cases (11/11 checks) passed on one Windows 11 host. An additional public-binary cross-surface audit checked two synthetic profiles × two sessions: selected Canvas pixel/PNG digests changed in all four sessions while the measured non-Canvas fields and context invariants stayed consistent. No cohort or real-site compatibility proof. |
| CPU, RAM, UTC | Limited native controls retained and audited across measured contexts. | Not a coherent full-browser fingerprint or proxy-derived timezone. |
| WebGL/WebGPU, translucent, float16, display-p3 | Stock or unverified. | No claim of graphics-surface parity or anti-linkability. |
| IP, DNS, UDP, IPv6, WebRTC/TURN | Bounded public STUN control on exact 0.8.7 observed direct `srflx`; proxy-bound rejector observed route-control while browser reported no ICE candidates / NetLog UDP. | No independent packet capture, provider-side proxy logs, general DNS/IPv6/TURN observation, or second network/host. |
| Hardware/OS diversity | 6 + 21 + 3 native tests passed; two staged runs gave 39 byte-identical files. The public ZIP was downloaded back and verified by hash and packaged self-test. | Second machine and Windows 10 **NOT RUN**; only the public-download gate is closed. |

This candidate is tied to Chromium source commit
`cfaadc5a132d78e1828635aa8405a499f3e14864`,
[V4b patch](chromium-native-persona-prototype-v4b.patch) SHA-256
`bba02390999c33bcf6097625c03093022ed534c316184462cc8468efbc79b708`
and `chrome.dll` SHA-256
`6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413`.
The combined V4b audit prints only booleans; its private report contains binary
hashes but no raw device traits. See
[`tools/native_persona_surface_audit.py`](../tools/native_persona_surface_audit.py)
and the [publication evidence](RELEASE_PUBLICATION_0.8.6-preview.md).
These narrow local passes do not establish anonymity.

### Historical V4b key handling review, 2026-10-13

Static review of the exact published V4b patch found that its random Canvas
session key is appended to renderer process command lines and then parsed from
the renderer command line. This does not expose the value to ordinary website
JavaScript, but same-user process inspection, diagnostics, or crash artifacts
may observe it. Therefore the patch's “in-memory only” wording was too broad
for that transport. The public 0.8.7 binary remains unchanged; no retroactive
security guarantee is implied. The 0.8.8 V5 release moved the key into an
early browser-to-renderer Mojo initialization payload and added bounded
renderer/worker argv absence and cross-context isolation tests. See the
[master implementation plan](MASTER_IMPLEMENTATION_PLAN.md#p1--проверяемое-снижение-fingerprint-энтропии), P1.2a.

### Published V5 key transport, 2026-10-14

The V5 source patch moves the random key into the early `InitializeRenderer`
Mojo payload. The renderer stores it once in process memory; the Canvas hot
path reads this initialized state without IPC. Active persona plus missing key
is a renderer failure, not a fallback to raw Canvas pixels. On the local
Chromium 155 candidate (`chrome.dll` SHA-256
`9d0943446e0cbe405f82286ce46c03ad8e928f7b8e46d3ed33082dce2f544075`),
native tests passed 21/21 and 6/6; the loopback two-BrowserContext
main/frame/worker, BrowserContext and session-rotation gate passed 7/7 and
inspected 15 owned process command
lines (9 renderers) without finding the key. The exact packaged and
repeat-downloaded 0.8.8 ZIP passed archive verification and self-test;
see the [publication record](RELEASE_PUBLICATION_0.8.8-preview.md). These
single-host checks do not establish general anonymity.

### P1.3 measurement expansion, 2026-10-14

The loopback-only [`fingerprint_surface_audit.py`](../tools/fingerprint_surface_audit.py)
now observes a tiny deterministic WebGL pixel readback, Canvas text metrics
and OfflineAudioContext sample rate in main, same-origin and cross-origin
frames. Unsupported/error/timeout observations cannot become PASS. On the
exact 0.8.8-preview Chromium extracted from the public ZIP, the expanded
two-profile/two-launch check passed **146/146 boolean checks** on one Windows
11 host. Only the bounded status and check count were printed; raw device
observations stay in a local, unpublished report. This measures consistency,
not reduced uniqueness. A same-revision stock control, second GPU/host,
population-level linkability and real-site compatibility remain **NOT RUN**;
no WebGL, Audio or font spoofing was added.

## Public 0.8.7-preview follow-up, 2026-10-13

Three fresh loopback-only audits were run against the Chromium binary extracted
from the repeat-downloaded public 0.8.7-preview ZIP. Identity was rechecked
before the run: ZIP SHA-256
`9bf12392f8c8057763024cb88666679e8d9938e73cc050f976e7057b5c5234d1`, manager
EXE SHA-256
`e3c97c1623dee5fa2f59d08744b8006d8ca82e2ef3fecf189785688e34bf07eb`, and
Chromium `155.0.8059.40` SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
The release is built from source commit
`d2e6eac9a50f5edfa474ec72aff9ace64c2e8801`.

- **Fingerprint/context consistency: PASS** (tool exit 0): two disposable
  profiles across two launches; tested main/same-origin/cross-origin frames,
  dedicated/shared/service workers, selected Canvas2D/WebGL/audio observations,
  HTTP/JavaScript UA and language parity, and requested UA/device-memory hints
  were observed and consistent. This is one Windows 11 host and the tool's
  selected surfaces, not a full fingerprint inventory or cohort test.
- **V4b surface checks: PASS**: selected Canvas PNG/pixel readbacks changed
  across four disposable sessions, while measured non-Canvas surfaces and
  tested context invariants remained stable. This does not prove reduced
  population uniqueness, unlinkability, compatibility or anonymity.
- **Two-site language/hint checks: PASS**: the tested language/Intl values,
  requested Client Hints and selected HTTP/JavaScript values agreed between
  loopback names `127.0.0.1` and `localhost`. No public website was contacted.

Raw reports with machine observations remain local under
`C:\\NeAntikBuild\\qa` and are excluded from the repository. These results
advance the single-host P0/P1 measurements only; cross-machine/GPU, Windows 10,
real-site compatibility, external DNS/IPv6/TURN, packet capture and
population-level linkability remain **NOT RUN**. The manager and website
binaries were not changed by these audits.

| Surface | Public 0.8.5-preview | Unreleased V3 | Required observation before a privacy claim |
| --- | --- | --- | --- |
| HTTP User-Agent, `navigator.userAgent`, platform | Upstream Chromium behavior | Same | Loopback audit compares request headers, main frame, both iframe origins, workers, and JavaScript/HTTP parity for UA Platform, full-version-list and platform-version UA-CH. Extend to more hint fields and real HTTPS sites. |
| Language and `Accept-Language` | Profile/Chromium defaults | Same | Loopback audit compares the primary HTTP language with `navigator.language`; Chromium may add a fallback language to the header, so full-list equality is not asserted. Compare `Intl` formatting and locale of real HTTPS pages before a privacy claim. |
| `hardwareConcurrency` | Narrow native reduction | Host-bounded profile value | Check Window, same/cross-origin frames and Dedicated/Shared/Service Workers against the same build's stock host result. |
| `deviceMemory` and Device-Memory Client Hint | Narrow native reduction | Host-bounded profile value | Check every JavaScript context plus `Sec-CH-Device-Memory`; reject missing hints and claims above stock. |
| Timezone, `Date`, `Intl` | System timezone | Profile UTC in V3 | Check all contexts, daylight-saving transitions, time arithmetic, rendered dates and real-site compatibility; proxy geography is not a reliable timezone source. |
| Canvas2D and OffscreenCanvas | Stock readback; the current loopback audit hashes one Canvas2D scene in main/same-origin/cross-origin frames and compares its pixel readback with a dedicated worker's OffscreenCanvas | Seeded opaque sRGB uint8 readback only; **held from release** after local linkability control | Repeat reads, subregions, PNG/blob decode, shared/service workers, alpha, color spaces, text, performance and consented linkability cohort. One scene on one host does not characterize Canvas tracking. Other paths must be reported as unmodified. |
| WebGL and WebGPU | Stock; the current loopback audit records WebGL vendor/renderer in three frame contexts | Stock | Record extensions, precision, pixels, WebGPU, GPU class and graphics compatibility on at least two GPU classes. Do not invent values before coherent native implementation and testing. |
| AudioContext and media devices | Stock | Stock | Measure offline-audio output, device enumeration/permissions and timing; evaluate compatibility and whether permission limits reduce exposure. |
| Fonts, text metrics and screen geometry | Stock | Stock | Measure font availability, layout/text metrics, scaling, window/fullscreen dimensions and accessibility at 100–200% DPI. |
| TLS, IP, DNS, QUIC, WebRTC/STUN/TURN | Partially tested proxy rules; no external guarantee | Same network layer | Independently observe direct/proxied routes on controlled external endpoints over IPv4 and IPv6, including failure/recovery and WebSocket. |
| Cookies, storage, service workers, extensions | Per-profile data folders; local tests | Same, plus opt-in identity | Verify isolation, restart, clean clone, backup/restore, update migration, and no accidental identity/log/argv disclosure. |

## Reproducible measurement protocol

1. Pin and record Chromium source commit, applied patch hashes, toolchain,
   Windows build, CPU/GPU/RAM class and proxy topology. Use only disposable
   profiles and consented loopback or external test endpoints.
2. Run a stock core from the *same* Chromium commit as a negative/control
   build. Record two fresh ordinary profiles, two V3 profiles, repeated starts
   and a clean clone. A changed hash alone does not count as a privacy benefit.
3. For each browser value, compare HTTP, Client Hints, main document,
   same-origin frame, different-origin frame and available worker types.
   Fail on missing required observations or disagreement. Mark unsupported
   contexts explicitly instead of silently skipping them.
4. Repeat on Windows 10 and 11, at least two distinct CPU/GPU/RAM classes,
   normal and high-DPI displays, direct and supported proxy routes. Collect
   median launch time, memory and page compatibility alongside privacy data.
5. Evaluate distinguishability and cross-session linkability against a
   consented cohort. Avoid releasing a stable per-profile Canvas variant if
   it increases uniqueness or makes sessions easier to correlate. Independent
   review must examine methodology, not just screenshots from checker sites.
6. Archive redacted aggregate findings with each release and keep raw local
   fingerprint reports private. The public claim must name the exact surface,
   test topology and remaining limitations; no single pass implies complete
   anonymity or invisibility.

Current automated evidence is linked from
[the V3 audit](NATIVE_PERSONA_PROTOTYPE_AUDIT.md). The implementation order and
release gates are in the [master plan](MASTER_IMPLEMENTATION_PLAN.md).
The eight-profile single-host Canvas control found one baseline output but
eight stable V3 outputs. This is a release warning for V3, not proof that the
baseline is anonymous or that every site can observe the difference.

The expanded audit run on 2026-10-13 observed equal Canvas2D scene hashes and
WebGL vendor/renderer objects across two fresh public-core profiles and their
main, same-origin and cross-origin frames. Pixel readback also matched a
dedicated worker's OffscreenCanvas in both profiles. The same-seed V3 run
repeated its Canvas hashes, but a different seed changed them while the
measured non-Canvas surfaces stayed equal. V3 therefore still fails the
release gate. Raw reports remain private; these observations cover one
Windows 11 host, one scene and headless loopback contexts, not a population
anonymity estimate.

The later P0 audit-tool update requires primary HTTP/JavaScript language parity,
ordinary UA-CH Platform parity, and equality of measured HTTP headers, Client
Hints and JavaScript surfaces across two fresh profiles. It returns a non-zero
code for any failed check. The updated tool passed on the exact extracted
0.8.4-preview Chromium on one Windows 11 host; the private raw report is
`C:\NeAntikBuild\qa\fingerprint-v084-full-gate-20261013.json`. Four blocked
background proxy attempts per profile were observed in the earlier audit, so
this loopback fingerprint pass must not be read as a network-silence result.
No browser binary or portable ZIP changed in this tooling-only step.

The stock-control tool now runs the two-profile/two-launch audit on both the
public 0.8.5-preview engine and a stock source build with the same recorded
Chromium commit and version. On one Windows 11 host, both local gates passed;
the public patch exposed no more CPU/RAM than stock, reduced both on this host,
and left the other measured surfaces equal. This does not quantify cohort
uniqueness, cross-machine behavior, external-network leaks or real-site
compatibility. Raw reports stay outside Git; only boolean checks are printed.

A separate probe of Chromium's built-in `--disable-reading-from-canvas`
switch blocked the tested main and dedicated-worker Canvas2D readbacks, but
the switched headless page stalled at a WebGL `readPixels` call. This is a
release-blocking compatibility result for that candidate, not a successful
WebGL privacy test. See the [Canvas decision](CANVAS_PROTECTION_DECISION_2026-10.md).
