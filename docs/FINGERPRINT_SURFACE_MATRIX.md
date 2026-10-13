# Fingerprint surface matrix and evidence plan

Status: 2026-10-13. This is an engineering inventory, not an anonymity score.
The public 0.8.4-preview (same core as 0.8.3) and unreleased V3 prototype must be kept separate.
An empty or inconsistent measurement is a failure of the audit, not proof of
privacy. Raw reports can reveal device traits and stay outside the repository.

| Surface | Public 0.8.4-preview | Unreleased V3 | Required observation before a privacy claim |
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

A separate probe of Chromium's built-in `--disable-reading-from-canvas`
switch blocked the tested main and dedicated-worker Canvas2D readbacks, but
the switched headless page stalled at a WebGL `readPixels` call. This is a
release-blocking compatibility result for that candidate, not a successful
WebGL privacy test. See the [Canvas decision](CANVAS_PROTECTION_DECISION_2026-10.md).
