# NeAntik Win 0.8.9-preview — publication record

Published on 2026-10-14 as an unsigned Windows prerelease. This release
corrects user-facing descriptions of ordinary versus opt-in V5 profiles; it
does not change the bundled Chromium engine or existing profile data.

- Source/binary commit and GitHub tag `v0.8.9-preview`:
  `0627b8b4ef06533899ff3a38048d9c0bed270709`.
- [GitHub Release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.9-preview)
  is marked prerelease and contains the ZIP, SHA-256 sidecar and manifest.
  The previous release was not overwritten.
- [Public portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.9-preview/NeAntikWin-portable-v0.8.9-preview.zip):
  262,388,492 bytes; SHA-256
  `5c6f334b3c5b7633f1e00c36c6a8df02b1c8f4200adbcf704489ccc1130a853b`.
  Repeat-downloaded public ZIP matched the local candidate and sidecar.
  Archive verifier: **PASS**, 1,066 files. Extracted public `NeAntikWin.exe`
  SHA-256: `8cebff582a486485c7b7f9928e8181f9636d2787bf4126f9cb7fc5d68a1bf135`;
  packaged self-test exit **0**. Bundled Chromium `chrome.exe` SHA-256:
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`;
  `chrome.dll` SHA-256:
  `9d0943446e0cbe405f82286ce46c03ad8e928f7b8e46d3ed33082dce2f544075`.
  These engine hashes match the published 0.8.8-preview runtime.

Source tests: 242 passed (3 skipped); specialized integration tests: 35 passed;
synthetic GUI regression: 16 passed; source self-test and release-tool checks:
PASS. [GitHub CI](https://github.com/AffPapa/NeAntik-Win/actions/runs/38439873590):
PASS. Exact 0.8.9 package: launcher 4/4, storage/profile/proxy/DPAPI
0.8.8→0.8.9 upgrade/rollback and one-origin cookie/localStorage migration:
PASS with the old snapshot preserved. On unchanged public V5 Chromium, a
four-session selected cross-surface gate passed 16/16; one owned loopback-only
HTTP-proxy loss/recovery gate passed 10/10. Those engine-only gates do not
replace tests of the manager EXE or public routes.

The 0.8.9 GUI opened and showed the corrected mode text. **INCONCLUSIVE:**
manual creation of a profile through Computer Use: the input tool did not
insert synthetic text into the focused Tk field, so neither product PASS nor
product FAIL follows. **NOT RUN:** independent external DNS/IPv6/TURN or proxy
egress capture, second computer, Windows 10/ARM64, real-site compatibility,
population-level linkability and full fingerprint protection. No complete
anonymity claim is made. Backup ZIPs remain unencrypted; keep private copies
of the old portable folder and `Data/` before upgrading.
