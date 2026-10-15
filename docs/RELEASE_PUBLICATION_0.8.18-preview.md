# NeAntik Win 0.8.18-preview — publication evidence

Verified on 2026-10-15. The browser source commit, downloaded binary, Site source
commit, and production deployment are separate artifacts and are recorded
independently below.

## GitHub release and portable ZIP

- Public prerelease: [v0.8.18-preview](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.18-preview).
- Browser source commit: `85580d07b28cd8d795576481b3119f04dd1ba6dd`.
- Portable ZIP: 262,377,848 bytes; SHA-256
  `62c73096470c62a9bfacefbfee30753e99def38bdc22aba1c90e222bd22af095`.
- Packaged EXE SHA-256:
  `fb7eef35dd4cadd3f7b6f8ff92bcc30c612c3006f4ce0d71198bf57b7f7fc10b`.
- Chromium: `155.0.8059.79`, source commit
  `a49e2e3d4addfd84e765b52afe230bedb81096db`; Windows build-compat patch SHA-256
  `2992c690bd16fd3f7196a52b018cdc0a2556f4148959fb7f3b7072803fe81a3d`.
- Manifest explicitly has `fingerprint_modification: false` and no privacy
  patch. This is a portable profile manager using stock Chromium, not a promise
  of anonymity or fingerprint spoofing.
- The public ZIP was downloaded again to an isolated QA folder. Local and public
  copies matched at 262,377,848 bytes and the SHA-256 above; the archive verifier
  passed for 1,066 files and found no user `Data/` directory.

## Tests on the exact 0.8.18 source / packaged artifact

- `python -m unittest discover -q`: **PASS**, 264 tests, 3 skipped.
- `python nevision_win.py --self-test`: **PASS**.
- `tools/gui_regression.py`: **PASS**, 18 cases.
- `tools/test-release-tools.ps1`: **PASS**, 58 cases.
- `tools/check-public-repo.ps1`: **PASS**, 211 files.
- Actual Windows-junction launch regression for a profile root:
  **PASS**, rejected before browser process/profile mutation.
- Exact extracted portable EXE `--self-test`: **PASS**, exit code 0; no `Data/`
  was created. Packaged launcher integration: **PASS**, 2 cases.
- After publication, `tools/fingerprint_surface_audit.py` on the extracted
  public ZIP's exact Chromium binary (SHA-256
  `7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`):
  **PASS**, 170 consistency checks, two disposable profiles, two launches per
  profile, loopback-only observers; all 8 attempted external requests were
  blocked. The private device-traits report stays outside Git at
  `C:\N155\audit-0.8.18-preview-20261015.json`.
- `tools/upgrade_rollback_integration.py` on the exact public 0.8.17 and 0.8.18
  ZIPs (both SHA-256 values verified against GitHub): **PASS** for a synthetic
  same-Windows-account storage/profile/proxy/DPAPI seed → 0.8.18 upgrade →
  0.8.17 rollback. The old snapshot remained unchanged and the candidate copy
  changed as expected. Private report:
  `C:\N155\upgrade-rollback-0.8.17-to-0.8.18-20261015.json`.
- `tools/upgrade_browser_session_integration.py` on the same exact public ZIP
  pair: **PASS**. Old Chromium wrote a synthetic loopback-origin cookie and
  localStorage value; 0.8.18 read both from the same profile. The old Data
  snapshot remained unchanged; 14 external proxy attempts were rejected.
  The harness now checks the portable root, `Data`, `Profiles`, and profile root
  for Windows reparse points before each Chromium process creation; its local
  controls exercised actual junctions at all three data-path levels (5/5 local
  harness tests and the product launch-junction regression passed).
- `tools/concurrent_profile_integration.py` on the exact public 0.8.18 ZIP:
  **PASS**, 17/17 checks for two simultaneous synthetic profiles via the
  application launcher. Cookie, localStorage, IndexedDB and Cache Storage
  values remained isolated; each service worker registered; profile locks
  coexisted and were released; operations on a busy profile were rejected.
  Private report:
  `C:\N155\concurrent-profile-0.8.18-preview-20261015.json`.
- `tools/proxy_loss_recovery_gate.py` on the exact public 0.8.18 Chromium
  (`chrome.exe` SHA-256 above): **PASS**, 10/10 loopback-only assertions. With
  the proxy stopped, the target got no request; after recovery, the same live
  Chromium process sent exactly two probes through the synthetic proxy. NetLog
  saw only `127.0.0.1` TCP and zero UDP sends. Local harness and actual junction
  launch controls passed (3/3 and product launch-junction regression). Harness
  source commit: `15c5039166f84cc4f4b170b6f5ce3cc70a855d0f`. Private report:
  `C:\N155\proxy-loss-0.8.18-preview-20261015-committed-harness.json`.
- `tools/https_proxy_integration.py` on the exact public 0.8.18 Chromium:
  **PASS**, 10 local IPv4/IPv6 HTTPS proxy/TLS cases, 75 assertions. Working
  CONNECT routes reached the synthetic target; untrusted certificates and
  unavailable endpoints failed closed. The 407 case followed a positive direct
  control and reached the target zero times, with no alternate proxy. Harness
  commit `95cdef0bb90b64ddb298ee29d2b3af74847ce407`, SHA-256
  `2955d5519f91248832fc9f71adfafd36a82967e4ab90e113a73985932ecd2a62`.
  Private report:
  `C:\N155\https-proxy-0.8.18-preview-20261015-committed-harness.json`.
