# P2.1 route matrix — 14 October 2026

This is an evidence inventory, **not** a leak-free or anonymity certificate. It
describes the bundled Chromium with a fixed proxy selected in NeAntik Win.
Installed Chrome/Edge and other Windows processes are outside these checks.
`PASS` below always names its narrow local/one-host scenario; it never implies
that an external-network gate passed. `NOT RUN` means no matching test was
identified. `INCONCLUSIVE` means a related observation exists but cannot prove
the stated route property. Entries reflect the linked recorded runs, not a new
execution of every test on the current commit. Bounded public STUN and external
HTTPS route audits were additionally rerun against the exact downloaded
0.8.7-preview Chromium; all other routes below were not rerun. Local
HTTPS-proxy and WebSocket supplements below were rerun against the unpacked
0.8.6-preview candidate-3 ZIP
(SHA-256 `bab9097883830edda661d64ee4d8a18f07bec57415f5c611173b960aabb138a9`),
whose `chrome.exe` SHA-256 is
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
Both use disposable loopback fixtures, not an independent public observer.

Additional 2026-10-14 local evidence on the exact 0.8.12 public Chromium core:
the HTTPS-proxy fixture passed 10/10 cases, including a 407 authentication
challenge. A positive direct control first reached the same IP-literal HTTPS
target; with the rejecting proxy selected, it received zero requests and the
alternate proxy received zero CONNECTs. This establishes no direct fallback
for that synthetic 407 case only. Correct/wrong credentials, GUI prompt,
external proxy, system DNS and packet capture remain **NOT RUN**. See
[`https_proxy_integration.py`](../tools/https_proxy_integration.py).

A later headless CDP Fetch attempt to supply synthetic Basic credentials on
the exact 0.8.13 core yielded no `Fetch.authRequired` event; the local proxy
returned two 407 responses and the target received no request. After one
bounded readiness repair, the result stayed **INCONCLUSIVE** as a test of
Chromium's GUI authentication prompt. No experimental code was retained.
The correct/wrong-password gate is still **NOT RUN**; next use a disposable
GUI profile with the native prompt, a positive direct target control and
aggregate proxy counters, never real credentials.

On the exact 0.8.8-preview core (`chrome.dll` SHA-256
`9d0943446e0cbe405f82286ce46c03ad8e928f7b8e46d3ed33082dce2f544075`),
an additional private-WSL STUN gate passed direct positive control (5 Binding
requests), HTTP proxy (0 UDP) and SOCKS5 proxy (0 UDP). The SOCKS5 fixture
observed one synthetic route-control request and four test-page requests.
This is **local cross-namespace evidence**, not independent public egress;
external DNS/IPv6/TURN and second-host checks remain NOT RUN. The report with
local addresses and raw NetLog remains outside the repository.

The launcher uses one `--proxy-server` and, for bundled Chromium only, removes
the implicit loopback bypass, blocks background hostname resolution except
the proxy endpoint, disables QUIC and sets WebRTC
`disable_non_proxied_udp`. See [`nevision_win.py`](../nevision_win.py)
(`proxy_endpoint`, `bundled_proxy_privacy_arguments`, `BrowserLauncher.launch`).
These browser flags do not control system DNS or provide a system firewall.

