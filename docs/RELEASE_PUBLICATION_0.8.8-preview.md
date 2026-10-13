# NeAntik Win 0.8.8-preview — publication record

Published on 2026-10-14 as an **unsigned prerelease**, not a claim of full
anonymity or complete fingerprint protection.

- Source/binary commit and tag `v0.8.8-preview`:
  `f9e244c517781a9ffe7b0b694bd3c1172289f60d`.
- [GitHub Release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.8-preview)
  contains the portable ZIP, its SHA-256 sidecar and standalone manifest. The
  release is marked prerelease; no earlier release was overwritten.
- [Public portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.8-preview/NeAntikWin-portable-v0.8.8-preview.zip):
  262,387,518 bytes; SHA-256
  `981209e9724cc8c469180eeda1e894f262118c1e6651107dfcbfc9a1567b9fc5`.
  A second download from GitHub matched the local ZIP byte-for-byte. Archive
  verifier: PASS, 1,066 files. Extracted public `NeAntikWin.exe` SHA-256:
  `c4ae8569475095ac10ede9d17af07b2cb2317fa34b83f833395b388e2a49b434`;
  packaged `--self-test`: PASS, exit 0. Bundled `chrome.dll` SHA-256:
  `9d0943446e0cbe405f82286ce46c03ad8e928f7b8e46d3ed33082dce2f544075`.
- [Public Site](https://nevision-win.mail782861.chatgpt.site/) version 40 was
  deployed from Site source commit `a6589829c6357b8d47c4c68de2ee2c7597aa0422`.
  Live `/` and `/CHANGELOG.md` returned HTTP 200 with 0.8.8 text; changelog
  Cyrillic decoded correctly. Live `/release.json` reported the exact source
  commit, public ZIP URL, 262,387,518-byte size and matching SHA-256.

Targeted local PASS checks on Windows 11 x64: Chromium native parser 21/21,
Canvas 6/6, Canvas main/frame/worker and BrowserContext/session gate 7/7,
15 owned Chromium command lines without the session key, launcher 4/4,
packaged browser/proxy/cookie/WebSocket integration, and synthetic same-account
0.8.7 → 0.8.8 data/session upgrade with old snapshot retained. The separate
proxy-loss/recovery 10/10 gate used the unchanged **0.8.7** browser core, not
the 0.8.8 GUI. The 0.8.8 GUI opened and rendered on this host.

**INCONCLUSIVE:** manual GUI profile creation: the automation tool did not
enter text, so neither PASS nor product FAIL can be inferred. **NOT RUN:**
external DNS/IPv6/TURN observation, independent proxy-egress capture, second
machine, Windows 10/ARM64 and full fingerprint protection. No assertion of
complete anonymity is made. Before upgrading, keep a private copy of the old
portable folder with `Data/`; never open a profile upgraded by the new browser
in an older Chromium build. Backup ZIP files are not encrypted.
