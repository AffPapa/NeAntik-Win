# NeAntik privacy architecture — decision record (2026-10-12)

Status: research and test baseline, **not a shipped anonymity feature**.

## Product goal and language

The aim is to make a simple, open, locally controlled browser that reduces
tracking and linkability. Profile separation is useful, but a different random
fingerprint for every profile does not equal anonymity: a rare combination can
identify a profile more easily. Prefer a small set of coherent, common browser
values and separate profiles by storage and, when configured, network route.
Never claim 100% anonymity or superiority to Tor Browser without independent
evidence. Even Tor Project states that perfect anonymity is not guaranteed.

## Current measured baseline

`tools/fingerprint_surface_audit.py` starts two clean bundled-Chromium profiles
on loopback-only pages. It compares JavaScript values in the main document,
same-origin iframe and dedicated worker, as well as the HTTP User-Agent.
On the Windows 11 release workstation and Chromium 155.0.8059.40, the measured
overlapping fields were consistent across contexts and the two fresh profiles.
That is **not** an anonymity result: the browser still exposes platform,
language, logical CPU count, approximate memory, timezone, display dimensions
and scale, among other properties. The audit does not exercise cross-origin
frames, shared/service workers, extensions, WebGL, Canvas, fonts, TLS, external
DNS, STUN/TURN, real proxy exits or adversarial sites. Its local JSON report
can contain device traits and must not be committed or uploaded.

## Threat model and order of work

| Observer | Main risks | Required evidence before a claim |
|---|---|---|
| Website / third-party tracker | Cookies, storage, JS/HTTP fingerprint, account login | Cross-site and cross-context tests, real Chromium behavior |
| Local network / ISP | Destination names and direct IP connections | Packet capture in a controlled network, DNS/UDP/QUIC tests |
| Proxy or exit operator | Destination metadata, traffic logging | Provider policy and independent route checks; never infer trust from an IP test |
| Local software with same Windows user | Browser data and DPAPI secrets | OS-level threat model; profile folders are not a malware sandbox |
| Global correlator | Timing and traffic correlation | No realistic absolute guarantee from a browser alone |

1. Keep the current Chromium profile/proxy edition accurately labelled as a
   privacy-oriented browser, not an anonymity network.
2. Build a native, reproducible fingerprint-reduction patch set only after
   tests cover document, frames, workers, HTTP headers, Client Hints, Canvas,
   WebGL, fonts, screen metrics and timezone. Values must be coherent across
   all these surfaces. Avoid per-profile random JavaScript injection.
3. Add an explicit high-privacy routing design. Tor Project warns against
   routing an ordinary browser through Tor: browser-level leaks remain. A
   genuine Tor-like mode therefore needs a purpose-built browser engine and
   network integration, not merely a SOCKS5 checkbox on Chromium.
4. Test fail-closed routing with real external endpoints under our control,
   including DNS, IPv4/IPv6, WebRTC STUN/TURN and proxy failure, before any
   public claim of leak resistance. User accounts and behavior can still
   identify a person even if network and fingerprint protections work.
5. Before claiming comparative security, publish patches and test protocols,
   commission independent review, fund security updates, and maintain a
   vulnerability-response process. A public repository alone is not an audit.

## Sources

- Tor Project, [fingerprinting protections](https://support.torproject.org/tor-browser/features/fingerprinting-protections/): minimize uniqueness through standardization, letterboxing, font/language limits and first-party isolation.
- Tor Project, [about Tor Browser](https://support.torproject.org/tor-browser/getting-started/about-tor-browser/): routing other browsers through Tor can create deanonymization and leakage risks.
- Tor Project, [safe use](https://support.torproject.org/tor-browser/security/using-tb-safely/): no perfect-anonymity guarantee; logins and disclosed personal data can identify the user.
- [UN Special Rapporteur report A/HRC/29/32](https://digitallibrary.un.org/record/798709/files/A_HRC_29_32-EN.pdf): supports tools for encryption and online anonymity as a privacy and expression matter; it does not certify any particular browser or override local law.