| Route property | Direct | HTTP proxy | HTTPS proxy | SOCKS5 proxy |
| --- | --- | --- | --- | --- |
| Destination DNS | **INCONCLUSIVE** — successful synthetic-name and one external HTTPS navigation do not identify the resolver; [`proxy_integration.py`](../tools/proxy_integration.py), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **INCONCLUSIVE** — proxy sees URL/CONNECT host, but OS DNS is not independently observed; proxy *hostname* may resolve locally; [`NETWORK_PRIVACY_2026-10.md`](NETWORK_PRIVACY_2026-10.md), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **NOT RUN** — no HTTPS-proxy DNS/packet test; [`NETWORK_PRIVACY_2026-10.md`](NETWORK_PRIVACY_2026-10.md). | **INCONCLUSIVE** — fixture saw destination as SOCKS5 domain (address type 3), but parallel DNS was not excluded; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| IPv4 HTTP/HTTPS URL route | **PASS (one host)** — exact 0.8.7 direct profile rendered the consented HTTPS JSON endpoint; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **PASS (one host)** — exact 0.8.7 rejecting control blocked rendering; allowlisted working CONNECT rendered via the proxy. NetLog showed loopback TCP only and zero UDP. Proxy used same host egress. | **PASS (loopback TLS/CONNECT only)** — local HTTPS proxy observed CONNECT and synthetic HTTPS target responded; untrusted proxy cert blocked the target; [`https_proxy_integration.py`](../tools/https_proxy_integration.py). External HTTPS-proxy route **NOT RUN**. | **PASS (one host)** — exact 0.8.7 rejecting control blocked rendering; allowlisted working SOCKS5 rendered via tunnel and sent the destination as a domain name. NetLog showed loopback TCP only and zero UDP. Proxy used same host egress; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| IPv6 URL/proxy route | **PASS (loopback only)** — `http://[::1]` reached local target; [`proxy_integration.py`](../tools/proxy_integration.py). External IPv6 **NOT RUN**. | **PASS (loopback URL and proxy endpoint)** — `::1` target worked through IPv4-loopback HTTP proxy; a separate HTTP proxy bound to `[::1]` routed the synthetic hostname and its unavailable control had no direct fallback. External IPv6 **NOT RUN**. | **PASS (proxy endpoint loopback only)** — exact 0.8.10 bundled Chromium reached a synthetic HTTPS target through a TLS proxy bound to `[::1]`; an untrusted certificate or unavailable proxy prevented the target request. The IPv6 *target URL* and external IPv6 remain **NOT RUN**; [`https_proxy_integration.py`](../tools/https_proxy_integration.py). | **PASS (loopback URL and proxy endpoint)** — `::1` target worked through IPv4-loopback SOCKS5 proxy; a separate SOCKS5 proxy bound to `[::1]` routed the synthetic hostname and its unavailable control had no direct fallback. External IPv6 **NOT RUN**. |
| HTTP/2 and HTTP/3 negotiation | **NOT RUN** — navigation tests do not assert negotiated protocol; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **NOT RUN** — CONNECT rendering does not assert negotiated HTTP version; same test. | **NOT RUN**. | **NOT RUN**. |
| QUIC/UDP for ordinary browsing | **INCONCLUSIVE** — direct-startup NetLog observed UDP attempts, not independent packet delivery; [`start_page_network_audit.py`](../tools/start_page_network_audit.py). | **INCONCLUSIVE** — launcher supplies `--disable-quic`; local proxy startup/HTTPS NetLogs observed zero UDP sends, but external packet capture is absent; [`nevision_win.py`](../nevision_win.py), [`start_page_network_audit.py`](../tools/start_page_network_audit.py), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **NOT RUN** — flag is supplied for this scheme but no HTTPS-proxy packet test exists. | **INCONCLUSIVE** — flag is supplied and one rejecting-proxy HTTPS NetLog had zero UDP sends; external packet capture is absent; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| WebRTC/STUN/TURN | **PASS (bounded STUN controls)** — private WSL receiver saw five direct Binding requests on 0.8.8; public Cloudflare STUN observed `srflx` and 17 NetLog UDP sends on public 0.8.6, 0.8.7 and exact public 0.8.16. TURN, DNS and IPv6 **NOT RUN**; [`wsl_stun_route_audit.py`](../tools/wsl_stun_route_audit.py), [`public_stun_policy_audit.py`](../tools/public_stun_policy_audit.py). | **PASS (bounded STUN controls)** — WSL receiver saw zero packets on 0.8.8; public STUN with rejecting HTTP proxy produced no ICE candidates and zero NetLog UDP sends on public 0.8.6, 0.8.7 and exact public 0.8.16. Cloudflare-side logs and independent packet capture unavailable; same tools. A no-STUN ICE test in [`privacy_browser_integration.py`](../tools/privacy_browser_integration.py) is not a leak test. | **NOT RUN**. | **PASS (private WSL gate only)** — on exact 0.8.8, SOCKS5 fixture observed the page and route control; WSL receiver saw zero UDP/STUN and NetLog zero UDP sends. External egress, DNS, IPv6 and TURN remain NOT RUN. |
| WebSocket (`ws`/`wss`) | **PASS (loopback only)** — synthetic WS/WSS handshake and message reached target directly; [`websocket_route_integration.py`](../tools/websocket_route_integration.py). | **PASS (loopback only)** — local HTTP proxy observed route and target received WS/WSS message; unavailable proxy blocked both; same test. | **PASS (loopback TLS/CONNECT only)** — separate disposable TLS proxy cert and target cert; proxy saw CONNECT and target received WS/WSS, while unavailable or untrusted proxy blocked both; [`websocket_route_integration.py`](../tools/websocket_route_integration.py). External route **NOT RUN**. | **PASS (loopback only)** — local SOCKS5 proxy observed route and target received WS/WSS message; unavailable proxy blocked both; same test. External routes **NOT RUN**. |
| PAC / automatic proxy configuration | **NOT RUN** — managed profiles currently launch with a fixed `--proxy-server`, not a tested PAC path; [`nevision_win.py`](../nevision_win.py). | **NOT RUN** — fixed-proxy tests do not validate PAC. | **NOT RUN**. | **NOT RUN**. |
| New tab, search and browser update/background requests | **INCONCLUSIVE** — new bundled profiles show a blank new tab, but background traffic was still observed; later search choices and core-update traffic are not controlled by this test; [`start_page_network_audit.py`](../tools/start_page_network_audit.py). | **INCONCLUSIVE** — local proxy startup tests observed attempted background requests and the assigned loopback route, not an independent public-network path; same audit. Search choices and updates **NOT RUN**. | **NOT RUN** — no HTTPS-proxy startup/background fixture. | **INCONCLUSIVE** — rejecting-proxy startup was tested locally; real search/update routes **NOT RUN**; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| `localhost` and link-local URLs | **PASS (loopback URL only)** — IPv4/IPv6 local target positive controls; [`proxy_integration.py`](../tools/proxy_integration.py). Link-local address **NOT RUN**. | **PASS (loopback URL only)** — fixture sees `127.0.0.1`/`::1` URL through proxy because implicit bypass is subtracted; same test. Link-local address **NOT RUN**. | **INCONCLUSIVE** — HTTPS-proxy test uses a synthetic `.invalid` target and loopback proxy, not a `localhost` URL; link-local **NOT RUN**. | **PASS (loopback URL only)** — local fixture sees proxied loopback URL; same test. Link-local address **NOT RUN**. |
| Windows/system and external-application traffic | **NOT RUN** — Chromium flags do not route arbitrary Windows processes; this is outside the browser-profile boundary. | **NOT RUN** — selecting a proxy in NeAntik Win does not proxy external applications or prove OS DNS isolation. | **NOT RUN** — same boundary. | **NOT RUN** — same boundary. |
| Proxy authentication | **NOT RUN (not applicable)** — no proxy selected. | **NOT RUN** — UI stores credentials and stock browser is expected to prompt, but authenticated HTTP CONNECT was not exercised; [`nevision_win.py`](../nevision_win.py), [`SECURITY_AND_SCOPE.md`](../SECURITY_AND_SCOPE.md). | **PASS (local 407 refusal only)** — one unauthenticated 407 challenge left a directly reachable IP-literal target untouched. Correct/wrong credentials and GUI prompt **NOT RUN**; [`https_proxy_integration.py`](../tools/https_proxy_integration.py). | **PASS (launch refusal only)** — authenticated SOCKS5 is rejected before launch; no authenticated SOCKS5 route is supported; [`nevision_win.py`](../nevision_win.py). |
| Route failure / fail-closed | **PASS (local positive control only)** — target works without proxy; [`proxy_integration.py`](../tools/proxy_integration.py). | **PASS (tested local cases)** — unavailable proxy returned `ERR_PROXY_CONNECTION_FAILED`, loopback target saw no request; rejecting local proxy prevented one external HTTPS page from rendering. On the exact public 0.8.16-preview Chromium, one owned loopback-only HTTP-proxy session passed **10/10** loss/recovery checks: no target hit while the proxy was down, same browser process routed again after recovery, NetLog saw loopback TCP only and zero UDP sends; [`proxy_loss_recovery_gate.py`](../tools/proxy_loss_recovery_gate.py). A `.invalid` proxy-host failure on the exact 0.8.11 core did not reach the target; exact DNS failure cause, auth failure and external packet route **NOT RUN**. | **PASS (loopback only)** — untrusted TLS proxy cert, unavailable proxy and one 407 refusal prevented target requests; direct control proved the 407 target reachable. Correct/wrong credentials, proxy loss/recovery and external packet route **NOT RUN**; [`https_proxy_integration.py`](../tools/https_proxy_integration.py). | **PASS (tested local cases)** — unavailable proxy did not reach local target; rejecting SOCKS5 did not render one external HTTPS page; `.invalid` proxy-host failure on exact 0.8.11 core did not reach target. Exact DNS failure cause, proxy loss/recovery and external packet route **NOT RUN**. |

