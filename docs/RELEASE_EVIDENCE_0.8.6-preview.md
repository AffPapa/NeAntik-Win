# 0.8.6-preview — local candidate evidence (2026-10-13)

This is an internal release-gate record, **not** a published-release claim.
Public download and site still serve 0.8.5-preview until independently verified.

## Exact candidate

- Source commit: `7f153af342ffd1e5dc879b43ef99fe130138d00d`.
- Portable ZIP: `C:\NeAntikBuild\releases-v0.8.6-preview-candidate-2\NeAntikWin-portable-v0.8.6-preview.zip`.
- ZIP SHA-256: `0af2680b9789113d6ca9e66001a569ac7d02ad8ce3e0f8316f17e95ed0cf73ce`.
- Extracted `chrome.dll` SHA-256: `6762cf6ead3b829b481fde9540069cc709c9de3a211c738856190850a6928413`.
- V4b patch SHA-256: `bba02390999c33bcf6097625c03093022ed534c316184462cc8468efbc79b708`.
- Tested on Windows 11 x64 build 26200; no other Windows release or GPU is covered.

## PASS on the exact unpacked candidate

- ZIP verifier: 1066 allowed files, manifest/version/hash consistency; no `Data/` in ZIP.
- Packaged EXE self-test: exit 0. Fresh GUI starts and creates local `Data/` in the extracted folder.
- V4 Canvas saved-profile/two-site/three-session gate: 12/12 cases.
- V4 context gate: main document, same-site and third-party iframe, dedicated/shared/service workers; aggregate checks pass.
- Storage isolation and backup/restore loopback integration: 21 assertions.
- Loopback HTTP/SOCKS5/no-DIRECT proxy integration: 37 assertions.
- Managed per-profile downloads and portable relocation: 3 cases.
- HTTPS third-party-cookie positive/negative control: allow profile stores cookie; block profile does not.
- Packaged launcher integration, including first-run AppContainer ACL and opt-in V4 core: 4 cases.

These tests use synthetic data and local endpoints. Raw device observations and any private network logs are kept outside Git.

## INCONCLUSIVE / NOT RUN

- **INCONCLUSIVE:** manual profile creation by Windows UI automation. The creation dialog displayed correctly, but its text field did not accept the automation tool's input after one refreshed retry. This is not evidence of an application defect or a successful end-to-end GUI workflow.
- **NOT RUN on this ZIP:** full keyboard/navigation, light/dark, profile editing and close/reopen, update/rollback, Windows security scan, and public downloaded-ZIP launch.
- **NOT RUN:** independent public DNS/IPv6/STUN/TURN egress observer, second Windows machine/GPU, WebGL/WebGPU fingerprint protection, real-site compatibility and statistical unlinkability. Local Canvas checks do not establish general anonymity.
- **NOT PUBLISHED:** GitHub source commits, release ZIP/checksum and site 0.8.6 update remain gated by final release review and public-download hash verification.

Before publication, rerun the release checklist against a final immutable ZIP, finish or explicitly scope the open GUI/security/compatibility gates, and verify the public artifact by downloading it again. Do not silently overwrite an existing versioned release.
