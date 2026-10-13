# NeAntik Win 0.8.13-preview — publication record

Published 2026-10-14 as an unsigned portable Windows prerelease. Source and
binary tag `v0.8.13-preview` points to
`4543ce34b92a6428f3540ed511b888ca64c19b12`. The bundled Chromium V5
core is byte-identical to 0.8.12-preview. This release clarifies transfer
choices in Settings and adds bounded local proxy/Canvas test gates; it does
not establish external-route privacy or anonymity.

- [GitHub Release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.13-preview)
  is a new prerelease with ZIP, SHA-256 sidecar and manifest. Previous assets
  were not overwritten. [Windows CI](https://github.com/AffPapa/NeAntik-Win/actions/runs/38453869676)
  **PASS** on the exact binary source commit.
- [Portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.13-preview/NeAntikWin-portable-v0.8.13-preview.zip):
  262,396,330 bytes; SHA-256
  `41cb553778d476e2dc175c9b57bd24d0b316af99d46e614e6043ad6eb05fac62`.
  The public ZIP and sidecar were downloaded again and matched the candidate.
  Archive verifier **PASS**, 1,066 files. Public extracted `NeAntikWin.exe`
  SHA-256 `c0347336de628264ed60bf0d9e5c78989496f4c1f9f89888651ab5ee63d6334d`;
  bundled `chrome.exe` SHA-256
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
- [Public Site](https://nevision-win.mail782861.chatgpt.site/) version 46 was
  deployed from Site source commit `d4e3ce330c9d9b3609e1b8ca9c9166907b08d206`.
  Live `/`, `/CHANGELOG.md` and `/release.json` returned HTTP 200. The live
  JSON reported 0.8.13, exact ZIP size/SHA and binary source commit; Cyrillic
  changelog text decoded correctly. Local Site typecheck/build passed. Its
  archive helper failed on Windows path translation after source push, so
  Sites built the pushed source remotely.

Source at commit: 257 discovered unit tests (3 skips), 66 integration tests,
8 Canvas verdict tests, 18 GUI regression tests, source self-test, 55 release
tool checks and public-repository guard: **PASS**. Candidate and redownloaded
public EXE `--self-test`: **PASS**. Five disposable packaged manager starts:
**PASS**. Exact packaged core: local HTTPS-proxy fixture **PASS 10/10** cases,
including 407 with a directly reachable control target and zero target hits
under the refusing proxy; Canvas stock/ordinary/opt-in compatibility and
bounded timing **PASS 33/33** checks on one Windows 11 host. Synthetic
same-account 0.8.12→0.8.13 storage upgrade and rollback: **PASS**, old
snapshot preserved.

**NOT RUN:** manual click-through of the new Settings transfer buttons in the
packaged EXE, real proxy credentials/prompt, external DNS/IPv6/UDP/TURN
observation, another PC/account, Windows 10/ARM64, broad real-site Canvas
compatibility or population-level anonymity measurement. The source GUI
regression exercised the new buttons; it is not a packaged manual GUI pass.
Settings-only JSON and full backup ZIPs remain unencrypted and can contain
user-entered personal data. Chromium-saved passwords/cookies/sessions may not
transfer to another Windows account or PC.