The reserved `.invalid` proxy-host failure cases for HTTP and SOCKS5 passed
on the exact public 0.8.11 Chromium core: the complete loopback harness had
**72/72 assertions over 19 launches**, including direct positive controls
before and after. Both failures produced `ERR_PROXY_CONNECTION_FAILED`, zero
synthetic target hits and no successful DOM. The first harness attempt
expected a different error label and failed as a test expectation; the
observed fail-closed result remained the same. This proves no DIRECT fallback
to this synthetic target after these proxy-host failures. It does **not**
establish the exact failure cause, identify the Windows resolver or exclude
OS DNS packets. The independent DNS/egress gate remains **NOT RUN**.

## Open P2 gates

On 2026-10-14 the extracted public 0.8.9-preview Chromium (`chrome.exe`
SHA-256 `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`)
passed the extended loopback route harness: **64/64 assertions in 17 owned
browser launches**. The new cases bind the HTTP and SOCKS5 proxy *itself* to
IPv6 loopback `[::1]`, with working and unavailable controls. A first run
failed before any route checks because the raw extracted engine lacked the
AppContainer ACL; the successful run used a hash-identical disposable engine
copy prepared as the product launcher does. This does not test external IPv6,
DNS, TURN, another host or independent packet capture.

On the exact 0.8.10-preview bundled Chromium with the same `chrome.exe` hash,
the separate HTTPS-proxy loopback fixture passed **8/8 cases**. Its new `[::1]`
TLS endpoint observed a working CONNECT and target hit, while untrusted-cert
and unavailable-endpoint controls saw no target hit or alternate-proxy use.
The disposable engine copy retained the packaged hash and received only the
product-equivalent AppContainer ACL. This is local IPv6 *proxy endpoint*
evidence, not an external DNS/IPv6/TURN or packet-capture result.

The current external HTTPS probe uses **one** consented origin and a proxy
running on the **same Windows host** as Chromium. The WSL STUN receiver has a
separate private network namespace but shares that physical machine. The
public STUN check got an external `srflx` response, but has no server-side
logs or independent capture of the proxy case. None of these
constitutes the independent external egress, DNS observer or packet capture
required by [`MASTER_IMPLEMENTATION_PLAN.md`](MASTER_IMPLEMENTATION_PLAN.md)
(P0.2/P2.2/P2.3). On the QA host, PktMon lacked elevation and the DNS Client
Operational log was disabled; see [`NETWORK_PRIVACY_2026-10.md`](NETWORK_PRIVACY_2026-10.md).
The overall P2 network gate remains **OPEN** (its independent egress/DNS/
packet-observation test is **NOT RUN**), irrespective of the individual local
and bounded public-STUN PASS entries above.

Next measurable run: with two controlled HTTPS origins and a separately
operated egress/DNS/UDP observer, execute disposable direct and proxy profiles
for each supported scheme, include a working and failing route, record browser
NetLog *and* independent server/packet observations, and require a positive
control for each transport. Keep raw reports private and publish only
redacted check results, exact engine commit and executable SHA-256.
