# P2.1 route matrix — 13 October 2026

This is an evidence inventory, **not** a leak-free or anonymity certificate. It
describes the bundled Chromium with a fixed proxy selected in NeAntik Win.
Installed Chrome/Edge and other Windows processes are outside these checks.
`PASS` below always names its narrow local/one-host scenario; it never implies
that an external-network gate passed. `NOT RUN` means no matching test was
identified. `INCONCLUSIVE` means a related observation exists but cannot prove
the stated route property. Entries reflect the linked recorded runs, not a new
execution of every test on the current commit.

The launcher uses one `--proxy-server` and, for bundled Chromium only, removes
the implicit loopback bypass, blocks background hostname resolution except
the proxy endpoint, disables QUIC and sets WebRTC
`disable_non_proxied_udp`. See [`nevision_win.py`](../nevision_win.py)
(`proxy_endpoint`, `bundled_proxy_privacy_arguments`, `BrowserLauncher.launch`).
These browser flags do not control system DNS or provide a system firewall.

| Route property | Direct | HTTP proxy | HTTPS proxy | SOCKS5 proxy |
| --- | --- | --- | --- | --- |
| Destination DNS | **INCONCLUSIVE** — successful synthetic-name and one external HTTPS navigation do not identify the resolver; [`proxy_integration.py`](../tools/proxy_integration.py), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **INCONCLUSIVE** — proxy sees URL/CONNECT host, but OS DNS is not independently observed; proxy *hostname* may resolve locally; [`NETWORK_PRIVACY_2026-10.md`](NETWORK_PRIVACY_2026-10.md), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **NOT RUN** — no HTTPS-proxy DNS/packet test; [`NETWORK_PRIVACY_2026-10.md`](NETWORK_PRIVACY_2026-10.md). | **INCONCLUSIVE** — fixture saw destination as SOCKS5 domain (address type 3), but parallel DNS was not excluded; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| IPv4 HTTP/HTTPS URL route | **PASS (one host)** — local HTTP target and project's consented HTTPS JSON endpoint reached directly; [`proxy_integration.py`](../tools/proxy_integration.py), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **PASS (one host)** — local HTTP target went via proxy; one external HTTPS origin rendered through allowlisted local CONNECT; browser NetLog only saw loopback TCP in that case; same tests. The proxy itself used the same host's egress. | **NOT RUN** — `https` is an accepted proxy scheme in [`nevision_win.py`](../nevision_win.py), but no working HTTPS-proxy integration is recorded. | **PASS (local)** — local HTTP target went via SOCKS5. External HTTPS was tested only with a *rejecting* SOCKS5 proxy, not a working tunnel; same tests. |
| IPv6 URL/proxy route | **PASS (loopback only)** — `http://[::1]` reached local target; [`proxy_integration.py`](../tools/proxy_integration.py). External IPv6 **NOT RUN**. | **PASS (loopback URL only)** — `::1` target reached through IPv4-loopback HTTP proxy; unavailable proxy did not reach it; same test. External IPv6/proxy IPv6 **NOT RUN**. | **NOT RUN** — no corresponding IPv6 fixture. | **PASS (loopback URL only)** — `::1` target reached through IPv4-loopback SOCKS5 proxy; unavailable proxy did not reach it; same test. External IPv6/proxy IPv6 **NOT RUN**. |
| HTTP/2 and HTTP/3 negotiation | **NOT RUN** — navigation tests do not assert negotiated protocol; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **NOT RUN** — CONNECT rendering does not assert negotiated HTTP version; same test. | **NOT RUN**. | **NOT RUN**. |
| QUIC/UDP for ordinary browsing | **INCONCLUSIVE** — direct-startup NetLog observed UDP attempts, not independent packet delivery; [`start_page_network_audit.py`](../tools/start_page_network_audit.py). | **INCONCLUSIVE** — launcher supplies `--disable-quic`; local proxy startup/HTTPS NetLogs observed zero UDP sends, but external packet capture is absent; [`nevision_win.py`](../nevision_win.py), [`start_page_network_audit.py`](../tools/start_page_network_audit.py), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **NOT RUN** — flag is supplied for this scheme but no HTTPS-proxy packet test exists. | **INCONCLUSIVE** — flag is supplied and one rejecting-proxy HTTPS NetLog had zero UDP sends; external packet capture is absent; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| WebRTC/STUN/TURN | **PASS (STUN, private WSL topology only)** — independent private receiver saw five direct STUN Binding requests with normal sandbox; public STUN, TURN and ICE address exposure **NOT RUN**; [`wsl_stun_route_audit.py`](../tools/wsl_stun_route_audit.py). | **PASS (STUN, private WSL topology only)** — receiver saw zero STUN packets for the rejecting HTTP-proxy case, browser NetLog zero UDP sends; no public-network/TURN proof; same test. A no-STUN ICE test in [`privacy_browser_integration.py`](../tools/privacy_browser_integration.py) is not a leak test. | **NOT RUN**. | **NOT RUN** — WebRTC path was not tested with SOCKS5. |
| WebSocket (`ws`/`wss`) | **NOT RUN** — no dedicated handshake/route assertion in the cited network tools. | **NOT RUN**. | **NOT RUN**. | **NOT RUN**. |
| PAC / automatic proxy configuration | **NOT RUN** — managed profiles currently launch with a fixed `--proxy-server`, not a tested PAC path; [`nevision_win.py`](../nevision_win.py). | **NOT RUN** — fixed-proxy tests do not validate PAC. | **NOT RUN**. | **NOT RUN**. |
| New tab, search and browser update/background requests | **INCONCLUSIVE** — new bundled profiles show a blank new tab, but background traffic was still observed; later search choices and core-update traffic are not controlled by this test; [`start_page_network_audit.py`](../tools/start_page_network_audit.py). | **INCONCLUSIVE** — local proxy startup tests observed attempted background requests and the assigned loopback route, not an independent public-network path; same audit. Search choices and updates **NOT RUN**. | **NOT RUN** — no HTTPS-proxy startup/background fixture. | **INCONCLUSIVE** — rejecting-proxy startup was tested locally; real search/update routes **NOT RUN**; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
| `localhost` and link-local URLs | **PASS (loopback URL only)** — IPv4/IPv6 local target positive controls; [`proxy_integration.py`](../tools/proxy_integration.py). Link-local address **NOT RUN**. | **PASS (loopback URL only)** — fixture sees `127.0.0.1`/`::1` URL through proxy because implicit bypass is subtracted; same test. Link-local address **NOT RUN**. | **NOT RUN** — flag is configured, but no HTTPS-proxy route test. | **PASS (loopback URL only)** — local fixture sees proxied loopback URL; same test. Link-local address **NOT RUN**. |
| Windows/system and external-application traffic | **NOT RUN** — Chromium flags do not route arbitrary Windows processes; this is outside the browser-profile boundary. | **NOT RUN** — selecting a proxy in NeAntik Win does not proxy external applications or prove OS DNS isolation. | **NOT RUN** — same boundary. | **NOT RUN** — same boundary. |
| Proxy authentication | **NOT RUN (not applicable)** — no proxy selected. | **NOT RUN** — UI stores credentials and stock browser is expected to prompt, but authenticated HTTP CONNECT was not exercised; [`nevision_win.py`](../nevision_win.py), [`SECURITY_AND_SCOPE.md`](../SECURITY_AND_SCOPE.md). | **NOT RUN** — authenticated HTTPS proxy not exercised. | **PASS (launch refusal only)** — authenticated SOCKS5 is rejected before launch; no authenticated SOCKS5 route is supported; [`nevision_win.py`](../nevision_win.py). |
| Route failure / fail-closed | **PASS (local positive control only)** — target works without proxy; [`proxy_integration.py`](../tools/proxy_integration.py). | **PASS (tested local cases)** — unavailable proxy returned `ERR_PROXY_CONNECTION_FAILED`, loopback target saw no request; rejecting local proxy prevented one external HTTPS page from rendering; [`proxy_integration.py`](../tools/proxy_integration.py), [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). DNS failure, auth failure, proxy loss/recovery and external packet route **NOT RUN**. | **NOT RUN** — no unavailable/auth-failure HTTPS-proxy control. | **PASS (tested local cases)** — unavailable proxy did not reach local target; rejecting SOCKS5 did not render one external HTTPS page; same tools. DNS failure, proxy loss/recovery and external packet route **NOT RUN**. |

## Open P2 gates

The current external HTTPS probe uses **one** consented origin and a proxy
running on the **same Windows host** as Chromium. The WSL STUN receiver has a
separate private network namespace but shares that physical machine. Neither
constitutes the independent external egress, DNS observer or packet capture
required by [`MASTER_IMPLEMENTATION_PLAN.md`](MASTER_IMPLEMENTATION_PLAN.md)
(P0.2/P2.2/P2.3). On the QA host, PktMon lacked elevation and the DNS Client
Operational log was disabled; see [`NETWORK_PRIVACY_2026-10.md`](NETWORK_PRIVACY_2026-10.md).
The overall P2 network gate is therefore **NOT RUN**, irrespective of the
individual local PASS entries above.

Next measurable run: with two controlled HTTPS origins and a separately
operated egress/DNS/UDP observer, execute disposable direct and proxy profiles
for each supported scheme, include a working and failing route, record browser
NetLog *and* independent server/packet observations, and require a positive
control for each transport. Keep raw reports private and publish only
redacted check results, exact engine commit and executable SHA-256.
