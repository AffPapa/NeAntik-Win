# NeAntik Win 0.8.14-preview — publication record

Published 2026-10-14 as an unsigned portable Windows prerelease. Source and
binary tag `v0.8.14-preview` points to
`9e9d5872bbe04dd657ceffcded1c70b8f3a681cf`. The bundled Chromium V5
core is byte-identical to 0.8.13-preview. This release fixes a confirmed
duplicate export notification and adds a bounded WebGL1/2 parity gate; it
does not establish anonymity or independent external routing.

- [GitHub Release](https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.14-preview)
  is a new prerelease with ZIP, SHA-256 sidecar and manifest; older assets
  were not overwritten. [Windows CI](https://github.com/AffPapa/NeAntik-Win/actions/runs/38455937502)
  **PASS** on the exact binary source commit.
- [Portable ZIP](https://github.com/AffPapa/NeAntik-Win/releases/download/v0.8.14-preview/NeAntikWin-portable-v0.8.14-preview.zip):
  262,397,107 bytes; SHA-256
  `44fef435ec5a46fa52d8441ac7e6d951e0577f611a16a21628a4a33ddcf61284`.
  Public ZIP and sidecar were downloaded again and matched the candidate;
  archive verifier **PASS**, 1,066 files. Public extracted `NeAntikWin.exe`
  SHA-256 `35aac2e793b36cb92f95cff968b630f16d8f391990573ce1837421395c47b6f7`;
  bundled `chrome.exe` SHA-256
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
- [Public Site](https://nevision-win.mail782861.chatgpt.site/) version 47 was
  deployed from Site source commit `f1f3524ccb2a8d1c1281cc3afbe9ffda9a6ed0b2`.
  Live `/`, `/CHANGELOG.md` and `/release.json` returned HTTP 200; the JSON
  reported the same ZIP size/SHA and binary source commit. Cyrillic changelog
  text decoded correctly. Local Site typecheck/build passed. The Windows
  archive helper failed on path translation after source push, so Sites built
  the pushed source remotely.

At binary source commit: 257 discovered unit tests (3 skips), 66 integration
tests, 7 WebGL verdict tests, 18 GUI regression tests, source self-test,
55 release-tool checks and public-repository guard: **PASS**. Candidate and
redownloaded public EXE `--self-test`: **PASS**. Five disposable packaged
manager starts: **PASS**. Exact packaged core passed **16/16** bounded
WebGL1/2 stock-vs-ordinary-vs-opt-in checks across six loopback launches on
one Windows 11 host/GPU. No Chromium rebuild was performed because the core
bytes are unchanged.

Manual disposable-GUI evidence: the exact public 0.8.13 EXE reproduced two
sequential info dialogs when exporting with no selected profile (**FAIL**).
In the exact 0.8.14 candidate EXE, the same empty-profile Settings action
showed exactly one info dialog and returned to Settings after OK (**PASS**).
The 0.8.13 public EXE also passed a separate Settings export/import test:
synthetic JSON was created, imported into a second empty profile and did not
alter the original. No real user `Data/` was read or changed.

**INCONCLUSIVE:** a headless CDP attempt to test HTTPS-proxy credentials did
not receive the authentication event; no experimental code was retained and
it does not prove a browser defect. **NOT RUN:** correct/wrong proxy-password
entry in the native Chromium GUI, external DNS/IPv6/UDP/TURN observer,
Windows 10/ARM64, another consumer PC/account, population-level fingerprint
linkability or broad real-site compatibility. The full backup ZIP and
settings-only JSON remain unencrypted, and browser-saved sessions may not
transfer to another Windows account or PC.

Post-publication, the **same public ZIP** passed a separate, manually dispatched
[Windows Server 2022 hosted-runner gate](https://github.com/AffPapa/NeAntik-Win/actions/runs/38458812853)
using QA harness commit `e228e1280113e0968fc39a2334d32705e900bf4e`.
The runner downloaded the immutable GitHub asset, matched ZIP SHA-256
`44fef435ec5a46fa52d8441ac7e6d951e0577f611a16a21628a4a33ddcf61284`,
verified archive/provenance, ran the packaged EXE self-test, and passed 21
synthetic loopback storage assertions across seven visits with the bundled
Chromium. This adds a fresh hosted Windows VM check; it does **not** replace
Windows 10/11 consumer-PC, cross-account, GUI, or external-network testing.
