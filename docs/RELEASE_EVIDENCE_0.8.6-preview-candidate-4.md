# 0.8.6-preview candidate-4 — local release evidence (2026-10-13)

This is evidence for one **local, unpublished** portable ZIP, not a public-download or anonymity claim. Reports contain synthetic data and stay outside Git.

## Exact artifact and host

- Clean public source commit embedded in the ZIP: `3934773840210c519817dce381d7ad8066cf3c61`.
- ZIP: `C:\NeAntikBuild\releases-v0.8.6-preview-candidate-4\NeAntikWin-portable-v0.8.6-preview.zip`; 262,382,459 bytes; SHA-256 `a370e9dfae4ccab89beb036a9a075b5372944aab19bdf151484ed4ace17da1c1`.
- Extracted EXE SHA-256: `74184dea8fad0472f95d4731ab921552d37ca0e794766871b1fce721d6144309`.
- Extracted `chrome.dll` SHA-256: `6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413` (unchanged from candidate-3).
- Windows 11 Pro x64 build 26200; no Windows 10, ARM64 or second-machine claim.
- Disposable extracted test folder: `C:\NeAntikBuild\qa-v0.8.6-preview-candidate-4\NeAntikWin-portable-v0.8.6-preview`.

## PASS on this exact ZIP or extracted payload

- Independent ZIP verifier: 1,066 allowlisted files, no `Data/`, consistent version and manifest. Packaged EXE `--self-test` exited 0.
- Packaged GUI smoke: fresh synthetic profile created, bundled `Engine/Chromium/chrome.exe` launched (exact process path and window handle observed), manager returned to Ready after browser exit, and the profile remained listed after manager close/reopen. This does not cover arbitrary text input, editing, full keyboard navigation or browser-content inspection.
- Packaged launcher integration: 4/4 cases including opt-in native mode and first-run AppContainer ACL.
- Real Chromium storage isolation and backup/restore: 21 assertions. The first raw-engine run failed before the disposable extraction's `Engine/Chromium` received the AppContainer read/execute ACL normally applied by the launcher; one rerun after granting that ACL **only to this test engine** passed. The raw-engine setup failure is not a product failure.
- HTTP/SOCKS5 proxy route integration: 37 assertions. HTTPS-proxy CONNECT/TLS: 5/5 cases. Local WS/WSS routing: 16/16 cases.
- Public 0.8.5 ZIP (SHA-256 `cc5d14702aa0facffbd88839e5b45645e871f3aab962c454bccf5895ab946dc4`) to candidate-4 synthetic same-account storage/proxy/DPAPI update and rollback passed with unchanged old snapshot. Separate bundled Chromium migration of one persistent cookie and localStorage value on one loopback origin also passed. Neither is a packaged GUI update or cross-account/cross-machine guarantee.
- V4b Canvas saved-profile/two-site/three-session gate: 12/12. Main/iframe/worker context gate passed. Stock-vs-candidate comparison from the same upstream Chromium commit passed 9/9 measured checks in ordinary mode. These do not measure population entropy, WebGL/WebGPU protection, other machines or real sites.
- Third-party-cookie HTTPS allow/block controls passed; managed downloads/portable relocation 3/3; fresh-profile sensitive permission defaults denied in the disposable browser and survived startup.
- Private WSL namespace STUN receiver: direct positive control and proxy-bound case passed (2 cases). One consented project HTTPS origin: direct, rejecting HTTP/SOCKS5 proxy and working CONNECT controls passed; the tested proxy runs showed loopback-only TCP and no UDP sends in Chromium NetLog. These are narrow local/one-origin observations, **not** independent external DNS/IPv6/UDP/TURN leakage proof.
- Blank new-tab document and preference verified. Startup NetLog still measured 4 HTTP requests and 24 UDP sends for direct blank startup; the tested rejecting loopback-proxy case measured 4 HTTP requests and zero UDP sends. Do not call startup telemetry-free.
- Microsoft Defender CLI custom scan of this exact ZIP exited 0 and reported no threats; Defender was enabled and antivirus signatures were last updated 2026-10-12 16:06:44 UTC. One scanner result is not a safety certificate.
- GitHub Windows CI for source commit `3934773840210c519817dce381d7ad8066cf3c61`: completed successfully.

## INCONCLUSIVE / NOT RUN / NOT PUBLISHED

- **INCONCLUSIVE:** previous Computer Use attempts to bind the launched Chromium window rejected its returned owner; candidate-4 browser process path and launcher status were verified, but visual browser-content inspection was not repeated without a new tool hypothesis. This is not evidence of a browser defect.
- **NOT RUN on candidate-4:** full manual keyboard/accessibility and light/dark review, profile edit and GUI backup/restore/update, migration of passwords/history/extensions, additional security scanners, and a second Windows version/machine. Prior candidate-3 results do not transfer to this ZIP.
- **NOT RUN:** independent external DNS/IPv6/STUN/TURN observer, statistical unlinkability, WebGL/WebGPU protection and real-site compatibility. No full anonymity or leak-free claim is supported.
- **NOT PUBLISHED:** GitHub Release ZIP/checksum and site still show 0.8.5-preview. Publication requires explicit release-scope review, immutable GitHub assets, repeat download/hash/launch verification, and matching site release metadata.

Before publishing, retain this exact ZIP unchanged, review the remaining risks for a clearly labeled Windows 11-only experimental preview, then verify the public asset and site separately. Do not overwrite a versioned release.
