# NeAntik Win 0.8.12-preview — publication record

Published 2026-10-14 as an unsigned portable Windows prerelease. Source and
binary tag `v0.8.12-preview`: `e6020f6b5988cbfc62deb87670535d12fea1af70`.
The bundled Chromium V5 core is byte-identical to 0.8.11-preview. This release
adds a settings-only profile template and profile-dialog wheel scrolling, not
new fingerprint or network protections.

- [GitHub Release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.12-preview)
  is a separate prerelease with ZIP, SHA-256 sidecar and manifest. No previous
  release was overwritten. Source [Windows CI](https://github.com/AffPapa/NeAntik-Win/actions/runs/38451634829): **PASS** for exact commit.
- [Public portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.12-preview/NeAntikWin-portable-v0.8.12-preview.zip):
  262,395,433 bytes; SHA-256
  `053c66852bdac7cbaed1edede83f53940fe66746813d598a9db99113b3732dbd`.
  Repeat-downloaded ZIP and checksum sidecar matched the candidate. Archive
  verifier: **PASS**, 1,066 files. Packaged `NeAntikWin.exe` SHA-256:
  `cc67968958e665a88d5eb3eae17d14d6748b8f80c89c48db6e1991092bc4ae27`;
  bundled `chrome.exe` SHA-256:
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
- [Public Site](https://nevision-win.mail782861.chatgpt.site/) version 45 was
  deployed from Site source commit `ef360dde05ea4cce96628562ca4575b3d7cfb6b0`.
  Live `/` and `/CHANGELOG.md` returned HTTP 200; `/release.json` reported
  0.8.12, the same ZIP size and SHA-256. Cyrillic in changelog decoded without
  replacement characters. Local Site typecheck and build passed. The Sites
  archive helper again failed on Windows path translation **after source push**;
  the platform built the pushed source remotely.

Exact source commit checks: 83 `test_nevision_win.py` tests run (1 skip),
26 profile-identity/privacy tests (2 skips), 64 integration tests,
18 GUI regression tests, source self-test, 55 release-tool checks and
public-repository guard: **PASS**. The extracted candidate EXE and the
repeat-downloaded public EXE each passed `--self-test`. Packaged launcher:
2/2, Chromium storage isolation: 21/21 over seven visits, local proxy routes:
72/72 over 19 launches. Synthetic same-Windows-account 0.8.11→0.8.12 storage
upgrade/rollback and one-origin cookie/localStorage migration: **PASS**; old
snapshot preserved. The first raw-engine storage attempt lacked disposable
AppContainer read/execute ACL and stopped before assertions; after granting it
to the test `Engine/Chromium` directory only, the bounded test passed. This was
a test-setup failure, not a product FAIL.

The exact candidate GUI opened and displayed the new File-menu action and
New Profile form. Automated typing into its name field produced no visible
text, so manual create/export/import through this UI tool is **INCONCLUSIVE**,
not PASS or a proven product defect. Source-level round-trip tests used two
synthetic portable roots and confirmed fresh profile ID/seed, empty browser
Data, no notes/proxy/cookies and rejection of malformed/oversized/duplicate-
field templates without partial profiles. A physical second-PC transfer is
**NOT RUN**.

**NOT RUN:** Windows 10/ARM64, another Windows account/PC, public-network
DNS/IPv6/TURN capture, real-site compatibility, population-level linkability
or a full anonymity assessment. Chromium-saved passwords, cookies and sessions
may not transfer to another PC/account. Proxy-vault passwords are not in the
settings template or full backup. The JSON settings template and backup ZIPs
are unencrypted; user-entered name/group/tags can contain personal data.
