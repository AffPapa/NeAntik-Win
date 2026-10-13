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
| IPv6 URL/proxy route | **PASS (loopback only)** — `http://[::1]` reached local target; [`proxy_integration.py`](../tools/proxy_integration.py). External IPv6 **NOT RUN**. | **PASS (loopback URL and proxy endpoint)** — `::1` target worked through IPv4-loopback HTTP proxy; a separate HTTP proxy bound to `[::1]` routed the synthetic hostname and its unavailable control had no direct fallback. External IPv6 **NOT RUN**. | **NOT RUN** — no corresponding IPv6 fixture. | **PASS (loopback URL and proxy endpoint)** — `::1` target worked through IPv4-loopback SOCKS5 proxy; a separate SOCKS5 proxy bound to `[::1]` routed the synthetic hostname and its unavailable control had no direct fallback. External IPv6 **NOT RUN**. |
| HTTP/2 and HTTP/3 negotiation | **NOT RUN** — navigation tests do not assert negotiated protocol; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **NOT RUN** — CONNECT rendering does not assert negotiated HTTP version; same test. | **NOT RUN**. | **NOT RUN**. |
| QUIC/UDP for ordinary browsing | **INCONCLUSIVE** — direct-startup NetLog observed UDP attempts, not independent packet delivery; [`start_page_network_audit.py`](../tools/start_page_network_audit.py). | **INCONCLUSIVE** — launcher supplies `--disable-quic`; local proxy startup/HTTPS NetLogs observed zero UDP sends, but external packet capture is absent; [`nevision_win.py`](../nevision_win.py), [`start_page_network_audit.py`](../tools/start_page_network_audit.py), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **NOT RUN** — flag is supplied for this scheme but no HTTPS-proxy packet test exists. | **INCONCLUSIVE** — flag is supplied and one rejecting-proxy HTTPS NetLog had zero UDP sends; external packet capture is absent; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| WebRTC/STUN/TURN | **PASS (bounded STUN controls)** — private WSL receiver saw five direct Binding requests on 0.8.8; public Cloudflare STUN observed `srflx` and 17 NetLog UDP sends on public 0.8.6 and exact public 0.8.7. TURN, DNS and IPv6 **NOT RUN**; [`wsl_stun_route_audit.py`](../tools/wsl_stun_route_audit.py), [`public_stun_policy_audit.py`](../tools/public_stun_policy_audit.py). | **PASS (bounded STUN controls)** — WSL receiver saw zero packets on 0.8.8; public STUN with rejecting HTTP proxy produced no ICE candidates and zero NetLog UDP sends on public 0.8.6 and exact 0.8.7. Cloudflare-side logs and independent packet capture unavailable; same tools. A no-STUN ICE test in [`privacy_browser_integration.py`](../tools/privacy_browser_integration.py) is not a leak test. | **NOT RUN**. | **PASS (private WSL gate only)** — on exact 0.8.8, SOCKS5 fixture observed the page and route control; WSL receiver saw zero UDP/STUN and NetLog zero UDP sends. External egress, DNS, IPv6 and TURN remain NOT RUN. |
| WebSocket (`ws`/`wss`) | **PASS (loopback only)** — synthetic WS/WSS handshake and message reached target directly; [`websocket_route_integration.py`](../tools/websocket_route_integration.py). | **PASS (loopback only)** — local HTTP proxy observed route and target received WS/WSS message; unavailable proxy blocked both; same test. | **PASS (loopback TLS/CONNECT only)** — separate disposable TLS proxy cert and target cert; proxy saw CONNECT and target received WS/WSS, while unavailable or untrusted proxy blocked both; [`websocket_route_integration.py`](../tools/websocket_route_integration.py). External route **NOT RUN**. | **PASS (loopback only)** — local SOCKS5 proxy observed route and target received WS/WSS message; unavailable proxy blocked both; same test. External routes **NOT RUN**. |
| PAC / automatic proxy configuration | **NOT RUN** — managed profiles currently launch with a fixed `--proxy-server`, not a tested PAC path; [`nevision_win.py`](../nevision_win.py). | **NOT RUN** — fixed-proxy tests do not validate PAC. | **NOT RUN**. | **NOT RUN**. |
| New tab, search and browser update/background requests | **INCONCLUSIVE** — new bundled profiles show a blank new tab, but background traffic was still observed; later search choices and core-update traffic are not controlled by this test; [`start_page_network_audit.py`](../tools/start_page_network_audit.py). | **INCONCLUSIVE** — local proxy startup tests observed attempted background requests and the assigned loopback route, not an independent public-network path; same audit. Search choices and updates **NOT RUN**. | **NOT RUN** — no HTTPS-proxy startup/background fixture. | **INCONCLUSIVE** — rejecting-proxy startup was tested locally; real search/update routes **NOT RUN**; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| `localhost` and link-local URLs | **PASS (loopback URL only)** — IPv4/IPv6 local target positive controls; [`proxy_integration.py`](../tools/proxy_integration.py). Link-local address **NOT RUN**. | **PASS (loopback URL only)** — fixture sees `127.0.0.1`/`::1` URL through proxy because implicit bypass is subtracted; same test. Link-local address **NOT RUN**. | **INCONCLUSIVE** — HTTPS-proxy test uses a synthetic `.invalid` target and loopback proxy, not a `localhost` URL; link-local **NOT RUN**. | **PASS (loopback URL only)** — local fixture sees proxied loopback URL; same test. Link-local address **NOT RUN**. |
| Windows/system and external-application traffic | **NOT RUN** — Chromium flags do not route arbitrary Windows processes; this is outside the browser-profile boundary. | **NOT RUN** — selecting a proxy in NeAntik Win does not proxy external applications or prove OS DNS isolation. | **NOT RUN** — same boundary. | **NOT RUN** — same boundary. |
| Proxy authentication | **NOT RUN (not applicable)** — no proxy selected. | **NOT RUN** — UI stores credentials and stock browser is expected to prompt, but authenticated HTTP CONNECT was not exercised; [`nevision_win.py`](../nevision_win.py), [`SECURITY_AND_SCOPE.md`](../SECURITY_AND_SCOPE.md). | **NOT RUN** — authenticated HTTPS proxy not exercised. | **PASS (launch refusal only)** — authenticated SOCKS5 is rejected before launch; no authenticated SOCKS5 route is supported; [`nevision_win.py`](../nevision_win.py). |
| Route failure / fail-closed | **PASS (local positive control only)** — target works without proxy; [`proxy_integration.py`](../tools/proxy_integration.py). | **PASS (tested local cases)** — unavailable proxy returned `ERR_PROXY_CONNECTION_FAILED`, loopback target saw no request; rejecting local proxy prevented one external HTTPS page from rendering. On the exact public 0.8.8-preview Chromium, one owned loopback-only HTTP-proxy session passed **10/10** loss/recovery checks: no target hit while the proxy was down, same browser process routed again after restart, NetLog saw loopback TCP only and zero UDP sends; [`proxy_loss_recovery_gate.py`](../tools/proxy_loss_recovery_gate.py). DNS failure, auth failure and external packet route **NOT RUN**. | **PASS (loopback only)** — untrusted TLS proxy cert and unavailable proxy both prevented the synthetic target request; [`https_proxy_integration.py`](../tools/https_proxy_integration.py). Auth failure, proxy loss/recovery and external packet route **NOT RUN**. | **PASS (tested local cases)** — unavailable proxy did not reach local target; rejecting SOCKS5 did not render one external HTTPS page; same tools. DNS failure, proxy loss/recovery and external packet route **NOT RUN**. |

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
