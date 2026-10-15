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

No independent external packet capture or public-STUN-provider server logs
were available. A bounded public STUN control on the exact public 0.8.6 and
0.8.7 cores is recorded below; it does not certify arbitrary DNS/IPv6/UDP
paths, HTTPS CONNECT authentication, WebRTC calls, extension traffic, rotating
proxies, browser updates, or cross-machine portability. The in-app TCP check
is only reachability, and the website's IP display is a one-site observation.
Do not use this release as a substitute for Tor Browser or a system-level
network isolation solution when anonymity is a hard requirement.

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

### Public STUN positive control — 13 October 2026

The [public STUN audit](../tools/public_stun_policy_audit.py) used the exact
Chromium extracted from the downloaded public 0.8.6-preview ZIP (`chrome.exe`
SHA-256 `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`,
`chrome.dll` SHA-256 `6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413`).
Two disposable profiles used a loopback-only WebRTC test page and
[Cloudflare's documented public STUN service](https://developers.cloudflare.com/realtime/turn/)
at `stun.cloudflare.com:3478`. That service could observe the QA host's
network address; no account, real profile, cookies or credentials were used.

The direct positive control yielded `host` and `srflx` ICE candidate *types*
and 17 Chromium NetLog UDP sends. The profile with an intentionally rejecting
HTTP proxy and `disable_non_proxied_udp` yielded no ICE candidates and zero
Chromium NetLog UDP sends. The private report retains only candidate types,
counts, status and binary hashes, never candidate addresses or raw NetLog.
This narrow comparison **PASSed** on one Windows host. Four synthetic unit
tests cover success, negative and missing-measurement classification.

The audit was then tightened with an explicit reserved `.invalid` route
control. In the proxy case the loopback rejector must observe that one
synthetic request; without it the result is `INCONCLUSIVE`, even if ICE and
UDP appear quiet. On the same public 0.8.6 core the repeated control passed:
direct had a `srflx` candidate and 19 NetLog UDP sends; proxy had zero ICE
candidates, zero NetLog UDP sends and one observed route-control request.
The report `public-stun-route-control-v2.json` remains outside Git. This
checks proxy assignment only for the synthetic request, not the routing of
arbitrary external traffic.

### Public STUN repeat on the public 0.8.7-preview binary — 13 October 2026

The same bounded test was repeated against the Chromium extracted from the
repeat-downloaded public 0.8.7-preview ZIP. `chrome.exe` SHA-256 is
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb` and
`chrome.dll` SHA-256 is
`6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413`.
The direct control observed `host` and `srflx` candidate types and 17 UDP
sends in Chromium NetLog. With a rejecting HTTP proxy, the test observed no ICE
candidates, zero NetLog UDP sends, and one expected synthetic route-control
request. The test returned **PASS** on this host. Cloudflare could observe the
test network's public IP during the direct control; no raw candidate address
or NetLog was put in the repository. The private summary is
`C:\NeAntikBuild\qa\public-stun-followup-0.8.7-20261013.json`.

This repeat strengthens the same-host comparison for the exact public 0.8.7
engine. There are still no Cloudflare-side proxy-case logs, independent packet
capture, system DNS observation, IPv6 or TURN test, second network/host, or
working public proxy egress. It is not a general WebRTC leak-free or anonymity
certificate; Gate P2 remains open.

An external `srflx` response confirms the direct positive control reached a
public STUN service. It does **not** supply Cloudflare-side logs for the proxy
case, independent packet capture, system DNS evidence, IPv6, TURN, a working
external proxy or a second host. Those parts of P2 remain open; this is not
an anonymity or general WebRTC leak-free certificate.

### Working SOCKS5 HTTPS route — 13 October 2026

The [external route audit](../tools/external_proxy_fail_closed_audit.py) now
adds an allowlisted SOCKS5 fixture that accepts only the project's named
HTTPS endpoint on port 443. On the same extracted public 0.8.6 Chromium
(`chrome.exe` SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`),
the endpoint rendered through this fixture. It recorded one connected tunnel
and nine domain-form requests; Chromium NetLog reported only loopback TCP
remote hosts and zero UDP sends in the working-SOCKS5 case. A synthetic
different destination was refused by a unit test. The private report is
`C:\NeAntikBuild\qa-public-v0.8.6-preview-20261013\external-route-working-socks5-v2.json`.
This proves one working SOCKS5 path on one Windows host, not browser-wide DNS
isolation: the proxy resolved and exited from the same machine. No external
IPv6, separate egress observer, packet capture or proxy-loss recovery was
tested. P2 remains open.

