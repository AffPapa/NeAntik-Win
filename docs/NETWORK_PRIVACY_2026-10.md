# Network privacy engineering — 12 October 2026

This document explains the **measured** 0.7.0-preview safeguards. It is not a
claim that NeAntik Win makes anyone anonymous. Privacy is a legitimate product
objective: [ICCPR Article 17](https://2covenants.ohchr.org/About-ICCPR.html)
protects against arbitrary or unlawful interference with privacy. It does not
make a particular browser technically anonymous or decide every jurisdiction's
rules for a given use. No legal conclusion is encoded in the software.

## Why we did not add random fingerprint spoofing

[Tor Browser's own explanation](https://support.torproject.org/ru/tor-browser/features/fingerprinting-protections/)
describes reducing distinguishability through coordinated standardization and
a large user set, not arbitrary per-API values. Its strategy includes window
letterboxing, limited fonts and standardized languages. A small Chromium fork
that changes only Canvas, User-Agent or one JavaScript property while leaving
HTTP headers, workers, TLS, fonts, GPU and behavior unchanged can create a
*more* distinctive identity. NeAntik currently leaves device/browser identity
surfaces inherited and exposes them in Diagnostics. A native identity layer
would require a versioned cross-process model, consistency tests in frames and
workers, and a cohort/uniqueness study before advertising protection.

## Proxy-bound bundled Chromium

The launcher supplies one fixed `--proxy-server` with no `direct://` fallback.
For this bundled Chromium only, it also uses:

- `--proxy-bypass-list=<-loopback>` to subtract Chromium's [implicit bypass for
  localhost and link-local URL hosts](https://chromium.googlesource.com/chromium/src/+/312b6bf/net/docs/proxy.md#implicit-bypass-rules).
- `--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE <proxy-host>` to block
  background local name resolution while allowing the proxy endpoint to be
  reached. The proxy's own hostname may still require local DNS. Chromium's
  [SOCKS guide](https://chromium.googlesource.com/website/+/HEAD/site/developers/design-documents/network-stack/socks-proxy/index.md)
  explicitly distinguishes URL proxying from raw DNS requests.
- `--disable-quic` and `--webrtc-ip-handling-policy=disable_non_proxied_udp`.
  Chromium [documents the WebRTC policy](https://chromium.googlesource.com/chromium/src/+/05de749c214c9f8379bed790bb9fac6e5c6619a6/content/public/common/webrtc_ip_handling_policy.h)
  as preventing non-proxied UDP and local-address exposure, not as an all-path
  anonymity guarantee.

These flags can break local web services and real-time calls. They do not
isolate other Windows processes, extensions with separate capabilities, OS DNS,
proxy-server logs, or traffic outside the tested Chromium URL paths.

## Evidence gates

- `tools/proxy_integration.py`: disposable local target, HTTP proxy and SOCKS5
  proxy; eight real Chromium launches. Hostname and 127.0.0.1 URL cases must
  reach the target *through* the controlled proxy. Unreachable proxies must
  fail without direct fallback. The SOCKS5 fixture observes a hostname rather
  than a client-resolved address for the synthetic remote name.
- `tools/launcher_integration.py`: packaged `BrowserLauncher` passes exact
  proxy/privacy flags to a copied engine before a real Chromium process starts.
- `tools/privacy_browser_integration.py`: new-profile permission denials and
  disabled preloading persist after real Chromium startup. With no STUN/TURN
  configured, ICE completes without host candidates under the proxy policy.
- `tools/cookie_integration.py`: disposable TLS certificate and two separate
  loopback HTTPS site names; the explicit allow-control profile sends the
  third-party cookie, while the new privacy-default profile does not. Only the
  owned headless test process ignores its self-signed certificate.

## Still unverified

No external packet capture or public STUN server was used. We have not
certified arbitrary DNS/IPv6/UDP paths, HTTPS CONNECT authentication, WebRTC
calls, extension traffic, rotating proxies, browser updates, or cross-machine
portability. The in-app TCP check is only reachability, and the website's IP
display is a one-site observation. Do not use this release as a substitute for
Tor Browser or a system-level network isolation solution when anonymity is a
hard requirement.

## Startup-network observation — 13 October 2026

The [disposable startup probe](../tools/start_page_network_audit.py) compared
two **headless** launches of the clean Chromium 155 V3 development core on one
Windows 11 machine. It used new profiles, a direct connection and the same
`--no-first-run` / `--no-default-browser-check` flags as the manager. The
private Chromium NetLogs were reduced to host counts before reporting; no URL
paths, query strings, cookies or personal profiles were retained.

| Startup URL | HTTP(S) request jobs seen | Distinct hosts seen |
| --- | ---: | ---: |
| `about:blank` | 5 | 4 |
| `chrome://newtab` | 12 | 7 |

The blank page removed new-tab-specific requests in this sample but did
**not** stop all Google-related background requests: the blank-page NetLog
still named `accounts.google.com`, `clients2.google.com`,
`update.googleapis.com` and `www.google.com`. A visual GUI smoke also
showed the standard Google new-tab page. These observations motivate a
privacy-conscious startup design; they do not prove that all requests reached
their destinations, that GUI and headless modes are identical, or that a
proxy-bound profile has no direct route. Chromium's
`--disable-background-networking` is documented in the pinned source as a
network-performance **test** switch and affects services including upgrade
detection and Safe Browsing configuration. It is not a safe blanket fix for a
distributed browser. Any startup change needs repeat measurements, an update
strategy and a way to respect the user's session-restore choice.

In a separate disposable GUI check, writing `session.restore_on_startup=4`
and `session.startup_urls=["about:blank"]` into initial Preferences did **not**
replace the new-tab page on first or second launch. Passing `about:blank` as
an explicit launch URL did open a blank tab. Therefore the preference edit is
not a verified product fix; forcing a URL on every launch would interfere
with session restoration and needs its own UX design and regression tests.

The same probe now has an optional **rejecting loopback HTTP proxy** case
using the launcher's actual bundled-proxy flags. In two fresh runs of the
clean development core, the proxy observed eight startup request attempts
for four hostnames. Chromium NetLog recorded eight TCP connections, all to
`127.0.0.1`, and zero UDP sends in the proxy-bound case. The same runs'
direct controls recorded external TCP endpoints and UDP sends. The proxy
never forwarded requests, and no raw URL paths or query strings enter the
summary. This is a positive local route check, not packet-capture evidence
that every transport on every network fails closed. A third-party extension,
IPv6, external DNS resolver, real WebRTC/TURN server or other Windows process
is outside this test.

The same startup/proxy probe also passed against the extracted **public
0.8.1-preview** engine: its local release ZIP matched the published SHA-256
`2b43c3ffad3e16754d376ebb49d45530a670f7540d580fa2939ebf2c649fc70e`,
and the extracted `chrome.exe` matched the release manifest. The proxy case
again observed eight requests, eight loopback TCP endpoints and zero NetLog
UDP sends. This extends local evidence to the downloadable binary, but does
not close the external-network gate.

## Consented external HTTPS fail-closed control — 13 October 2026

The [external route probe](../tools/external_proxy_fail_closed_audit.py)
used the project's public, no-store `/api/headers` endpoint with two fresh
profiles. In the direct case, the browser rendered the endpoint's JSON. In
the proxy-bound case, an intentionally rejecting loopback HTTP proxy observed
the request to that exact hostname, while the browser did **not** render the
JSON. NetLog showed only loopback TCP endpoints and zero UDP sends for this
proxy-bound run. Seven explicit assertions passed on both the extracted,
byte-verified public 0.8.1 core and the clean V3 development core. The proxy
never forwarded traffic; the report records no response body, public IP,
cookie, full URL path or query string.

This is a useful external positive control plus a negative fail-closed test
for **one HTTPS destination, one proxy type and one Windows/network topology**.
It does not prove that DNS, IPv6, WebRTC/STUN/TURN, extension traffic or all
other destinations are routed correctly, nor can Chromium NetLog replace
independent packet capture or server-side observation from a separate egress
node. The P2 release gate remains open.

### SOCKS5 HTTPS negative control — 13 October 2026

The same [external route probe](../tools/external_proxy_fail_closed_audit.py)
now runs a third fresh profile through a rejecting loopback SOCKS5 fixture.
Its direct positive control rendered the project's no-store HTTPS JSON page.
The SOCKS5 fixture observed a CONNECT request with the destination **domain
name** (SOCKS5 address type 3), then returned a failure without forwarding.
The browser did not render the page, and Chromium NetLog for that profile
showed only `127.0.0.1` TCP endpoints and zero UDP sends. All eight SOCKS5
assertions passed on both the byte-verified public 0.8.1 core and the clean
V3 development core, alongside the seven HTTP-proxy assertions. The local
reports are outside Git and store only host counts and address types, not
response bodies, cookies or full URLs.

This establishes that this tested HTTPS request was handed to the SOCKS5
proxy as a domain and did not silently fall back to a visible direct Chromium
connection on this host. It does **not** prove that Windows or Chromium made
no parallel DNS query, that another destination or proxy configuration is
safe, or that IPv6, WebRTC/TURN and other processes cannot bypass the route.
Independent DNS/packet observation and a second egress topology remain P2
requirements.

An attempt to use Windows PktMon on the QA host returned **Access denied**:
the current process is not elevated. The DNS Client Operational log is also
disabled. Neither source produced a packet trace, so there is no new claim
about absence of local DNS queries. The manager's unreleased source now makes
the proxy-hostname caveat visible in Settings and when saving a named proxy;
using an IP literal removes only the lookup of the proxy host itself, not
other possible DNS paths.
