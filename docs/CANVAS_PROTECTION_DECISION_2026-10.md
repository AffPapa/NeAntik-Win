# Canvas protection candidate: blocked release gate

Status: 2026-10-13, development research only. The downloadable 0.8.5-preview
does **not** include this switch or the V3 per-profile Canvas patch. Raw local
audit reports stay outside Git.

## Decision

Do not ship V3's stable per-profile Canvas seed as a privacy feature: on one
Windows host, eight seeds made eight repeatable Canvas outputs. A different
output per profile is not evidence of anonymity and can itself become a stable
identifier. [V3 audit](NATIVE_PERSONA_PROTOTYPE_AUDIT.md).
The Canvas linkability CLI now returns exit code 2 when measurement succeeds
but its release decision is blocked or needs manual review; code 0 is reserved
for an approved gate. A disposable four-sample stock/V3 run returned 2 with
`blocked_by_stable_per_profile_canvas_identifier`. The measurement remains a
single-host warning, not a general linkability estimate.

Do not enable Chromium's existing `--disable-reading-from-canvas` switch yet.
The [disposable control probe](../tools/canvas_readback_policy_audit.py) on the
exact 0.8.3 bundled core observed:

| Probe | Without switch | With switch |
| --- | --- | --- |
| Main Canvas2D `getImageData` | Allowed | `SecurityError` |
| Main Canvas2D `toDataURL` | Allowed | `SecurityError` |
| Dedicated-worker OffscreenCanvas2D `getImageData` | Allowed | `SecurityError` |
| Main WebGL `readPixels` | Allowed | Headless page stalled after WebGL context creation; no result in 25 seconds |

The negative WebGL result is a compatibility failure in this test topology,
not proof that WebGL pixels are hidden. The flag's behavior in a normal GUI,
other WebGL paths, additional contexts, applications and hardware is not yet
verified. The probe fails closed for this candidate rather than turning the
partial Canvas2D result into a product claim.

## Design constraints for the next candidate

