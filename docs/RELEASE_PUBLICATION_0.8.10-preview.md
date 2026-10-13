# NeAntik Win 0.8.10-preview — publication record

Published on 2026-10-14 as an unsigned portable Windows prerelease. The
bundled Chromium V5 engine and profile/backup formats are unchanged from
0.8.9. The manager now states cross-PC credential/session limitations in
Settings and the quick guide, and confirms them before backup restoration.

- Source/binary commit and GitHub tag `v0.8.10-preview`:
  `92a2d6fc93b7c4fbe1bcc89a3e9adc1509bc7738`.
- [GitHub Release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.10-preview)
  is a prerelease with a ZIP, SHA-256 sidecar and manifest. The previous
  release was not overwritten.
- [Public portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.10-preview/NeAntikWin-portable-v0.8.10-preview.zip):
  262,391,807 bytes; SHA-256
  `b3ae8a7972565589319dd4ca0b2c92580656b880ad83de0ca024276b47adf05d`.
  The repeat-downloaded public ZIP matched the local candidate. Archive
  verifier: **PASS**, 1,066 files and no user Data paths. Packaged
  `NeAntikWin.exe` SHA-256:
  `9a90b5f1e250b0b024fc406f11f17e6788f83412f28bbe07ca41d0ac3e604a87`;
  bundled `chrome.exe` SHA-256:
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
- [Public Site](https://nevision-win.mail782861.chatgpt.site/) version 42
  deployed from Site source commit
  `7b19a5744ef57130ad4442eb5eda2534a00e2068`. Live `/`,
  `/CHANGELOG.md` and `/release.json` returned HTTP 200; the changelog
  decoded correctly as UTF-8. The page and JSON displayed 0.8.10, the
  verified source commit, 262,391,807-byte ZIP and SHA-256. Local Site
  typecheck/build passed. The Sites archive helper failed on Windows path
  translation, so the platform remotely built the pushed source commit.

Source tests at the exact binary commit: 244 run (3 skipped), specialized
integration tests 51 passed, two-manager harness tests 3 passed, GUI
regression 17 passed, source self-test and 55 release-tool checks passed.
[GitHub CI](https://github.com/AffPapa/NeAntik-Win/actions/runs/38444869655):
**PASS**. Candidate packaged launcher: 4/4; loopback direct/HTTP/SOCKS5
including IPv6 proxy endpoints: 64/64 assertions over 17 Chromium launches.
Synthetic same-Windows-account 0.8.9→0.8.10 storage upgrade/rollback and
one-origin cookie/localStorage session migration: **PASS**, old snapshot
preserved. The unchanged engine also passed the earlier concurrent-profile,
seasonal-timezone and proxy-route gates; those engine-only checks do not
replace manager or external-network tests.

The exact candidate EXE opened in an isolated portable copy, showed the
0.8.10 window and visible cross-PC warning in Settings, then closed. This
is a GUI smoke check, not exhaustive manual interaction. **NOT RUN:** a
second Windows account/PC, Windows 10/ARM64, external DNS/IPv6/TURN capture,
real-site compatibility, population-level linkability or a full anonymity
assessment. Chromium-saved passwords, cookies and sessions may not transfer
to another PC/account; proxy-vault passwords are not included in backup.
Backup ZIPs are unencrypted. Keep private copies of the old portable folder
and `Data/` before upgrading.
