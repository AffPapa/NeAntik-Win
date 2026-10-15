# NeAntik Win: mission, limits and release roadmap

## Mission

NeAntik Win is an open-source, local-first, portable Windows browser project for
people who want understandable privacy controls and independent browsing
profiles. A person should be able to inspect the code, download one complete
portable package, keep data on their own computer and know exactly what the
browser does and does not protect.

Privacy is a legitimate product goal. This document is not a legal opinion or a
promise that every use is lawful in every jurisdiction. NeAntik must not claim
"complete anonymity", "undetectability" or superiority to Tor Browser without
independent evidence. Different-looking fingerprints are not necessarily more
anonymous: uncommon or inconsistent values can make a user easier to track.

## Non-negotiable design principles

1. **One understandable package:** a pinned, security-maintained Chromium core,
   launcher and required notices in one Windows x64 ZIP; no account or cloud
   service required. Data stays beside the executable and is never put in a
   release archive.
2. **Independent local profiles:** separate browser storage, cookies, history,
   permissions and extension state. Proxy and network policy are explicit per
   profile. A profile is not an identity guarantee; signed-in accounts and
   behavior can still correlate sessions.
3. **Reduce, do not randomly spoof:** prefer a small number of coherent,
   standardized browser configurations over a unique random fingerprint per
   profile. If a browser-exposed value is modified, it must agree in HTTP,
   JavaScript, iframes, workers and applicable client hints, with a regression
   test against real browser builds.
4. **Fail visibly:** proxy connection failure must not silently become a direct
   connection. Network controls must be described with their verified limits.
   A configured proxy is not equivalent to Tor, a VPN or anonymity.
5. **Open and auditable:** project-authored source is under the root MPL-2.0
   license. Third-party components retain their own licenses and notices.
   Release manifests, hashes, core provenance and changelog accompany binaries.
   MPL-2.0 does not grant trademark rights in the NeAntik name or logo.
6. **Performance and accessibility:** no heavy application framework; keep
   launch fast, controls keyboard-accessible and default settings few.

## Threat model and proof standard

The protected assets are local browsing state, proxy secrets, profile separation
and the user's ability to understand observable browser and network behavior.
Adversaries may include trackers, visited sites and a party observing network
traffic. The current preview does not protect against compromised Windows,
malicious extensions, browser exploits, account-based tracking, traffic
correlation, a malicious proxy, or all browser/device fingerprinting.

Every protection claim needs a test that observes behavior rather than just
configuration. Publish a matrix covering direct, HTTP CONNECT and SOCKS5
routes; authentication; DNS, IPv4/IPv6, WebRTC/STUN/TURN and QUIC; page,
iframe, worker and client-hint values; first and subsequent launches; and
Windows 10/11. Unknown is reported as unknown, not passed. Test with disposable
accounts/profiles and consented endpoints; do not publish private profile data.

## Delivery phases and release gates

| Phase | Work | Gate before claiming success |
| --- | --- | --- |
| 0: open project | MPL-2.0, licensing scope, source hygiene, product limits, public roadmap and a portable archive containing the license. | Source guard, archive verifier, license inventory, clean downloadable ZIP. |
| 1: reliable baseline | Maintain isolated profiles, backups, proxy vault, explicit proxy errors, safe defaults and a simple UI. | GUI, backup/restore, profile isolation, proxy failure and public-download smoke tests. |
| 2: fingerprint reduction | Research native-core standardization of high-entropy surfaces, prioritize consistency and security updates. No per-profile random identities by default. | Cross-context/cross-profile measurements, regression suite, externally reviewed patch and no misleading claim of invisibility. |
| 3: network privacy | Decide between a separately audited anonymity network integration and clearly limited proxy-only mode. A stock Chromium build over Tor is not automatically Tor Browser-equivalent. | External leak tests, fail-closed behavior, threat-model review and independent audit. |
| 4: mature release | Accessibility, performance budgets, signed or reproducible distribution where feasible, vulnerability response and documented migration. | Windows test matrix, independent security review and published reproducibility evidence. |

The phases are not marketing milestones. Version numbers advance only when the
corresponding code, tests and public artifact exist. After each release, update
`CHANGELOG.md`, the website's version/history and downloadable hash; verify
the public ZIP by downloading it again. Do not replace an existing versioned
archive in place.

## Current status (2026-10-15)

The public release remains 0.8.16-preview until a new portable ZIP is published.
The next 0.8.17-preview candidate is intentionally scoped as a local profile
manager with pinned, unmodified stock Chromium 155.0.8059.79: no browser
fingerprint override is included. The local Chromium compile and blank-page
startup smoke passed, but staging, app integration, exact-ZIP gates and public
release checks are still pending. Earlier native-persona work is historical;
the new candidate preserves its stored profiles but does not launch them.
Profile separation and selected proxy tests do not prove anonymity or absence
of network leaks. Windows 10 compatibility and cross-machine session portability
remain unvalidated. See the [detailed implementation plan](MASTER_IMPLEMENTATION_PLAN.md)
for exact remaining gates, not claims about an unpublished candidate.