Tor Browser documents Canvas extraction blocking as one part of a larger
fingerprinting defense that relies on coherent, shared configurations:
[Tor Browser anti-fingerprinting](https://tb-manual.torproject.org/ru/anti-fingerprinting/).
Brave describes a different strategy: deterministic farbling scoped to a
session and first-party site, not a permanent per-profile value:
[Brave's farbling design](https://brave.com/privacy-updates/4-fingerprinting-defenses-2.0/).
Neither design can be copied as one Chromium flag and presented as equivalent
to either browser.

The next implementation must choose and review one coherent policy across
Canvas2D, OffscreenCanvas, WebGL/WebGPU, iframe origins and workers. Its
release gate must include (1) no stable per-profile Canvas identifier across
sessions and sites, (2) no browser/page hang on common graphics operations,
(3) a positive readable control and explicit blocked/modified observations,
(4) repeatable tests on at least two CPU/GPU classes and Windows versions,
(5) real-site compatibility and consented linkability measurements. Until
then, ordinary Chromium behavior and the narrow CPU/RAM reduction remain the
accurate public description. No single Canvas policy can prove anonymity.

## V4 engineering decision (2026-10-13)

The V3 pixel mask is keyed by a persistent profile seed and a non-cryptographic
mix of pixel position. Merely rotating that number at launch would keep one
value shared across sites in a session and would not cover WebGL/WebGPU. It is
not a defensible privacy fix. Do not publish V3 or claim it protects Canvas.

The next safe buildable increment is **V4a**: remove the four V3 Canvas
readback/export mutations and remove the Canvas capability claim. Retain only
the separately measured CPU/RAM/timezone settings; describe Canvas as stock
Chromium. Verify every previously modified Canvas2D/OffscreenCanvas path and
page compatibility against stock before treating V4a as a candidate. This is
a safety correction, not completion of P1.

**V4b** is a separate research prototype: a fresh in-memory browser-session
secret, first-party site and storage partition context, and one policy shared
by main frames, third-party frames and dedicated workers. No key derived from
a persistent profile identifier may affect Canvas output. Shared/service
workers without an unambiguous first-party context need an explicit policy,
not fallback to the profile seed. WebGL/WebGPU and other exposed surfaces are
separate scope; any untested surface remains stock and disclosed. A release
gate needs saved-profile restarts and at least two local sites in addition to
the existing fresh-profile probe, plus graphics compatibility and external
network checks. The existing `native_canvas_linkability_audit.py` is a V3
blocker only: its `requires_manual_review` result is not approval.

Brave's [published farbling design](https://brave.com/privacy-updates/4-fingerprinting-defenses-2.0/)
motivates session/site scoping, while the [W3C fingerprinting guidance](https://www.w3.org/TR/fingerprinting-guidance/)
warns that randomization is not by itself a universal defense. Neither source
validates our unbuilt V4b implementation.

The local `tools/native_canvas_v4_gate.py` is a deliberately narrow first
measurement gate: two disposable saved profiles, three launches each, and two
loopback top-level sites per launch. It reports only aggregate invariants and
the SHA-256 of both `chrome.exe` and the adjacent `chrome.dll`. A stock 0.8.5
core (`chrome.dll` SHA-256:
`022aa456ffb934e683ea805aada52be45525c5abcc884d54cef5bf4f8dd57930`)
completed all 12 cases and returned expected `FAIL` for site/session variation;
this calibrates the test, not the V4 core. Even `PASS` from a future candidate
would not cover external origins, shared/service workers, WebGL/WebGPU, another
machine or network anonymity; those remain separate release gates.

### V4b local checkpoint (not a release approval)

An incremental V4b development build on Windows 11 completed the twelve-case
saved-profile/two-site gate: both pixel and PNG outputs changed between the
two loopback top-level sites and across three launches. This is a narrow
functional `PASS`, not a linkability study or an anonymity claim. The tested
`chrome.dll` SHA-256 is
`1ecd56eba06db5c6dbef6785fa6efe23c842ff925a723aa3192182d18d3c46de`;
the browser source remains an uncommitted experimental Chromium checkout at
upstream commit `cfaadc5a132d78e1828635aa8405a499f3e14864`.

A separate six-context gate on that exact DLL measured main frame, same-site
iframe, third-party iframe embedded under the same top-level site, dedicated,
shared and service workers across a saved-profile restart. Main and both
iframes plus dedicated worker matched the first-party context; **shared and
service workers did not**, and therefore the overall gate is `FAIL`. The
third-party iframe is intentionally expected to match its top-level site's
policy; a separate top-level site is covered by the twelve-case gate. V4b is
held from release until the worker mismatch is fixed and the gate rerun on
the rebuilt DLL. Unit/graphics/compatibility and external network gates also
remain open.

The worker propagation fix was rebuilt locally. On the new `chrome.dll`
SHA-256
`6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413`,
the saved-profile/six-context gate returned `PASS`: all six contexts were
measured, all five matched the main frame under the same top-level site, and
all six changed across a restart. The separate 12-case/two-site gate also
returned `PASS` on that exact DLL. This replaces the prior *candidate's*
worker FAIL, not the remaining release gates: Chromium unit tests, external
network observation, a second machine/GPU class, WebGL/WebGPU and compatibility
checks are still pending. The DLL is a development binary, not the public ZIP.
An opt-in readback/liveness smoke on the same DLL also returned `PASS` for
Canvas2D in the main page and dedicated worker and for WebGL `readPixels`
without a hang. This checks availability only: it does **not** test WebGL
fingerprint protection, WebGPU, visual correctness or real-site compatibility.
The schema-2 profile still stores a legacy numeric seed and passes it as a
persona-mode switch. In V4b the Canvas hooks use the fresh session/site key,
not that saved seed; the remaining seed contract is migration/cleanup debt,
not evidence of a per-profile Canvas identifier. Removing it requires a
versioned profile migration and separate compatibility tests.
An ordinary-mode comparison against the clean Chromium build at the same
upstream commit passed all nine local checks, including all measured
JS/HTTP/graphics surfaces and CPU/RAM parity. This verifies the no-persona
default on one host; it is not a cross-platform equivalence or privacy proof.