- Post-release source-harness check `tools/proxy_integration.py` on the same
  exact public Chromium: **PASS**, 72/72 assertions over 19 disposable-profile
  launches. Direct positive controls; HTTP/SOCKS5 success against synthetic
  IPv4/IPv6 loopback targets through IPv4/IPv6 proxy endpoints; and unavailable
  endpoint cases with zero target requests. Actual Windows profile-junction
  regression passed immediately before the run, and the harness invokes the
  product profile-path isolation check immediately before each Popen. Harness
  commit `9d16e8a2ad0b963969d48d2d08c5c9342d1573dd`, SHA-256
  `9af53f5f0c84c74d690486a241cd0b5bcc411d6ab270d6da7d810e74200fc5b6`;
  product source SHA-256 `3c7ef3590cae465549241040393f6db99a5840b9f021de40c3f596e487168168`.
  Private report: `C:\N155\proxy-integration-0.8.18-preview-20261015.json`.
  These are loopback source-harness results, not packaged GUI/authentication or
  external DNS/IPv6/UDP/TURN evidence.
- `tools/download_integration.py` on the exact public 0.8.18 Chromium:
  **PASS**, 3/3 synthetic 4,880-byte downloads. Files stayed in separate A/B
  managed folders; profile A retained its prior file and accepted another after
  moving the entire disposable portable root. The harness uses the production
  profile reparse/path check before each Popen and a byte-identical sandbox-ACL
  prepared engine copy. Junction regression passed immediately before the run.
  Harness commit `7fb6240baa736e71821d9317d729cb08f170f67e`, SHA-256
  `7038d05d7b88a2a6555aa968d7fd8f713136a7b020f4c16e28585f3f567f981e`; exact
  source engine SHA-256 `7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`.
  Private report: `C:\N155\download-integration-final-diagnostic-0.8.18-preview-20261015.json`.
  Source harness only; it is not packaged GUI or cross-machine/cross-account proof.
- `tools/wsl_stun_route_audit.py` + `tools/webrtc_udp_integration.py` on the
  exact public 0.8.18 Chromium: **PASS**, three same-machine Windows↔Ubuntu WSL
  network-namespace cases. Direct positive control sent 5 STUN Binding requests
  and 5 UDP datagrams. HTTP and SOCKS5 proxy cases each produced 0 receiver STUN
  requests, 0 receiver UDP datagrams and 0 NetLog UDP sends; SOCKS5 route
  controls confirmed one synthetic route-control and four proxied page
  requests. Both proxy-policy evaluators passed. Harness profiles use
  `Data/Profiles` and the product path isolation check before each Popen.
  Harness source commit `9b406be691f2ed3bc34528e70a601594855e483c`; source
  Chromium SHA-256 `7db4c6d779289100e04458d74863c6edd86c141a59c7c1c36e696567aba41baa`.
  Private report: `C:\N155\wsl-stun-0.8.18-preview-20261015.json`.
  Same-host namespace control only; external egress, DNS, public IPv6, TURN,
  proxy authentication and GUI are not covered.

Not rerun on this exact archive: proxy-auth success and broader browser/network
integration suites. Migration coverage is same-account, synthetic and limited
to one cookie/localStorage origin; it is not an interactive update or a check
of another Windows account or machine.
Manual visible GUI, independent external DNS/IPv6/UDP/STUN/TURN observers and
fingerprint-spoofing checks are **NOT RUN** (fingerprint spoofing is
intentionally absent). Loopback blocking does not prove external-route privacy.
These limitations must not be represented as release PASS.

## Production Site

- Existing public Site: [nevision-win.mail782861.chatgpt.site](https://nevision-win.mail782861.chatgpt.site/).
- Site source commit: `77ddb4c405d8aa571ee98527b6027c32711db5e3` (separate from
  the browser binary commit above).
- Published Site version: `52`; deployment completed successfully on
  2026-10-15.
- The local Site deployment archive from that commit was 16,171,152 bytes,
  SHA-256 `85e070ab27e4643cb097234b76cac3b01bf7cba8459ba3a9c903dcd5cd17dbfb`.
  Sites stored the build artifact as 17,807,360 bytes with content hash
  `sha256:a21e3e9d21080457593d749cebf2fb193ddfa5f7e913ca248a5fd42946d8f736`.
- Live `/`, `/release.json`, `/CHANGELOG.md`: **PASS**, HTTP 200. `release.json`
  reports version `0.8.18-preview`, browser source commit and ZIP size/SHA above;
  changelog contains the release entry with zero Unicode replacement characters.

## Change in this release

Profile identifiers are now validated as exact lowercase UUID-hex IDs before
constructing a `Profiles/<id>` path, preventing malformed stored identifiers
from traversing outside the profile directory during backup/delete operations.
Regression tests cover corrupt IDs and the real Windows junction launch boundary.
