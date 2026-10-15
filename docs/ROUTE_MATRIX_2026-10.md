# P2.1 route matrix — updated 15 October 2026

This is an evidence inventory, **not** a leak-free or anonymity certificate. It
describes the bundled Chromium with a fixed proxy selected in NeAntik Win.
Installed Chrome/Edge and other Windows processes are outside these checks.
`PASS` below always names its narrow local/one-host scenario; it never implies
that an external-network gate passed. `NOT RUN` means no matching test was
identified. `INCONCLUSIVE` means a related observation exists but cannot prove
the stated route property. Detailed historical entries reflect their linked
runs, not a new execution of every test on the current commit. Bounded public
STUN and external HTTPS route audits were rerun against the exact downloaded
0.8.7-preview Chromium; local HTTPS proxy TLS/CONNECT and HTTP/SOCKS5 loopback
gates were rerun on the exact public 0.8.18-preview Chromium, then the local
HTTP/SOCKS5, HTTPS, WS/WSS, proxy-loss/recovery, and cross-namespace WebRTC
gates were rerun against the exact public 0.8.19-preview Chromium in dated
addenda below. Other historical routes were not rerun on 0.8.19. The older local
HTTPS-proxy/WebSocket supplements were run against the unpacked
0.8.6-preview candidate-3 ZIP; a newer full WS/WSS matrix is separately
recorded below for exact public 0.8.18-preview
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
| IPv4 HTTP/HTTPS URL route | **PASS (one host)** — exact 0.8.7 direct profile rendered the consented HTTPS JSON endpoint; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). | **PASS (one host)** — exact public 0.8.16-preview repeat-downloaded ZIP, same-host HTTPS endpoint: rejecting proxy blocked rendering; working CONNECT rendered via proxy. 28 assertions across four cases passed; proxied NetLogs showed loopback TCP only and zero UDP. Same-host proxy egress; independent packet/DNS observation **NOT RUN**. | **PASS (one host, same-host endpoint)** — exact public 0.8.16-preview via working CONNECT. Independent proxy host/egress, DNS and packet capture **NOT RUN**. | **PASS (one host)** — exact public 0.8.16-preview rejecting control blocked rendering; working SOCKS5 rendered via tunnel and sent destination as a domain name. The four HTTP/SOCKS reject/working cases passed 28 assertions total. Proxied NetLogs showed loopback TCP only and zero UDP. Same-host proxy egress; [`external_proxy_fail_closed_audit.py`](../tools/external_proxy_fail_closed_audit.py). |
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

### Exact public 0.8.18-preview HTTPS proxy controls — 15 October 2026

On the repeat-downloaded 0.8.18-preview Chromium (`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`), the
local HTTPS-proxy harness passed **10 cases / 75 assertions**. Working IPv4
and IPv6 TLS proxy CONNECTs reached the synthetic target; untrusted proxy
certificates and reserved unavailable proxy ports did not. The 407-auth case
had a preceding direct positive control, but with the rejecting proxy selected
the target received zero requests and no alternate proxy was used (two 407
challenges recorded). Correct proxy credentials and GUI prompt remain
**NOT RUN**. The exact release record is in
[`RELEASE_PUBLICATION_0.8.18-preview.md`](RELEASE_PUBLICATION_0.8.18-preview.md);
the report remains local and contains only synthetic fixture measurements.

These controls share one Windows host and use loopback-only services. They do
not close external DNS, public IPv6, TURN, packet-capture or independent-egress
gates; P2 remains **OPEN**.

### Exact public 0.8.18-preview HTTP/SOCKS5 loopback controls — 15 October 2026

The exact downloaded Chromium (`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`) passed
**72/72 assertions over 19 launches** using disposable local profiles. Direct
positive controls, HTTP and SOCKS5 success, IPv4/IPv6 loopback targets and
proxy endpoints, and unavailable HTTP/SOCKS5 endpoints were exercised. Every
unavailable-endpoint case produced zero target requests; the working SOCKS5
fixture received the destination hostname (SOCKS5 domain address type 3).
Before each Chromium Popen the harness calls the product's
`BrowserLauncher.ensure_profile_path_is_isolated`; the actual Windows junction
launch regression passed immediately before this run. Harness commit
`9d16e8a2ad0b963969d48d2d08c5c9342d1573dd`, harness SHA-256
`9af53f5f0c84c74d690486a241cd0b5bcc411d6ab270d6da7d810e74200fc5b6`, and
product-source SHA-256 `3c7ef3590cae465549241040393f6db99a5840b9f021de40c3f596e487168168`.
Private report:
`C:\N155\proxy-integration-0.8.18-preview-20261015.json`.

This is source-harness evidence against the exact release engine, not packaged
GUI coverage. It does not establish external DNS/IPv6/UDP/TURN behavior,
proxy-auth success, independent egress, or anonymity; P2 remains **OPEN**.

### Exact public 0.8.18-preview WebRTC UDP cross-namespace controls — 15 October 2026

