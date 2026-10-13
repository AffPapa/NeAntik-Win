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
- Packaged GUI smoke on a fresh extraction at `C:\NeAntikBuild\qa-gui-086-candidate3-20261013`: a synthetic profile was created and appeared in the list, its Launch action started `Engine/Chromium/chrome.exe` from that same extraction (verified by the exact process path and window handle), the manager returned to Ready after the browser closed, and the profile remained listed after closing and reopening the manager. The tested EXE SHA-256 is `7866bcb02e2c4de83931774427e8f33b844ed378224ed4f5bc9462e032d05645`. This is a narrow GUI create/launch/persistence PASS, not a full UI, browser content or update gate.
- V4 Canvas saved-profile/two-site/three-session gate: 12/12 cases.
- V4 context gate: main document, same-site and third-party iframe, dedicated/shared/service workers; aggregate checks pass.
- Storage isolation and backup/restore loopback integration: 21 assertions.
- Synthetic same-account storage update/rollback from a freshly downloaded public 0.8.5 ZIP (SHA-256 `cc5d14702aa0facffbd88839e5b45645e871f3aab962c454bccf5895ab946dc4`) to this candidate: old-source seed, candidate-source read/write of copied `Data/`, synthetic DPAPI decrypt and untouched old snapshot reopen all passed; [`upgrade_rollback_integration.py`](../tools/upgrade_rollback_integration.py). This uses each ZIP's exact embedded source commit and extracted folders, not packaged GUI interaction or real Chromium session migration.
- Synthetic browser-session migration from the same public 0.8.5 ZIP to this candidate: the old bundled Chromium saved a persistent cookie and localStorage value on one loopback origin, the candidate's bundled Chromium read both after copying `Data/`, and the old snapshot remained unchanged; [`upgrade_browser_session_integration.py`](../tools/upgrade_browser_session_integration.py). Independent rerun passed on 2026-10-13, report `C:\NeAntikBuild\qa-v0.8.6-preview-candidate-3\upgrade-browser-session-review.json`. This covers one ordinary profile on the same Windows account, not the packaged GUI update flow, password/history/extension migration, or another machine.
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

- **Resolved narrow GUI-create uncertainty:** an earlier Windows UI automation attempt could not enter text with `type_text` even though a caret was visible. A fresh extraction and a changed input method (`press_key`) entered one synthetic character; saving, bundled launch and restart persistence passed as above. This does not validate arbitrary text input, keyboard layouts or the complete create/edit workflow.
- **INCONCLUSIVE:** visual inspection of the launched Chromium window through Computer Use. The window and executable path were observed, but `get_window` rejected its returned `Chrome` owner twice, including after refreshing the window list. Do not treat this tool binding error as a browser defect or a browser-content PASS.
- **NOT RUN on this ZIP:** full keyboard/navigation, light/dark, profile editing, packaged GUI update/rollback, migration of other browser-session surfaces (including passwords/history/extensions), additional security scanners, and public downloaded-0.8.6-ZIP launch.
- **NOT RUN:** independent public DNS/IPv6/STUN/TURN egress observer, external WebSocket route, second Windows machine/GPU, WebGL/WebGPU fingerprint protection, real-site compatibility and statistical unlinkability. Local Canvas and route checks do not establish general anonymity.
- **NOT PUBLISHED:** the 0.8.6 release ZIP/checksum and site update remain gated by final release review and public-download hash verification. Candidate source and this QA record are on GitHub `main`, without a 0.8.6 release tag.

Before publication, rerun the release checklist against a final immutable ZIP, finish or explicitly scope the open GUI/security/compatibility gates, and verify the public artifact by downloading it again. Do not silently overwrite an existing versioned release.