### External HTTPS routes on the public 0.8.7-preview binary — 13 October 2026

The same [external route audit](../tools/external_proxy_fail_closed_audit.py)
was run against the Chromium extracted from the repeat-downloaded 0.8.7 ZIP
and the site's no-store `/api/headers` endpoint. Direct navigation passed. Both
rejecting HTTP and SOCKS5 controls observed the endpoint request at the local
proxy, did not render the endpoint response, and showed only loopback TCP plus
zero UDP sends in Chromium NetLog. Both allowlisted working CONNECT and
SOCKS5 fixtures opened a tunnel, rendered the endpoint response, and showed
only loopback TCP plus zero NetLog UDP sends. The SOCKS5 fixture observed a
domain-form destination. All reported assertions passed.

The first raw-engine attempt exited before assertions because the isolated
public-download extraction lacked Chromium's AppContainer read/execute ACL.
After granting that product-equivalent ACL only to the disposable
`Engine/Chromium` test directory, the full audit passed. The downloaded ZIP
bytes were not altered; the ACL applies only to that local extraction. The
private summary is
`C:\NeAntikBuild\qa\external-proxy-followup-0.8.7-after-acl-20261013.json`.

This checks selected HTTP(S) routes and proxy fixtures on one Windows host.
The fixtures themselves resolved and connected to the endpoint using the
same host's DNS and egress; the public endpoint saw the test requests. This is
not independent DNS observation, packet capture, separate proxy egress,
IPv6/TURN evidence, or proxy-loss/recovery coverage. P2 remains open.

### HTTP proxy loss/recovery on the public 0.8.16-preview engine — 14 October 2026

[`proxy_loss_recovery_gate.py`](../tools/proxy_loss_recovery_gate.py) was run
against Chromium extracted from the repeat-downloaded public 0.8.16-preview
ZIP. The ZIP SHA-256 was
`8b9099f20dce636966e8bfac358e7c4bc1c616c204e4da128a7d41b81db42116`; browser
binary source commit `3fd8777de5d04f6e1cf706756096df950f60d98c`; harness source
commit `900d7f150c89914e38cb6ea16a170f9b1c6ee4ff`. The tested
`chrome.exe` SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb` and
`chrome.dll` SHA-256
`9d0943446e0cbe405f82286ce46c03ad8e928f7b8e46d3ed33082dce2f544075` match
the release manifest. The disposable-engine copy received the required
AppContainer read/execute ACL; the downloaded archive and user data were not
modified.

All 10 assertions passed: initial request used the loopback HTTP proxy; the
browser process remained alive when the proxy stopped; neither the synthetic
target nor another target received a request during the outage; after proxy
recovery the same browser process again used it; exactly two intended requests
reached the target; NetLog showed loopback TCP only and zero UDP sends. The
private summary is
`C:\NeAntikBuild\route-loss-v0.8.16-preview-20261014.json`.

This is a bounded one-host, one-browser-process, loopback HTTP-proxy test. It
does not independently observe public DNS, IPv6, TURN, system packet routes,
other proxy types, another machine or another egress network. P2 remains open;
this is not a general leak-free or anonymity claim.

### Public STUN control on the public 0.8.16-preview engine — 14 October 2026

[`public_stun_policy_audit.py`](../tools/public_stun_policy_audit.py) was run
against the same repeat-downloaded public 0.8.16-preview ZIP. ZIP SHA-256 was
`8b9099f20dce636966e8bfac358e7c4bc1c616c204e4da128a7d41b81db42116`; binary
source commit was
`3fd8777de5d04f6e1cf706756096df950f60d98c`; tested `chrome.exe` and
`chrome.dll` hashes matched the public release manifest. Harness source commit
was `9fb1226c51400d751507b5d4a532e9e3bb0b577a`.

All four assertions passed on this host. The direct control observed `host` and
`srflx` ICE candidate types and 17 UDP sends in Chromium NetLog. In the
rejecting-HTTP-proxy profile, the test observed no ICE candidates, zero NetLog
UDP sends, and its synthetic proxy-route control. As documented by the
harness, Cloudflare received a direct STUN request and could see this test
connection's public IP; raw candidates, the IP and NetLog were not retained in
the report. The private summary is
`C:\NeAntikBuild\public-stun-v0.8.16-preview-20261014.json`.

This is a bounded positive control and a one-host result for this Chromium
core/proxy combination. Cloudflare-side proxy-case logs, independent packet
capture, system DNS, IPv6, TURN, external proxy egress and a second host remain
unavailable or **NOT RUN**. This does not establish that every WebRTC, DNS or
network route is leak-free; P2 remains open.

### External HTTPS proxy routes on the public 0.8.16-preview engine — 14 October 2026

[`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py)
was rerun against the exact repeat-downloaded public ZIP (SHA-256
`8b9099f20dce636966e8bfac358e7c4bc1c616c204e4da128a7d41b81db42116`); its
manifest's `chrome.exe` and `chrome.dll` hashes matched the tested files. The
committed harness was `018f1a28e1144aec843a855fffffae6f1513c590`. The harness
prepared a disposable engine copy because ZIP extraction does not preserve
Chromium's Windows AppContainer ACL; the public release tree was not modified.

