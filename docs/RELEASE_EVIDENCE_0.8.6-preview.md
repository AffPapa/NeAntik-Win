# 0.8.6-preview — local candidate evidence (2026-10-13)

This is an internal release-gate record, **not** a published-release claim.
Public download and site still serve 0.8.5-preview until independently verified.

## Exact candidate

- Source commit: `c0ef941fabbf2e24ce24d0ef9ac51456900f71e6`.
- Portable ZIP: `C:\NeAntikBuild\releases-v0.8.6-preview-candidate-3\NeAntikWin-portable-v0.8.6-preview.zip`.
- ZIP SHA-256: `bab9097883830edda661d64ee4d8a18f07bec57415f5c611173b960aabb138a9`.
- Extracted `chrome.dll` SHA-256: `6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413`.
- V4b patch SHA-256: `bba02390999c33bcf6097625c03093022ed534c316184462cc8468efbc79b708`.
- Tested on Windows 11 x64 build 26200; no other Windows release or GPU is covered.

## PASS on the exact unpacked candidate

- ZIP verifier: 1066 allowed files, manifest/version/hash consistency; no `Data/` in ZIP.
- Packaged EXE self-test: exit 0. Fresh GUI starts and creates local `Data/` in the extracted folder.
- V4 Canvas saved-profile/two-site/three-session gate: 12/12 cases.
- V4 context gate: main document, same-site and third-party iframe, dedicated/shared/service workers; aggregate checks pass.
- Storage isolation and backup/restore loopback integration: 21 assertions.
- Synthetic same-account storage update/rollback from a freshly downloaded public 0.8.5 ZIP (SHA-256 `cc5d14702aa0facffbd88839e5b45645e871f3aab962c454bccf5895ab946dc4`) to this candidate: old-source seed, candidate-source read/write of copied `Data/`, synthetic DPAPI decrypt and untouched old snapshot reopen all passed; [`upgrade_rollback_integration.py`](../tools/upgrade_rollback_integration.py). This uses each ZIP's exact embedded source commit and extracted folders, not packaged GUI interaction or real Chromium session migration.
- Loopback HTTP/SOCKS5/no-DIRECT proxy integration: 37 assertions.
- Local HTTPS-proxy TLS/CONNECT route: 5/5 scenarios on the exact extracted core (direct controls, working HTTPS proxy, untrusted proxy certificate, unavailable proxy); [`https_proxy_integration.py`](../tools/https_proxy_integration.py). Disposable certificate pinned by SPKI for positive controls, no trust-store change or global TLS bypass.
- Local WebSocket `ws`/`wss` routes: 16/16 scenarios on the exact extracted core across direct, HTTP/HTTPS/SOCKS5 proxy, unavailable-proxy and untrusted-HTTPS-proxy controls; [`websocket_route_integration.py`](../tools/websocket_route_integration.py). WSS target and HTTPS proxy use separate disposable SPKI pins, not a global TLS bypass.
- Managed per-profile downloads and portable relocation: 3 cases.
- HTTPS third-party-cookie positive/negative control: allow profile stores cookie; block profile does not.
- Packaged launcher integration, including first-run AppContainer ACL and opt-in V4 core: 4 cases.
- WSL STUN receiver in a separate local network namespace: direct positive control received, proxy case passed; 2 cases. This is not an external DNS/IPv6/TURN gate.
- One consented external HTTPS origin (`/api/headers` on the project site): direct positive control, rejecting HTTP/SOCKS5 proxies with no rendered endpoint, and working allowlisted HTTP CONNECT all passed. The local proxy fixture and Chromium NetLog showed no UDP sends in those cases. This is one-host, one-origin route evidence, not independent DNS/IPv6/UDP packet observation.
- Exact extracted core against stock Chromium from the same upstream commit: 9/9 baseline-comparison checks passed in ordinary mode, including measured HTTP/Client Hints and graphics/audio surfaces. This says nothing about unmeasured fingerprint entropy or opt-in real-site compatibility.
- Fresh-profile permission defaults: geolocation, notifications, camera and microphone denied; Preferences survived Chromium startup. Separate HTTPS cookie controls above test network behavior.
- Blank/new-tab startup: the new-tab document was blank and its preference persisted. The NetLog still recorded 4 HTTP requests and 24 UDP sends for direct blank startup; with the tested rejecting local HTTP proxy it recorded 4 HTTP requests, loopback-only TCP and zero UDP sends. A blank tab is not a no-telemetry or leak-free guarantee.
- Windows Defender custom scan of the exact ZIP completed with no detection associated with this candidate; signatures were last updated on 2026-10-12. This is one scanner observation, not proof that the binary is safe.

These tests use synthetic data and local endpoints. Raw device observations and any private network logs are kept outside Git.
The direct cookie test initially failed before the freshly extracted engine had
AppContainer read/execute ACLs. Granting ACLs only on the disposable
`Engine/Chromium` directory and rerunning once passed both controls. The
packaged launcher independently passed its first-run ACL scenario; the raw
`chrome.exe` test bypasses that launcher.

## INCONCLUSIVE / NOT RUN

- **INCONCLUSIVE:** packaged GUI profile creation by Windows UI automation. On 2026-10-13 the exact candidate EXE (SHA-256 `7866bcb02e2c4de83931774427e8f33b844ed378224ed4f5bc9462e032d05645`) opened the main window and creation dialog; the name field visibly had a caret after a screenshot-targeted click, but `type_text` entered no characters. The tool reported focus on a generic panel and did not list the modal as a separate top-level window. One refreshed, changed-target attempt was made, then the test stopped. Cancel and app close worked. This does not prove an application defect or a successful end-to-end workflow.
- **NOT RUN on this ZIP:** full keyboard/navigation, light/dark, profile editing and close/reopen, packaged GUI update/rollback and browser-session migration, additional security scanners, and public downloaded-0.8.6-ZIP launch.
- **NOT RUN:** independent public DNS/IPv6/STUN/TURN egress observer, external WebSocket route, second Windows machine/GPU, WebGL/WebGPU fingerprint protection, real-site compatibility and statistical unlinkability. Local Canvas and route checks do not establish general anonymity.
- **NOT PUBLISHED:** the 0.8.6 release ZIP/checksum and site update remain gated by final release review and public-download hash verification. Candidate source and this QA record are on GitHub `main`, without a 0.8.6 release tag.

Before publication, rerun the release checklist against a final immutable ZIP, finish or explicitly scope the open GUI/security/compatibility gates, and verify the public artifact by downloading it again. Do not silently overwrite an existing versioned release.
