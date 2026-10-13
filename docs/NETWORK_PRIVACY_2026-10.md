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
  proxy; thirteen real Chromium launches. Hostname and 127.0.0.1 URL cases must
  reach the target *through* the controlled proxy. Unreachable proxies must
  fail without direct fallback. An IPv6 `::1` direct positive control and
  working HTTP/SOCKS5 proxy controls must reach the same target, while
  unavailable proxies must not. The SOCKS5 fixture observes a hostname rather than a client-resolved
  address for the synthetic remote name.
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

### IPv6 loopback fail-closed control — 13 October 2026

The disposable [proxy integration](../tools/proxy_integration.py) now binds a
second test target to IPv6 loopback `::1`. A fresh direct profile reached it;
two more fresh profiles reached it **through** the controlled HTTP/SOCKS5
fixtures, as observed by both the fixtures and the target peer-route marker.
Fresh profiles with unavailable HTTP and SOCKS5 proxies both reported
`ERR_PROXY_CONNECTION_FAILED`, and the IPv6 target saw zero requests from
either. The extracted public 0.8.2 Chromium passed 37 assertions over thirteen
launches. The generated report is kept outside Git at
`C:\NeAntikBuild\qa\proxy-ipv6-positive-v0.8.2-20261013.json`.

This extends the local fail-closed evidence to an IPv6 URL without implying
that an external IPv6 route, operating-system DNS, WebRTC/TURN or a working
IPv6 proxy is covered. P2 remains open pending independent packet capture and
a second egress topology.

An attempt to use Windows PktMon on the QA host returned **Access denied**:
the current process is not elevated. The DNS Client Operational log is also
disabled. Neither source produced a packet trace, so there is no new claim
about absence of local DNS queries. The manager's unreleased source now makes
the proxy-hostname caveat visible in Settings and when saving a named proxy;
using an IP literal removes only the lookup of the proxy host itself, not
other possible DNS paths.

### Network-service sandbox diagnostic — 13 October 2026

The exact extracted public 0.8.2 Chromium was tested with self-hosted STUN
sinks on `127.0.0.1` and the host's private LAN IPv4 address. In normal
sandboxed mode, its direct NetLog recorded five
STUN sends, but the sink received zero packets; the proxy-bound case recorded
zero UDP sends. In an **explicit disposable diagnostic control** using
`--disable-features=NetworkServiceSandbox`, the direct sink received all five
STUN Binding requests in each topology, while the proxy-bound case still
recorded zero UDP sends. The status is `diagnostic_control_only` with a
nonzero process exit code, never a release/privacy pass. Both local reports
are outside Git in `C:\NeAntikBuild\qa\`.

This strongly narrows the discrepancy to the Windows network-service sandbox
path, but does not prove whether the block is a Windows firewall rule, socket
broker behavior or another environment-specific interaction. Chromium's
[upstream socket-broker change](https://chromium.googlesource.com/chromium/src/+/3129fd20b466c9aafbe60e086607badb99bf8ad6)
describes AppContainer firewall drops for some destinations, and its
[enterprise policy](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/components/policy/resources/templates/policy_definitions/Miscellaneous/NetworkServiceSandboxEnabled.yaml)
warns that disabling the network sandbox increases security risk. We will
**not** disable it in the shipped browser to make a test pass. Independent
packet observation and tests on another Windows/network topology remain
necessary before any WebRTC leak claim.

### Separate WSL network-namespace STUN control — 13 October 2026

The new [private receiver](../tools/remote_stun_sink.py) ran in Ubuntu WSL on
its own private IPv4 interface. The [Windows orchestrator](../tools/wsl_stun_route_audit.py)
used the exact extracted public 0.8.3 Chromium, normal network-service
sandboxing, two disposable profiles and the existing loopback WebRTC page.
The receiver counted UDP packets independently of Chromium NetLog. In the
direct case it received **five STUN Binding requests**, matching five NetLog
sends to that WSL address. In the proxy-bound case it received **zero** and
NetLog recorded **zero UDP sends**; the rejecting proxy observed nine
background external attempts. The authenticated control endpoint was bound
only to the private WSL address; the QA report retained counts, not packet
payloads or peer addresses. One completed run produced status
`cross_namespace_passed`; the raw report remains outside Git.

This resolves the missing direct positive control for **this** distinct
network namespace without weakening Chromium's sandbox. It does not prove
the behavior of public STUN/TURN servers, Windows system DNS, IPv6, a working
external proxy, other interfaces or another Windows host. WSL and Windows
still share one physical computer; P2's independent public-network and packet
capture gates remain open. The earlier host-local inconclusive result is not
rewritten as a pass.

### Working HTTPS CONNECT control — 13 October 2026

The [external route probe](../tools/external_proxy_fail_closed_audit.py) now
has an allowlisted working HTTP CONNECT fixture alongside its rejecting HTTP
and SOCKS5 fixtures. It accepts tunnels only to the consented test origin on
port 443; unrelated destinations receive 403 and are never forwarded. On the
exact extracted public 0.8.4 Chromium (`chrome.exe` SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`),
the browser rendered the project's no-store HTTPS JSON endpoint through this
fixture. The fixture recorded a successful tunnel to the destination host;
Chromium NetLog for the proxied case contained only loopback TCP endpoints and
zero UDP sends. The direct positive control and both rejecting-proxy negative
controls also passed. The private report is
`C:\NeAntikBuild\qa\external-route-working-v084-20261013.json`; it keeps
host counts and check results, not response bodies, cookies or full URLs.

The fixture itself resolves the destination with the Windows host DNS and
exits through the same computer. Therefore this is a **working proxy-path
control**, not proof of DNS isolation, a distinct public egress IP, external
IPv6, TURN/WebRTC behavior or leak freedom on another network. Those parts
of Gate P2 remain open. The shipped browser binary and v0.8.4 ZIP are
unchanged; this is an audit-tool improvement.