The five-case report passed 28/28 assertions: rejecting HTTP proxy 7/7,
rejecting SOCKS5 8/8, working HTTPS CONNECT 6/6 and working SOCKS5 7/7, with
positive direct controls. Rejecting profiles did not render the test endpoint;
allowlisted routes rendered through their proxy. SOCKS5 received the
destination as a domain name. Proxied NetLogs showed loopback TCP only and
zero UDP sends. The same-host proxy used the same host's DNS/egress; this does
not establish independent proxy egress or DNS. System DNS, independent packet
capture, IPv6, TURN and another host remain **NOT RUN**. The private report is
outside the repository at
`C:\NeAntikBuild\external-route-v0.8.16-preview-20261014-committed-harness.json`.

### HTTP proxy loss/recovery on the public 0.8.18-preview engine — 15 October 2026

[`proxy_loss_recovery_gate.py`](../tools/proxy_loss_recovery_gate.py) was run
on the Chromium binary extracted from the exact repeat-downloaded public
0.8.18-preview ZIP (ZIP SHA-256
`62c73096470c62a9bfacefbfee30753e99def38bdc22aba1c90e222bd22af095`, binary
source commit `85580d07b28cd8d795576481b3119f04dd1ba6dd`). The tested
`chrome.exe` SHA-256 was
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`; the
disposable engine copy alone received the AppContainer read/execute ACL.
The immutable harness source commit was
`15c5039166f84cc4f4b170b6f5ce3cc70a855d0f`.

All 10 assertions passed: requests initially traversed the synthetic
loopback-only HTTP proxy; while it was stopped the browser stayed alive but the
target received no request; after restart the same browser process sent exactly
two probes through the proxy. NetLog recorded only `127.0.0.1` TCP and zero UDP
sends. The QA harness also rejects a junction/reparse point at its temporary
profile root before creating Chromium; its Windows junction controls passed.
Private report: `C:\N155\proxy-loss-0.8.18-preview-20261015-committed-harness.json`.

This is one host, one browser process, and loopback fixtures only. It does not
observe the public DNS resolver, external IPv6 route, TURN, other proxy types,
another machine or another egress. It is not a general leak-free or anonymity
claim; P2 remains open.

### HTTPS proxy TLS/CONNECT controls on the public 0.8.18-preview engine — 15 October 2026

[`https_proxy_integration.py`](../tools/https_proxy_integration.py) ran against
the exact repeat-downloaded public 0.8.18-preview Chromium (`chrome.exe`
SHA-256 `7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`;
ZIP SHA-256
`62c73096470c62a9bfacefbfee30753e99def38bdc22aba1c90e222bd22af095`). Its
committed harness was `95cdef0bb90b64ddb298ee29d2b3af74847ce407`, SHA-256
`2955d5519f91248832fc9f71adfafd36a82967e4ab90e113a73985932ecd2a62`.

All 10 cases and 75 assertions passed. IPv4 and IPv6 TLS proxy endpoints
completed CONNECT to the synthetic HTTPS target; untrusted certificates and
unavailable endpoints made no target request. A direct positive control reached
the auth-case IP-literal target before the rejecting 407 proxy case. During the
407 case the target received zero requests, the alternate proxy received zero
CONNECTs, and the fixture recorded two authentication challenges. This covers
only missing/rejected credentials; correct proxy credentials and the GUI auth
prompt remain **NOT RUN**. The private report is
`C:\N155\https-proxy-0.8.18-preview-20261015-committed-harness.json`.

Fixtures and proxy egress were confined to IPv4/IPv6 loopback on this Windows
host. This is not an independent public egress, DNS, packet capture, TURN or
second-host result; P2 remains open.
