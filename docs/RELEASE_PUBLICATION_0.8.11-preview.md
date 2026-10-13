# NeAntik Win 0.8.11-preview — publication record

Published on 2026-10-14 as an unsigned portable Windows prerelease. The
bundled Chromium V5 engine and profile/backup formats are unchanged from
0.8.10. This release makes profile backup fail closed for file symlinks and
Windows reparse files, and repairs the V5 measurement gate for schema 3.

- Source/binary commit and GitHub tag `v0.8.11-preview`:
  `72ae1d60e30df7b951b3ba449eb06c9b299a4499`.
- [GitHub Release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.11-preview)
  is a prerelease with ZIP, SHA-256 sidecar and manifest. The previous release
  was not overwritten.
- [Public portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.11-preview/NeAntikWin-portable-v0.8.11-preview.zip):
  262,392,220 bytes; SHA-256
  `97343ef069797b833138ae6ae1c754c3d830d2f340b632f42c26c0f7d368be7c`.
  The repeat-downloaded public ZIP matched the local candidate. Archive
  verifier: **PASS**, 1,066 files. Independent provenance audit matched all
  17 recorded source files and found no loose user Data paths in the package.
  Packaged `NeAntikWin.exe` SHA-256:
  `e56e0e182dac0478168e068bb1246042fdd0f683df2f7fce88c94d13346097bf`;
  bundled `chrome.exe` SHA-256:
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
- [Public Site](https://nevision-win.mail782861.chatgpt.site/) version 43
  deployed from Site source commit
  `789abb763710b3a4eca35bbe23efb2f884f0f089`. Live `/`, `/CHANGELOG.md`
  and `/release.json` returned HTTP 200. The changelog decoded as UTF-8
  without replacement characters. The page and JSON displayed 0.8.11, and
  JSON matched the source commit, ZIP size and SHA-256. Local Site typecheck
  and build passed. The Sites archive helper failed on Windows path
  translation after pushing source; the platform remotely built that commit.

Source tests at the exact binary commit: 249 run (3 skipped); specialized
integration suite 56 passed, GUI regression 17 passed, source self-test and
55 release-tool checks passed. [GitHub CI](https://github.com/AffPapa/NeAntik-Win/actions/runs/38448039331):
**PASS**. The exact candidate passed packaged self-test, launcher 4/4,
browser storage isolation 21/21 across seven visits, local proxy routes
64/64 across 17 Chromium launches, and a two-site third-party cookie test.
Synthetic same-Windows-account 0.8.10→0.8.11 storage upgrade/rollback and
one-origin cookie/localStorage migration: **PASS**, old snapshot preserved.
The unchanged engine passed the repaired V5 cross-surface gate 16/16 on the
previous exact packaged core with the same chrome.exe SHA-256.

The exact candidate EXE opened in an isolated portable copy and showed its
0.8.11 main screen and New Profile dialog, then closed. Automated text input
did not appear in that field after one retry; manual creation via this UI
tool is **INCONCLUSIVE**, not a product FAIL or PASS. The first raw-engine
browser integration attempt lacked the disposable Chromium sandbox ACL and
failed as a setup error; after granting read/execute access only to that
test Engine directory, the 21 assertions passed. No user Data was tested.

**NOT RUN:** Windows 10/ARM64, another Windows account/PC, public-network
DNS/IPv6/TURN capture, real-site compatibility, population-level linkability
or a full anonymity assessment. Chromium-saved passwords, cookies and
sessions may not transfer to another PC/account; proxy-vault passwords are
not included in backup. Backup ZIPs are unencrypted. Keep a private copy of
the old portable folder and `Data/` before upgrading.