The exact public Chromium (`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`) passed
the direct-positive-control plus HTTP/SOCKS5 proxy comparison against a STUN
receiver in the local Ubuntu WSL network namespace: **3 cases**, HTTP and
SOCKS5 route checks both **PASS**. Direct sent 5 STUN Binding requests and
5 UDP datagrams to the controlled receiver. With HTTP and SOCKS5 proxies
selected, the receiver saw 0 STUN requests and 0 UDP datagrams; Chromium NetLog
reported 0 UDP sends in both proxy cases. SOCKS5 positive route controls saw
one synthetic route-control request and four proxied page requests. The harness
used disposable profiles under `Data/Profiles`, production
`BrowserLauncher.ensure_profile_path_is_isolated` before each Popen, and a
byte-identical sandbox-ACL prepared copy. The Windows junction regression
passed immediately before the run.

Harness source commit `251aebca3e67208af758a71e6bcbca64e1babfad`;
`webrtc_udp_integration.py` SHA-256
`7a4c56340b806028a686797fc88bbbeed0c81b4c40cf6bd108d4c68e9e8d64db`;
`wsl_stun_route_audit.py` SHA-256
`89c63d91b382e322f4006c22b499c6cc0d8919de40a073b418ef10f99f768be1`.
The harness verified the source and sandbox-prepared executable hashes match.
Private report:
`C:\N155\wsl-stun-0.8.18-preview-provenance-20261015.json`.

This is a same-machine cross-network-namespace control, not an independent
public egress/packet observer. External DNS, public IPv6, TURN, another host,
proxy authentication and anonymity remain **NOT RUN**; P2 remains **OPEN**.

### Exact public 0.8.18-preview WebSocket route controls — 15 October 2026

The exact downloaded Chromium (`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`) passed
**16/16 loopback cases**: `ws` and `wss` over direct, HTTP, HTTPS and SOCKS5;
unavailable HTTP/HTTPS/SOCKS5 proxies; and an untrusted HTTPS-proxy certificate.
All successful cases observed exactly one expected target message and the
selected proxy route. All unavailable/untrusted cases observed no target
message and no proxy connection. The target, proxies, DNS mapping, and DevTools
endpoint were local fixtures; generated certificate keys were disposable.
Profiles were stored in `Data/Profiles`, production profile-path isolation was
checked before each Popen, and the ACL-prepared Chromium copy matched the
release executable hash. The Windows junction regression passed immediately
before this run.

Harness source commit `9baae953bf38d169b7c768c4a83558bd94e69806`, SHA-256
`08c51b6810da7072028754832c559b83cb036de66d9fd50b24b9ff1e009d759f`.
Private report: `C:\N155\websocket-route-0.8.18-preview-20261015.json`.
This establishes only the listed same-host loopback routes. External
WebSocket/proxy/DNS/IPv6 and proxy-auth success remain **NOT RUN**.

### Exact public 0.8.19-preview route checks — 15 October 2026

All browser cases used `chrome.exe` extracted from the verified public
0.8.19-preview ZIP (ZIP SHA-256
`adec43f1fb17c1864cac0ca826b329162a0f7b56d924f87ecc4d7aa1a4910d2a`;
`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`). The
Chromium image matches the exact 0.8.18 engine; binary source commit is
`826f81671aa164434840eb023170c6ddf831cb51`. Test harness/source commit was
`d40d839b713962e3790a97893cfb36637a0e7639`; `nevision_win.py` is byte-identical
between the release and harness commits. Before each launched case the harness
called `BrowserLauncher.ensure_profile_path_is_isolated`. A real Windows
junction regression on the same harness commit exercised that production guard
against `Data`, `Profiles` and the selected profile root; all three were
rejected before process creation.

| Gate | Result | Narrow evidence |
| --- | --- | --- |
| HTTP/SOCKS5 | **72/72 assertions, 19 launches PASS** | Direct controls; IPv4/IPv6 loopback target/proxy; unavailable proxies had zero target requests; SOCKS5 hostname forwarded to fixture. |
| HTTPS proxy | **10/10 cases PASS** | IPv4/IPv6 CONNECT, untrusted cert, dead endpoints, 407 rejection with no target/direct fallback. Successful authentication was not covered. |
| WS/WSS | **16/16 cases PASS** | Direct + HTTP/HTTPS/SOCKS5 success and unavailable/untrusted failure controls; local fixtures only. |
| Proxy loss/recovery | **10/10 checks PASS** | Same browser session; zero target hits during outage; recovered through proxy; NetLog loopback TCP only and zero UDP sends. |
| WebRTC cross-namespace | **3 cases PASS** | Same-PC private WSL UDP sink: direct positive control got 5 STUN/UDP packets; HTTP and SOCKS5 routes got zero STUN/UDP and NetLog zero UDP sends. |

Full unit suite on the test commit: **266 PASS, 3 skipped**. Raw reports remain
outside the public repository because they contain private-interface addresses
and synthetic run tokens; only allowlisted summaries are published here.
SHA-256 identities:

- `chrome.exe`: `7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`;
  `nevision_win.py`: `0903fd0e75fd3d9b7adb316398bbc60d6546724ecd6635b03ac7cb6429ece594`.
- `proxy_integration.py`: `9af53f5f0c84c74d690486a241cd0b5bcc411d6ab270d6da7d810e74200fc5b6`;
  report: `e87f3cd84befd5caa431c4b00d7455fa7f4de6b36943814b5cf2b2d96d80a5de`.
- `https_proxy_integration.py`: `2955d5519f91248832fc9f71adfafd36a82967e4ab90e113a73985932ecd2a62`;
  report: `8036614a68ba2f1d244c4ccb6d3965de33c26ccba6cbd5db5df331169583f8bc`.
- `websocket_route_integration.py`: `08c51b6810da7072028754832c559b83cb036de66d9fd50b24b9ff1e009d759f`;
  report: `242c2d12f5fd35e42baf2e26cac3138b95530b6fa22b14666117d171c99adf75`.
- `proxy_loss_recovery_gate.py`: `2b5350167d7aeefc7a5dcf2829d45a85830532f57a0cdeb748baa5d5df64a500ea`;
  report: `f22434d079710a9e2bd3949dd8dfddf31a00e8ba369d29c482201add470517e4`.
- `wsl_stun_route_audit.py`: `89c63d91b382e322f4006c22b499c6cc0d8919de40a073b418ef10f99f768be1`;
  `webrtc_udp_integration.py`: `7a4c56340b806028a686797fc88bbbeed0c81b4c40cf6bd108d4c68e9e8d64db`;
  report: `850dc5ce7da0816727042bb7d8a52efd0b3fef1577aee14e8a72aa963b88b456`.

These tests establish only the enumerated local routes. They do not observe
public DNS, external IPv6/UDP/STUN/TURN or an independent egress/packet
observer, and do not cover proxy-auth success or prove anonymity. Those gates
remain **NOT RUN**; P2 remains **OPEN**.

### Exact public 0.8.23-preview HTTPS and proxy-loss controls — 15 October 2026

The exact Chromium extracted from the public 0.8.23-preview ZIP (archive
SHA-256
`f2a3e6829d8a904d3454586d967c4d150f8c1608f3d940785ee18129271249ca`;
`chrome.exe` SHA-256
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`) passed
two targeted loopback-only checks. The HTTPS proxy fixture passed **10/10
cases**: direct positive controls, IPv4/IPv6 TLS CONNECT, untrusted
certificates, unavailable proxy ports, and a rejecting 407 auth challenge
with no alternate/direct target request. Correct proxy credentials remain
**NOT RUN**. The separate one-process HTTP-proxy loss/recovery gate passed
**10/10 checks**: positive route before loss, zero target requests during the
outage, route restored through the proxy in the same live browser process,
NetLog TCP destinations limited to `127.0.0.1`, and zero NetLog UDP sends.

Both harnesses used disposable profiles/engine copies and synthetic local
listeners only. Harness commit `c7f91db7875272a186282d7c2c641e6cd158a011`;
`https_proxy_integration.py` SHA-256
`2955d5519f91248832fc9f71adfafd36a82967e4ab90e113a73985932ecd2a62`;
`proxy_loss_recovery_gate.py` SHA-256
`2b5350167d7aefc7a5dcf2829d45a85830532f57a0cdeb748baa5ddf64a500ea`;
`chrome.dll` SHA-256
`be2e1ab71dd749509e2f2cf64c3f7e883b0ce5218e644e3e58e087dee3a4bdc9`.
This redacted summary is the public evidence record; raw reports remain under
ignored local `build/` artifacts, not in the public repository.

This adds no evidence about public DNS, external IPv6/UDP/STUN/TURN, another
host, or independent egress/packet observations. Overall network privacy gate
remains **OPEN** and those checks remain **NOT RUN**; no anonymity claim follows.

### Exact public 0.8.27-preview WSL WebRTC route repeat — 15 October 2026

The repeat-verified public 0.8.27-preview ZIP (SHA-256
`daa9da39bb19428e2989439b6200fbf4d9ee0a5d999f834880e2bbb800ba2eb0`) was
tested by `wsl_stun_route_audit.py`; bundled Chromium `chrome.exe` SHA-256 was
`7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`. Ubuntu
WSL ran a private, token-gated UDP counter. Direct positive control: 5 STUN
Binding requests received / 5 NetLog sends. HTTP proxy: 0 received / 0 NetLog
UDP sends. SOCKS5 proxy: 0 received / 0 NetLog UDP sends; the local SOCKS5
fixture observed one synthetic route-control request and four test-page
requests. Both proxy gates **PASS**.

This is a same-machine cross-namespace repeat, not an independent egress
observer. The local raw report contains a private WSL address and remains
outside GitHub. Public DNS, IPv6, TURN, another host/network, external proxy
egress and anonymity remain **NOT RUN**; P2 remains **OPEN**. See the
[release-specific evidence](RELEASE_PUBLICATION_0.8.27-preview.md) and
[network protocol](NETWORK_PRIVACY_2026-10.md).
