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
