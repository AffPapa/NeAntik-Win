# Canvas protection candidate: blocked release gate

Status: 2026-10-13, development research only. The downloadable 0.8.3-preview
does **not** include this switch or the V3 per-profile Canvas patch. Raw local
audit reports stay outside Git.

## Decision

Do not ship V3's stable per-profile Canvas seed as a privacy feature: on one
Windows host, eight seeds made eight repeatable Canvas outputs. A different
output per profile is not evidence of anonymity and can itself become a stable
identifier. [V3 audit](NATIVE_PERSONA_PROTOTYPE_AUDIT.md).

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
